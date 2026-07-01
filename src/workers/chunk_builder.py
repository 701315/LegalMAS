# src/workers/chunk_builder.py

"""
Chunk Builder Worker (V2_ONLY).

Назначение:
- Построить per-segment chunk snapshots через SegmentChunkBuilderV2.
- Сохранить segment_chunks_ref в DocumentSegment.
- Сохранить file-level chunks_manifest_v2_ref в DocumentVersion.
- Обновить статус документа: STRUCTURED -> CHUNKED.
- Запустить downstream-orchestrator только после committed=True.

Позиция в пайплайне:
- import -> convert -> build_primary_language_source -> extract -> pii
  -> structure -> chunking -> classify/checks/...

Контракт стадии (V2_ONLY):
- Единственный source of truth для chunking:
  - DocumentSegment rows для document_version;
  - segment_chunks_ref в DocumentSegment;
  - chunks_manifest_v2_ref в DocumentVersion.
- Legacy v1 file-level chunk snapshot не используется.
- Любое структурное нарушение контракта -> PermanentError
  c type=chunking_v2_contract_violation.
- Quarantine используется только для контентных кейсов.

Этап 5 — dual-write legal units:
- После сохранения chunk snapshot для каждого сегмента
  builder опционально сохраняет legal_units_v1.json рядом.
- Ссылка legal_units_ref пишется в DocumentSegment.segment_meta.
- Ошибка сохранения legal units НЕ ломает основной chunk pipeline.
- Если legal_units_snapshot отсутствует (builder упал или отключён)
  — продолжаем как обычно, segment_meta не обновляется.
Phase 12 — semantic enrichment formal stage:
- chunk_builder НЕ строит enrichment sidecar inline;
- после успешного commit orchestrator планирует workers.build_legal_units_enrichment;
- dedicated enrichment worker строит legal_units_enrichment_v1.json в heavy_llm queue;
- chunk_builder очищает stale legal_units_enrichment_ref при rebuild baseline.

Audit trail:
- На успешном завершении пишет CHUNK_BUILD_COMPLETED.
- При PermanentError переводит документ в FAILED и пишет CHUNK_BUILD_FAILED.
- При QuarantineError переводит документ в QUARANTINE и пишет CHUNK_BUILD_QUARANTINED.
- Audit logging best-effort: проблемы аудита не должны ломать бизнес-стадию.
"""

from __future__ import annotations

import time
import uuid
from typing import Any
from core.stage_trace import build_stage_trace_fragment
from core.config import settings
from core.constants import DocumentStatus
from core.exceptions import PermanentError, QuarantineError, TransientError
from core.logging import get_logger
from core.pipeline_errors import (
    ChunkingQuarantineReason,
    ChunkingV2ErrorReason,
    PipelineErrorType,
)
from db.repositories import AuditRepository
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_segment_repo import DocumentSegmentRepository
from db.repositories.document_stage_execution_repo import (
    DocumentStageExecutionRepository,
)
from db.repositories.document_version_repo import DocumentVersionRepository
from db.uow import UnitOfWork, db_uow
from engine.content.segment_chunk_builder_v2 import (
    FileChunkManifestSegmentV2,
    SegmentChunkBuilderV2,
)
from services.structure.chunk_planner._retrieval_readiness import (
    build_retrieval_readiness_report,
)
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.run_orchestrator_trigger import retrigger_run_pipeline
from storage.artifact_store import ArtifactPath, ArtifactStore
from services.structure.chunk_planner import FileChunkPlan

from workers._tenant_resolver import resolve_artifact_tenant_id

