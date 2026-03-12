# src/workers/orchestrator.py

"""
Orchestrator — создаёт Run и запускает пайплайн по сделке.

Назначение:
- Создать запись Run в БД на основе playbook'а сделки.
- Поставить в очередь первую таску пайплайна: workers.import_bundle.
- Вернуть run_id, чтобы фронт/клиент мог отслеживать прогресс.

Архитектура:
- Внешний интерфейс — синхронная функция start_pipeline, которую вызывает API.
- Внутри мы один раз переходим в async‑уровень через безопасный мост
  (run_async → _create_run) без ручного управления event loop.
- Orchestrator сам по себе не выполняет анализ, он только создаёт Run и
  инициирует первую Celery‑таску пайплайна.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.repositories import PlaybookRepository, RunRepository
from db.uow import db_uow
from mas_queue.celery_app import celery_app
from mas_queue.async_helpers import run_async

logger = get_logger(__name__)


def start_pipeline(deal_id: str, tenant_id: str, source_path: str) -> dict:
    """
    Синхронная точка входа для запуска пайплайна по сделке.

    Делает две вещи:
      1) в async‑уровне создаёт Run в БД (run_async → _create_run);
      2) ставит в очередь Celery‑таску workers.import_bundle с run_id.

    Переход в async‑мир делаем через общий мост run_async,
    без ручного создания event loop.
    """

    # 1. Создаём Run в async‑уровне
    run_id = run_async(run_async_entry(deal_id, tenant_id))

    # 2. Стартуем импорт как первую Celery‑таску пайплайна
    celery_app.send_task(
        "workers.import_bundle",
        kwargs={
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "source_path": source_path,
            "run_id": run_id,
            # idempotency_key можно добавить при необходимости
        },
    )

    logger.info(
        "Pipeline started",
        deal_id=deal_id,
        tenant_id=tenant_id,
        run_id=run_id,
        source_path=source_path,
    )

    return {"status": "started", "run_id": run_id}


async def run_async_entry(deal_id: str, tenant_id: str) -> str:
    """
    Async entrypoint: создаёт Run и возвращает run_id.

    Не знает про Celery — только про бизнес‑логику создания Run.
    """
    return await _create_run(deal_id, tenant_id)


async def _create_run(deal_id: str, tenant_id: str) -> str:
    """
    Внутренний helper: создаёт Run запись в БД для сделки.
    """
    async with db_uow() as uow:
        db: AsyncSession = uow.session

        playbook_repo = PlaybookRepository(db)
        run_repo = RunRepository(db)

        deal_uuid = uuid.UUID(deal_id)
        playbook = await playbook_repo.get_for_deal(deal_uuid)
        assert playbook is not None, "No playbook found for deal and no global default"

        run = await run_repo.create(
            deal_id=deal_uuid,
            playbook_version_id=playbook.id,
            model_config_id=playbook.model_config_id,
            bundle_id=None,
            environment_hash=None,
            profile="full",
        )

        logger.info(
            "Run created",
            run_id=str(run.id),
            deal_id=deal_id,
            playbook_id=str(playbook.id),
        )

        return str(run.id)
