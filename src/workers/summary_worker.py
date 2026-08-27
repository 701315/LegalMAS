# src/workers/summary_worker.py

"""
Summary Worker — тонкий Celery adapter для генерации executive summary.

Назначение:
- Принимает Celery task вызов после завершения Run (через Outbox).
- Открывает db_uow.
- Вызывает RunSummaryService.generate(run_id).
- Возвращает результат обратно в Celery.

Позиция в пайплайне:
  run_deal_checks → finalize_run_if_ready → [Outbox] → generate_run_summary

Важно:
- Этот файл НЕ содержит бизнес-логики генерации.
- Вся логика живёт в RunSummaryService (services layer).
- Worker — транспортный адаптер между Celery и application layer.

Архитектура retry (два уровня):
- Уровень 1 (MASBaseTask): инфраструктурные сбои (DB, Redis) →
  Celery retry с backoff 10→30→90 сек, макс 3 попытки → DLQ.
- Уровень 2 (RunSummaryService): LLM-сбои (OOM, timeout, bad output) →
  запись в БД status='failed' + retry_count + next_retry_at →
  SummaryDispatcher подхватит через 300 сек.
  Эти два уровня НЕ конфликтуют: LLM-сбой не бросает исключение
  из generate(), а записывается в БД и возвращает response.
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
    """
    Сгенерировать executive summary для завершённого Run.

    Параметры:
    - run_id: идентификатор завершённого Run.
    - deal_id: идентификатор сделки (для correlation context).
    - tenant_id: идентификатор tenant'а (для DLQ и audit).

    Вызывается:
    - автоматически через Outbox после finalize_run_if_ready;
    - через SummaryDispatcher (recovery) для зависших/failed записей.
    """
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


