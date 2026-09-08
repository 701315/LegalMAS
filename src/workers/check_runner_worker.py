# src/workers/check_runner_worker.py

"""
CheckRunner Worker — запуск playbook-checks по уже классифицированным документам сделки.

Позиция в пайплайне:
- import → extract → pii → structure → classify → run_deal_checks → export_results.

Что делает:
- Для одного Run по deal_id:
  - вытаскивает все non-duplicate документы сделки;
  - строит execution plan (пары doc_id/check_id);
  - фиксирует instruction_versions для воспроизводимости review path;
  - публикует отдельные Celery-задачи run_single_check;
  - сохраняет прогресс и статус Run;
  - финализирует Run, когда все checks достигают terminal execution_status.

Архитектура:
- Снаружи — синхронные Celery-таски.
- Внутри — один переход sync → async через run_async.
- Работа с БД идёт через db_uow() / AsyncSession.
- run_deal_checks запускается один раз на весь Run.
- run_single_check выполняет ровно одну проверку для одного документа.
- finalize_run_if_ready — отдельная lightweight task, которая смотрит на CheckResult и
  решает, пора ли перевести Run в COMPLETED / COMPLETED_WITH_ERRORS.

Важное правило работы с ORM (snapshot architecture):
- SQLAlchemy asyncpg не допускает синхронный lazy reload атрибутов ORM-объектов
  после await-границы (MissingGreenlet).
- Поэтому все нужные поля ORM-объектов снимаются в snapshot/примитивы сразу
  после загрузки объекта, до следующего await-вызова.
- Shared snapshot-контракты живут в core.pipeline_snapshots и переиспользуются
  всеми orchestration/worker файлами.

Instruction snapshot freeze:
- После построения document scope и до отправки run_single_check задач
  worker фиксирует frozen instruction snapshot в Run.
- Для каждого уникального doc_type freeze path резолвит canonical effective payload:
    published base → tenant active override → deal active override.
- Если published base version пока отсутствует, используется controlled
  registry-backed seed fallback для platform path.
- Зафиксированная карта {doc_type: version_id} сохраняет БАЗОВЫЕ instruction versions,
  а instruction_snapshot_payload хранит final effective payload для исполнения.
- Это гарантирует, что DD Grid review path и runtime checks используют
  одинаковую frozen конфигурацию конкретного Run.
- Ошибка freeze роняет Run в FAILED — strict snapshot обязателен для новых Run.
"""

from __future__ import annotations

import time
import uuid
from contextlib import nullcontext
from typing import Any

from celery.exceptions import SoftTimeLimitExceeded

from core.check_result_persist_errors import (
    CheckFailureAction,
    CheckResultPersistError,
    decide_check_failure_action,
)
from core.constants import CheckExecutionStatus, RunStatus
from core.logging import get_logger
from core.pipeline_snapshots import (
    RunSnapshot,
    snapshot_run,
)
from db.repositories.audit_repo import AuditRepository
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_stage_execution_repo import DocumentStageExecutionRepository

from db.repositories.runner_repo import RunnerRepository
from engine.checks.instruction_snapshot import (
    build_doc_type_loader,
    freeze_instruction_snapshot,
)
from db.repositories.playbook_repo import PlaybookRepository
from db.repositories.result_repo import ResultRepository
from db.repositories.run_repo import RunRepository
from db.uow import db_uow
from engine.checks_runner import CheckRunner
from engine.llm.client import LLMClient
from engine.playbook.loader import load_playbook_from_version
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.outbox_service import OutboxService
from ops.metrics import get_metrics
from db.repositories.run_check_plan_item_repo import RunCheckPlanItemRepository
from engine.checks.snapshot_policy import ConfigurationIntegrityError
from services.import_helpers import _build_finalize_run_outbox_dedup_key

logger = get_logger(__name__)

# Один экземпляр LLMClient на весь процесс воркера.
_shared_llm_client = LLMClient()


def _resolve_effective_tenant_id(
    task_tenant_id: str | None,
    run_snap: RunSnapshot,
) -> uuid.UUID | None:
    """
    Определить эффективный tenant_id для audit/orchestration.

    Приоритет:
    1. task_tenant_id из kwargs задачи — явно переданный вызывающим кодом.
    2. run_snap.tenant_id — прочитан из Run при snapshot, первичный источник истины.
    3. None — tenant определить невозможно.

    НЕ возвращает zero UUID (uuid.UUID(int=0)).
    Если tenant не найден — это должно обрабатываться вызывающим кодом явно:
    - либо fail-fast (для orchestration),
    - либо пропуск audit (для best-effort audit paths).
    """
    if task_tenant_id:
        try:
            return uuid.UUID(task_tenant_id)
        except (ValueError, AttributeError):
            logger.warning(
                "check_runner_worker: invalid tenant_id in task kwargs, falling back to run_snap",
                raw_tenant_id=str(task_tenant_id)[:64],
            )

    if run_snap.tenant_id is not None:
        return run_snap.tenant_id

    return None


# ─── run_deal_checks ──────────────────────────────────────────────────────────

async def _enqueue_finalize_via_outbox(
    *,
    session: Any,
    run_id: str,
    plan_item_id: str,
    tenant_id: str | None,
) -> None:
    """
    Зарегистрировать finalize_run_if_ready через outbox в текущей транзакции.

    Этот outbox event будет опубликован в Celery только после commit транзакции.
    Гарантирует: finalize увидит уже закоммиченный mark_terminal.
    """
    dedup_key = _build_finalize_run_outbox_dedup_key(run_id, plan_item_id)
    outbox = OutboxService(session)

    try:
        await outbox.enqueue_task(
            task_name="workers.finalize_run_if_ready",
            payload={
                "run_id": run_id,
                "tenant_id": tenant_id,
            },
            aggregate_type="run",
            aggregate_id=run_id,
            dedup_key=dedup_key,
            headers={"queue": "default"},
        )
    except Exception:
        get_logger(__name__).exception(
            "run_single_check: failed to enqueue finalize_run_if_ready via outbox",
            run_id=run_id,
            plan_item_id=plan_item_id,
        )

