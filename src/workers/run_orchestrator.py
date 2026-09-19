"""
Run Orchestrator Worker (Phase 9).

Отвечает за координацию и планирование переходов стадий на уровне документа.

В архитектуре v2 (DOCUMENT_LAYOUT_V2_ENABLED = True):
- Считывает ссылки на макеты (layout_primary_ref, layout_primary_sanitized_ref)
  не из DocumentVersion, а из run-scoped таблицы document_run_language_resolution.
- Проверяет индивидуальную доступность целевого языка (eligibility check) для документа.
- Применяет missing_target_language_policy при отсутствии целевого языка.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.constants import DocumentStageExecutionStatus, DocumentStatus, RunStatus
from core.exceptions import TransientError
from core.logging import get_logger
from core.pipeline_snapshots import (
    DocumentSnapshot,
    RunSnapshot,
    VersionSnapshot,
    snapshot_document,
    snapshot_run,
    snapshot_version,
)
from services.document_layout.config import layout_config
from db.repositories.audit_repo import AuditRepository
from db.repositories.deal_repo import DealRepository
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_segment_repo import DocumentSegmentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.repositories.document_stage_execution_repo import DocumentStageExecutionRepository
from db.repositories.run_repo import RunRepository
from db.repositories.document_run_language_resolution_repo import (
    DocumentRunLanguageResolutionRepository,
)
from db.uow import db_uow
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from mas_queue.task_dispatcher import send_task_with_context
from services.run_checks_auto_starter import maybe_start_run_checks

logger = get_logger(__name__)

CONVERTIBLE_TO_PDF: set[str] = {
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "odt",
    "ods",
    "odp",
    "rtf",
    "csv",
    "html",
    "htm",
}

ORCHESTRATION_STRATEGY_V2_ONLY = "V2_ONLY"
_ZERO_UUID = uuid.UUID(int=0)


def _is_non_zero_uuid_str(value: str | None) -> bool:
    if not value:
        return False
    try:
        return uuid.UUID(value) != _ZERO_UUID
    except (ValueError, TypeError, AttributeError):
        return False


# ─── TaskPlan ─────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class TaskPlan:
    task_name: str
    kwargs: dict[str, Any]
    reason: str
    stage: str


# ─── Segment helpers ──────────────────────────────────────────────────────────


def _is_multi_document_snapshot(snap: VersionSnapshot) -> bool:
    return bool(snap.segments_count and snap.segments_count > 1)


async def _count_relevant_segments(
    seg_repo: DocumentSegmentRepository,
    version_id: uuid.UUID,
) -> int:
    return await seg_repo.count_by_version_and_has_segment_id(version_id)


async def _count_unclassified_segments(
    seg_repo: DocumentSegmentRepository,
    version_id: uuid.UUID,
) -> int:
    return await seg_repo.count_unclassified_for_version(version_id)


async def _is_segment_classification_complete(
    seg_repo: DocumentSegmentRepository,
    snap: VersionSnapshot,
) -> bool:
    if not _is_multi_document_snapshot(snap):
        return True

    total = await _count_relevant_segments(seg_repo, snap.version_id)
    if total == 0:
        return True

    unclassified = await _count_unclassified_segments(seg_repo, snap.version_id)
    return unclassified == 0


# NOTE: Функция _can_start_checks_for_run удалена в рамках race-condition фикса.
# Ранее вычислялась, но результат нигде не использовался (dead code).
# Решение "готов ли документ к проверкам" теперь принимается точечно
# в двух авторитетных местах:
#   1) build_legal_units_enrichment — после commit enrichment для документа.
#   2) run_orchestrator — для документов, для которых НЕ запланирована
#      ни одна новая стадия в текущем run.


# ─── Celery task entrypoint ───────────────────────────────────────────────────


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.start_run_pipeline",
    track_job=False,
    queue="default",
)
def start_run_pipeline(
    self,
    run_id: str,
    deal_id: str | None = None,
    tenant_id: str | None = None,
    force_reclassify: bool = False,
    stage_execution_id: str | None = None,
    orchestration_strategy: str | None = None,
    **kwargs: Any,
) -> dict:
    """
    Sync Celery entrypoint для оркестрации Run.
    """

    async def _wrapper() -> dict:
        async with db_uow() as uow:
            return await _start_run_pipeline_async(
                run_id=run_id,
                deal_id=deal_id,
                tenant_id=tenant_id,
                force_reclassify=force_reclassify,
                db=uow.session,
            )

    try:
        from mas_queue.async_helpers import run_async
        return run_async(_wrapper())
    except SoftTimeLimitExceeded as exc:
        raise TransientError(
            "Task 'workers.start_run_pipeline' exceeded soft time limit"
        ) from exc


# ─── Tenant resolver ──────────────────────────────────────────────────────────


async def _resolve_tenant_id(
    tenant_id: str | None,
    deal_uuid: uuid.UUID,
    db: AsyncSession,
) -> str:
    if _is_non_zero_uuid_str(tenant_id):
        return str(uuid.UUID(tenant_id))

    deal_repo = DealRepository(db)
    deal_obj = await deal_repo.internal_unsafe_get_by_id(deal_uuid)
    deal_tenant_id = getattr(deal_obj, "tenant_id", None) if deal_obj is not None else None

    if deal_tenant_id and deal_tenant_id != _ZERO_UUID:
        resolved = str(deal_tenant_id)
        return resolved

    raise ValueError(
        f"Cannot resolve tenant_id for deal {deal_uuid}: "
        "neither task kwargs nor deal.tenant_id provided valid tenant"
    )


# ─── Async core ───────────────────────────────────────────────────────────────


async def _start_run_pipeline_async(
    run_id: str,
    deal_id: str | None,
    tenant_id: str | None,
    force_reclassify: bool,
    db: AsyncSession,
) -> dict:
    logger.info(
        "Starting run pipeline",
        run_id=run_id,
        deal_id=deal_id,
        tenant_id=tenant_id,
        force_reclassify=force_reclassify,
    )

    run_repo = RunRepository(db)
    doc_repo = DocumentRepository(db)
    ver_repo = DocumentVersionRepository(db)
    res_repo = DocumentRunLanguageResolutionRepository(db)
    dse_repo = DocumentStageExecutionRepository(db)
    audit_repo = AuditRepository(db)

    run_uuid = uuid.UUID(run_id)
    run_obj = await run_repo.get_by_id(run_uuid)

    if run_obj is None:
        logger.error("Run not found for orchestrator", run_id=run_id)
        return {
            "run_id": run_id,
            "deal_id": None,
            "tenant_id": tenant_id,
            "documents_total": 0,
            "tasks_scheduled": 0,
            "documents_with_plan": 0,
        }

    run_snap = snapshot_run(run_obj)
    current_status = run_snap.status

    if current_status == RunStatus.PENDING.value:
        started = await run_repo.try_start_run(run_uuid)
        if not started:
            run_obj = await run_repo.get_by_id(run_uuid)
            if run_obj is not None:
                run_snap = snapshot_run(run_obj)
                current_status = run_snap.status
            else:
                current_status = None

            if current_status != RunStatus.RUNNING.value:
                return {
                    "run_id": run_id,
                    "deal_id": run_snap.deal_id_str,
                    "tenant_id": tenant_id,
                    "documents_total": 0,
                    "tasks_scheduled": 0,
                    "documents_with_plan": 0,
                }
        else:
            if run_snap.tenant_id is not None:
                try:
                    await audit_repo.log(
                        tenant_id=run_snap.tenant_id,
                        deal_id=run_snap.deal_id,
                        action="ANALYSIS_STARTED",
                        actor="system",
                        actor_role="worker",
                        details={
                            "run_id": run_id,
                            "deal_id": run_snap.deal_id_str,
                            "pipeline_strategy": run_snap.pipeline_strategy,
                            "force_reclassify": force_reclassify,
                        },
                    )
                except Exception:
                    pass

    elif current_status in {
        RunStatus.COMPLETED.value,
        RunStatus.COMPLETED_WITH_ERRORS.value,
        RunStatus.FAILED.value,
    }:
        return {
            "run_id": run_id,
            "deal_id": run_snap.deal_id_str,
            "tenant_id": tenant_id,
            "documents_total": 0,
            "tasks_scheduled": 0,
            "documents_with_plan": 0,
        }

    pipeline_strategy = run_snap.pipeline_strategy or "REUSE_STRUCTURE"
    is_full_rerun = pipeline_strategy == "FULL_RERUN"

    deal_uuid = run_snap.deal_id if run_snap.deal_id else (uuid.UUID(deal_id) if deal_id else None)
    if deal_uuid is None:
        await run_repo.update_status(
            run_uuid,
            RunStatus.FAILED.value,
            error_details={
                "stage": "orchestrator",
                "type": "config_error",
                "reason": "deal_not_bound",
                "message": f"Run {run_id} has no deal_id",
            },
        )
        return {
            "run_id": run_id,
            "deal_id": None,
            "tenant_id": tenant_id,
            "documents_total": 0,
            "tasks_scheduled": 0,
            "documents_with_plan": 0,
        }

    deal_id_str = str(deal_uuid)
    tenant_id_str = await _resolve_tenant_id(
        tenant_id=tenant_id,
        deal_uuid=deal_uuid,
        db=db,
    )

    deal_repo = DealRepository(db)
    deal = await deal_repo.internal_unsafe_get_by_id(deal_uuid)
    if deal is None:
        return {
            "run_id": run_id,
            "deal_id": deal_id_str,
            "tenant_id": tenant_id_str,
            "documents_total": 0,
            "tasks_scheduled": 0,
            "documents_with_plan": 0,
        }

    deal_primary_language: str | None = getattr(deal, "primary_language", None)
    deal_language_discovery_status: str | None = getattr(deal, "language_discovery_status", None)
    deal_languages: list[str] | None = getattr(deal, "languages", None)

    if not deal_primary_language:
        return {
            "run_id": run_id,
            "deal_id": deal_id_str,
            "tenant_id": tenant_id_str,
            "documents_total": 0,
            "tasks_scheduled": 0,
            "documents_with_plan": 0,
            "blocked_reason": "primary_language_not_selected",
        }

    docs = await doc_repo.get_by_deal(deal_uuid)
    if not docs:
        await run_repo.update_status(run_uuid, RunStatus.COMPLETED.value)
        return {
            "run_id": run_id,
            "deal_id": deal_id_str,
            "tenant_id": tenant_id_str,
            "documents_total": 0,
            "tasks_scheduled": 0,
            "documents_with_plan": 0,
        }

    doc_snaps: list[DocumentSnapshot] = [snapshot_document(doc) for doc in docs]
    documents_total = len(doc_snaps)

    tasks_scheduled = 0
    documents_with_plan = 0
    seg_repo = DocumentSegmentRepository(db)

    # Мастер-переключатель V2
    v2_enabled = getattr(settings, "DOCUMENT_LAYOUT_V2_ENABLED", False) or layout_config.document_layout_v2_enabled
    policy = run_snap.missing_target_language_policy or "BLOCK_DOCUMENT_CONTINUE_RUN"

    scheduled_document_ids: set[uuid.UUID] = set()

    for doc_snap in doc_snaps:
        doc_id: uuid.UUID = doc_snap.document_id
        doc_id_str = doc_snap.document_id_str
        status: str = doc_snap.status

        version = await ver_repo.get_latest(doc_id)
        if version is None:
            continue

        ver_snap = snapshot_version(version)

        # ─── V2 Eligibility & Run-scoped Resolution lookup ───────────────────
        if v2_enabled and status != DocumentStatus.PENDING.value:
            res_record = await res_repo.get_by_run_and_version(run_uuid, ver_snap.version_id)

            if not res_record:
                status = DocumentStatus.PENDING.value
            else:
                if res_record.resolution_status == "LANGUAGE_RESOLVING":
                    logger.info("V2: Resolution is resolving, waiting", run_id=run_id, document_id=doc_id_str)
                    continue

                elif res_record.resolution_status == "LANGUAGE_UNAVAILABLE":
                    if policy == "FAIL_RUN_IF_ANY_DOCUMENT_MISSING_LANGUAGE":
                        logger.error(
                            "V2: Run failed by policy: target language missing",
                            document_id=doc_id_str,
                            run_id=run_id,
                        )
                        await run_repo.mark_run_failed(
                            run_uuid,
                            f"Run policy blocked execution: target language missing for document {doc_id_str}",
                        )
                        return {
                            "run_id": run_id,
                            "deal_id": deal_id_str,
                            "tenant_id": tenant_id_str,
                            "documents_total": documents_total,
                            "tasks_scheduled": tasks_scheduled,
                            "documents_with_plan": documents_with_plan,
                        }
                    logger.info("V2: Skipping ineligible document by run policy", document_id=doc_id_str)
                    continue

                elif res_record.resolution_status == "LANGUAGE_READY":
                    ver_snap = VersionSnapshot(
                        id=ver_snap.id,
                        origin_filetype=ver_snap.origin_filetype,
                        original_ref=ver_snap.original_ref,
                        converted_pdf_ref=ver_snap.converted_pdf_ref,
                        canonical_layout_ref=res_record.canonical_layout_ref,
                        detected_languages=tuple(res_record.available_languages) if res_record.available_languages else (),
                        layout_primary_ref=res_record.layout_primary_ref,
                        layout_primary_sanitized_ref=res_record.layout_primary_sanitized_ref,
                        file_graph_ref=ver_snap.file_graph_ref,
                        chunks_manifest_v2_ref=ver_snap.chunks_manifest_v2_ref,
                        segments_count=ver_snap.segments_count,
                        text_layout_raw_ref=ver_snap.text_layout_raw_ref,
                        pipeline_strategy=ver_snap.pipeline_strategy,
                        extraction_strategy=ver_snap.extraction_strategy,
                        ocr_confidence=ver_snap.ocr_confidence,
                    )

        plan = await _build_document_task_plan(
            doc_id_str=doc_id_str,
            snap=ver_snap,
            status=status,
            run_id=run_id,
            deal_id_str=deal_id_str,
            tenant_id_str=tenant_id_str,
            is_full_rerun=is_full_rerun,
            force_reclassify=force_reclassify,
            seg_repo=seg_repo,
            deal_primary_language=deal_primary_language,
            doc_snap=doc_snap,
        )

        if plan is None:
            continue

        orchestration_strategy = ORCHESTRATION_STRATEGY_V2_ONLY

        execution = await dse_repo.create_planned_or_none_on_conflict(
            run_id=run_uuid,
            document_id=doc_id,
            document_version_id=ver_snap.version_id,
            from_status=status,
            to_status=_target_status_for_stage(plan.stage),
            orchestration_strategy=orchestration_strategy,
            task_name=plan.task_name,
        )

        if execution is None:
            continue

        execution_id_str = str(execution.id)
        await db.flush()
        await db.commit()

        try:
            celery_task_id = _send_task(
                plan=plan,
                stage_execution_id=execution_id_str,
                run_id=run_id,
                deal_id=deal_id_str,
                tenant_id=tenant_id_str,
                document_id=doc_id_str,
                document_version_id=ver_snap.version_id_str,
                orchestration_strategy=orchestration_strategy,
            )
        except Exception as send_exc:
            try:
                await dse_repo.mark_failed(
                    execution.id,
                    error_details={
                        "stage": plan.stage,
                        "type": "dispatch_failed",
                        "reason": "send_task_exception",
                        "message": str(send_exc),
                        "run_id": run_id,
                    },
                )
                await db.flush()
                await db.commit()
            except Exception:
                pass
            raise TransientError(
                f"Failed to dispatch stage task '{plan.task_name}' for document {doc_id_str}"
            ) from send_exc

        await dse_repo.mark_dispatched(execution.id, celery_task_id=celery_task_id)
        await db.flush()
        await db.commit()

        scheduled_document_ids.add(doc_id)
        tasks_scheduled += 1
        documents_with_plan += 1

    # ─── Инкрементальный запуск проверок ─────────────────────────────────────
    from services.run_checks_auto_starter import start_checks_for_document
    from db.models.document import DocumentStageExecution
    from sqlalchemy import func

    documents_triggered = 0
    for doc_snap in doc_snaps:
        if doc_snap.document_id in scheduled_document_ids:
            continue

        if doc_snap.status not in {
            DocumentStatus.ENRICHED.value,
            DocumentStatus.COMPLETED.value,
        }:
            continue

        if not getattr(doc_snap, "doc_type", None):
            continue

        # ── Защита от повторных запусков оркестратора (Гонка быстрых стадий) ──
        # Проверяем в БД, нет ли уже активных (planned, dispatched, started) стадий
        # для этого документа в рамках текущего run. Это защищает от ситуации,
        # когда быстрый документ триггерит оркестратор заново, а медленный
        # документ всё ещё выполняет свои стадии (и в БД его статус по-прежнему
        # "enriched", но задачи для него уже запущены).
        active_exec_stmt = select(func.count()).select_from(DocumentStageExecution).where(
            DocumentStageExecution.run_id == run_uuid,
            DocumentStageExecution.document_id == doc_snap.document_id,
            DocumentStageExecution.status.in_([
                DocumentStageExecutionStatus.PLANNED.value,
                DocumentStageExecutionStatus.DISPATCHED.value,
                DocumentStageExecutionStatus.STARTED.value,
            ])
        )
        active_exec_res = await db.execute(active_exec_stmt)
        active_exec_count = int(active_exec_res.scalar_one() or 0)
        if active_exec_count > 0:
            logger.info(
                "Run checks: skipping direct orchestrator dispatch — "
                "document has active stage executions in current run",
                run_id=run_id,
                document_id=doc_snap.document_id_str,
                active_stages_count=active_exec_count,
            )
            continue

        triggered = await start_checks_for_document(
            db=db,
            run_id=run_snap.run_id,
            document_id=doc_snap.document_id,
        )
        if triggered:
            documents_triggered += 1

    if documents_triggered > 0:
        logger.info(
            "Run checks: orchestrator dispatched checks for documents without new stages",
            run_id=run_id,
            documents_triggered=documents_triggered,
            documents_with_new_stages=len(scheduled_document_ids),
        )
    else:
        logger.debug(
            "Run checks: no documents ready for direct orchestrator dispatch",
            run_id=run_id,
            documents_with_new_stages=len(scheduled_document_ids),
        )
        
    # ── FINALIZE TRIGGER ──────────────────────────────────────────────
    # Orchestrator завершил планирование. Если он не запланировал ни одной
    # новой стадии и не запустил проверок — это единственный момент, когда
    # он ТОЧНО знает, что больше работы по этому run у него нет.
    # Триггерим finalize, чтобы он перепроверил готовность с новым guard'ом
    # (по Document.status) и закрыл run, если pipeline действительно завершён.
    #
    # Это второй, независимый механизм финализации. Первый —
    # base_task._enqueue_finalize_if_needed — остаётся как safety net.
    # Здесь мы даём точный сигнал из правильного места.
    if tasks_scheduled == 0 and documents_triggered == 0:
        try:
            from mas_queue.task_dispatcher import send_task_with_context  # noqa: PLC0415
            send_task_with_context(
                "workers.finalize_run_if_ready",
                kwargs={
                    "run_id": run_id,
                    "tenant_id": tenant_id_str,
                },
            )
            logger.info(
                "Orchestrator: no more work planned, triggered finalize",
                run_id=run_id,
                documents_total=documents_total,
            )
        except Exception as exc:  # noqa: BLE001
            # Non-fatal: если Celery недоступен — stale_reaper восстановит.
            logger.warning(
                "Orchestrator: failed to trigger finalize (non-fatal)",
                run_id=run_id,
                error=str(exc),
            )
    # ── КОНЕЦ FINALIZE TRIGGER ────────────────────────────────────────


    return {
        "run_id": run_id,
        "deal_id": deal_id_str,
        "tenant_id": tenant_id_str,
        "documents_total": documents_total,
        "tasks_scheduled": tasks_scheduled,
        "documents_with_plan": documents_with_plan,
    }


# ─── Stage mapping ────────────────────────────────────────────────────────────


def _target_status_for_stage(stage: str) -> str:
    if stage == "convert_to_pdf":
        return DocumentStatus.PENDING.value
    if stage == "build_primary_language_source":
        return DocumentStatus.PRIMARY_READY.value
    if stage == "extract_document":
        return DocumentStatus.EXTRACTED.value
    if stage == "sanitize_document":
        return DocumentStatus.SANITIZED.value
    if stage == "build_structure":
        return DocumentStatus.STRUCTURED.value
    if stage == "build_chunks":
        return DocumentStatus.CHUNKED.value
    if stage in {"classify_document", "classify_document_segments"}:
        return DocumentStatus.CLASSIFIED.value
    if stage == "build_legal_units_enrichment":
        return DocumentStatus.ENRICHED.value
    return stage


# ─── Task plan builder ────────────────────────────────────────────────────────


async def _build_document_task_plan(
    *,
    doc_id_str: str,
    snap: VersionSnapshot | None,
    status: str,
    run_id: str,
    deal_id_str: str,
    tenant_id_str: str,
    is_full_rerun: bool,
    force_reclassify: bool,
    seg_repo: DocumentSegmentRepository,
    deal_primary_language: str | None,
    doc_snap: DocumentSnapshot | None = None,
) -> TaskPlan | None:
    if not deal_primary_language:
        raise ValueError("deal_primary_language must be selected before building run task plan")

    # ── PENDING ───────────────────────────────────────────────────────────────

    if status == DocumentStatus.PENDING.value:
        if snap is None:
            return None

        if snap.origin_filetype in CONVERTIBLE_TO_PDF and not snap.converted_pdf_ref:
            return TaskPlan(
                task_name="workers.convert_to_pdf",
                stage="convert_to_pdf",
                reason="convertible_type_without_converted_pdf",
                kwargs={
                    "document_id": doc_id_str,
                    "document_version_id": snap.version_id_str,
                    "deal_id": deal_id_str,
                    "tenant_id": tenant_id_str,
                    "run_id": run_id,
                },
            )

        return TaskPlan(
            task_name="workers.build_primary_language_source",
            stage="build_primary_language_source",
            reason="pending_document_ready_for_v2_or_v1_pipeline",
            kwargs={
                "document_version_id": snap.version_id_str,
                "document_id": doc_id_str,
                "deal_id": deal_id_str,
                "tenant_id": tenant_id_str,
                "run_id": run_id,
                "target_language": deal_primary_language,
            },
        )

    # ── PRIMARY_READY ─────────────────────────────────────────────────────────

    if status == DocumentStatus.PRIMARY_READY.value:
        if snap is None:
            return None

        has_primary_source = bool(snap.primary_source_ref)
        has_canonical_layout = bool(snap.layout_primary_ref)

        if not has_primary_source and not has_canonical_layout:
            return None

        readiness_source = "primary_source_ref" if has_primary_source else "canonical_layout_primary_ref"

        return TaskPlan(
            task_name="workers.extract_document",
            stage="extract_document",
            reason=f"ready_via_{readiness_source}",
            kwargs={
                "document_version_id": snap.version_id_str,
                "document_id": doc_id_str,
                "deal_id": deal_id_str,
                "tenant_id": tenant_id_str,
                "run_id": run_id,
            },
        )

    # ── EXTRACTED ─────────────────────────────────────────────────────────────

    if status == DocumentStatus.EXTRACTED.value:
        if snap is None:
            return None

        if not snap.layout_primary_ref:
            return None

        return TaskPlan(
            task_name="pii.sanitize_document",
            stage="sanitize_document",
            reason="layout_primary_ready",
            kwargs={
                "document_version_id": snap.version_id_str,
                "deal_id": deal_id_str,
                "tenant_id": tenant_id_str,
                "run_id": run_id,
            },
        )

    # ── SANITIZED ─────────────────────────────────────────────────────────────

    if status == DocumentStatus.SANITIZED.value:
        if snap is None:
            return None

        if not snap.layout_primary_sanitized_ref:
            return None

        return TaskPlan(
            task_name="workers.build_structure",
            stage="build_structure",
            reason="sanitized_layout_ready",
            kwargs={
                "document_version_id": snap.version_id_str,
                "run_id": run_id,
            },
        )

    # ── STRUCTURED ────────────────────────────────────────────────────────────

    if status == DocumentStatus.STRUCTURED.value:
        if snap is None:
            return None

        if not snap.file_graph_ref:
            return None

        if not snap.segments_count or snap.segments_count <= 0:
            return None

        return TaskPlan(
            task_name="workers.build_chunks",
            stage="build_chunks",
            reason="structure_v2_ready",
            kwargs={
                "document_version_id": snap.version_id_str,
                "document_id": doc_id_str,
                "deal_id": deal_id_str,
                "tenant_id": tenant_id_str,
                "run_id": run_id,
            },
        )

    # ── CHUNKED ───────────────────────────────────────────────────────────────

    if status == DocumentStatus.CHUNKED.value:
        if snap is None:
            return None

        if not snap.chunks_manifest_v2_ref:
            return None

        summary = await seg_repo.get_chunk_refs_summary(snap.version_id)
        total_segments = summary["total_segments"]
        segments_with_chunks = summary["segments_with_chunks"]

        if total_segments <= 0:
            return None

        if segments_with_chunks != total_segments:
            return None

        return TaskPlan(
            task_name="workers.classify_document",
            stage="classify_document",
            reason="chunks_v2_contract_ready",
            kwargs={
                "document_id": doc_id_str,
                "run_id": run_id,
                "deal_id": deal_id_str,
                "tenant_id": tenant_id_str,
            },
        )

    # ── CLASSIFIED ────────────────────────────────────────────────────────────

    if status == DocumentStatus.CLASSIFIED.value:
        if snap is None:
            return None

        # ── FIX #2: Блокировка enrichment для любых документов на ревью ───────
        if (doc_snap is not None 
                and (getattr(doc_snap, "classification_requires_review", False) 
                     or not getattr(doc_snap, "doc_type", None))):
            logger.info(
                "Orchestrator: skipping enrichment — document requires manual review or lacks doc_type",
                document_id=doc_id_str,
                run_id=run_id,
                current_doc_type=getattr(doc_snap, "doc_type", None),
            )
            return None
        # ── КОНЕЦ FIX #2 ──────────────────────────────────────────────────────

        if is_full_rerun or force_reclassify:
            return TaskPlan(
                task_name="workers.classify_document",
                stage="classify_document",
                reason="reclassify_requested",
                kwargs={
                    "document_id": doc_id_str,
                    "run_id": run_id,
                    "deal_id": deal_id_str,
                    "tenant_id": tenant_id_str,
                },
            )

        if _is_multi_document_snapshot(snap):
            segment_stage_complete = await _is_segment_classification_complete(seg_repo, snap)
            if not segment_stage_complete:
                return TaskPlan(
                    task_name="workers.classify_document_segments",
                    stage="classify_document_segments",
                    reason="multi_document_segment_classification_incomplete",
                    kwargs={
                        "document_id": doc_id_str,
                        "run_id": run_id,
                        "deal_id": deal_id_str,
                        "tenant_id": tenant_id_str,
                    },
                )

        return TaskPlan(
            task_name="workers.build_legal_units_enrichment",
            stage="build_legal_units_enrichment",
            reason="classification_path_complete",
            kwargs={
                "document_version_id": snap.version_id_str,
                "document_id": doc_id_str,
                "deal_id": deal_id_str,
                "tenant_id": tenant_id_str,
                "run_id": run_id,
            },
        )

    # ── COMPLETED ─────────────────────────────────────────────────────────────

    if status == DocumentStatus.COMPLETED.value:
        if is_full_rerun or force_reclassify:
            return TaskPlan(
                task_name="workers.classify_document",
                stage="classify_document",
                reason="rerun_reclassification_requested",
                kwargs={
                    "document_id": doc_id_str,
                    "run_id": run_id,
                    "deal_id": deal_id_str,
                    "tenant_id": tenant_id_str,
                },
            )
        return None

    return None


def _send_task(
    *,
    plan: TaskPlan,
    stage_execution_id: str,
    run_id: str,
    deal_id: str,
    tenant_id: str,
    document_id: str,
    document_version_id: str,
    orchestration_strategy: str,
) -> str:
    kwargs = dict(plan.kwargs)
    kwargs.update(
        {
            "stage_execution_id": stage_execution_id,
            "run_id": run_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "document_id": document_id,
            "document_version_id": document_version_id,
            "orchestration_strategy": orchestration_strategy,
        }
    )
    result = send_task_with_context(plan.task_name, kwargs=kwargs)
    return result.id
