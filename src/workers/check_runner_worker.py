# src/workers/check_runner_worker.py

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
"""

from __future__ import annotations

import time
import uuid

from celery.exceptions import SoftTimeLimitExceeded

from core.constants import RunStatus
from core.logging import get_logger
from db.repositories.document_repo import DocumentRepository
from db.repositories.playbook_repo import PlaybookRepository
from db.repositories.result_repo import ResultRepository
from db.repositories.run_repo import RunRepository
from db.uow import db_uow
from engine.llm.client import LLMClient
from engine.playbook.loader import load_playbook_from_version
from engine.checks_runner import CheckRunner
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from ops.metrics import get_metrics

logger = get_logger(__name__)


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.run_deal_checks",
    track_job=False,
)
def run_deal_checks(
    self,
    run_id: str,
    deal_id: str,
    tenant_id: str | None = None,
) -> dict:
    """
    Celery-task scheduler уровня Run:
    - загружает Run и Playbook;
    - строит пары (doc_id, check_id);
    - публикует отдельные задачи run_single_check;
    - переводит Run в RUNNING и обновляет total_checks;
    - не выполняет сами checks внутри себя.
    """
    logger.info(
        "Run deal checks scheduler received",
        extra={
            "run_id": run_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
        },
    )

    started_at = time.time()
    metrics = get_metrics()
    llm_client = LLMClient()
    run_uuid = uuid.UUID(run_id)
    deal_uuid = uuid.UUID(deal_id)

    async def _run() -> dict:
        async with db_uow() as uow:
            run_repo = RunRepository(uow.session)
            pb_repo = PlaybookRepository(uow.session)

            try:
                logger.info(
                    "Run deal checks scheduler: loading run and playbook",
                    extra={
                        "run_id": run_id,
                        "deal_id": deal_id,
                    },
                )

                run_obj = await run_repo.get(run_uuid)
                if run_obj is None:
                    raise ValueError(f"Run not found: {run_uuid}")

                started = await run_repo.try_start_run(run_uuid)
                if not started and run_obj.status != RunStatus.RUNNING.value:
                    logger.info(
                        "Run deal checks scheduler: run already started or finalized, skipping",
                        extra={
                            "run_id": run_id,
                            "deal_id": deal_id,
                            "current_status": run_obj.status,
                        },
                    )
                    return {
                        "status": "SKIPPED",
                        "reason": "run_not_pending",
                        "current_status": run_obj.status,
                    }

                checks_mode = getattr(run_obj, "checks_mode", "global_and_doc_type")
                checks_scope = getattr(run_obj, "checks_scope", None)


                pb_version = await pb_repo.get_by_id(run_obj.playbook_version_id)
                if pb_version is None:
                    raise ValueError(
                        f"PlaybookVersion not found: {run_obj.playbook_version_id}"
                    )


                playbook = load_playbook_from_version(pb_version)


                logger.info(
                    "Run deal checks scheduler: playbook loaded",
                    extra={
                        "run_id": run_id,
                        "deal_id": deal_id,
                        "playbook_version_id": str(run_obj.playbook_version_id),
                        "checks_mode": checks_mode,
                        "checks_scope": checks_scope,
                    },
                )


                runner = CheckRunner(
                    llm_client=llm_client,
                    playbook_version_id=run_obj.playbook_version_id,
                    checks_mode=checks_mode,
                    run_repo=run_repo,
                    checks_scope=checks_scope,
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

                await run_repo.update_status(
                    run_uuid,
                    RunStatus.RUNNING.value,
                    total_checks=total_checks,
                )

                scheduled = 0
                for pair in pairs:
                    celery_app.send_task(
                        "workers.run_single_check",
                        kwargs={
                            "run_id": run_id,
                            "deal_id": deal_id,
                            "doc_id": pair["doc_id"],
                            "check_id": pair["check_id"],
                            "playbook_version_id": str(run_obj.playbook_version_id),
                            "checks_mode": checks_mode,
                            "force": False,
                        },
                        queue="heavy_llm",
                    )
                    scheduled += 1

                duration = time.time() - started_at

                try:
                    metrics.checks_duration.labels(stage="deal_checks_schedule").observe(duration)
                except Exception:
                    logger.exception(
                        "run_deal_checks scheduler: failed to update checks_duration metric",
                        extra={
                            "run_id": run_id,
                            "deal_id": deal_id,
                        },
                    )

                logger.info(
                    "Run deal checks scheduler completed",
                    extra={
                        "run_id": run_id,
                        "deal_id": deal_id,
                        "duration_sec": round(duration, 2),
                        "processed_docs": processed_docs,
                        "planned_checks": total_checks,
                        "scheduled_checks": scheduled,
                        "planning_errors": errors,
                        "status": RunStatus.RUNNING.value,
                    },
                )

                if total_checks == 0:
                    finalized = await run_repo.finalize_run_if_finished(run_uuid)
                    return {
                        "status": finalized.status if finalized else RunStatus.RUNNING.value,
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
                    extra={
                        "run_id": run_id,
                        "deal_id": deal_id,
                        "error": str(e),
                    },
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


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.run_single_check",
    track_job=False,
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
) -> dict:
    """
    Выполнить одну проверку (check_id) для одного документа в рамках Run.

    Логика:
    - находим Run, Playbook и Document;
    - выполняем одну проверку через CheckRunner;
    - сохраняем/обновляем CheckResult с execution_status;
    - в finally публикуем finalize_run_if_ready для возможной финализации всего Run.
    """
    logger.info(
        "Run single check task received",
        extra={
            "run_id": run_id,
            "deal_id": deal_id,
            "doc_id": doc_id,
            "check_id": check_id,
            "playbook_version_id": playbook_version_id,
            "checks_mode": checks_mode,
            "force": force,
        },
    )

    started_at = time.time()
    llm_client = LLMClient()
    run_uuid = uuid.UUID(run_id)
    deal_uuid = uuid.UUID(deal_id)
    doc_uuid = uuid.UUID(doc_id)
    pb_version_uuid = uuid.UUID(playbook_version_id) if playbook_version_id else None

    async def _run() -> dict:
        async with db_uow() as uow:
            run_repo = RunRepository(uow.session)
            pb_repo = PlaybookRepository(uow.session)
            doc_repo = DocumentRepository(uow.session)
            result_repo = ResultRepository(uow.session)

            try:
                run_obj = await run_repo.get(run_uuid)
                if run_obj is None:
                    raise ValueError(f"Run not found: {run_uuid}")

                effective_checks_mode = checks_mode or getattr(
                    run_obj, "checks_mode", "global_and_doc_type"
                )
                effective_pb_version_id = pb_version_uuid or run_obj.playbook_version_id

                if run_obj.deal_id != deal_uuid:
                    logger.warning(
                        "run_single_check: deal_id mismatch between task and Run",
                        extra={
                            "run_id": run_id,
                            "deal_id_task": str(deal_uuid),
                            "deal_id_run": str(run_obj.deal_id),
                        },
                    )

                pb_version = await pb_repo.get_by_id(effective_pb_version_id)
                if pb_version is None:
                    raise ValueError(
                        f"PlaybookVersion not found: {effective_pb_version_id}"
                    )
                playbook = load_playbook_from_version(pb_version)

                doc = await doc_repo.get_by_id(doc_uuid)
                if doc is None:
                    raise ValueError(f"Document not found: {doc_uuid}")

                existing = await result_repo.get_one(run_uuid, doc_uuid, check_id)
                if existing and existing.execution_status == "SUCCESS" and not force:
                    logger.info(
                        "run_single_check: result already SUCCESS, skipping",
                        extra={
                            "run_id": run_id,
                            "doc_id": doc_id,
                            "check_id": check_id,
                        },
                    )
                    return {
                        "status": "SKIPPED",
                        "reason": "already_success",
                    }

                checks_scope = getattr(run_obj, "checks_scope", None)

                runner = CheckRunner(
                    llm_client=llm_client,
                    playbook_version_id=effective_pb_version_id,
                    checks_mode=effective_checks_mode,
                    run_repo=run_repo,
                    checks_scope=checks_scope,
                )

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

                logger.info(
                    "run_single_check completed",
                    extra={
                        "run_id": run_id,
                        "deal_id": deal_id,
                        "doc_id": doc_id,
                        "check_id": check_id,
                        "result": exec_result.get("result"),
                        "severity": exec_result.get("severity"),
                        "duration_sec": round(duration, 2),
                    },
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
                    extra={
                        "run_id": run_id,
                        "doc_id": doc_id,
                        "check_id": check_id,
                        "error": str(e),
                    },
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
                    execution_status="TIMEOUT",
                    error_details={"type": "soft_time_limit", "message": str(e)},
                )
                raise

            except Exception as e:
                logger.exception(
                    "run_single_check failed",
                    extra={
                        "run_id": run_id,
                        "deal_id": deal_id,
                        "doc_id": doc_id,
                        "check_id": check_id,
                        "error": str(e),
                    },
                )
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
                    execution_status="FAILED",
                    error_details={"type": "exception", "message": str(e)},
                )
                raise

            finally:
                try:
                    celery_app.send_task(
                        "workers.finalize_run_if_ready",
                        kwargs={"run_id": run_id},
                        queue="default",
                    )
                except Exception:
                    logger.exception(
                        "run_single_check: failed to enqueue finalize_run_if_ready",
                        extra={
                            "run_id": run_id,
                            "doc_id": doc_id,
                            "check_id": check_id,
                        },
                    )

    return run_async(_run())


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
) -> dict:
    """
    Проверить, завершены ли все checks по Run, и при готовности финализировать Run.

    Используем единую логику RunRepository.finalize_run_if_finished(), чтобы не
    дублировать правила переходов RUNNING / COMPLETED / COMPLETED_WITH_ERRORS.
    """
    logger.info(
        "Finalize run task received",
        extra={"run_id": run_id},
    )

    run_uuid = uuid.UUID(run_id)

    async def _run() -> dict:
        async with db_uow() as uow:
            run_repo = RunRepository(uow.session)
            result_repo = ResultRepository(uow.session)

            run_obj = await run_repo.get(run_uuid)
            if run_obj is None:
                raise ValueError(f"Run not found: {run_uuid}")

            total_checks = int(getattr(run_obj, "total_checks", 0) or 0)
            finished_checks = await result_repo.count_finished_checks_for_run(run_uuid)
            materialized_checks = await result_repo.count_distinct_checks_for_run(run_uuid)

            updated_run = await run_repo.finalize_run_if_finished(run_uuid)
            if updated_run is None:
                raise ValueError(f"Run not found during finalize: {run_uuid}")

            logger.info(
                "finalize_run_if_ready: run state synced",
                extra={
                    "run_id": run_id,
                    "status": updated_run.status,
                    "run_total_checks": updated_run.total_checks,
                    "run_completed_checks": updated_run.completed_checks,
                    "materialized_checks": materialized_checks,
                    "finished_checks": finished_checks,
                    "has_errors": updated_run.has_errors,
                },
            )

            if updated_run.status in (
                RunStatus.COMPLETED.value,
                RunStatus.COMPLETED_WITH_ERRORS.value,
                RunStatus.FAILED.value,
            ):
                return {
                    "status": updated_run.status,
                    "total_checks": updated_run.total_checks,
                    "completed_checks": updated_run.completed_checks,
                    "has_errors": updated_run.has_errors,
                }

            if total_checks <= 0:
                return {
                    "status": "NOT_READY",
                    "reason": "no_total_checks",
                    "materialized_checks": materialized_checks,
                    "finished_checks": finished_checks,
                }

            return {
                "status": "NOT_READY",
                "total_checks": total_checks,
                "finished_checks": finished_checks,
                "materialized_checks": materialized_checks,
                "run_status": updated_run.status,
            }

    return run_async(_run())