@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.run_deal_checks",
    track_job=True,
)
def run_deal_checks(
    self,
    run_id: str,
    deal_id: str,
    tenant_id: str | None = None,
    job_id: str | None = None,
    stage_execution_id: str | None = None,
    orchestration_strategy: str | None = None,
    **kwargs: Any,
) -> dict:
    """
    Celery-task scheduler уровня Run:
    - загружает Run и Playbook;
    - строит пары (doc_id, check_id);
    - фиксирует instruction_versions для воспроизводимости;
    - публикует отдельные задачи run_single_check;
    - переводит Run в RUNNING и обновляет total_checks;
    - при total_checks == 0 детерминированно финализирует Run.
    """
    logger.info(
        "Run deal checks scheduler received",
        run_id=run_id,
        deal_id=deal_id,
        tenant_id=tenant_id,
        job_id=job_id,
    )

    started_at = time.time()
    metrics = get_metrics()
    run_uuid = uuid.UUID(run_id)
    deal_uuid = uuid.UUID(deal_id)

    async def _run() -> dict:
        async with db_uow() as uow:
            run_repo = RunRepository(uow.session)
            pb_repo = PlaybookRepository(uow.session)
            audit_repo = AuditRepository(uow.session)
            plan_item_repo = RunCheckPlanItemRepository(uow.session)

            try:
                logger.info(
                    "Run deal checks scheduler: loading run and playbook",
                    run_id=run_id,
                    deal_id=deal_id,
                )

                run_obj = await run_repo.get(run_uuid)
                if run_obj is None:
                    raise ValueError(f"Run not found: {run_uuid}")

                # Снимаем snapshot сразу после загрузки ORM-объекта Run.
                # Дальше orchestration работает только с run_snap,
                # а не с run_obj.
                run_snap: RunSnapshot = snapshot_run(run_obj)

                started = await run_repo.try_start_run(run_uuid)
                if not started and run_snap.status != RunStatus.RUNNING.value:
                    logger.info(
                        "Run deal checks scheduler: run already started or finalized, skipping",
                        run_id=run_id,
                        deal_id=deal_id,
                        current_status=run_snap.status,
                    )
                    return {
                        "status": "SKIPPED",
                        "reason": "run_not_pending",
                        "current_status": run_snap.status,
                    }

                pb_version = await pb_repo.get_by_id(run_snap.playbook_version_id)
                if pb_version is None:
                    raise ValueError(f"PlaybookVersion not found: {run_snap.playbook_version_id}")

                playbook = load_playbook_from_version(pb_version)

                logger.info(
                    "Run deal checks scheduler: playbook loaded",
                    run_id=run_id,
                    deal_id=deal_id,
                    playbook_version_id=str(run_snap.playbook_version_id),
                    checks_mode=run_snap.checks_mode,
                    checks_scope=run_snap.checks_scope,
                )

                docs_for_snapshot = await RunnerRepository(uow.session).get_non_duplicate_docs(
                    deal_uuid
                )
                doc_types_for_snapshot = {
                    getattr(d, "doc_type", None) for d in docs_for_snapshot
                }
                doc_types_for_snapshot.discard(None)

                # ── FIX #3: Идемпотентное расширение snapshot ─────────────────
                if not doc_types_for_snapshot:
                    logger.info(
                        "Run deal checks scheduler: no doc_types for snapshot, "
                        "global_only checks will proceed without frozen snapshot",
                        run_id=run_id,
                        deal_id=deal_id,
                    )
                else:
                    try:
                        fixed_versions = await freeze_instruction_snapshot(
                            run_uuid=run_uuid,
                            doc_types=doc_types_for_snapshot,
                            run_repo=run_repo,
                            session=uow.session,
                            tenant_id=run_snap.tenant_id,
                            deal_id=run_snap.deal_id or deal_uuid,
                            extend_existing=True,
                        )
                        logger.info(
                            "Run deal checks scheduler: instruction snapshot fixed/extended",
                            run_id=run_id,
                            deal_id=deal_id,
                            fixed_doc_types_count=len(fixed_versions),
                            snapshot_schema_version=1,
                        )
                    except Exception as version_exc:
                        logger.exception(
                            "Run deal checks scheduler: failed to freeze/extend strict instruction snapshot; "
                            "aborting scheduling",
                            run_id=run_id,
                            deal_id=deal_id,
                            error=str(version_exc),
                            error_type=type(version_exc).__name__,
                        )
                        raise RuntimeError(
                            "Strict instruction snapshot freeze/extension failed; "
                            "checks scheduling aborted"
                        ) from version_exc
                # ── КОНЕЦ FIX #3 ──────────────────────────────────────────────

                # Перечитываем Run, чтобы snapshot содержал только что
                # зафиксированный instruction_snapshot_payload.
                run_obj_refreshed = await run_repo.get(run_uuid)
                run_snap = snapshot_run(run_obj_refreshed)
                doc_type_loader = build_doc_type_loader(run_snap)

                runner = CheckRunner(
                    llm_client=_shared_llm_client,
                    playbook_version_id=run_snap.playbook_version_id,
                    checks_mode=run_snap.checks_mode or "global_and_doc_type",
                    run_repo=run_repo,
                    checks_scope=run_snap.checks_scope,
                    doc_type_loader=doc_type_loader,
                )

                plan = await runner.plan_checks_for_run(
                    session=uow.session,
                    deal_id=deal_uuid,
                    run_id=run_uuid,
                    playbook=playbook,
                )

                pairs = plan.get("pairs", [])
                
                # ── FIX #7: Высокопроизводительная Batch дедупликация ─────────
                if pairs:
                    from db.repositories.result_repo import ResultRepository
                    result_repo = ResultRepository(uow.session)

                    pair_keys = [
                        (uuid.UUID(p["doc_id"]) if isinstance(p["doc_id"], str) else p["doc_id"],
                         p["check_id"])
                        for p in pairs
                    ]

                    existing_success_keys = await result_repo.get_successful_doc_check_keys(
                        run_id=run_uuid,
                        doc_check_pairs=pair_keys,
                    )

                    filtered_pairs = [
                        p for p, key in zip(pairs, pair_keys)
                        if key not in existing_success_keys
                    ]
                    skipped_count = len(pairs) - len(filtered_pairs)

                    if skipped_count > 0:
                        logger.info(
                            "Run deal checks: deduplicated already successful checks",
                            run_id=run_id,
                            deal_id=deal_id,
                            original=len(pairs),
                            after_dedup=len(filtered_pairs),
                            skipped=skipped_count,
                        )

                    pairs = filtered_pairs
                # ── КОНЕЦ FIX #7 ──────────────────────────────────────────────

                processed_docs = int(plan.get("processed_docs", 0) or 0)
                total_checks = int(plan.get("total_checks", 0) or 0)
                errors = int(plan.get("errors", 0) or 0)

                logger.info(
                    "Run deal checks scheduler: plan built",
                    run_id=run_id,
                    deal_id=deal_id,
                    processed_docs=processed_docs,
                    pairs_count=len(pairs),
                    total_checks=total_checks,
                    planning_errors=errors,
                    checks_mode=run_snap.checks_mode,
                    checks_scope=run_snap.checks_scope,
                )

                if total_checks != len(pairs):
                    logger.warning(
                        "Run deal checks scheduler: total_checks differs from pairs_count",
                        run_id=run_id,
                        deal_id=deal_id,
                        total_checks=total_checks,
                        pairs_count=len(pairs),
                    )

                materialized_items = []
                for pair in pairs:
                    item = await plan_item_repo.create_planned(
                        run_id=run_uuid,
                        deal_id=deal_uuid,
                        document_id=uuid.UUID(pair["doc_id"]),
                        check_id=pair["check_id"],
                        playbook_version_id=run_snap.playbook_version_id,
                        segment_id=pair.get("segment_id"),
                        doc_type=pair.get("doc_type"),
                        check_name=pair.get("check_name"),
                        check_origin=pair.get("check_origin"),
                    )
                    materialized_items.append(item)

                materialized_count = len(materialized_items)

                await run_repo.update_status(
                    run_uuid,
                    RunStatus.RUNNING.value,
                    total_checks=materialized_count,
                )

                scheduled = 0
                outbox_service = OutboxService(uow.session)

                for item in materialized_items:
                    outbox_message_id = await outbox_service.enqueue_task(
                        task_name="workers.run_single_check",
                        payload={
                            "run_id": run_id,
                            "deal_id": deal_id,
                            "doc_id": str(item.document_id),
                            "check_id": item.check_id,
                            "plan_item_id": str(item.id),
                            "playbook_version_id": str(run_snap.playbook_version_id),
                            "checks_mode": run_snap.checks_mode,
                            "force": False,
                            "tenant_id": tenant_id,
                        },
                        aggregate_type="run",
                        aggregate_id=run_id,
                        dedup_key=f"run_single_check:{run_id}:{item.id}",
                        headers={
                            "queue": "heavy_llm_checks",
                        },
                    )

                    marked_item = await plan_item_repo.mark_dispatched(item.id, outbox_message_id)
                    if marked_item is None:
                        raise RuntimeError(
                            f"Failed to mark dispatched for plan_item={item.id}: "
                            "item is not in planned status"
                        )

                    scheduled += 1

                try:
                    # Резолюция tenant_id: task kwargs → run_snap → None.
                    # Если tenant не определён — audit пропускается,
                    # не пишем в zero UUID.
                    effective_tenant = _resolve_effective_tenant_id(tenant_id, run_snap)
                    if effective_tenant is None:
                        logger.error(
                            "run_deal_checks: tenant_id unavailable, "
                            "skipping CHECKS_SCHEDULED audit",
                            run_id=run_id,
                            deal_id=deal_id,
                        )
                    else:
                        await audit_repo.log(
                            tenant_id=effective_tenant,
                            deal_id=deal_uuid,
                            action="CHECKS_SCHEDULED",
                            actor="system",
                            actor_role="worker",
                            details={
                                "run_id": run_id,
                                "playbook_version_id": str(run_snap.playbook_version_id),
                                "checks_mode": run_snap.checks_mode,
                                "checks_scope": run_snap.checks_scope,
                                "processed_docs": processed_docs,
                                "total_checks": materialized_count,
                                "pairs_count": len(pairs),
                                "scheduled_checks": scheduled,
                                "planning_errors": errors,
                            },
                        )
                except Exception:
                    logger.warning(
                        "run_deal_checks: failed to write audit log for CHECKS_SCHEDULED",
                        run_id=run_id,
                        deal_id=deal_id,
                    )

                duration = time.time() - started_at

                try:
                    metrics.checks_duration.labels(stage="deal_checks_schedule").observe(duration)
                except Exception:
                    logger.exception(
                        "run_deal_checks scheduler: failed to update checks_duration metric",
                        run_id=run_id,
                        deal_id=deal_id,
                    )

                logger.info(
                    "Run deal checks scheduler completed",
                    run_id=run_id,
                    deal_id=deal_id,
                    duration_sec=round(duration, 2),
                    processed_docs=processed_docs,
                    planned_checks=materialized_count,
                    scheduled_checks=scheduled,
                    planning_errors=errors,
                    status=RunStatus.RUNNING.value,
                )

                if materialized_count == 0:
                    logger.warning(
                        "Run deal checks scheduler: zero checks planned, "
                        "finalizing run immediately",
                        run_id=run_id,
                        deal_id=deal_id,
                        processed_docs=processed_docs,
                        planning_errors=errors,
                        checks_mode=run_snap.checks_mode,
                        checks_scope=run_snap.checks_scope,
                    )

                    finalized = await run_repo.finalize_run_if_finished(run_uuid)
                    if finalized is None:
                        raise ValueError(
                            f"Run not found during zero-check finalize: {run_uuid}"
                        )

                    # Снимаем snapshot финализированного Run сразу после получения.
                    finalized_snap: RunSnapshot = snapshot_run(finalized)

                    return {
                        "status": finalized_snap.status,
                        "processed_docs": processed_docs,
                        "total_checks": materialized_count,
                        "scheduled_checks": scheduled,
                        "errors": errors,
                        "duration_sec": round(duration, 2),
                    }

                return {
                    "status": RunStatus.RUNNING.value,
                    "processed_docs": processed_docs,
                    "total_checks": materialized_count,
                    "scheduled_checks": scheduled,
                    "errors": errors,
                    "duration_sec": round(duration, 2),
                }

            except Exception as e:
                logger.exception(
                    "Run deal checks scheduler failed",
                    run_id=run_id,
                    deal_id=deal_id,
                    error=str(e),
                )
                await run_repo.mark_run_failed(
                    run_uuid,
                    message="Run orchestration failed during checks scheduling",
                    error_details={
                        "stage": "run_deal_checks_schedule",
                        "type": "failed",
                        "reason": "checks_schedule_error",
                        "message": str(e),
                    },
                )
                raise

    return run_async(_run())


