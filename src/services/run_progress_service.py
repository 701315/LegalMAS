# src/services/run_progress_service.py

"""
Streaming-прогресс для Run (SSE).

Сервис отвечает за периодический опрос строки Run в БД и генерацию событий
прогресса для фронтенда в формате Server-Sent Events (SSE).

Функция subscribe_run_progress:
- раз в poll_interval секунд читает Run по run_id;
- при изменении статуса или счётчиков (completed_checks / total_checks)
  эмитит RunProgressEvent;
- после перехода Run в финальный статус (completed / completed_with_errors / failed)
  отдаёт последнее событие и завершает поток.

Архитектурно важно:
- сервис не принимает long-lived AsyncSession извне;
- каждая итерация polling открывает свою короткоживущую session через get_session();
- это не удерживает request-scoped DB session на весь срок жизни StreamingResponse
  и снижает риск забивания пула соединений.

Используется endpoint'ом GET /api/v1/runs/{run_id}/events, который оборачивает
subscribe_run_progress в StreamingResponse с media_type="text/event-stream".
Фронтенд подписывается на этот поток через EventSource и показывает живой
прогресс выполнения проверки (Run) пользователю.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator
from uuid import UUID

from sqlalchemy import select

from api.schemas.runs import RunProgressEvent
from core.logging import get_logger
from db.models.run import Run
from db.session import get_session

logger = get_logger(__name__)

# Финальные статусы, когда можно прекратить стрим
FINAL_STATUSES: set[str] = {
    "completed",
    "completed_with_errors",
    "failed",
}


async def subscribe_run_progress(
    run_id: UUID,
    poll_interval: float = 2.0,
) -> AsyncIterator[RunProgressEvent]:
    """
    Простейшая реализация прогресса Run для SSE.

    Как работает:
    - раз в poll_interval секунд читает Run из БД;
    - если статус/счётчики изменились — отдаёт новое событие;
    - после перехода в финальный статус отдаёт последнее событие и завершает генератор.

    Важно:
    - на каждую итерацию используется отдельная короткоживущая read-session;
    - generator корректно завершается при asyncio.CancelledError.
    """
    last_status: str | None = None
    last_completed: int | None = None
    last_total: int | None = None

    try:
        while True:
            async with get_session() as db:
                stmt = select(Run).where(Run.id == run_id)
                result = await db.execute(stmt)
                run: Run | None = result.scalar_one_or_none()

                if not run:
                    logger.info(
                        "run_progress_not_found",
                        extra={"run_id": str(run_id)},
                    )
                    yield RunProgressEvent(
                        run_id=run_id,
                        status="not_found",
                        completed_checks=0,
                        total_checks=0,
                        current_document=None,
                        error="Run not found",
                    )
                    return

                current_run_id = run.id
                status = run.status or "unknown"
                completed = run.completed_checks or 0
                total = run.total_checks or 0
                error = (
                    str(getattr(run, "error_details", {}).get("message"))
                    if getattr(run, "error_details", None)
                    else None
                )

            # Не спамим одинаковыми событиями, только при изменении
            if (
                status != last_status
                or completed != last_completed
                or total != last_total
            ):
                event = RunProgressEvent(
                    run_id=current_run_id,
                    status=status,
                    completed_checks=completed,
                    total_checks=total,
                    # Здесь при желании можно использовать реальное поле,
                    # если в модели Run появится current_document_name и т.п.
                    current_document=None,
                    error=error,
                )
                logger.info(
                    "run_progress_event",
                    extra={
                        "run_id": str(current_run_id),
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
                    extra={"run_id": str(current_run_id), "status": status},
                )
                return

            await asyncio.sleep(poll_interval)

    except asyncio.CancelledError:
        logger.info(
            "run_progress_cancelled",
            extra={"run_id": str(run_id)},
        )
        raise
