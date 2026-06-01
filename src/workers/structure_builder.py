# src/workers/structure_builder.py

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
    **kwargs: Any,
) -> dict[str, Any]:
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
    stage_execution_id = kwargs.get("stage_execution_id")

    async def _wrapper() -> dict[str, Any]:
        try:
            async with db_uow() as uow:
                return await _build_structure_async(
                    document_version_id=document_version_id,
                    extra_args=kwargs,
                    uow=uow,
                    stage_execution_id=stage_execution_id,
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
                await _mark_failed(
                    uow=uow_status,
                    document_version_id=document_version_id,
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
            tenant_id=tenant_id,
            run_id=run_id,
            clause_tree_ref=result.get("clause_tree_ref"),
            file_graph_ref=result.get("file_graph_ref"),
        )
        retrigger_run_pipeline(
            run_id=run_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
        )

    return result


async def _build_structure_async(
    *,
    document_version_id: str,
    extra_args: dict[str, Any],
    uow: UnitOfWork,
    stage_execution_id: str | None,
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
    dse_repo = DocumentStageExecutionRepository(uow.session)
    audit_repo = AuditRepository(uow.session)

    # 1. Помечаем execution как STARTED (если он есть).
    if stage_execution_id:
        try:
            await dse_repo.mark_started(uuid.UUID(stage_execution_id))
        except Exception as e:
            logger.exception(
                "Failed to mark stage execution as STARTED for structure",
                document_version_id=document_version_id,
                stage_execution_id=stage_execution_id,
                error=str(e),
            )
            # Не прерываем саму стадию: лучше пусть структура всё равно строится.

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
        return {
            "status": DocumentStatus.STRUCTURED.value,
            "document_id": str(doc.id),
            "document_version_id": str(v_id),
            "skipped": True,
            "committed": False,
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

    if hasattr(doc, "deal") and doc.deal and hasattr(doc.deal, "tenant_id"):
        tenant_id = str(doc.deal.tenant_id)
    else:
        tenant_id = str(doc.deal_id)

    deal_id = str(doc.deal_id)

    builder = StructureBuilder()

    file_graph_ref: str | None = None
    segments_count: int | None = None
    clause_tree = None
    segment_rows_to_create: list[dict[str, Any]] = []
    old_segment_tree_refs: list[str] = []

    try:
        if store_file_graph:
            file_result = builder.build_file_structure(
                document_id=str(doc.id),
                elements=elements,
                document_version_id=str(v_id),
            )

            clause_tree = file_result.primary_tree

            file_graph_path = ArtifactPath.file_graph(
                tenant_id=tenant_id,
                deal_id=deal_id,
                document_id=str(doc.id),
            )
            file_graph_ref = store.put_json(
                file_graph_path,
                file_result.file_graph.to_dict(),
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
                        segment_id=seg_id,
                    )
                    segment_tree_ref = store.put_json(
                        segment_tree_path,
                        clause_tree_obj.to_dict(),
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

    except Exception as e:
        logger.exception(
            "Failed to build clause tree",
            document_id=str(doc.id),
            document_version_id=str(v_id),
            layout_ref=layout_ref,
            error=str(e),
            store_file_graph=store_file_graph,
        )
        raise PermanentError(
            f"Failed to build clause tree: {e}",
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
    )

    try:
        clause_tree_ref = store.put_json(clause_tree_path, clause_tree.to_dict())
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

    await uow.session.commit()

    # 2. На успешном пути помечаем execution как SUCCEEDED (если он есть).
    if stage_execution_id:
        try:
            await dse_repo.mark_succeeded(uuid.UUID(stage_execution_id))
        except Exception as e:
            logger.exception(
                "Failed to mark stage execution as SUCCEEDED for structure",
                document_version_id=document_version_id,
                stage_execution_id=stage_execution_id,
                error=str(e),
            )

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
    if stale_refs:
        try:
            cleanup_result = store.delete_many_best_effort(stale_refs)
            logger.info(
                "Structure builder: post-commit cleanup stale segment trees",
                document_id=str(doc.id),
                stale_count=len(stale_refs),
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
        segments_count=segments_count,
        materialized_segments=len(segment_rows_to_create) if store_file_graph else 0,
        layout_source=layout_source,
        layout_ref=layout_ref,
        confidence=getattr(clause_tree, "structure_confidence", None),
        is_degraded=getattr(clause_tree, "degraded", None),
        duration_seconds=duration,
        status=DocumentStatus.STRUCTURED.value,
    )

    return {
        "status": DocumentStatus.STRUCTURED.value,
        "document_id": str(doc.id),
        "document_version_id": str(v_id),
        "clause_tree_ref": clause_tree_ref,
        "file_graph_ref": file_graph_ref,
        "segments_count": segments_count,
        "materialized_segments": len(segment_rows_to_create) if store_file_graph else 0,
        "layout_ref": layout_ref,
        "layout_source": layout_source,
        "confidence": getattr(clause_tree, "structure_confidence", None),
        "is_degraded": getattr(clause_tree, "degraded", None),
        "duration_seconds": duration,
        "committed": True,
    }


async def _mark_failed(
    uow: UnitOfWork,
    document_version_id: str,
    *,
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
                tenant_id=getattr(document, "tenant_id", None) or uuid.UUID(int=0),
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