# ─── run_single_check ─────────────────────────────────────────────────────────


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.run_single_check",
    track_job=False,
    queue="heavy_llm_checks",
)
def run_single_check(
    self,
    run_id: str,
    deal_id: str,
    doc_id: str,
    check_id: str,
    plan_item_id: str,
    *,
    playbook_version_id: str | None = None,
    checks_mode: str | None = None,
    force: bool = False,
    tenant_id: str | None = None,
    stage_execution_id: str | None = None,
    orchestration_strategy: str | None = None,
    **kwargs: Any,
) -> dict:
    """
    Выполнить одну проверку (check_id) для одного документа в рамках Run.

    Логика:
    - находим Run, Playbook и Document;
    - выполняем одну проверку через CheckRunner;
    - сохраняем/обновляем CheckResult с execution_status;
    - в finally публикуем finalize_run_if_ready для возможной финализации всего Run.

    Business span stage.run_single_check:
    - охватывает полный lifecycle одного check внутри worker
    - включает LLM call, SQL reads/writes
    - атрибуты: check_id, document_id, run_id, deal_id
    - обогащается результатом check после выполнения
    """
    logger.info(
        "Run single check task received",
        run_id=run_id,
        deal_id=deal_id,
        doc_id=doc_id,
        check_id=check_id,
        playbook_version_id=playbook_version_id,
        checks_mode=checks_mode,
        force=force,
    )

    started_at = time.time()
    run_uuid = uuid.UUID(run_id)
    deal_uuid = uuid.UUID(deal_id)
    doc_uuid = uuid.UUID(doc_id)
    pb_version_uuid = uuid.UUID(playbook_version_id) if playbook_version_id else None
    plan_item_uuid = uuid.UUID(plan_item_id)

    async def _run() -> dict:
        from core.tracing import get_stage_tracer  # noqa: PLC0415

        _stage_tracer = get_stage_tracer()
        _stage_span_ctx = (
            _stage_tracer.start_as_current_span(
                "stage.run_single_check",
                attributes={
                    "check_id": check_id,
                    "document_id": doc_id,
                    "run_id": run_id,
                    "deal_id": deal_id,
                },
            )
            if _stage_tracer else nullcontext()
        )

        with _stage_span_ctx:
            async with db_uow() as uow:
                run_repo = RunRepository(uow.session)
                pb_repo = PlaybookRepository(uow.session)
                doc_repo = DocumentRepository(uow.session)
                result_repo = ResultRepository(uow.session)
                plan_item_repo = RunCheckPlanItemRepository(uow.session)

                effective_pb_version_id = pb_version_uuid

                try:
                    item = await plan_item_repo.get_by_id(plan_item_uuid)
                    if item is None:
                        raise ValueError(f"RunCheckPlanItem not found: {plan_item_uuid}")

                    if (
                        item.run_id != run_uuid
                        or item.document_id != doc_uuid
                        or item.check_id != check_id
                    ):
                        
                        raise ValueError(
                            "RunCheckPlanItem mismatch with task payload: "
                            f"item_id={plan_item_uuid}, run_id={item.run_id}, "
                            f"document_id={item.document_id}, check_id={item.check_id}"
                        )
                    

                    if (
                        pb_version_uuid is not None
                        and item.playbook_version_id is not None
                        and item.playbook_version_id != pb_version_uuid
                    ):
                        raise ValueError(
                            "RunCheckPlanItem playbook_version_id mismatch with task payload: "
                            f"item_id={plan_item_uuid}, "
                            f"item_playbook_version_id={item.playbook_version_id}, "
                            f"task_playbook_version_id={pb_version_uuid}"
                        )

                    started_item = await plan_item_repo.mark_started(plan_item_uuid)
                    if started_item is None:
                        logger.info(
                            "run_single_check: plan item already terminal or not startable",
                            run_id=run_id,
                            deal_id=deal_id,
                            doc_id=doc_id,
                            check_id=check_id,
                            plan_item_id=plan_item_id,
                        )
                        return {
                            "status": "SKIPPED",
                            "reason": "plan_item_not_startable",
                        }

                    run_obj = await run_repo.get(run_uuid)
                    if run_obj is None:
                        raise ValueError(f"Run not found: {run_uuid}")

                    # Снимаем snapshot сразу после загрузки ORM-объекта Run.
                    # Дальше работаем только с run_snap, а не с run_obj.
                    run_snap: RunSnapshot = snapshot_run(run_obj)

                    effective_checks_mode = checks_mode or run_snap.checks_mode or "global_and_doc_type"
                    effective_pb_version_id = pb_version_uuid or run_snap.playbook_version_id

                    if run_snap.deal_id != deal_uuid:
                        logger.warning(
                            "run_single_check: deal_id mismatch between task and Run",
                            run_id=run_id,
                            deal_id_task=str(deal_uuid),
                            deal_id_run=run_snap.deal_id_str,
                        )

                    pb_version = await pb_repo.get_by_id(effective_pb_version_id)
                    if pb_version is None:
                        raise ValueError(f"PlaybookVersion not found: {effective_pb_version_id}")
                    playbook = load_playbook_from_version(pb_version)

                    doc_type_loader = build_doc_type_loader(run_snap)

                    doc = await doc_repo.get_by_id(doc_uuid)

                    if doc is None:
                        raise ValueError(f"Document not found: {doc_uuid}")

                    already_success = await result_repo.has_success_for_doc_check(
                        run_id=run_uuid,
                        document_id=doc_uuid,
                        check_id=check_id,
                    )

                    if already_success and not force:
                        success_row = await result_repo.get_first_success_for_doc_check(
                            run_id=run_uuid,
                            document_id=doc_uuid,
                            check_id=check_id,
                        )

                        logger.debug(
                            "run_single_check: existing SUCCESS details for doc/check aggregate",
                            run_id=run_id,
                            deal_id=deal_id,
                            doc_id=doc_id,
                            check_id=check_id,
                            force=force,
                            success_result_id=(str(success_row.id) if success_row else None),
                            success_segment_id=(success_row.segment_id if success_row else None),
                            success_segment_type=(
                                success_row.segment_type if success_row else None
                            ),
                            success_segment_title=(
                                success_row.segment_title if success_row else None
                            ),
                            success_segment_order=(
                                success_row.segment_order if success_row else None
                            ),
                            success_is_primary_segment=(
                                success_row.is_primary_segment if success_row else None
                            ),
                            success_created_at=(
                                success_row.created_at.isoformat()
                                if success_row and success_row.created_at
                                else None
                            ),
                        )

                        logger.info(
                            "run_single_check: result already SUCCESS for doc/check aggregate, skipping",
                            run_id=run_id,
                            deal_id=deal_id,
                            doc_id=doc_id,
                            check_id=check_id,
                            force=force,
                        )
                        await plan_item_repo.mark_terminal(plan_item_uuid, "skipped")
                        await _enqueue_finalize_via_outbox(
                            session=uow.session,
                            run_id=run_id,
                            plan_item_id=plan_item_id,
                            tenant_id=tenant_id,
                        )
                        return {
                            "status": "SKIPPED",
                            "reason": "already_success",
                        }

                    runner = CheckRunner(
                        llm_client=_shared_llm_client,
                        playbook_version_id=effective_pb_version_id,
                        checks_mode=effective_checks_mode,
                        run_repo=run_repo,
                        checks_scope=run_snap.checks_scope,
                        doc_type_loader=doc_type_loader,
                    )

                    # doc здесь — живой ORM Document, загруженный в этом UoW.
                    # execute_single_check внутри сразу снимает DocumentCheckSnapshot
                    # через _snapshot_check_doc() в engine/checks/check_runner.py.
                    outcome = await runner.execute_single_check(
                        session=uow.session,
                        repo=result_repo,
                        doc=doc,
                        run_id=run_uuid,
                        playbook=playbook,
                        check_id=check_id,
                        plan_item_id=plan_item_uuid,
                    )

                    exec_result = outcome["exec_result"]

                    # ── LLM Usage Ledger: checks ──────────────────────────────
                    if exec_result is not None:
                        try:
                            from services.llm_usage_recorder import (
                                LLMUsageRecorder,
                                STAGE_CHECKS_DETECTION_LLM,
                                STAGE_CHECKS_EXTRACTION_LLM,
                            )

                            _check_raw = exec_result.get("raw") or {}
                            _effective_tenant = (
                                uuid.UUID(tenant_id)
                                if tenant_id
                                else run_snap.tenant_id
                            )

                            # Detection LLM
                            _det_method = exec_result.get("detector_method")
                            _det_error = _check_raw.get("llm_error_type")
                            if (
                                _det_method in {"llm", "hybrid"}
                                or bool(_det_error)
                            ) and _effective_tenant is not None:
                                await LLMUsageRecorder.record_event_isolated(
                                    tenant_id=_effective_tenant,
                                    deal_id=deal_uuid,
                                    run_id=run_uuid,
                                    document_id=doc_uuid,
                                    stage=STAGE_CHECKS_DETECTION_LLM,
                                    check_id=check_id,
                                    provider=str(
                                        _check_raw.get("provider") or "ollama"
                                    ),
                                    model=str(_check_raw.get("model") or ""),
                                    prompt_tokens=_check_raw.get(
                                        "prompt_tokens"
                                    ),
                                    completion_tokens=_check_raw.get(
                                        "completion_tokens"
                                    ),
                                    duration_ms=_check_raw.get("duration_ms"),
                                    llm_attempts=_check_raw.get("llm_attempts"),
                                    parse_success=_check_raw.get("parse_success"),
                                    error_type=_det_error,
                                )

                            # Extraction LLM
                            _extr = _check_raw.get("extraction_telemetry") or {}
                            if (
                                _extr.get("extraction_llm_invoked")
                                and _effective_tenant is not None
                            ):
                                await LLMUsageRecorder.record_event_isolated(
                                    tenant_id=_effective_tenant,
                                    deal_id=deal_uuid,
                                    run_id=run_uuid,
                                    document_id=doc_uuid,
                                    stage=STAGE_CHECKS_EXTRACTION_LLM,
                                    check_id=check_id,
                                    provider=str(
                                        _extr.get("provider") or "ollama"
                                    ),
                                    model=str(_extr.get("model") or ""),
                                    prompt_tokens=_extr.get("prompt_tokens"),
                                    completion_tokens=_extr.get(
                                        "completion_tokens"
                                    ),
                                    duration_ms=_extr.get("duration_ms"),
                                    llm_attempts=_extr.get("llm_attempts"),
                                    parse_success=_extr.get("parse_success"),
                                    error_type=_extr.get("error_type"),
                                )
                        except Exception:
                            logger.warning(
                                "run_single_check: failed to record LLM usage"
                                " (non-fatal)",
                                run_id=run_id,
                                deal_id=deal_id,
                                doc_id=doc_id,
                                check_id=check_id,
                            )
                    # ── конец LLM Usage Ledger ────────────────────────────────

                    duration = time.time() - started_at

                    if exec_result is None:
                        logger.info(
                            "run_single_check completed: check not applicable",
                            run_id=run_id,
                            deal_id=deal_id,
                            doc_id=doc_id,
                            check_id=check_id,
                            duration_sec=round(duration, 2),
                        )
                        await plan_item_repo.mark_terminal(plan_item_uuid, "skipped")
                        await _enqueue_finalize_via_outbox(
                            session=uow.session,
                            run_id=run_id,
                            plan_item_id=plan_item_id,
                            tenant_id=tenant_id,
                        )
                        return {
                            "status": "SUCCESS",
                            "result": None,
                            "severity": None,
                            "check_id": check_id,
                            "doc_id": str(doc_uuid),
                            "reason": "not_applicable",
                        }

                    logger.info(
                        "run_single_check completed",
                        run_id=run_id,
                        deal_id=deal_id,
                        doc_id=doc_id,
                        check_id=check_id,
                        result=exec_result.get("result"),
                        severity=exec_result.get("severity"),
                        duration_sec=round(duration, 2),
                    )

                    # Обогатить span результатом check.
                    # Это позволяет в Tempo сразу видеть результат check
                    # без перехода в логи.
                    try:
                        from opentelemetry import trace as _otel_trace  # noqa: PLC0415
                        _cur = _otel_trace.get_current_span()
                        if _cur and _cur.is_recording():
                            _cur.set_attribute("check.result", exec_result.get("result") or "")
                            _cur.set_attribute("check.severity", exec_result.get("severity") or "")
                            _cur.set_attribute("check.duration_sec", round(duration, 2))
                    except Exception:  # noqa: BLE001
                        pass

                    await plan_item_repo.mark_terminal(plan_item_uuid, "succeeded")

                    await _enqueue_finalize_via_outbox(
                        session=uow.session,
                        run_id=run_id,
                        plan_item_id=plan_item_id,
                        tenant_id=tenant_id,
                    )

                    return {
                        "status": "SUCCESS",
                        "result": exec_result.get("result"),
                        "severity": exec_result.get("severity"),
                        "check_id": check_id,
                        "doc_id": str(doc_uuid),
                    }

                except SoftTimeLimitExceeded as e:
                    logger.warning(
                        "run_single_check: soft time limit exceeded",
                        run_id=run_id,
                        doc_id=doc_id,
                        check_id=check_id,
                        error=str(e),
                    )
                    await result_repo.upsert_single_check_result(
                        run_id=run_uuid,
                        document_id=doc_uuid,
                        check_id=check_id,
                        check_name=check_id,
                        result="unclear",
                        severity="unclear",
                        value_text="timeout",
                        evidence_ref=None,
                        confidence=None,
                        detector_used=None,
                        quality_flags={"raw": {"source": "timeout", "error_message": str(e)}},
                        structured_data=None,
                        conditional_check_triggered=False,
                        trigger_name=None,
                        origin=None,
                        playbook_version_id=effective_pb_version_id,
                        plan_item_id=plan_item_uuid,
                        page=None,
                        clause_uid=None,
                        element_id=None,
                        bbox=None,
                        execution_status=CheckExecutionStatus.TIMEOUT.value,
                        error_details={"type": "soft_time_limit", "message": str(e)},
                    )

                    await plan_item_repo.mark_terminal(
                        plan_item_uuid,
                        "timeout",
                        error_details={"type": "soft_time_limit", "message": str(e)},
                    )

                    await _enqueue_finalize_via_outbox(
                        session=uow.session,
                        run_id=run_id,
                        plan_item_id=plan_item_id,
                        tenant_id=tenant_id,
                    )

                    raise

                except CheckResultPersistError as e:
                    action = decide_check_failure_action(e)

                    if action == CheckFailureAction.RETRY:
                        logger.warning(
                            "run_single_check: transient check_result persist error, retrying task",
                            run_id=run_id,
                            deal_id=deal_id,
                            doc_id=doc_id,
                            check_id=check_id,
                            sqlstate=e.sqlstate,
                            error=str(e),
                        )
                        raise self.retry(exc=e, countdown=30)

                    logger.exception(
                        "run_single_check: permanent check_result persist error",
                        run_id=run_id,
                        deal_id=deal_id,
                        doc_id=doc_id,
                        check_id=check_id,
                        sqlstate=e.sqlstate,
                        error=str(e),
                    )

                    try:
                        await result_repo.upsert_single_check_result(
                            run_id=run_uuid,
                            document_id=doc_uuid,
                            check_id=check_id,
                            check_name=check_id,
                            result="unclear",
                            severity="unclear",
                            value_text="persist_error",
                            evidence_ref=None,
                            confidence=None,
                            detector_used=None,
                            quality_flags={
                                "raw": {
                                    "source": "persist_exception",
                                    "error_message": str(e),
                                    "sqlstate": e.sqlstate,
                                    "retryable": e.retryable,
                                }
                            },
                            structured_data=None,
                            conditional_check_triggered=False,
                            trigger_name=None,
                            origin=None,
                            playbook_version_id=effective_pb_version_id,
                            plan_item_id=plan_item_uuid,
                            page=None,
                            clause_uid=None,
                            element_id=None,
                            bbox=None,
                            execution_status=CheckExecutionStatus.PERSIST_FAILED.value,
                            error_details={
                                "type": "persist_error",
                                "message": str(e),
                                "sqlstate": e.sqlstate,
                                "retryable": e.retryable,
                            },
                        )

                        await plan_item_repo.mark_terminal(
                            plan_item_uuid,
                            "failed",
                            error_details={
                                "type": "persist_error",
                                "message": str(e),
                                "sqlstate": e.sqlstate,
                                "retryable": e.retryable,
                            },
                        )

                        await _enqueue_finalize_via_outbox(
                            session=uow.session,
                            run_id=run_id,
                            plan_item_id=plan_item_id,
                            tenant_id=tenant_id,
                        )

                    except Exception:
                        logger.exception(
                            "run_single_check: failed to persist PERSIST_FAILED sentinel row",
                            run_id=run_id,
                            deal_id=deal_id,
                            doc_id=doc_id,
                            check_id=check_id,
                        )

                    raise

                except ConfigurationIntegrityError as e:
                    logger.exception(
                        "run_single_check failed: strict snapshot configuration integrity error",
                        run_id=run_id,
                        deal_id=deal_id,
                        doc_id=doc_id,
                        check_id=check_id,
                        error=str(e),
                    )

                    try:
                        await result_repo.upsert_single_check_result(
                            run_id=run_uuid,
                            document_id=doc_uuid,
                            check_id=check_id,
                            check_name=check_id,
                            result="unclear",
                            severity="unclear",
                            value_text="configuration_integrity_error",
                            evidence_ref=None,
                            confidence=None,
                            detector_used=None,
                            quality_flags={
                                "raw": {
                                    "source": "configuration_integrity",
                                    "error_message": str(e),
                                }
                            },
                            structured_data=None,
                            conditional_check_triggered=False,
                            trigger_name=None,
                            origin=None,
                            playbook_version_id=effective_pb_version_id,
                            plan_item_id=plan_item_uuid,
                            page=None,
                            clause_uid=None,
                            element_id=None,
                            bbox=None,
                            execution_status=CheckExecutionStatus.COMPUTE_FAILED.value,
                            error_details={
                                "type": "configuration_integrity",
                                "message": str(e),
                            },
                        )

                        await plan_item_repo.mark_terminal(
                            plan_item_uuid,
                            "failed",
                            error_details={
                                "type": "configuration_integrity",
                                "message": str(e),
                            },
                        )

                        await _enqueue_finalize_via_outbox(
                            session=uow.session,
                            run_id=run_id,
                            plan_item_id=plan_item_id,
                            tenant_id=tenant_id,
                        )

                    except Exception:
                        logger.exception(
                            "run_single_check: failed to persist configuration integrity failure sentinel",
                            run_id=run_id,
                            deal_id=deal_id,
                            doc_id=doc_id,
                            check_id=check_id,
                        )

                    raise


                except Exception as e:
                    logger.exception(
                        "run_single_check failed",
                        run_id=run_id,
                        deal_id=deal_id,
                        doc_id=doc_id,
                        check_id=check_id,
                        error=str(e),
                    )

                    try:
                        await result_repo.upsert_single_check_result(
                            run_id=run_uuid,
                            document_id=doc_uuid,
                            check_id=check_id,
                            check_name=check_id,
                            result="unclear",
                            severity="unclear",
                            value_text="error",
                            evidence_ref=None,
                            confidence=None,
                            detector_used=None,
                            quality_flags={"raw": {"source": "exception", "error_message": str(e)}},
                            structured_data=None,
                            conditional_check_triggered=False,
                            trigger_name=None,
                            origin=None,
                            playbook_version_id=effective_pb_version_id,
                            plan_item_id=plan_item_uuid,
                            page=None,
                            clause_uid=None,
                            element_id=None,
                            bbox=None,
                            execution_status=CheckExecutionStatus.COMPUTE_FAILED.value,
                            error_details={"type": "exception", "message": str(e)},
                        )

                        await plan_item_repo.mark_terminal(
                            plan_item_uuid,
                            "failed",
                            error_details={"type": "exception", "message": str(e)},
                        )

                        await _enqueue_finalize_via_outbox(
                            session=uow.session,
                            run_id=run_id,
                            plan_item_id=plan_item_id,
                            tenant_id=tenant_id,
                        )

                    except Exception:
                        logger.exception(
                            "run_single_check: failed to persist COMPUTE_FAILED status after exception",
                            run_id=run_id,
                            deal_id=deal_id,
                            doc_id=doc_id,
                            check_id=check_id,
                        )

                    raise

                finally:
                    # finalize_run_if_ready публикуется через outbox в той же транзакции,
                    # что и mark_terminal / upsert_result.
                    # outbox_dispatcher сам доставит задачу после commit.
                    # Прямой send_task_with_context здесь запрещён:
                    # он бы отправил задачу ДО commit, и finalize мог бы
                    # увидеть незафиксированные данные.
                    pass

    return run_async(_run())


