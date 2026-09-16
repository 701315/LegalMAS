# src/workers/stale_run_reaper.py

"""
Reaper для зависших runs.

Назначение:
- находить runs, застрявшие в статусе 'running' дольше порога;
- убедиться, что у run нет активных document_stage_executions;
- корректно финализировать run (failed / completed_with_errors),
  записав причину в error_details.

Зачем нужен:
- Run может зависнуть, если pipeline упал до фазы чеков
  (например, на build_structure) или если finalize_run_if_ready
  не был вызван из-за hard kill worker'а.
- Существующий reap_stale_stage_executions закрывает только stage executions,
  но не родительский run. Этот reaper закрывает именно runs.

Запускается через Celery Beat с настраиваемым интервалом.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from core.constants import RunStatus
from core.logging import get_logger
from db.repositories.document_stage_execution_repo import (
    DocumentStageExecutionRepository,
)
from db.repositories.run_repo import RunRepository
from db.uow import db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app

logger = get_logger(__name__)

# Порог, после которого run считается зависшим.
# Должен быть больше максимального времени легальной работы pipeline:
# - semantic_enrichment: до 4 ч 35 мин (SEMANTIC_ENRICHMENT_WORKER_TIME_LIMIT_SECONDS);
# - build_structure: до 50 мин (BUILD_STRUCTURE_TIME_LIMIT_SEC);
# - checks: до 1 часа (RUN_SINGLE_CHECK_TIME_LIMIT_SEC) × N параллельных.
# Берём 6 часов — безопасный верхний предел для полного pipeline.
STALE_RUN_THRESHOLD_SECONDS = 6 * 60 * 60  # 6 hours


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.reap_stale_runs",
    track_job=False,
    queue="system",
    soft_time_limit=60,
    time_limit=90,
)
def reap_stale_runs(self, **kwargs: Any) -> dict:
    """
    Закрывает runs, зависшие в 'running' дольше STALE_RUN_THRESHOLD_SECONDS.

    Логика:
    1. Найти runs в 'running' старше порога.
    2. Для каждого проверить count_active_for_run == 0.
       Если активные stages есть — пропустить (run ещё работает).
    3. Определить финальный статус:
       - есть failed stages → FAILED;
       - иначе → COMPLETED_WITH_ERRORS (не завершился нормально).
    4. Обновить run через RunRepository.update_status.
    """
    _ = self

    async def _wrapper() -> dict:
        cutoff = datetime.now(UTC) - timedelta(seconds=STALE_RUN_THRESHOLD_SECONDS)

        async with db_uow() as uow:
            run_repo = RunRepository(uow.session)
            dse_repo = DocumentStageExecutionRepository(uow.session)

            stale_runs = await run_repo.list_stale_running_runs(cutoff)

            if not stale_runs:
                logger.info(
                    "reap_stale_runs: no stale runs found",
                    cutoff=cutoff.isoformat(),
                )
                return {"reaped_count": 0}

            reaped_count = 0
            skipped_count = 0

            for run in stale_runs:
                # Проверяем: есть ли активные stages?
                active = await dse_repo.count_active_for_run(run.id)
                if active > 0:
                    logger.info(
                        "reap_stale_runs: run has active stages, skipping",
                        run_id=str(run.id),
                        active_stages=active,
                    )
                    skipped_count += 1
                    continue

                # Определяем финальный статус по stages
                stages = await dse_repo.list_by_run(run.id)
                has_failed = any(s.status == "failed" for s in stages)

                if has_failed:
                    final_status = RunStatus.FAILED.value
                else:
                    # Нет активных stages, все закрыты, но run не финализировался.
                    # Считаем это "завершено с ошибками", потому что был зависший сбой.
                    final_status = RunStatus.COMPLETED_WITH_ERRORS.value

                error_details = {
                    "reason": "stale_run_reaped",
                    "message": (
                        "Run was stuck in 'running' beyond threshold with no "
                        "active stage executions. Marked terminal by reaper."
                    ),
                    "stale_threshold_seconds": STALE_RUN_THRESHOLD_SECONDS,
                    "previous_status": run.status,
                    "started_at": (
                        run.started_at.isoformat() if run.started_at else None
                    ),
                    "reaped_at": datetime.now(UTC).isoformat(),
                    "total_stages": len(stages),
                    "has_failed_stages": has_failed,
                }

                await run_repo.update_status(
                    run.id,
                    final_status,
                    error_details=error_details,
                )

                reaped_count += 1

                logger.warning(
                    "reap_stale_runs: stale run marked terminal",
                    run_id=str(run.id),
                    previous_status=run.status,
                    new_status=final_status,
                    started_at=(
                        run.started_at.isoformat() if run.started_at else None
                    ),
                    total_stages=len(stages),
                    has_failed_stages=has_failed,
                )

            return {
                "reaped_count": reaped_count,
                "skipped_count": skipped_count,
            }

    return run_async(_wrapper())
