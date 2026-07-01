# src/workers/structure_builder.py

"""
Structure Builder Worker.

Назначение:
- Считать санитизированный одноязычный макет документа из хранилища.
- Построить древовидную структуру документа (clause_tree) через StructureBuilder.
- Сохранить clause_tree в хранилище и обновить ссылку в DocumentVersion.
- Обновить статус документа: SANITIZED -> STRUCTURED.
- Запуск последующих задач пайплайна выполняется централизованным оркестратором.

Позиция в пайплайне:
- import -> convert -> build_primary_language_source -> extract -> pii -> structure -> ...

Контракт стадии:
- Основной source of truth для structure — только layout_primary_sanitized_ref.
- Fallback на layout_primary_ref допускается только через feature flag
  ALLOW_LEGACY_LAYOUT_FALLBACK=True.
- В нормальном боевом режиме fallback выключен.
- retrigger downstream допустим только после подтверждённого commit результатов structure.

Архитектурный паттерн:
- Внешняя Celery-задача синхронная (def).
- Асинхронная бизнес-логика живёт в _build_structure_async().
- Один sync -> async переход через run_async().
- Ошибки уровня контракта стадии переводятся в FAILED через отдельный UoW.

После введения document_stage_executions:
- Входной параметр stage_execution_id сообщает, какая execution-запись в БД
  соответствует текущему запуску.
- В начале успешного запуска мы помечаем execution как STARTED.
- После успешного commit отмечаем execution как SUCCEEDED.
- При PermanentError помечаем execution как FAILED с понятным error_details.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from core.config import settings
from core.constants import DocumentStatus
from core.exceptions import PermanentError, TransientError
from core.logging import get_logger
from core.pipeline_errors import (
    PipelineErrorType,
    StructureV2ErrorReason,
)
from core.stage_trace import build_stage_trace_fragment
from db.repositories import AuditRepository
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_segment_repo import DocumentSegmentRepository
from db.repositories.document_stage_execution_repo import (
    DocumentStageExecutionRepository,
)
from db.repositories.document_version_repo import DocumentVersionRepository
from db.uow import UnitOfWork, db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.run_orchestrator_trigger import retrigger_run_pipeline
from services.structure.builder import StructureBuilder
from storage.artifact_store import ArtifactPath, ArtifactStore
from workers._tenant_resolver import resolve_artifact_tenant_id
from services.structure.pipeline import build_file_structure_with_chunk_plan

logger = get_logger(__name__)


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.build_structure",
    queue="default",
)
def build_structure(
    self,
    document_version_id: str,
    stage_execution_id: str | None = None,
    orchestration_strategy: str | None = None,
    **kwargs: Any,
) -> dict:
    """
    Sync Celery entrypoint.

    Поведение:
    - выполняет только стадию structure;
    - при PermanentError переводит документ в FAILED;
    - при TransientError отдаёт управление retry-механизму;
    - при успехе будит оркестратор только после commit.

    Дополнительно:
    - если передан stage_execution_id, то воркер обновляет запись
      в document_stage_executions (STARTED/SUCCEEDED/FAILED).
    """

    run_id = kwargs.get("run_id")
    deal_id = kwargs.get("deal_id")
    tenant_id = kwargs.get("tenant_id")
    document_id = kwargs.get("document_id")

    async def _wrapper() -> dict[str, Any]:
        try:
            async with db_uow() as uow:
                resolved_tenant_id = await resolve_artifact_tenant_id(
                    session=uow.session,
                    deal_id=deal_id,
                    document_id=document_id,
                    payload_tenant_id=tenant_id,
                )
                return await _build_structure_async(
                    document_version_id=document_version_id,
                    extra_args=kwargs,
                    uow=uow,
                    stage_execution_id=stage_execution_id,
                    artifact_tenant_id=resolved_tenant_id,
                )

        except TransientError as e:
            logger.warning(
                "Transient error during structure building; task should be retried",
                document_version_id=document_version_id,
                deal_id=deal_id,
                tenant_id=tenant_id,
                run_id=run_id,
                error=str(e),
            )
            raise

        except PermanentError as e:
            reason_code = (getattr(e, "details", {}) or {}).get(
                "reason", StructureV2ErrorReason.STRUCTURE_BUILD_ERROR
            )
            logger.error(
                "Permanent error during structure building",
                document_version_id=document_version_id,
                deal_id=deal_id,
                tenant_id=tenant_id,
                run_id=run_id,
                error=str(e),
            )
            async with db_uow() as uow_status:
                failed_tenant_id = await resolve_artifact_tenant_id(
                    session=uow_status.session,
                    deal_id=deal_id,
                    document_id=document_id,
                    payload_tenant_id=tenant_id,
                )
                await _mark_failed(
                    uow=uow_status,
                    document_version_id=document_version_id,
                    tenant_id=failed_tenant_id,
                    message=str(e),
                    stage_execution_id=stage_execution_id,
                    reason_code=reason_code,
                )
            return {
                "status": DocumentStatus.FAILED.value,
                "document_version_id": document_version_id,
                "error": str(e),
                "committed": False,
            }

    result = run_async(_wrapper())

    if run_id and result.get("committed") is True:
        logger.info(
            "Structure building committed, retriggering run pipeline",
            document_version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=result.get("tenant_id", tenant_id),
            run_id=run_id,
            clause_tree_ref=result.get("clause_tree_ref"),
            file_graph_ref=result.get("file_graph_ref"),
        )
        retrigger_run_pipeline(
            run_id=run_id,
            deal_id=deal_id,
            tenant_id=result.get("tenant_id", tenant_id),
        )

    return result


async def _build_structure_async(
    *,
    document_version_id: str,
    extra_args: dict[str, Any],
    uow: UnitOfWork,
    stage_execution_id: str | None,
    artifact_tenant_id: str,
) -> dict[str, Any]:
    """
    Асинхронное ядро стадии structure.


    Делает только свою стадию:
    1) загружает DocumentVersion и Document;
    2) читает layout по sanitization-first контракту;
    3) строит clause_tree / file_graph (под флагом);
    4) сохраняет артефакты в хранилище;
    5) materialize'ит DocumentSegment в БД (под флагом);
    6) обновляет refs в DocumentVersion и статус документа;
    7) делает flush -> verify -> commit;
    8) возвращает committed=True только после commit.


    При наличии stage_execution_id:
    - перед основной логикой помечает execution как STARTED;
    - после успешного commit помечает execution как SUCCEEDED.
    """
    _ = extra_args

    start = time.time()
    store = ArtifactStore(settings)

    v_id = uuid.UUID(document_version_id)

    ver_repo = DocumentVersionRepository(uow.session)
    doc_repo = DocumentRepository(uow.session)
    seg_repo = DocumentSegmentRepository(uow.session)
    audit_repo = AuditRepository(uow.session)

    version = await ver_repo.get_by_id(v_id)
    if not version:
        raise PermanentError(
            f"DocumentVersion {v_id} not found",
            details={
                "stage": "structure",
                "type": PipelineErrorType.STRUCTURE_V2_CONTRACT_VIOLATION,
                "reason": StructureV2ErrorReason.VERSION_NOT_FOUND,
            },
        )

    doc = await doc_repo.get_by_id(version.document_id)
    if not doc:
        raise PermanentError(
            f"Document {version.document_id} not found",
            details={
                "stage": "structure",
                "type": PipelineErrorType.STRUCTURE_V2_CONTRACT_VIOLATION,
                "reason": StructureV2ErrorReason.DOCUMENT_NOT_FOUND,
            },
        )

    if doc.status in (
        DocumentStatus.STRUCTURED.value,
        DocumentStatus.CLASSIFIED.value,
        DocumentStatus.ANALYZING.value,
    ):
        logger.info(
            "Document already structured, skipping rebuild",
            document_id=str(doc.id),
            document_version_id=str(v_id),
            status=doc.status,
        )
        _skip_trace = build_stage_trace_fragment(
            strategy="structure_v2",
            input_summary={
                "document_version_id": str(v_id),
                "skip_reason": "already_structured",
                "current_status": doc.status,
            },
            output_summary={},
            warnings=["skipped_already_structured"],
            artifact_refs={},
            decision_details=None,
        )
        return {
            "status": DocumentStatus.STRUCTURED.value,
            "document_id": str(doc.id),
            "document_version_id": str(v_id),
            "skipped": True,
            "committed": False,
            "stage_execution_trace_status": "skipped",
            "stage_execution_result_details": _skip_trace,
        }

    allow_legacy_layout_fallback = bool(getattr(settings, "ALLOW_LEGACY_LAYOUT_FALLBACK", False))

    store_file_graph = bool(getattr(settings, "STRUCTURE_STORE_FILE_GRAPH", False))
    store_segment_trees = bool(getattr(settings, "STRUCTURE_STORE_SEGMENT_TREES", True))

    sanitized_layout_ref = getattr(version, "layout_primary_sanitized_ref", None)
    primary_layout_ref = getattr(version, "layout_primary_ref", None)

    layout_ref = sanitized_layout_ref
    layout_source = "layout_primary_sanitized_ref"

    if not layout_ref and allow_legacy_layout_fallback:
        layout_ref = primary_layout_ref
        layout_source = "layout_primary_ref_legacy_fallback"

        logger.warning(
            "Structure builder is using legacy unsanitized layout fallback",
            document_id=str(doc.id),
            document_version_id=str(v_id),
            layout_primary_ref=primary_layout_ref,
        )

    if not layout_ref:
        raise PermanentError(
            "Sanitized layout is required for structure building: " f"doc={doc.id}, version={v_id}",
            details={
                "stage": "structure",
                "type": PipelineErrorType.STRUCTURE_V2_CONTRACT_VIOLATION,
                "reason": StructureV2ErrorReason.MISSING_SANITIZED_LAYOUT,
                "allow_legacy_layout_fallback": allow_legacy_layout_fallback,
            },
        )

    chunk_plan_ref: str | None = None

    try:
        raw_layout = store.get_json(layout_ref)
    except Exception as e:
        logger.exception(
            "Failed to read layout for structure building",
            document_id=str(doc.id),
            document_version_id=str(v_id),
            layout_ref=layout_ref,
            layout_source=layout_source,
            error=str(e),
        )
        raise PermanentError(
            f"Failed to read layout for structure building: {e}",
            details={
                "stage": "structure",
                "type": PipelineErrorType.STRUCTURE_V2_CONTRACT_VIOLATION,
                "reason": StructureV2ErrorReason.LAYOUT_READ_ERROR,
            },
        )

    elements = raw_layout.get("elements", [])
    if not elements:
        raise PermanentError(
            f"No elements found in layout for version {v_id}",
            details={
                "stage": "structure",
                "type": PipelineErrorType.STRUCTURE_V2_CONTRACT_VIOLATION,
                "reason": StructureV2ErrorReason.EMPTY_LAYOUT,
            },
        )

    tenant_id = artifact_tenant_id
    deal_id = str(doc.deal_id)

    builder = StructureBuilder()

    file_graph_ref: str | None = None
    segments_count: int | None = None
    clause_tree = None
    segment_rows_to_create: list[dict[str, Any]] = []
    old_segment_tree_refs: list[str] = []

    def _verify_json_artifact_roundtrip(
        *,
        ref: str,
        expected_payload: dict | list,
        artifact_kind: str,
        segment_id: str | None = None,
    ) -> None:
        """
        Проверить, что только что записанный JSON-артефакт немедленно читается
        обратно в том же виде.

        Это защищает от silent stale-artifact / wrong-ref / unexpected overwrite
        ситуаций и делает persisted state проверяемым.
        """
        try:
            actual_payload = store.get_json(ref)
        except Exception as e:
            raise TransientError(
                f"{artifact_kind} artifact is not readable immediately after write: "
                f"ref={ref}, segment_id={segment_id or '<none>'}, error={e}"
            )

        if actual_payload != expected_payload:
            raise TransientError(
                f"{artifact_kind} artifact roundtrip mismatch after write: "
                f"ref={ref}, segment_id={segment_id or '<none>'}"
            )

    try:
        if store_file_graph:
            file_analysis, file_chunk_plan = build_file_structure_with_chunk_plan(
                document_id=str(doc.id),
                elements=elements,
                document_version_id=str(v_id),
            )
            file_result = file_analysis.file_structure
            clause_tree = file_result.primary_tree

            # ── Phase 10: сохранить chunk plan артефакт ───────────────────────────
            # Best-effort: ошибка сохранения plan НЕ прерывает pipeline.
            # chunk_builder при отсутствии chunk_plan_ref использует defaults.
            try:
                chunk_plan_path = ArtifactPath.chunk_plan(
                    tenant_id=tenant_id,
                    deal_id=deal_id,
                    document_id=str(doc.id),
                    document_version_id=str(v_id),
                )
                chunk_plan_payload = file_chunk_plan.to_dict()
                chunk_plan_ref = store.put_json(
                    chunk_plan_path,
                    chunk_plan_payload,
                )
                _verify_json_artifact_roundtrip(
                    ref=chunk_plan_ref,
                    expected_payload=chunk_plan_payload,
                    artifact_kind="chunk_plan",
                )
                logger.info(
                    "Structure builder: chunk plan saved",
                    document_id=str(doc.id),
                    document_version_id=str(v_id),
                    chunk_plan_ref=chunk_plan_ref,
                    chunk_plan_mode=file_chunk_plan.mode_decision.mode.value,
                    overall_retrieval_safe=file_chunk_plan.overall_retrieval_safe,
                    segment_count=len(file_chunk_plan.segment_plans),
                    any_layout_fallback=file_chunk_plan.any_layout_fallback,
                    all_segments_full_fallback=file_chunk_plan.all_segments_full_fallback,
                )
            except Exception as _plan_exc:
                logger.warning(
                    "Structure builder: failed to save chunk plan, "
                    "chunk stage will use default chunking params",
                    document_id=str(doc.id),
                    document_version_id=str(v_id),
                    error=str(_plan_exc),
                )
                chunk_plan_ref = None

            file_graph_path = ArtifactPath.file_graph(
                tenant_id=tenant_id,
                deal_id=deal_id,
                document_id=str(doc.id),
                document_version_id=str(v_id),
            )
            file_graph_payload = file_result.file_graph.to_dict()
            file_graph_ref = store.put_json(
                file_graph_path,
                file_graph_payload,
            )
            _verify_json_artifact_roundtrip(
                ref=file_graph_ref,
                expected_payload=file_graph_payload,
                artifact_kind="file_graph",
            )

            graph_segments = getattr(file_result.file_graph, "segments", []) or []
            segments_count = len(graph_segments)

            segment_tree_ref_by_id: dict[str, str] = {}

            if store_segment_trees:
                for seg in graph_segments:
                    seg_id = str(getattr(seg, "segment_id", "") or "")
                    if not seg_id:
                        raise PermanentError(
                            f"FileGraph segment has empty segment_id for version {v_id}",
                            details={
                                "stage": "structure",
                                "type": PipelineErrorType.STRUCTURE_V2_CONTRACT_VIOLATION,
                                "reason": StructureV2ErrorReason.INVALID_FILE_GRAPH_SEGMENT,
                            },
                        )

                    clause_tree_obj = file_result.get_tree_for_segment(seg_id)
                    if not clause_tree_obj:
                        raise PermanentError(
                            f"No ClauseTree found for segment {seg_id} in FileStructureResult "
                            f"(version={v_id}). segment_trees has "
                            f"{len(file_result.segment_trees)} entries.",
                            details={
                                "stage": "structure",
                                "type": PipelineErrorType.STRUCTURE_V2_CONTRACT_VIOLATION,
                                "reason": StructureV2ErrorReason.STRUCTURE_BUILD_ERROR,
                            },
                        )

                    segment_tree_path = ArtifactPath.segment_clause_tree(
                        tenant_id=tenant_id,
                        deal_id=deal_id,
                        document_id=str(doc.id),
                        document_version_id=str(v_id),
                        segment_id=seg_id,
                    )
                    segment_tree_payload = clause_tree_obj.to_dict()
                    segment_tree_ref = store.put_json(
                        segment_tree_path,
                        segment_tree_payload,
                    )
                    _verify_json_artifact_roundtrip(
                        ref=segment_tree_ref,
                        expected_payload=segment_tree_payload,
                        artifact_kind="segment_clause_tree",
                        segment_id=seg_id,
                    )
                    segment_tree_ref_by_id[seg_id] = segment_tree_ref

            for index, seg in enumerate(graph_segments):
                seg_id = str(getattr(seg, "segment_id", "") or "")
                seg_order = int(getattr(seg, "segment_order", index) or index)
                seg_type = str(getattr(seg, "segment_type", "unknown") or "unknown")
                seg_title = getattr(seg, "segment_title", None)
                page_start = int(getattr(seg, "page_start", 1) or 1)
                page_end = int(getattr(seg, "page_end", page_start) or page_start)
                is_primary = bool(getattr(seg, "is_primary", seg_order == 0))
                confidence = str(getattr(seg, "confidence", "MEDIUM") or "MEDIUM")

                segment_meta = getattr(seg, "segment_meta", None)
                if segment_meta is None:
                    segment_meta = getattr(seg, "meta", None)

                if not seg_id:
                    raise PermanentError(
                        f"FileGraph segment has empty segment_id for version {v_id}",
                        details={
                            "stage": "structure",
                            "type": PipelineErrorType.STRUCTURE_V2_CONTRACT_VIOLATION,
                            "reason": StructureV2ErrorReason.INVALID_FILE_GRAPH_SEGMENT,
                            "segment_order": seg_order,
                        },
                    )

                segment_rows_to_create.append(
                    {
                        "document_version_id": v_id,
                        "document_id": doc.id,
                        "segment_id": seg_id,
                        "segment_order": seg_order,
                        "segment_type": seg_type,
                        "segment_title": seg_title,
                        "page_start": page_start,
                        "page_end": page_end,
                        "is_primary": is_primary,
                        "confidence": confidence,
                        "segment_clause_tree_ref": segment_tree_ref_by_id.get(seg_id),
                        "segment_chunks_ref": None,
                        "segment_meta": segment_meta,
                    }
                )

        else:
            clause_tree = builder.build(
                document_id=str(doc.id),
                elements=elements,
            )

    except TransientError:
        raise
    except Exception as e:
        logger.exception(
            "Failed to build structure artifacts",
            document_id=str(doc.id),
            document_version_id=str(v_id),
            layout_ref=layout_ref,
            error=str(e),
            store_file_graph=store_file_graph,
        )
        raise PermanentError(
            f"Failed to build structure artifacts: {e}",
            details={
                "stage": "structure",
                "type": PipelineErrorType.STRUCTURE_V2_CONTRACT_VIOLATION,
                "reason": StructureV2ErrorReason.STRUCTURE_BUILD_ERROR,
            },
        )

    clause_tree_path = ArtifactPath.clause_tree(
        tenant_id=tenant_id,
        deal_id=deal_id,
        document_id=str(doc.id),
        document_version_id=str(v_id),
    )

    try:
        clause_tree_payload = clause_tree.to_dict()
        clause_tree_ref = store.put_json(clause_tree_path, clause_tree_payload)
        _verify_json_artifact_roundtrip(
            ref=clause_tree_ref,
            expected_payload=clause_tree_payload,
            artifact_kind="clause_tree",
        )
    except TransientError:
        raise
    except Exception as e:
        logger.exception(
            "Failed to store clause tree",
            document_id=str(doc.id),
            document_version_id=str(v_id),
            clause_tree_path=clause_tree_path,
            error=str(e),
        )
        raise PermanentError(
            f"Failed to store clause tree: {e}",
            details={
                "stage": "structure",
                "type": PipelineErrorType.STRUCTURE_V2_CONTRACT_VIOLATION,
                "reason": StructureV2ErrorReason.CLAUSE_TREE_STORE_ERROR,
            },
        )

    if store_file_graph:
        # ── Phase 14.4: snapshot old segment refs for post-commit cleanup ────
        try:
            existing_segments = await seg_repo.list_by_version(v_id)
            for old_seg in existing_segments:
                old_ref = getattr(old_seg, "segment_clause_tree_ref", None)
                if old_ref:
                    old_segment_tree_refs.append(old_ref)
        except Exception as _snap_exc:
            logger.debug(
                "Structure builder: failed to snapshot old segment refs (non-critical)",
                document_id=str(doc.id),
                error=str(_snap_exc),
            )

        try:
            await seg_repo.replace_segments(
                document_version_id=v_id,
                items=segment_rows_to_create,
            )
        except Exception as e:

            logger.exception(
                "Failed to replace document segments for structure result",
                document_id=str(doc.id),
                document_version_id=str(v_id),
                segments_count=len(segment_rows_to_create),
                error=str(e),
            )
            raise PermanentError(
                f"Failed to persist document segments: {e}",
                details={
                    "stage": "structure",
                    "type": PipelineErrorType.STRUCTURE_V2_CONTRACT_VIOLATION,
                    "reason": StructureV2ErrorReason.DOCUMENT_SEGMENTS_PERSIST_ERROR,
                },
            )

    updated_version = await ver_repo.update_refs(
        version_id=v_id,
        clause_tree_ref=clause_tree_ref,
        file_graph_ref=file_graph_ref,
        segments_count=segments_count,
        chunk_plan_ref=chunk_plan_ref,
    )
    if not updated_version:
        raise PermanentError(
            f"Failed to update structure refs for version {v_id}",
            details={
                "stage": "structure",
                "type": PipelineErrorType.STRUCTURE_V2_CONTRACT_VIOLATION,
                "reason": StructureV2ErrorReason.VERSION_UPDATE_FAILED,
            },
        )

    updated_doc = await doc_repo.update_status(
        doc.id,
        DocumentStatus.STRUCTURED.value,
        processing_error_details=None,
    )
    if not updated_doc:
        raise PermanentError(
            f"Failed to update document status to STRUCTURED for doc {doc.id}",
            details={
                "stage": "structure",
                "type": PipelineErrorType.STRUCTURE_V2_CONTRACT_VIOLATION,
                "reason": StructureV2ErrorReason.DOCUMENT_STATUS_UPDATE_FAILED,
            },
        )

    await uow.session.flush()

    refreshed_version = await ver_repo.get_by_id(v_id)
    if not refreshed_version:
        raise TransientError(f"DocumentVersion {v_id} is not visible after flush")

    refreshed_clause_tree_ref = getattr(refreshed_version, "clause_tree_ref", None)
    if not refreshed_clause_tree_ref:
        raise TransientError(f"clause_tree_ref is not visible after flush for version {v_id}")

    if refreshed_clause_tree_ref != clause_tree_ref:
        raise TransientError(f"clause_tree_ref mismatch after flush for version {v_id}")

    refreshed_file_graph_ref = getattr(refreshed_version, "file_graph_ref", None)
    if file_graph_ref and not refreshed_file_graph_ref:
        raise TransientError(f"file_graph_ref is not visible after flush for version {v_id}")

    if file_graph_ref and refreshed_file_graph_ref != file_graph_ref:
        raise TransientError(f"file_graph_ref mismatch after flush for version {v_id}")

    refreshed_chunk_plan_ref = getattr(refreshed_version, "chunk_plan_ref", None)
    if chunk_plan_ref and not refreshed_chunk_plan_ref:
        logger.warning(
            "Structure builder: chunk_plan_ref not visible after flush "
            "(non-critical, chunk stage will use default params)",
            document_id=str(doc.id),
            document_version_id=str(v_id),
        )

    if store_file_graph:
        persisted_segments = await seg_repo.list_by_version(v_id)

        if len(persisted_segments) != len(segment_rows_to_create):
            raise TransientError(
                "document_segments count mismatch after flush "
                f"for version {v_id}: expected={len(segment_rows_to_create)}, "
                f"actual={len(persisted_segments)}"
            )

        persisted_primary_count = sum(1 for s in persisted_segments if s.is_primary)
        if persisted_segments and persisted_primary_count != 1:
            raise TransientError(
                "document_segments primary invariant violated after flush "
                f"for version {v_id}: primary_count={persisted_primary_count}"
            )

        expected_segment_ids = {
            str(row["segment_id"])
            for row in segment_rows_to_create
        }
        actual_segment_ids = {
            str(seg.segment_id)
            for seg in persisted_segments
        }
        if actual_segment_ids != expected_segment_ids:
            raise TransientError(
                "document_segments segment_id set mismatch after flush "
                f"for version {v_id}: expected={sorted(expected_segment_ids)}, "
                f"actual={sorted(actual_segment_ids)}"
            )

        expected_tree_refs_by_segment_id = {
            str(row["segment_id"]): row.get("segment_clause_tree_ref")
            for row in segment_rows_to_create
        }
        actual_tree_refs_by_segment_id = {
            str(seg.segment_id): getattr(seg, "segment_clause_tree_ref", None)
            for seg in persisted_segments
        }

        for seg_id, expected_ref in expected_tree_refs_by_segment_id.items():
            actual_ref = actual_tree_refs_by_segment_id.get(seg_id)
            if actual_ref != expected_ref:
                raise TransientError(
                    "segment_clause_tree_ref mismatch after flush "
                    f"for version {v_id}, segment_id={seg_id}: "
                    f"expected={expected_ref}, actual={actual_ref}"
                )

    await uow.session.commit()

    # ── Phase 14.4: post-commit cleanup stale segment tree artifacts ─────────
    # Удаляем только те refs, которые больше не в текущем committed state.
    # Best-effort: ошибка cleanup НЕ ломает pipeline.
    current_tree_refs: set[str] = set()
    if clause_tree_ref:
        current_tree_refs.add(clause_tree_ref)
    for row in segment_rows_to_create:
        ref = row.get("segment_clause_tree_ref")
        if ref:
            current_tree_refs.add(ref)

    stale_refs = [r for r in old_segment_tree_refs if r not in current_tree_refs]

    versioned_stale_refs = [r for r in stale_refs if "/versions/" in str(r)]
    legacy_stale_refs = [r for r in stale_refs if "/versions/" not in str(r)]

    if legacy_stale_refs:
        logger.info(
            "Structure builder: skipping cleanup for legacy non-versioned segment tree refs",
            document_id=str(doc.id),
            stale_count=len(legacy_stale_refs),
        )

    if versioned_stale_refs:
        try:
            cleanup_result = store.delete_many_best_effort(versioned_stale_refs)
            logger.info(
                "Structure builder: post-commit cleanup stale versioned segment trees",
                document_id=str(doc.id),
                stale_count=len(versioned_stale_refs),
                deleted=cleanup_result.get("deleted", 0),
                failed=cleanup_result.get("failed", 0),
            )
        except Exception as _cleanup_exc:
            logger.warning(
                "Structure builder: post-commit cleanup failed (non-critical)",
                document_id=str(doc.id),
                error=str(_cleanup_exc),
            )

    # ── Phase 14.4: write artifact manifest best-effort ──────────────────────
    try:
        from storage._artifact_manifest import write_artifact_manifest_best_effort

        manifest_segment_refs: list[dict[str, Any]] = []
        for row in segment_rows_to_create:
            manifest_segment_refs.append({
                "segment_id": row.get("segment_id", ""),
                "segment_clause_tree_ref": row.get("segment_clause_tree_ref"),
                "segment_chunks_ref": row.get("segment_chunks_ref"),
            })

        write_artifact_manifest_best_effort(
            store=store,
            tenant_id=tenant_id,
            deal_id=deal_id,
            document_id=str(doc.id),
            document_version_id=str(v_id),
            clause_tree_ref=clause_tree_ref,
            file_graph_ref=file_graph_ref,
            chunk_plan_ref=chunk_plan_ref,
            chunks_manifest_v2_ref=None,
            segment_refs=manifest_segment_refs,
            stage="structure",
        )
    except Exception as _manifest_exc:
        logger.warning(
            "Structure builder: failed to write artifact manifest (non-critical)",
            document_id=str(doc.id),
            error=str(_manifest_exc),
        )

    duration = round(time.time() - start, 2)

    try:
        await audit_repo.log(
            tenant_id=uuid.UUID(tenant_id),
            deal_id=uuid.UUID(deal_id),
            action="STRUCTURE_COMPLETED",
            actor="system",
            actor_role="worker",
            details={
                "document_id": str(doc.id),
                "document_version_id": str(v_id),
                "stage_execution_id": stage_execution_id,
                "clause_tree_ref": clause_tree_ref,
                "file_graph_ref": file_graph_ref,
                "chunk_plan_ref": chunk_plan_ref,
                "segments_count": segments_count,
                "materialized_segments": len(segment_rows_to_create) if store_file_graph else 0,
                "layout_source": layout_source,
                "layout_ref": layout_ref,
                "confidence": getattr(clause_tree, "structure_confidence", None),
                "is_degraded": getattr(clause_tree, "degraded", None),
                "duration_seconds": duration,
            },
        )
    except Exception:
        logger.warning(
            "Structure builder: failed to write audit log for STRUCTURE_COMPLETED",
            document_id=str(doc.id),
            document_version_id=str(v_id),
            stage_execution_id=stage_execution_id,
        )

    logger.info(
        "Structure building committed successfully",
        document_id=str(doc.id),
        document_version_id=str(v_id),
        clause_tree_ref=clause_tree_ref,
        file_graph_ref=file_graph_ref,
        chunk_plan_ref=chunk_plan_ref,
        segments_count=segments_count,
        materialized_segments=len(segment_rows_to_create) if store_file_graph else 0,
        layout_source=layout_source,
        layout_ref=layout_ref,
        confidence=getattr(clause_tree, "structure_confidence", None),
        is_degraded=getattr(clause_tree, "degraded", None),
        duration_seconds=duration,
        status=DocumentStatus.STRUCTURED.value,
    )

    _trace = build_stage_trace_fragment(
        strategy="structure_v2",
        input_summary={
            "document_version_id": str(v_id),
            "layout_source": layout_source,
            "layout_ref": layout_ref,
            "allow_legacy_layout_fallback": allow_legacy_layout_fallback,
            "store_file_graph": store_file_graph,
            "store_segment_trees": store_segment_trees,
        },
        output_summary={
            "segments_count": segments_count,
            "materialized_segments": (
                len(segment_rows_to_create) if store_file_graph else 0
            ),
            "confidence": getattr(clause_tree, "structure_confidence", None),
            "is_degraded": getattr(clause_tree, "degraded", None),
            "duration_seconds": duration,
        },
        warnings=(
            ["legacy_layout_fallback_used"]
            if layout_source == "layout_primary_ref_legacy_fallback"
            else []
        ),
        artifact_refs={
            "clause_tree_ref": clause_tree_ref,
            "file_graph_ref": file_graph_ref,
            "chunk_plan_ref": chunk_plan_ref,
        },
        decision_details=None,
    )

    return {
        "status": DocumentStatus.STRUCTURED.value,
        "document_id": str(doc.id),
        "document_version_id": str(v_id),
        "clause_tree_ref": clause_tree_ref,
        "file_graph_ref": file_graph_ref,
        "chunk_plan_ref": chunk_plan_ref,
        "segments_count": segments_count,
        "materialized_segments": len(segment_rows_to_create) if store_file_graph else 0,
        "layout_ref": layout_ref,
        "layout_source": layout_source,
        "confidence": getattr(clause_tree, "structure_confidence", None),
        "is_degraded": getattr(clause_tree, "degraded", None),
        "duration_seconds": duration,
        "tenant_id": tenant_id,
        "committed": True,
        "stage_execution_result_details": _trace,
    }


async def _mark_failed(
    uow: UnitOfWork,
    document_version_id: str,
    *,
    tenant_id: str,
    message: str,
    stage_execution_id: str | None,
    reason_code: str,
) -> None:
    """
    Best-effort перевод документа в FAILED,
    если стадия structure завершилась постоянной ошибкой.

    Дополнительно:
    - если есть stage_execution_id, помечаем execution как FAILED
      с понятными подробностями.
    """
    ver_repo = DocumentVersionRepository(uow.session)
    doc_repo = DocumentRepository(uow.session)
    dse_repo = DocumentStageExecutionRepository(uow.session)
    audit_repo = AuditRepository(uow.session)

    v_id = uuid.UUID(document_version_id)
    version = await ver_repo.get_by_id(v_id)
    if not version:
        logger.warning(
            "Cannot mark document as FAILED during structure stage: version not found",
            document_version_id=document_version_id,
        )
        return

    # Обновляем бизнес-статус документа.
    await doc_repo.set_failed(
        version.document_id,
        stage="structure",
        message=message,
        reason=PipelineErrorType.STRUCTURE_V2_CONTRACT_VIOLATION,
        run_id=None,
    )

    try:
        document = await doc_repo.get_by_id(version.document_id)
        if document:
            await audit_repo.log(
                tenant_id=uuid.UUID(tenant_id),
                deal_id=document.deal_id,
                action="STRUCTURE_FAILED",
                actor="system",
                actor_role="worker",
                details={
                    "document_id": str(version.document_id),
                    "document_version_id": document_version_id,
                    "stage_execution_id": stage_execution_id,
                    "reason_code": reason_code,
                    "message": message,
                    "stage": "structure",
                    "error_type": PipelineErrorType.STRUCTURE_V2_CONTRACT_VIOLATION,
                },
            )
    except Exception:
        logger.warning(
            "Structure builder: failed to write audit log for STRUCTURE_FAILED",
            document_version_id=document_version_id,
            stage_execution_id=stage_execution_id,
        )

    # Обновляем execution-запись (если есть).
    if stage_execution_id:
        try:
            await dse_repo.mark_failed(
                uuid.UUID(stage_execution_id),
                error_details={
                    "stage": "structure",
                    "type": PipelineErrorType.STRUCTURE_V2_CONTRACT_VIOLATION,
                    "reason": reason_code,
                    "message": message,
                    "document_version_id": document_version_id,
                },
            )
        except Exception as e:
            logger.exception(
                "Failed to mark stage execution as FAILED for structure",
                document_version_id=document_version_id,
                stage_execution_id=stage_execution_id,
                error=str(e),
            )