logger = get_logger(__name__)


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.build_chunks",
    queue="default",
)
def build_chunks(
    self,
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    run_id: str | None = None,
    stage_execution_id: str | None = None,
    orchestration_strategy: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Sync Celery entry point для построения чанков.

    Поведение:
    - выполняет только V2_ONLY chunking;
    - при PermanentError переводит документ в FAILED;
    - при TransientError отдаёт управление retry-механизму;
    - при QuarantineError переводит документ в карантин по стадии chunking;
    - при успехе будит оркестратор только после commit.
    """
    _ = self

    async def _wrapper() -> dict[str, Any]:
        try:
            async with db_uow() as uow:
                resolved_tenant_id = await resolve_artifact_tenant_id(
                    session=uow.session,
                    deal_id=deal_id,
                    document_id=document_id,
                    payload_tenant_id=tenant_id,
                )
                return await _build_chunks_v2_async(
                    document_version_id=document_version_id,
                    document_id=document_id,
                    deal_id=deal_id,
                    tenant_id=resolved_tenant_id,
                    run_id=run_id,
                    uow=uow,
                    stage_execution_id=stage_execution_id,
                )

        except TransientError as e:
            logger.warning(
                "Transient error during chunk building; task should be retried",
                document_id=document_id,
                document_version_id=document_version_id,
                deal_id=deal_id,
                tenant_id=tenant_id,
                run_id=run_id,
                error=str(e),
            )
            raise

        except QuarantineError as e:
            quarantine_reason = getattr(
                e,
                "reason",
                ChunkingQuarantineReason.EMPTY_SEGMENTS_CONTENT,
            )

            logger.warning(
                "Quarantine during chunk building",
                document_id=document_id,
                document_version_id=document_version_id,
                deal_id=deal_id,
                tenant_id=tenant_id,
                run_id=run_id,
                reason=quarantine_reason,
                error=str(e),
            )

            async with db_uow() as uow_status:
                failed_tenant_id = await resolve_artifact_tenant_id(
                    session=uow_status.session,
                    deal_id=deal_id,
                    document_id=document_id,
                    payload_tenant_id=tenant_id,
                )
                await _mark_quarantined(
                    uow=uow_status,
                    document_uuid=uuid.UUID(document_id),
                    tenant_uuid=uuid.UUID(failed_tenant_id),
                    deal_uuid=uuid.UUID(deal_id),
                    message=str(e),
                    reason=quarantine_reason,
                    run_id=uuid.UUID(run_id) if run_id else None,
                    stage_execution_id=stage_execution_id,
                    document_version_id=document_version_id,
                )

            return {
                "status": DocumentStatus.QUARANTINE.value,
                "document_id": document_id,
                "document_version_id": document_version_id,
                "quarantined": True,
                "quarantine_reason": quarantine_reason,
                "error": str(e),
                "committed": False,
            }

        except PermanentError as e:
            details = getattr(e, "details", {}) or {}
            reason_code = details.get(
                "reason",
                ChunkingV2ErrorReason.SEGMENT_BUILDER_ERROR,
            )

            logger.error(
                "Permanent error during chunk building",
                document_id=document_id,
                document_version_id=document_version_id,
                deal_id=deal_id,
                tenant_id=tenant_id,
                run_id=run_id,
                reason_code=reason_code,
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
                    document_uuid=uuid.UUID(document_id),
                    tenant_uuid=uuid.UUID(failed_tenant_id),
                    deal_uuid=uuid.UUID(deal_id),
                    message=str(e),
                    run_id=uuid.UUID(run_id) if run_id else None,
                    stage_execution_id=stage_execution_id,
                    document_version_id=document_version_id,
                    reason_code=reason_code,
                )

            return {
                "status": DocumentStatus.FAILED.value,
                "document_id": document_id,
                "document_version_id": document_version_id,
                "error": str(e),
                "reason_code": reason_code,
                "committed": False,
            }

    result = run_async(_wrapper())

    if run_id and result.get("committed") is True:
        logger.info(
            "Chunk building committed, retriggering run pipeline",
            document_id=document_id,
            document_version_id=document_version_id,
            deal_id=deal_id,
            tenant_id=result.get("tenant_id", tenant_id),
            run_id=run_id,
            chunks_manifest_v2_ref=result.get("chunks_manifest_v2_ref"),
            segments_count=result.get("segments_count"),
            chunk_count_total=result.get("chunk_count_total"),
            legal_units_count=result.get("legal_units_count", 0),
        )
        retrigger_run_pipeline(
            run_id=run_id,
            deal_id=deal_id,
            tenant_id=result.get("tenant_id", tenant_id),
        )

    return result


async def _build_chunks_v2_async(
    *,
    document_version_id: str,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    run_id: str | None,
    uow: UnitOfWork,
    stage_execution_id: str | None,
) -> dict[str, Any]:
    """
    V2_ONLY-логика построения чанков:
    - строим per-segment snapshots и file-level manifest через SegmentChunkBuilderV2;
    - сохраняем segment_chunks и manifest в MinIO;
    - обновляем segment_chunks_ref и chunks_manifest_v2_ref в БД;
    - статус документа -> CHUNKED.

    Этап 5 — dual-write legal units:
    - для каждого сегмента опционально сохраняем legal_units_v1.json;
    - ссылку legal_units_ref пишем в segment_meta (JSON merge, не замена);
    - ошибка сохранения legal units не прерывает основной pipeline.

    Дополнительно:
    - execution STARTED перед выполнением;
    - execution SUCCEEDED после commit;
    - жёсткие проверки v2-контракта.
    """
    start = time.time()
    store = ArtifactStore(settings)

    ver_repo = DocumentVersionRepository(uow.session)
    doc_repo = DocumentRepository(uow.session)
    seg_repo = DocumentSegmentRepository(uow.session)
    dse_repo = DocumentStageExecutionRepository(uow.session)
    audit_repo = AuditRepository(uow.session)

    v_id = uuid.UUID(document_version_id)
    d_id = uuid.UUID(document_id)
    tenant_uuid = uuid.UUID(tenant_id)
    deal_uuid = uuid.UUID(deal_id)

    # ── Phase 13.1: Telemetry collector для этого документа ──────────────────
    from services.telemetry._collector import TelemetryCollector
    from services.telemetry._events import ChunkingCompletedEvent

    telemetry_collector = TelemetryCollector(document_id=str(d_id))

    version = await ver_repo.get_by_id(v_id)
    if not version:
        raise PermanentError(
            f"DocumentVersion {v_id} not found",
            details={
                "stage": "chunking_v2",
                "type": PipelineErrorType.CHUNKING_V2_CONTRACT_VIOLATION,
                "reason": ChunkingV2ErrorReason.VERSION_NOT_FOUND,
            },
        )

    # ── P3a: загрузить Phase 10 chunk plan ───────────────────────────────────────
    # Plan вычислен structure_builder и сохранён как chunk_plan.json.
    # Если plan недоступен — используем defaults (graceful degradation).
    # Это гарантирует backward compatibility с документами без plan
    # (старые runs, ошибка planning, legacy mode).
    chunk_plan: FileChunkPlan | None = None
    _chunk_plan_ref = getattr(version, "chunk_plan_ref", None)

    if _chunk_plan_ref:
        try:
            _plan_data = store.get_json(_chunk_plan_ref)
            if not isinstance(_plan_data, dict):
                raise TypeError(
                    f"chunk_plan artifact is not a dict: {type(_plan_data).__name__}"
                )
            chunk_plan = FileChunkPlan.from_dict(_plan_data)
            logger.info(
                "Chunk builder: chunk plan loaded",
                document_id=document_id,
                document_version_id=document_version_id,
                chunk_plan_ref=_chunk_plan_ref,
                chunk_plan_mode=chunk_plan.mode_decision.mode.value,
                overall_retrieval_safe=chunk_plan.overall_retrieval_safe,
                segment_count=len(chunk_plan.segment_plans),
                any_layout_fallback=chunk_plan.any_layout_fallback,
                all_segments_full_fallback=chunk_plan.all_segments_full_fallback,
            )
        except Exception as _plan_exc:
            logger.warning(
                "Chunk builder: failed to load chunk plan, "
                "proceeding with default chunking params",
                document_id=document_id,
                document_version_id=document_version_id,
                chunk_plan_ref=_chunk_plan_ref,
                error=str(_plan_exc),
            )
            chunk_plan = None
    else:
        logger.info(
            "Chunk builder: no chunk_plan_ref on version, "
            "using default chunking params",
            document_id=document_id,
            document_version_id=document_version_id,
        )

    doc = await doc_repo.get_by_id(d_id)
    if not doc:
        raise PermanentError(
            f"Document {d_id} not found",
            details={
                "stage": "chunking_v2",
                "type": PipelineErrorType.CHUNKING_V2_CONTRACT_VIOLATION,
                "reason": ChunkingV2ErrorReason.DOCUMENT_NOT_FOUND,
            },
        )

    segments = await seg_repo.list_by_version(v_id)
    if not segments:
        raise PermanentError(
            f"No DocumentSegment rows found for version {v_id}",
            details={
                "stage": "chunking_v2",
                "type": PipelineErrorType.CHUNKING_V2_CONTRACT_VIOLATION,
                "reason": ChunkingV2ErrorReason.SEGMENTS_MISSING,
            },
        )

    builder_v2 = SegmentChunkBuilderV2(store=store)

    try:
        file_manifest, segment_snapshots = await builder_v2.build_for_version(
            session=uow.session,
            document_version_id=v_id,
            target_tokens=300,
            max_tokens=800,
            overlap_ratio=0.15,
            chunk_plan=chunk_plan,                  # ← P3a
            collector=telemetry_collector,
        )
    except PermanentError:
        raise
    except Exception as e:
        logger.exception(
            "SegmentChunkBuilderV2 failed",
            document_id=str(doc.id),
            document_version_id=str(v_id),
            error=str(e),
        )
        raise PermanentError(
            f"SegmentChunkBuilderV2 failed: {e}",
            details={
                "stage": "chunking_v2",
                "type": PipelineErrorType.CHUNKING_V2_CONTRACT_VIOLATION,
                "reason": ChunkingV2ErrorReason.SEGMENT_BUILDER_ERROR,
            },
        )

    if not segment_snapshots:
        logger.warning(
            "SegmentChunkBuilderV2 produced no segment snapshots",
            document_id=str(doc.id),
            document_version_id=str(v_id),
        )
        raise QuarantineError(
            "No usable segment chunks built from valid structure",
            document_id=str(doc.id),
            reason=ChunkingQuarantineReason.EMPTY_SEGMENTS_CONTENT,
            details={
                "document_version_id": str(version.id),
            },
        )

    manifest_segments_list = getattr(file_manifest, "segments", None) or []
    if not manifest_segments_list:
        raise PermanentError(
            "File chunk manifest v2 is empty",
            details={
                "stage": "chunking_v2",
                "type": PipelineErrorType.CHUNKING_V2_CONTRACT_VIOLATION,
                "reason": ChunkingV2ErrorReason.MANIFEST_EMPTY,
            },
        )

    db_segment_ids = {s.segment_id for s in segments}
    manifest_segment_ids = {s.segment_id for s in manifest_segments_list}

    if db_segment_ids != manifest_segment_ids:
        raise PermanentError(
            "File chunk manifest v2 is inconsistent with persisted segments",
            details={
                "stage": "chunking_v2",
                "type": PipelineErrorType.CHUNKING_V2_CONTRACT_VIOLATION,
                "reason": ChunkingV2ErrorReason.MANIFEST_INCONSISTENT_WITH_SEGMENTS,
            },
        )

    segments_by_id = {s.segment_id: s for s in segments}
    manifest_segments: dict[str, FileChunkManifestSegmentV2] = {
        s.segment_id: s for s in manifest_segments_list
    }

    chunk_count_total = 0
    legal_unit_chunk_count_total = 0
    segment_rows_to_replace: list[dict[str, Any]] = []

    # ── Этап 5: счётчики для legal units ─────────────────────────────────────
    # Собираем статистику по всем сегментам для audit log и return value.
    legal_units_saved_count = 0  # сколько сегментов успешно сохранили legal units
    legal_units_refs: list[str] = []  # все сохранённые refs

    # Phase 12: enrichment sidecar is now built by the dedicated
    # build_legal_units_enrichment worker after classification.
    # These counters remain zero in chunk_builder; kept for audit schema compat.
    enrichment_saved_count = 0
    enrichment_refs: list[str] = []


    for snapshot in segment_snapshots:
        seg = segments_by_id.get(snapshot.segment_id)
        if seg is None:
            raise PermanentError(
                f"Internal error: no DocumentSegment row for snapshot.segment_id={snapshot.segment_id}",
                details={
                    "stage": "chunking_v2",
                    "type": PipelineErrorType.CHUNKING_V2_CONTRACT_VIOLATION,
                    "reason": ChunkingV2ErrorReason.SEGMENT_NOT_FOUND_FOR_SNAPSHOT,
                },
            )

        snapshot_dict = snapshot.to_dict()
        snapshot_chunks = snapshot_dict.get("chunks", {}) or {}
        section_chunks = snapshot_chunks.get("section", []) or []
        clause_chunks = snapshot_chunks.get("clause", []) or []

        subclause_chunks = snapshot_chunks.get("subclause", []) or []
        legal_unit_chunks = snapshot_chunks.get("legal_unit", []) or []

        legal_unit_chunk_count_total += len(legal_unit_chunks)

        all_segment_chunks: list[dict[str, Any]] = [
            *section_chunks,
            *clause_chunks,
            *subclause_chunks,
            *legal_unit_chunks,
        ]
        retrieval_report = build_retrieval_readiness_report(
            document_id=str(doc.id),
            chunks=all_segment_chunks,
        )

        snapshot_chunk_count = retrieval_report.total_chunks

        # ── Phase 13.1: emit ChunkingCompletedEvent per segment ──────────────
        try:
            telemetry_collector.emit(ChunkingCompletedEvent(
                document_id=str(doc.id),
                segment_id=snapshot.segment_id,
                total_chunks=snapshot_chunk_count,
                section_chunks=len(section_chunks),
                clause_chunks=len(clause_chunks),
                subclause_chunks=len(subclause_chunks),
                legal_unit_chunks=len(legal_unit_chunks),
                chunking_mode=(
                    (snapshot.planning or {}).get("mode") or "unknown"
                ),
                retrieval_safe_chunks=retrieval_report.retrieval_safe_chunks,
                degraded_chunks=retrieval_report.degraded_chunks,
                layout_fallback_chunks=retrieval_report.layout_fallback_chunks,
                retrieval_recommended_action=retrieval_report.recommended_action,
            ))
        except Exception as _tel_exc:
            logger.debug(
                "Chunk builder: telemetry ChunkingCompletedEvent failed (non-critical)",
                document_id=str(doc.id),
                segment_id=snapshot.segment_id,
                error=str(_tel_exc),
            )

        chunk_count_total += snapshot_chunk_count

        chunk_path = ArtifactPath.segment_chunks(
            tenant_id=tenant_id,
            deal_id=deal_id,
            document_id=str(doc.id),
            segment_id=snapshot.segment_id,
        )

        try:
            segment_chunks_ref = store.put_json(chunk_path, snapshot_dict)
        except Exception as e:
            logger.exception(
                "Failed to store segment chunk snapshot",
                document_id=str(doc.id),
                document_version_id=str(v_id),
                segment_id=snapshot.segment_id,
                chunks_path=chunk_path,
                error=str(e),
            )
            raise PermanentError(
                f"Failed to store segment chunk snapshot: {e}",
                details={
                    "stage": "chunking_v2",
                    "type": PipelineErrorType.CHUNKING_V2_CONTRACT_VIOLATION,
                    "reason": ChunkingV2ErrorReason.SEGMENT_CHUNKS_STORE_ERROR,
                },
            )

        manifest_segment = manifest_segments.get(snapshot.segment_id)
        if manifest_segment is not None:
            manifest_segment.segment_chunks_ref = segment_chunks_ref

        # ── Этап 5: dual-write legal_units_v1.json ────────────────────────────
        # Сохраняем legal units snapshot опционально.
        # Ошибка сохранения НЕ ломает основной chunk pipeline —
        # мы логируем warning и продолжаем без legal_units_ref.
        legal_units_ref: str | None = None
        legal_units_snapshot = getattr(snapshot, "legal_units_snapshot", None)

        if legal_units_snapshot is not None:
            lu_path = ArtifactPath.legal_units_v1(
                tenant_id=tenant_id,
                deal_id=deal_id,
                document_id=str(doc.id),
                segment_id=snapshot.segment_id,
            )
            try:
                legal_units_ref = store.put_json(
                    lu_path,
                    legal_units_snapshot.to_dict(),
                )
                legal_units_saved_count += 1
                legal_units_refs.append(legal_units_ref)

                logger.info(
                    "Chunk builder: legal units saved",
                    document_id=str(doc.id),
                    document_version_id=str(v_id),
                    segment_id=snapshot.segment_id,
                    legal_units_ref=legal_units_ref,
                    total_units=len(legal_units_snapshot.units),
                    units_with_known_type=legal_units_snapshot.units_with_known_type,
                )
            except Exception as lu_store_exc:
                logger.warning(
                    "Chunk builder: failed to store legal units, continuing without legal_units_ref",
                    document_id=str(doc.id),
                    document_version_id=str(v_id),
                    segment_id=snapshot.segment_id,
                    error=str(lu_store_exc),
                )
        else:
            logger.debug(
                "Chunk builder: no legal units snapshot for segment, skipping dual-write",
                document_id=str(doc.id),
                document_version_id=str(v_id),
                segment_id=snapshot.segment_id,
            )

        # ── Phase 14.4: clean segment_meta — удаляем stale refs ──────────────
        # Если на текущем прогоне legal_units / enrichment не были построены,
        # то старые refs больше не валидны и должны быть удалены.
        # Это предотвращает downstream чтение устаревших артефактов.
        existing_meta = dict(seg.segment_meta or {})

        if legal_units_ref is not None:
            existing_meta["legal_units_ref"] = legal_units_ref
        else:
            existing_meta.pop("legal_units_ref", None)

        # Always remove stale enrichment ref on baseline rebuild.
        # The dedicated build_legal_units_enrichment worker will set a fresh ref
        # after classification is complete.
        existing_meta.pop("legal_units_enrichment_ref", None)


        segment_rows_to_replace.append(
            {
                "document_version_id": seg.document_version_id,
                "document_id": seg.document_id,
                "segment_id": seg.segment_id,
                "segment_order": seg.segment_order,
                "segment_type": seg.segment_type,
                "segment_title": seg.segment_title,
                "page_start": seg.page_start,
                "page_end": seg.page_end,
                "is_primary": seg.is_primary,
                "confidence": seg.confidence,
                "segment_clause_tree_ref": seg.segment_clause_tree_ref,
                "segment_chunks_ref": segment_chunks_ref,
                # Мерджированный meta: старые поля + legal_units_ref если есть
                "segment_meta": existing_meta,
            }
        )

    if len(segment_rows_to_replace) != len(segments):
        raise PermanentError(
            "Prepared segment rows count does not match persisted segment rows",
            details={
                "stage": "chunking_v2",
                "type": PipelineErrorType.CHUNKING_V2_CONTRACT_VIOLATION,
                "reason": ChunkingV2ErrorReason.MANIFEST_INCONSISTENT_WITH_SEGMENTS,
            },
        )

    if chunk_count_total <= 0:
        raise QuarantineError(
            "No usable chunk items built from valid segment snapshots",
            document_id=str(doc.id),
            reason=ChunkingQuarantineReason.EMPTY_CHUNKS_CONTENT,
            details={
                "document_version_id": str(version.id),
            },
        )

    for manifest_segment in manifest_segments_list:
        if not getattr(manifest_segment, "segment_chunks_ref", None):
            raise PermanentError(
                "File chunk manifest v2 is inconsistent: some manifest segments have no segment_chunks_ref",
                details={
                    "stage": "chunking_v2",
                    "type": PipelineErrorType.CHUNKING_V2_CONTRACT_VIOLATION,
                    "reason": ChunkingV2ErrorReason.MANIFEST_INCONSISTENT_WITH_SEGMENTS,
                },
            )

    # ── Phase 14.4: snapshot old artifact refs for post-commit cleanup ────────
    old_chunk_refs: list[str] = []
    old_legal_units_refs: list[str] = []
    old_enrichment_refs: list[str] = []
    try:
        for seg in segments:
            old_chunks_ref = getattr(seg, "segment_chunks_ref", None)
            if old_chunks_ref:
                old_chunk_refs.append(old_chunks_ref)

            old_meta = getattr(seg, "segment_meta", None) or {}
            old_lu_ref = old_meta.get("legal_units_ref")
            if old_lu_ref:
                old_legal_units_refs.append(old_lu_ref)
            old_enr_ref = old_meta.get("legal_units_enrichment_ref")
            if old_enr_ref:
                old_enrichment_refs.append(old_enr_ref)
    except Exception as _snap_exc:
        logger.debug(
            "Chunk builder: failed to snapshot old artifact refs (non-critical)",
            document_id=str(doc.id),
            error=str(_snap_exc),
        )


    await seg_repo.replace_segments(
        document_version_id=v_id,
        items=segment_rows_to_replace,
    )

    manifest_path = ArtifactPath.chunks_manifest_v2(
        tenant_id=tenant_id,
        deal_id=deal_id,
        document_id=str(doc.id),
    )

    try:
        chunks_manifest_v2_ref = store.put_json(manifest_path, file_manifest.to_dict())
    except Exception as e:
        logger.exception(
            "Failed to store file chunk manifest v2",
            document_id=str(doc.id),
            document_version_id=str(v_id),
            manifest_path=manifest_path,
            error=str(e),
        )
        raise PermanentError(
            f"Failed to store file chunk manifest v2: {e}",
            details={
                "stage": "chunking_v2",
                "type": PipelineErrorType.CHUNKING_V2_CONTRACT_VIOLATION,
                "reason": ChunkingV2ErrorReason.MANIFEST_STORE_ERROR,
            },
        )

    updated_version = await ver_repo.update_refs(
        version_id=v_id,
        chunks_manifest_v2_ref=chunks_manifest_v2_ref,
    )
    if not updated_version:
        raise PermanentError(
            f"Failed to update chunks_manifest_v2_ref for version {v_id}",
            details={
                "stage": "chunking_v2",
                "type": PipelineErrorType.CHUNKING_V2_CONTRACT_VIOLATION,
                "reason": ChunkingV2ErrorReason.VERSION_UPDATE_FAILED,
            },
        )

    updated_doc = await doc_repo.update_status(
        doc.id,
        DocumentStatus.CHUNKED.value,
        processing_error_details=None,
    )
    if not updated_doc:
        raise PermanentError(
            f"Failed to update document status to CHUNKED for doc {doc.id}",
            details={
                "stage": "chunking_v2",
                "type": PipelineErrorType.CHUNKING_V2_CONTRACT_VIOLATION,
                "reason": ChunkingV2ErrorReason.DOCUMENT_STATUS_UPDATE_FAILED,
            },
        )

    await uow.session.flush()

    refreshed_version = await ver_repo.get_by_id(v_id)
    if not refreshed_version:
        raise TransientError(f"DocumentVersion {v_id} is not visible after flush (v2)")

    refreshed_manifest_ref = getattr(refreshed_version, "chunks_manifest_v2_ref", None)
    if not refreshed_manifest_ref:
        raise TransientError(
            f"chunks_manifest_v2_ref is not visible after flush for version {v_id}"
        )

    if refreshed_manifest_ref != chunks_manifest_v2_ref:
        raise TransientError(f"chunks_manifest_v2_ref mismatch after flush for version {v_id}")

    refreshed_segments = await seg_repo.list_by_version(v_id)
    if len(refreshed_segments) != len(segments):
        raise TransientError(
            "document_segments count mismatch after flush "
            f"for version {v_id}: expected={len(segments)}, actual={len(refreshed_segments)}"
        )

    missing_segment_chunk_refs = [
        s.segment_id for s in refreshed_segments if not getattr(s, "segment_chunks_ref", None)
    ]
    if missing_segment_chunk_refs:
        raise TransientError(
            "segment_chunks_ref missing after flush "
            f"for version {v_id}: missing_segment_ids={missing_segment_chunk_refs}"
        )

    await uow.session.commit()

    # ── Phase 14.4: post-commit cleanup stale chunk/legal/enrichment artifacts ─
    current_chunk_refs: set[str] = set()
    current_lu_refs: set[str] = set()
    current_enr_refs: set[str] = set()

    for row in segment_rows_to_replace:
        chunks_ref = row.get("segment_chunks_ref")
        if chunks_ref:
            current_chunk_refs.add(chunks_ref)
        meta = row.get("segment_meta") or {}
        lu_ref = meta.get("legal_units_ref")
        if lu_ref:
            current_lu_refs.add(lu_ref)
        enr_ref = meta.get("legal_units_enrichment_ref")
        if enr_ref:
            current_enr_refs.add(enr_ref)

    stale_all: list[str] = []
    stale_all.extend(r for r in old_chunk_refs if r not in current_chunk_refs)
    stale_all.extend(r for r in old_legal_units_refs if r not in current_lu_refs)
    stale_all.extend(r for r in old_enrichment_refs if r not in current_enr_refs)
    stale_all = list(dict.fromkeys(stale_all))  # deduplicate, preserve order

    if stale_all:
        try:
            cleanup_result = store.delete_many_best_effort(stale_all)
            logger.info(
                "Chunk builder: post-commit cleanup stale artifacts",
                document_id=str(doc.id),
                stale_count=len(stale_all),
                deleted=cleanup_result.get("deleted", 0),
                failed=cleanup_result.get("failed", 0),
            )
        except Exception as _cleanup_exc:
            logger.warning(
                "Chunk builder: post-commit cleanup failed (non-critical)",
                document_id=str(doc.id),
                error=str(_cleanup_exc),
            )

    # ── Phase 14.4: write artifact manifest best-effort ──────────────────────
    try:
        from storage._artifact_manifest import write_artifact_manifest_best_effort

        manifest_segment_refs = []
        for row in segment_rows_to_replace:
            meta = row.get("segment_meta") or {}
            manifest_segment_refs.append({
                "segment_id": row.get("segment_id", ""),
                "segment_clause_tree_ref": row.get("segment_clause_tree_ref"),
                "segment_chunks_ref": row.get("segment_chunks_ref"),
                "legal_units_ref": meta.get("legal_units_ref"),
                "legal_units_enrichment_ref": meta.get("legal_units_enrichment_ref"),
            })

        # Для clause_tree_ref и file_graph_ref берём из version,
        # т.к. chunk_builder их не меняет.
        write_artifact_manifest_best_effort(
            store=store,
            tenant_id=tenant_id,
            deal_id=deal_id,
            document_id=str(doc.id),
            document_version_id=str(v_id),
            clause_tree_ref=getattr(version, "clause_tree_ref", None),
            file_graph_ref=getattr(version, "file_graph_ref", None),
            chunk_plan_ref=getattr(version, "chunk_plan_ref", None),
            chunks_manifest_v2_ref=chunks_manifest_v2_ref,
            segment_refs=manifest_segment_refs,
            stage="chunking",
            extra={
                "chunk_count_total": chunk_count_total,
                "legal_units_saved_count": legal_units_saved_count,
                "enrichment_saved_count": enrichment_saved_count,
            },
        )
    except Exception as _manifest_exc:
        logger.warning(
            "Chunk builder: failed to write artifact manifest (non-critical)",
            document_id=str(doc.id),
            error=str(_manifest_exc),
        )

    duration = round(time.time() - start, 2)

    # ── Phase 13.1 + 13.2: telemetry summary — строим ДО audit log ───────────
    # doc_summary нужен в audit details, поэтому строим его первым.
    doc_summary = None
    try:
        doc_summary = telemetry_collector.build_document_summary()
        logger.info(
            "TELEMETRY document_processed",
            document_id=str(doc.id),
            document_version_id=str(v_id),
            total_segments=doc_summary.total_segments,
            total_chunks=doc_summary.total_chunks,
            legal_unit_chunks=doc_summary.legal_unit_chunks,
            retrieval_safe_chunks=doc_summary.retrieval_safe_chunks,
            enrichment_total_units=doc_summary.total_units,
            avg_orphan_ratio=doc_summary.avg_orphan_ratio,
            avg_retrieval_safety_score=doc_summary.avg_retrieval_safety_score,
            enrichment_applied_count=doc_summary.enrichment_applied_count,
            enrichment_failed_count=doc_summary.enrichment_failed_count,
            enrichment_llm_unavailable=doc_summary.enrichment_llm_unavailable,
            overall_retrieval_safe=doc_summary.overall_retrieval_safe,
            recommended_action=doc_summary.recommended_action,
            elapsed_ms=doc_summary.elapsed_ms,
        )

        if (
            doc_summary.total_chunks != chunk_count_total
            or doc_summary.legal_unit_chunks != legal_unit_chunk_count_total
            or doc_summary.retrieval_safe_chunks > doc_summary.total_chunks
        ):
            logger.warning(
                "TELEMETRY aggregation_invariant_violation",
                document_id=str(doc.id),
                document_version_id=str(v_id),
                chunk_count_total=chunk_count_total,
                summary_total_chunks=doc_summary.total_chunks,
                legal_unit_chunk_count_total=legal_unit_chunk_count_total,
                summary_legal_unit_chunks=doc_summary.legal_unit_chunks,
                summary_retrieval_safe_chunks=doc_summary.retrieval_safe_chunks,
                chunking_events_count=len(segment_snapshots),
            )
    except Exception as _tel_exc:
        logger.debug(
            "Chunk builder: telemetry summary failed (non-critical)",
            document_id=str(doc.id),
            error=str(_tel_exc),
        )

    # ── CHUNK_BUILD_COMPLETED audit — после summary, т.к. включает его ───────
    try:
        await audit_repo.log(
            tenant_id=tenant_uuid,
            deal_id=deal_uuid,
            action="CHUNK_BUILD_COMPLETED",
            actor="system",
            actor_role="worker",
            details={
                "document_id": str(doc.id),
                "document_version_id": str(v_id),
                "stage_execution_id": stage_execution_id,
                "chunks_manifest_v2_ref": chunks_manifest_v2_ref,
                "segments_count": len(segment_snapshots),
                "chunk_count_total": chunk_count_total,
                "duration_seconds": duration,
                "run_id": run_id,
                # ── Этап 5 ───────────────────────────────────────────────────
                "legal_units_saved_count": legal_units_saved_count,
                "legal_units_refs": legal_units_refs,
                "enrichment_saved_count": enrichment_saved_count,
                "enrichment_refs": enrichment_refs,
                # ── Phase 13.2: telemetry summary для future temporal drift ──
                # Сохраняем всегда — даже если drift alerts нет.
                # Это накапливает historical baseline для следующего уровня.
                "telemetry_summary": (
                    doc_summary.to_dict() if doc_summary is not None else None
                ),
            },
        )
    except Exception:
        logger.warning(
            "Chunk builder: failed to write audit log for CHUNK_BUILD_COMPLETED",
            document_id=str(doc.id),
            document_version_id=str(v_id),
            stage_execution_id=stage_execution_id,
        )

    # ── Phase 13.2: Drift Detection — один раз, после всех сегментов ─────────
    # Запускается только если telemetry summary успешно построен.
    # Non-blocking: любая ошибка логируется и игнорируется.
    if doc_summary is not None:
        try:
            from services.telemetry._drift import DriftDetector

            drift_detector = DriftDetector()
            drift_report = drift_detector.check(doc_summary)

            if drift_report.has_alerts:
                logger.warning(
                    "DRIFT processing_degradation_detected",
                    document_id=str(doc.id),
                    document_version_id=str(v_id),
                    has_critical=drift_report.has_critical,
                    alert_count=drift_report.alert_count,
                    critical_count=drift_report.critical_count,
                    warning_count=drift_report.warning_count,
                    alerts=[a.to_dict() for a in drift_report.alerts],
                )

                # Persist drift alert — отдельный UoW, т.к. основной uow
                # уже закрыт после commit выше.
                try:
                    async with db_uow() as uow_drift:
                        drift_audit_repo = AuditRepository(uow_drift.session)
                        await drift_audit_repo.log(
                            tenant_id=tenant_uuid,
                            deal_id=deal_uuid,
                            action="PROCESSING_DEGRADATION_ALERT",
                            actor="system",
                            actor_role="drift_detector",
                            details={
                                "document_id": str(doc.id),
                                "document_version_id": str(v_id),
                                "run_id": run_id,
                                "has_critical": drift_report.has_critical,
                                "alert_count": drift_report.alert_count,
                                "critical_count": drift_report.critical_count,
                                "warning_count": drift_report.warning_count,
                                "alerts": [
                                    a.to_dict() for a in drift_report.alerts
                                ],
                                "document_summary": doc_summary.to_dict(),
                            },
                        )
                        await uow_drift.session.commit()
                except Exception as _drift_audit_exc:
                    logger.warning(
                        "DRIFT failed to persist alert to audit log (non-critical)",
                        document_id=str(doc.id),
                        error=str(_drift_audit_exc),
                    )

        except Exception as _drift_exc:
            logger.warning(
                "DRIFT detector_failed (non-critical)",
                document_id=str(doc.id),
                error=str(_drift_exc),
            )

    logger.info(
        "Segment chunks and file manifest v2 built and committed successfully",
        document_id=str(doc.id),
        document_version_id=str(v_id),
        chunks_manifest_v2_ref=chunks_manifest_v2_ref,
        segments_count=len(segment_snapshots),
        chunk_count_total=chunk_count_total,
        duration_seconds=duration,
        status=DocumentStatus.CHUNKED.value,
        legal_units_saved_count=legal_units_saved_count,
        legal_units_count=len(legal_units_refs),
    )

    _trace = build_stage_trace_fragment(
        strategy="segment_chunk_builder_v2",
        input_summary={
            "document_id": str(doc.id),
            "document_version_id": str(v_id),
            "segments_count": len(segment_snapshots),
            "chunk_plan_available": chunk_plan is not None,
        },
        output_summary={
            "chunk_count_total": chunk_count_total,
            "legal_units_count": len(legal_units_refs),
            "enrichment_count": len(enrichment_refs),
            "legal_unit_chunks": legal_unit_chunk_count_total,
            "duration_seconds": duration,
        },
        warnings=(
            ["retrieval_not_fully_safe"]
            if (doc_summary is not None and not doc_summary.overall_retrieval_safe)
            else []
        ),
        artifact_refs={
            "chunks_manifest_v2_ref": chunks_manifest_v2_ref,
        },
        decision_details={
            "telemetry_summary": doc_summary.to_dict() if doc_summary is not None else None,
        },
    )

    if stage_execution_id:
        try:
            await dse_repo.mark_succeeded(
                uuid.UUID(stage_execution_id),
                result_details=_trace,
            )
        except Exception as e:
            logger.exception(
                "Failed to mark stage execution as SUCCEEDED for chunking",
                document_version_id=document_version_id,
                stage_execution_id=stage_execution_id,
                error=str(e),
            )

    return {
        "status": DocumentStatus.CHUNKED.value,
        "document_id": str(doc.id),
        "document_version_id": str(v_id),
        "chunks_manifest_v2_ref": chunks_manifest_v2_ref,
        "segments_count": len(segment_snapshots),
        "chunk_count_total": chunk_count_total,
        "duration_seconds": duration,
        "tenant_id": tenant_id,
        "committed": True,
        "legal_units_refs": legal_units_refs,
        "legal_units_count": len(legal_units_refs),
        "enrichment_refs": enrichment_refs,
        "enrichment_count": len(enrichment_refs),
        "stage_execution_result_details": _trace,
    }


async def _mark_quarantined(
    uow: UnitOfWork,
    document_uuid: uuid.UUID,
    tenant_uuid: uuid.UUID,
    deal_uuid: uuid.UUID,
    *,
    message: str,
    reason: str,
    run_id: uuid.UUID | None,
    stage_execution_id: str | None,
    document_version_id: str,
) -> None:
    """
    Перевести документ в карантин на стадии chunking.
    """
    doc_repo = DocumentRepository(uow.session)
    dse_repo = DocumentStageExecutionRepository(uow.session)
    audit_repo = AuditRepository(uow.session)

    await doc_repo.set_quarantined(
        document_uuid,
        stage="chunking",
        message=message,
        reason=reason,
        run_id=run_id,
    )

    try:
        await audit_repo.log(
            tenant_id=tenant_uuid,
            deal_id=deal_uuid,
            action="CHUNK_BUILD_QUARANTINED",
            actor="system",
            actor_role="worker",
            details={
                "document_id": str(document_uuid),
                "document_version_id": document_version_id,
                "stage_execution_id": stage_execution_id,
                "stage": "chunking_v2",
                "reason": reason,
                "message": message,
                "run_id": str(run_id) if run_id else None,
            },
        )
    except Exception:
        logger.warning(
            "Chunk builder: failed to write audit log for CHUNK_BUILD_QUARANTINED",
            document_uuid=str(document_uuid),
            document_version_id=document_version_id,
            stage_execution_id=stage_execution_id,
        )

    if stage_execution_id:
        try:
            await dse_repo.mark_failed(
                uuid.UUID(stage_execution_id),
                error_details={
                    "stage": "chunking_v2",
                    "type": "chunking_quarantine",
                    "reason": reason,
                    "message": message,
                    "document_uuid": str(document_uuid),
                    "document_version_id": document_version_id,
                },
            )
        except Exception as e:
            logger.exception(
                "Failed to mark stage execution as FAILED(quarantine) for chunking",
                document_uuid=str(document_uuid),
                document_version_id=document_version_id,
                stage_execution_id=stage_execution_id,
                error=str(e),
            )


async def _mark_failed(
    uow: UnitOfWork,
    document_uuid: uuid.UUID,
    tenant_uuid: uuid.UUID,
    deal_uuid: uuid.UUID,
    *,
    message: str,
    run_id: uuid.UUID | None,
    stage_execution_id: str | None,
    document_version_id: str,
    reason_code: str,
) -> None:
    """
    Best-effort перевод документа в FAILED при ошибке chunking.
    """
    doc_repo = DocumentRepository(uow.session)
    dse_repo = DocumentStageExecutionRepository(uow.session)
    audit_repo = AuditRepository(uow.session)

    await doc_repo.set_failed(
        document_uuid,
        stage="chunking",
        message=message,
        reason=PipelineErrorType.CHUNKING_V2_CONTRACT_VIOLATION,
        run_id=run_id,
    )

    try:
        await audit_repo.log(
            tenant_id=tenant_uuid,
            deal_id=deal_uuid,
            action="CHUNK_BUILD_FAILED",
            actor="system",
            actor_role="worker",
            details={
                "document_id": str(document_uuid),
                "document_version_id": document_version_id,
                "stage_execution_id": stage_execution_id,
                "stage": "chunking_v2",
                "reason_code": reason_code,
                "message": message,
                "run_id": str(run_id) if run_id else None,
                "error_type": PipelineErrorType.CHUNKING_V2_CONTRACT_VIOLATION,
            },
        )
    except Exception:
        logger.warning(
            "Chunk builder: failed to write audit log for CHUNK_BUILD_FAILED",
            document_uuid=str(document_uuid),
            document_version_id=document_version_id,
            stage_execution_id=stage_execution_id,
        )

    if stage_execution_id:
        try:
            await dse_repo.mark_failed(
                uuid.UUID(stage_execution_id),
                error_details={
                    "stage": "chunking_v2",
                    "type": PipelineErrorType.CHUNKING_V2_CONTRACT_VIOLATION,
                    "reason": reason_code,
                    "message": message,
                    "document_uuid": str(document_uuid),
                    "document_version_id": document_version_id,
                },
            )
        except Exception as e:
            logger.exception(
                "Failed to mark stage execution as FAILED for chunking",
                document_uuid=str(document_uuid),
                document_version_id=document_version_id,
                stage_execution_id=stage_execution_id,
                error=str(e),
            )
