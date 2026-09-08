"""
Celery adapter for locale-specific result presentation translation.

The worker contains no translation business logic. It delegates all lifecycle,
source-hash validation, LLM execution, and persistence to the application
use case ResultPresentationTranslationUseCase.
"""

from __future__ import annotations

from typing import Any

from core.logging import get_logger
from db.uow import db_uow
from db.repositories.outbox import OutboxRepository
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.result_presentation_translation_use_case import (
    ResultPresentationTranslationUseCase,
)


logger = get_logger(__name__)


RESULT_PRESENTATION_TRANSLATION_TASK_NAME = (
    "workers.process_pending_result_presentations"
)


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name=RESULT_PRESENTATION_TRANSLATION_TASK_NAME,
    track_job=False,
    queue="heavy_llm_checks",
    soft_time_limit=300,
    time_limit=360,
)
def process_pending_result_presentations(
    self,
    run_id: str,
    deal_id: str,
    tenant_id: str,
    locale: str,
    content_version: str = "v1",
    batch_limit: int = 5,
    stage_execution_id: str | None = None,
    orchestration_strategy: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Process one bounded Run + locale presentation batch.

    The task is safe for redelivery:
    - only pending rows are claimed;
    - claim is atomic;
    - terminal rows are never reopened;
    - each batch is processed sequentially to avoid excessive local LLM load.
    """
    _ = self
    _ = stage_execution_id
    _ = orchestration_strategy
    _ = kwargs

    async def _wrapper() -> dict[str, Any]:
        async with db_uow() as uow:
            use_case = ResultPresentationTranslationUseCase(
                db=uow.session,
            )

            return await use_case.execute(
                run_id=run_id,
                deal_id=deal_id,
                tenant_id=tenant_id,
                locale=locale,
                content_version=content_version,
                batch_limit=batch_limit,
            )

    result = run_async(_wrapper())

    logger.info(
        "Result presentation translation batch finished",
        run_id=run_id,
        deal_id=deal_id,
        tenant_id=tenant_id,
        locale=locale,
        content_version=content_version,
        claimed=result.get("claimed"),
        ready=result.get("ready"),
        failed=result.get("failed"),
        stale=result.get("stale"),
    )

    # Outbox-driven continuation: if we hit the batch limit, more pending
    # rows likely exist. Create a new outbox message so the dispatcher picks
    # up the next batch within 5 seconds. This is crash-safe (PostgreSQL-
    # backed) unlike Redis self-chaining.
    if result.get("claimed", 0) >= batch_limit:
        async def _schedule_next() -> None:
            async with db_uow() as uow:
                repo = OutboxRepository(uow.session)
                await repo.create(
                    task_name=RESULT_PRESENTATION_TRANSLATION_TASK_NAME,
                    payload={
                        "run_id": run_id,
                        "deal_id": deal_id,
                        "tenant_id": tenant_id,
                        "locale": locale,
                        "content_version": content_version,
                        "batch_limit": batch_limit,
                    },
                    aggregate_type="run_translation",
                    aggregate_id=f"{run_id}:{locale}",
                    headers={"queue": "heavy_llm_checks"},
                )

        run_async(_schedule_next())
        logger.info(
            "Scheduled next translation batch via outbox continuation",
            run_id=run_id,
            locale=locale,
            claimed=result.get("claimed"),
        )

    return result
