# src/workers/outbox_dispatcher.py

from __future__ import annotations

from typing import Any

from core.logging import get_logger
from db.repositories.outbox import OutboxRepository
from db.uow import db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app

logger = get_logger(__name__)


def _retry_delay(attempt: int) -> int:
    schedule = {
        1: 5,
        2: 15,
        3: 30,
        4: 60,
        5: 120,
        6: 300,
    }
    return schedule.get(attempt, 600)


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.outbox_dispatcher",
    track_job=False,
    queue="system",
)
def outbox_dispatcher(
    self,
    batch_size: int = 100,
    requeue_stuck: bool = True,
    stage_execution_id: str | None = None,
    orchestration_strategy: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    _ = self

    async def _wrapper() -> dict[str, Any]:
        published_count = 0
        failed_count = 0
        requeued_count = 0

        if requeue_stuck:
            async with db_uow() as uow:
                repo = OutboxRepository(uow.session)
                requeued_count = await repo.requeue_stuck_processing()

        async with db_uow() as uow:
            repo = OutboxRepository(uow.session)
            messages = await repo.claim_batch(batch_size=batch_size)

        for message in messages:
            try:
                celery_app.send_task(
                    message.task_name,
                    kwargs=message.payload,
                    headers=message.headers or {},
                )

                async with db_uow() as uow:
                    repo = OutboxRepository(uow.session)
                    await repo.mark_published(message.id)

                published_count += 1
                logger.info(
                    "Outbox message published",
                    outbox_message_id=str(message.id),
                    task_name=message.task_name,
                )
            except Exception as e:
                failed_count += 1
                retry_delay = _retry_delay(message.attempts + 1)

                async with db_uow() as uow:
                    repo = OutboxRepository(uow.session)
                    await repo.mark_failed(
                        message.id,
                        error=str(e),
                        retry_delay_seconds=retry_delay,
                    )

                logger.warning(
                    "Outbox publish failed",
                    outbox_message_id=str(message.id),
                    task_name=message.task_name,
                    attempt=message.attempts + 1,
                    retry_delay_seconds=retry_delay,
                    error=str(e),
                )

        return {
            "claimed_count": len(messages),
            "published_count": published_count,
            "failed_count": failed_count,
            "requeued_count": requeued_count,
        }

    return run_async(_wrapper())
