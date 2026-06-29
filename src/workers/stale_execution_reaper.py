# src/workers/stale_execution_reaper.py

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from core.config import settings
from core.constants import DocumentStageExecutionStatus
from core.logging import get_logger
from db.repositories.document_stage_execution_repo import DocumentStageExecutionRepository
from db.uow import db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app

logger = get_logger(__name__)

# Берём max hard time limit самого длинного stage + запас.
STALE_EXECUTION_THRESHOLD_SECONDS = (
    settings.SEMANTIC_ENRICHMENT_WORKER_TIME_LIMIT_SECONDS + 600
)


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.reap_stale_stage_executions",
    track_job=False,
    queue="system",
    soft_time_limit=60,
    time_limit=90,
)
def reap_stale_stage_executions(
    self,
    **kwargs: Any,
) -> dict:
    """
    Периодически переводит stale active document_stage_executions
    в FAILED, чтобы снять блокировку unique partial index.
    """
    _ = self

    async def _wrapper() -> dict:
        cutoff = datetime.now(UTC) - timedelta(seconds=STALE_EXECUTION_THRESHOLD_SECONDS)

        async with db_uow() as uow:
            dse_repo = DocumentStageExecutionRepository(uow.session)

            stale = await dse_repo.list_stale_active_executions(cutoff)
            if not stale:
                logger.info(
                    "reap_stale_stage_executions: no stale executions found",
                    extra={"cutoff": cutoff.isoformat()},
                )
                return {"reaped_count": 0}

            reaped_count = 0

            for execution in stale:
                await dse_repo.mark_failed(
                    execution.id,
                    error_details={
                        "stage": execution.task_name,
                        "type": "stale_execution_reaped",
                        "reason": "active_execution_older_than_threshold",
                        "message": (
                            "Execution was still active after stale threshold and was "
                            "marked FAILED by reaper to unblock scheduling."
                        ),
                        "stale_threshold_seconds": STALE_EXECUTION_THRESHOLD_SECONDS,
                        "created_at": execution.created_at.isoformat(),
                        "previous_status": execution.status,
                    },
                )
                reaped_count += 1

                logger.warning(
                    "reap_stale_stage_executions: stale execution marked FAILED",
                    extra={
                        "execution_id": str(execution.id),
                        "document_id": str(execution.document_id),
                        "document_version_id": str(execution.document_version_id),
                        "task_name": execution.task_name,
                        "status": execution.status,
                        "created_at": execution.created_at.isoformat(),
                        "celery_task_id": execution.celery_task_id,
                    },
                )

            return {"reaped_count": reaped_count}

    return run_async(_wrapper())


    