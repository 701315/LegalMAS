"""
Summary Worker — Celery adapter для генерации и перевода executive summary.

Назначение:
- Принимает Celery-вызовы из Outbox/Dispatcher.
- Открывает db_uow.
- Делегирует выполнение в RunSummaryService.
- Возвращает результат.

Позиция в пайплайне:
  - run_deal_checks → finalize_run_if_ready → [Outbox] → generate_run_summary
  - GET /summary?locale=en → [Outbox] → translate_run_summary

Этот файл является тонким транспортным Celery-адаптером и не содержит бизнес-логики.
"""

from __future__ import annotations

import uuid
from typing import Any

from core.logging import get_logger
from db.uow import db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.run_summary_service import RunSummaryService

logger = get_logger(__name__)


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.generate_run_summary",
    track_job=False,
    queue="heavy_llm_checks",
)
def generate_run_summary(
    self,
    run_id: str,
    deal_id: str | None = None,
    tenant_id: str | None = None,
    stage_execution_id: str | None = None,
    orchestration_strategy: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Сгенерировать master executive summary для завершённого Run."""
    _ = self
    run_uuid = uuid.UUID(run_id)

    async def _wrapper() -> dict[str, Any]:
        async with db_uow() as uow:
            service = RunSummaryService(session=uow.session)
            result = await service.generate(run_uuid)
            return result or {}

    result = run_async(_wrapper())

    logger.info(
        "Generate run summary task finished",
        run_id=run_id,
        deal_id=deal_id,
        tenant_id=tenant_id,
        status=result.get("status"),
        model=result.get("model"),
    )

    return result


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.translate_run_summary",
    track_job=False,
    queue="heavy_llm_checks",
)
def translate_run_summary(
    self,
    run_id: str,
    target_locale: str,
    deal_id: str | None = None,
    tenant_id: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Перевести существующее резюме на целевой язык (target_locale)."""
    _ = self
    run_uuid = uuid.UUID(run_id)

    async def _wrapper() -> dict[str, Any]:
        async with db_uow() as uow:
            service = RunSummaryService(session=uow.session)
            result = await service.translate(run_uuid, target_locale)
            return result or {}

    result = run_async(_wrapper())

    logger.info(
        "Translate run summary task finished",
        run_id=run_id,
        target_locale=target_locale,
        deal_id=deal_id,
        tenant_id=tenant_id,
        status=result.get("status"),
    )

    return result