# ─── finalize_run_if_ready ────────────────────────────────────────────────────

@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.finalize_run_if_ready",
    track_job=False,
    queue="default",
)
def finalize_run_if_ready(
    self,
    run_id: str,
    tenant_id: str | None = None,
    stage_execution_id: str | None = None,
    orchestration_strategy: str | None = None,
    **kwargs: Any,
) -> dict:
    """
    Проверить, завершены ли все checks по Run, и при готовности финализировать Run.
    """
    logger.info(
        "Finalize run task received",
        run_id=run_id,
        tenant_id=tenant_id,
    )

    run_uuid = uuid.UUID(run_id)

    async def _run() -> dict:
        async with db_uow() as uow:
            run_repo = RunRepository(uow.session)
            plan_item_repo = RunCheckPlanItemRepository(uow.session)
            audit_repo = AuditRepository(uow.session)
            dse_repo = DocumentStageExecutionRepository(uow.session)

            run_obj = await run_repo.get(run_uuid)
            if run_obj is None:
                raise ValueError(f"Run not found: {run_uuid}")

            run_snap: RunSnapshot = snapshot_run(run_obj)

            progress_stats = await plan_item_repo.get_run_progress_stats(run_uuid)
            terminal_items = int(progress_stats["terminal_items"] or 0)
            total_items = int(progress_stats["total_items"] or 0)
            active_items = int(progress_stats["active_items"] or 0)
            has_plan_errors = bool(progress_stats["has_errors"])

            active_stage_executions = await dse_repo.count_active_for_run(run_uuid)
            if active_stage_executions > 0:
                logger.info(
                    "finalize_run_if_ready: active document stage executions remain, postponing",
                    run_id=run_id,
                    active_stage_executions=active_stage_executions,
                    terminal_items=terminal_items,
                    total_items=total_items,
                    active_items=active_items,
                    has_plan_errors=has_plan_errors,
                )
                return {
                    "status": "WAITING_FOR_STAGE_EXECUTIONS",
                    "active_stage_executions": active_stage_executions,
                    "terminal_items": terminal_items,
                    "total_items": total_items,
                    "active_items": active_items,
                    "has_errors": has_plan_errors,
                    "run_status": run_snap.status,
                }

            updated_run = await run_repo.finalize_run_if_finished(run_uuid)
            if updated_run is None:
                raise ValueError(f"Run not found during finalize: {run_uuid}")

            updated_snap: RunSnapshot = snapshot_run(updated_run)

            logger.info(
                "finalize_run_if_ready: run state synced",
                run_id=run_id,
                status=updated_snap.status,
                run_total_checks=updated_snap.total_checks,
                run_completed_checks=updated_snap.completed_checks,
                terminal_items=terminal_items,
                total_items=total_items,
                active_items=active_items,
                has_errors=updated_snap.has_errors,
            )

            if updated_snap.status in (
                RunStatus.COMPLETED.value,
                RunStatus.COMPLETED_WITH_ERRORS.value,
                RunStatus.FAILED.value,
            ):
                if updated_snap.status == RunStatus.COMPLETED.value:
                    action = "ANALYSIS_COMPLETED"
                elif updated_snap.status == RunStatus.COMPLETED_WITH_ERRORS.value:
                    action = "ANALYSIS_COMPLETED_WITH_ERRORS"
                else:
                    action = "ANALYSIS_FAILED"

                # ── Event-driven trigger: генерация резюме ──────────────
                # При успешном завершении Run регистрируем задачу генерации
                # executive summary через Outbox. Outbox гарантирует, что
                # задача уйдёт в Celery только после commit транзакции.
                if updated_snap.status in (
                    RunStatus.COMPLETED.value,
                    RunStatus.COMPLETED_WITH_ERRORS.value,
                ):
                    effective_tenant_for_summary = _resolve_effective_tenant_id(
                        tenant_id, updated_snap
                    )
                    logger.info(
                        "finalize_run_if_ready: enqueuing summary generation via Outbox",
                        run_id=run_id,
                        status=updated_snap.status,
                    )
                    summary_outbox = OutboxService(uow.session)
                    await summary_outbox.enqueue_task(
                        task_name="workers.generate_run_summary",
                        payload={
                            "run_id": run_id,
                            "tenant_id": (
                                str(effective_tenant_for_summary)
                                if effective_tenant_for_summary
                                else None
                            ),
                        },
                        aggregate_type="run",
                        aggregate_id=run_id,
                        dedup_key=f"generate_run_summary:{run_id}",
                        headers={"queue": "heavy_llm_checks"},
                    )

                    # ── Auto-prime English translation post-run ──────────────
                    from services.auto_translation_dispatcher import (
                        dispatch_auto_translation_if_needed,
                    )
                    await dispatch_auto_translation_if_needed(
                        uow.session,
                        run=updated_run,
                        target_locale="en",
                        actor="system:post_run_finalize",
                    )
                # ── конец trigger ───────────────────────────────────────

                # Резолюция tenant_id: task kwargs → run_snap.tenant_id → None.
                # Если tenant не определён — audit пропускается.
                # Лучше пропустить audit запись, чем записать её в zero UUID.
                effective_tenant_id = _resolve_effective_tenant_id(tenant_id, updated_snap)

                if effective_tenant_id is None:
                    logger.error(
                        "finalize_run_if_ready: tenant_id unavailable, "
                        "skipping audit — check task dispatch chain",
                        run_id=run_id,
                        status=updated_snap.status,
                    )
                else:
                    try:
                        await audit_repo.log(
                            tenant_id=effective_tenant_id,
                            deal_id=updated_snap.deal_id,
                            action=action,
                            actor="system",
                            actor_role="worker",
                            details={
                                "run_id": run_id,
                                "status": updated_snap.status,
                                "total_checks": updated_snap.total_checks,
                                "completed_checks": updated_snap.completed_checks,
                                "terminal_items": terminal_items,
                                "total_items": total_items,
                                "active_items": active_items,
                                "has_errors": updated_snap.has_errors,
                            },
                        )
                    except Exception:
                        logger.warning(
                            "finalize_run_if_ready: failed to write audit log",
                            run_id=run_id,
                            status=updated_snap.status,
                        )

                return {
                    "status": updated_snap.status,
                    "total_checks": updated_snap.total_checks,
                    "completed_checks": updated_snap.completed_checks,
                    "has_errors": updated_snap.has_errors,
                }

            if run_snap.total_checks <= 0:
                logger.error(
                    "finalize_run_if_ready: zero-check run is still non-terminal after finalize",
                    run_id=run_id,
                    status=updated_snap.status,
                    run_total_checks=updated_snap.total_checks,
                    run_completed_checks=updated_snap.completed_checks,
                    terminal_items=terminal_items,
                    total_items=total_items,
                    active_items=active_items,
                    has_errors=updated_snap.has_errors,
                )
                raise RuntimeError(
                    f"Run {run_id} has zero total_checks but remained non-terminal after finalize"
                )

            return {
                "status": "NOT_READY",
                "total_checks": updated_snap.total_checks,
                "completed_checks": updated_snap.completed_checks,
                "terminal_items": terminal_items,
                "total_items": total_items,
                "active_items": active_items,
                "has_errors": updated_snap.has_errors,
                "run_status": updated_snap.status,
            }

    return run_async(_run())


    