# src/services/run_progress_service.py

from __future__ import annotations

import asyncio
from typing import AsyncIterator
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.run import Run
from api.schemas.runs import RunProgressEvent

from core.logging import get_logger
logger = get_logger(__name__)

# Финальные статусы, когда можно прекратить стрим
FINAL_STATUSES: set[str] = {
    "completed",
    "completed_with_errors",
    "failed",
}


async def subscribe_run_progress(
    db: AsyncSession,
    run_id: UUID,
    poll_interval: float = 2.0,
) -> AsyncIterator[RunProgressEvent]:
    """
    Простейшая реализация прогресса Run для SSE.

    Как работает:
    - раз в poll_interval секунд читает Run из БД;
    - если статус/счётчики изменились — отдаёт новое событие;
    - после перехода в финальный статус отдаёт последнее событие и завершает генератор.

    Это даёт реальный "пуш" для фронта без необходимости править воркеры.
    """

    last_status: str | None = None
    last_completed: int | None = None
    last_total: int | None = None

    while True:
        stmt = select(Run).where(Run.id == run_id)
        result = await db.execute(stmt)
        run: Run | None = result.scalar_one_or_none()

        if not run:
            # Если run не найден — отдаём одно событие и выходим
            yield RunProgressEvent(
                run_id=run_id,
                status="not_found",
                completed_checks=0,
                total_checks=0,
                error="Run not found",
            )
            return

        status = run.status or "unknown"
        completed = run.completed_checks or 0
        total = run.total_checks or 0

        # Не спамим одинаковыми событиями, только при изменении
        if (
            status != last_status
            or completed != last_completed
            or total != last_total
        ):
            event = RunProgressEvent(
                run_id=run.id,
                status=status,
                completed_checks=completed,
                total_checks=total,
                # Здесь при желании можно использовать реальное поле,
                # если в модели Run появится current_document_name и т.п.
                current_document=None,
                error=(
                    str(getattr(run, "error_details", {}).get("message"))
                    if getattr(run, "error_details", None)
                    else None
                ),
            )
            logger.info(
                "run_progress_event",
                extra={
                    "run_id": str(run.id),
                    "status": status,
                    "completed": completed,
                    "total": total,
                },
            )
            yield event

            last_status = status
            last_completed = completed
            last_total = total

        if status in FINAL_STATUSES:
            # Финальный статус — завершаем стрим
            logger.info(
                "run_progress_final",
                extra={"run_id": str(run.id), "status": status},
            )
            return

        await asyncio.sleep(poll_interval)
