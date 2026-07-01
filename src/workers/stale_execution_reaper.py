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

    Дополнительно обновляет Prometheus метрики:
    - stuck_stage_executions_total — сколько stale execution нашлось
    - dlq_size — текущий размер DLQ таблицы
    """
    _ = self

    async def _wrapper() -> dict:
        cutoff = datetime.now(UTC) - timedelta(seconds=STALE_EXECUTION_THRESHOLD_SECONDS)

        async with db_uow() as uow:
            dse_repo = DocumentStageExecutionRepository(uow.session)

            stale = await dse_repo.list_stale_active_executions(cutoff)

            # ── Обновить Prometheus metrics ───────────────────────────────
            _update_operational_metrics(stuck_count=len(stale), session=uow.session)
            # ─────────────────────────────────────────────────────────────

            if not stale:
                logger.info(
                    "reap_stale_stage_executions: no stale executions found",
                    cutoff=cutoff.isoformat(),
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
                    execution_id=str(execution.id),
                    document_id=str(execution.document_id),
                    document_version_id=str(execution.document_version_id),
                    task_name=execution.task_name,
                    status=execution.status,
                    created_at=execution.created_at.isoformat(),
                    celery_task_id=execution.celery_task_id,
                )

            return {"reaped_count": reaped_count}

    return run_async(_wrapper())


def _update_operational_metrics(stuck_count: int, session: Any) -> None:
    """
    Обновить Prometheus operational metrics.

    Вызывается из reap_stale_stage_executions.
    Ошибки изолированы — не влияют на основную логику reaper.
    """
    try:
        from ops.metrics import get_metrics  # noqa: PLC0415
        _m = get_metrics()

        # Количество stuck executions.
        _m.stuck_stage_executions_total.set(stuck_count)

        # Размер DLQ — читаем count напрямую через SQL.
        # Не используем DLQManager чтобы не создавать лишний UoW —
        # у нас уже есть сессия.
        import asyncio  # noqa: PLC0415
        from sqlalchemy import func, select  # noqa: PLC0415
        from db.models.ops import DLQRecord  # noqa: PLC0415

        async def _get_dlq_count() -> int:
            result = await session.execute(select(func.count(DLQRecord.id)))
            return int(result.scalar_one() or 0)

        # run_async уже есть в контексте воркера.
        from mas_queue.async_helpers import run_async as _run_async  # noqa: PLC0415
        dlq_count = _run_async(_get_dlq_count())
        _m.dlq_size.set(dlq_count)

        logger.info(
            "reap_stale_stage_executions: operational metrics updated",
            stuck_executions=stuck_count,
            dlq_size=dlq_count,
        )

    except Exception as exc:
        logger.warning(
            "reap_stale_stage_executions: failed to update operational metrics",
            error=str(exc),
        )


        