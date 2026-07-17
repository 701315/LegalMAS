"""
CheckRunner Worker — запуск playbook-checks по уже классифицированным документам сделки.

Позиция в пайплайне:
- import → extract → pii → structure → classify → run_deal_checks → export_results.

Что делает:
- Для одного Run по deal_id:
  - вытаскивает все non-duplicate документы сделки;
  - строит execution plan (пары doc_id/check_id);
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
from mas_queue.task_dispatcher import send_task_with_context
from ops.metrics import get_metrics

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

                runner = CheckRunner(
                    llm_client=_shared_llm_client,
                    playbook_version_id=run_snap.playbook_version_id,
                    checks_mode=run_snap.checks_mode or "global_and_doc_type",
                    run_repo=run_repo,
                    checks_scope=run_snap.checks_scope,
                )

                plan = await runner.plan_checks_for_run(
                    session=uow.session,
                    deal_id=deal_uuid,
                    run_id=run_uuid,
                    playbook=playbook,
                )

                pairs = plan.get("pairs", [])
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

                await run_repo.update_status(
                    run_uuid,
                    RunStatus.RUNNING.value,
                    total_checks=total_checks,
                )

                scheduled = 0
                for pair in pairs:
                    send_task_with_context(
                        "workers.run_single_check",
                        kwargs={
                            "run_id": run_id,
                            "deal_id": deal_id,
                            "doc_id": pair["doc_id"],
                            "check_id": pair["check_id"],
                            "playbook_version_id": str(run_snap.playbook_version_id),
                            "checks_mode": run_snap.checks_mode,
                            "force": False,
                            "tenant_id": tenant_id,        
                        },
                        queue="heavy_llm_checks",
                    )
                    scheduled += 1

                try:
                    # Резолюция tenant_id: task kwargs → run_snap → None.
                    # Если tenant не определён — audit пропускается, не пишем в zero UUID.
                    effective_tenant = _resolve_effective_tenant_id(tenant_id, run_snap)
                    if effective_tenant is None:
                        logger.error(
                            "run_deal_checks: tenant_id unavailable, skipping CHECKS_SCHEDULED audit",
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
                                "total_checks": total_checks,
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
                    planned_checks=total_checks,
                    scheduled_checks=scheduled,
                    planning_errors=errors,
                    status=RunStatus.RUNNING.value,
                )

                if total_checks == 0:
                    logger.warning(
                        "Run deal checks scheduler: zero checks planned, finalizing run immediately",
                        run_id=run_id,
                        deal_id=deal_id,
                        processed_docs=processed_docs,
                        planning_errors=errors,
                        checks_mode=run_snap.checks_mode,
                        checks_scope=run_snap.checks_scope,
                    )

                    finalized = await run_repo.finalize_run_if_finished(run_uuid)
                    if finalized is None:
                        raise ValueError(f"Run not found during zero-check finalize: {run_uuid}")

                    # Снимаем snapshot финализированного Run сразу после получения.
                    finalized_snap: RunSnapshot = snapshot_run(finalized)

                    return {
                        "status": finalized_snap.status,
                        "processed_docs": processed_docs,
                        "total_checks": total_checks,
                        "scheduled_checks": scheduled,
                        "errors": errors,
                        "duration_sec": round(duration, 2),
                    }

                return {
                    "status": RunStatus.RUNNING.value,
                    "processed_docs": processed_docs,
                    "total_checks": total_checks,
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

                effective_pb_version_id = pb_version_uuid

                try:
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
                    )

                    exec_result = outcome["exec_result"]
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
                        page=None,
                        clause_uid=None,
                        element_id=None,
                        bbox=None,
                        execution_status=CheckExecutionStatus.TIMEOUT.value,
                        error_details={"type": "soft_time_limit", "message": str(e)},
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
                    except Exception:
                        logger.exception(
                            "run_single_check: failed to persist PERSIST_FAILED sentinel row",
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
                            page=None,
                            clause_uid=None,
                            element_id=None,
                            bbox=None,
                            execution_status=CheckExecutionStatus.COMPUTE_FAILED.value,
                            error_details={"type": "exception", "message": str(e)},
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
                    try:
                        send_task_with_context(
                            "workers.finalize_run_if_ready",
                            kwargs={
                                "run_id": run_id,
                                # tenant_id приходит из параметров задачи run_single_check.
                                # Передаём явно, чтобы finalize_run_if_ready мог корректно
                                # атрибутировать audit записи финализации Run.
                                "tenant_id": tenant_id,
                            },
                            queue="default",
                        )
                    except Exception:
                        logger.exception(
                            "run_single_check: failed to enqueue finalize_run_if_ready",
                            run_id=run_id,
                            doc_id=doc_id,
                            check_id=check_id,
                        )

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
    # ИСПРАВЛЕНО: добавлен tenant_id.
    # Ранее отсутствовал — audit записи финализации Run записывались с
    # tenant_id=uuid.UUID(int=0) (zero UUID = несуществующий tenant).
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
            result_repo = ResultRepository(uow.session)
            audit_repo = AuditRepository(uow.session)
            dse_repo = DocumentStageExecutionRepository(uow.session)

            run_obj = await run_repo.get(run_uuid)
            if run_obj is None:
                raise ValueError(f"Run not found: {run_uuid}")

            run_snap: RunSnapshot = snapshot_run(run_obj)

            finished_checks = await result_repo.count_finished_checks_for_run(run_uuid)
            materialized_checks = await result_repo.count_distinct_checks_for_run(run_uuid)

            active_stage_executions = await dse_repo.count_active_for_run(run_uuid)
            if active_stage_executions > 0:
                logger.info(
                    "finalize_run_if_ready: active document stage executions remain, postponing",
                    run_id=run_id,
                    active_stage_executions=active_stage_executions,
                    finished_checks=finished_checks,
                    materialized_checks=materialized_checks,
                )
                return {
                    "status": "WAITING_FOR_STAGE_EXECUTIONS",
                    "active_stage_executions": active_stage_executions,
                    "finished_checks": finished_checks,
                    "materialized_checks": materialized_checks,
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
                materialized_checks=materialized_checks,
                finished_checks=finished_checks,
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

                # ИСПРАВЛЕНО: используем tenant_id из параметра задачи.
                # Ранее: uuid.UUID(int=0) — zero UUID, несуществующий tenant.
                # Теперь: реальный tenant_id из run_single_check → finalize_run_if_ready.
                # Fallback: run_snap.tenant_id если доступен, иначе zero UUID с предупреждением.
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
                                "materialized_checks": materialized_checks,
                                "finished_checks": finished_checks,
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
                    materialized_checks=materialized_checks,
                    finished_checks=finished_checks,
                    has_errors=updated_snap.has_errors,
                )
                raise RuntimeError(
                    f"Run {run_id} has zero total_checks but remained non-terminal after finalize"
                )

            return {
                "status": "NOT_READY",
                "total_checks": run_snap.total_checks,
                "finished_checks": finished_checks,
                "materialized_checks": materialized_checks,
                "run_status": updated_snap.status,
            }

    return run_async(_run())




    