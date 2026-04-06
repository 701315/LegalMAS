# src/workers/orchestrator.py

"""
Pipeline Orchestrator — создаёт Run и запускает первую задачу пайплайна по сделке.

Назначение:
- Создать запись Run в БД на основе playbook'а сделки.
- Поставить в очередь первую Celery-задачу пайплайна: workers.import_bundle.
- Вернуть run_id, чтобы API / фронт могли отслеживать прогресс запуска.

Архитектура:
- Внешний интерфейс — синхронная функция start_pipeline(...), которую вызывает API.
- Внутри один раз выполняется безопасный переход sync → async через run_async(...)
  для создания Run в БД.
- Orchestrator сам не выполняет импорт/анализ документов; он только:
  1) создаёт Run;
  2) инициирует первую задачу пайплайна.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import PermanentError
from core.logging import get_logger
from db.repositories import PlaybookRepository, RunRepository
from db.uow import db_uow
from mas_queue.async_helpers import run_async
from mas_queue.celery_app import celery_app

logger = get_logger(__name__)


def start_pipeline(deal_id: str, tenant_id: str, source_path: str) -> dict[str, Any]:
    """
    Синхронная точка входа для запуска пайплайна по сделке.

    Делает две вещи:
      1) создаёт Run в БД;
      2) ставит в очередь первую Celery-задачу workers.import_bundle.

    Если первую задачу не удалось поставить в очередь,
    исключение пробрасывается наружу — API не должен отвечать "started",
    если фактический запуск не произошёл.
    """
    logger.info(
        "Pipeline start requested",
        deal_id=deal_id,
        tenant_id=tenant_id,
        source_path=source_path,
    )

    # 1. Создаём Run в async-уровне
    run_id = run_async(create_run_async(deal_id=deal_id, tenant_id=tenant_id))

    # 2. Ставим первую задачу пайплайна в очередь
    try:
        celery_app.send_task(
            "workers.import_bundle",
            kwargs={
                "deal_id": deal_id,
                "tenant_id": tenant_id,
                "source_path": source_path,
                "run_id": run_id,
            },
        )
    except Exception as e:
        logger.exception(
            "Failed to enqueue first pipeline task",
            deal_id=deal_id,
            tenant_id=tenant_id,
            run_id=run_id,
            source_path=source_path,
            task_name="workers.import_bundle",
            error=str(e),
        )
        raise PermanentError(
            f"Run {run_id} was created, but failed to enqueue workers.import_bundle"
        ) from e

    logger.info(
        "Pipeline started",
        deal_id=deal_id,
        tenant_id=tenant_id,
        run_id=run_id,
        source_path=source_path,
        first_task="workers.import_bundle",
    )

    return {
        "status": "started",
        "run_id": run_id,
    }


async def create_run_async(*, deal_id: str, tenant_id: str) -> str:
    """
    Async entrypoint для создания Run.

    Не знает про Celery и не запускает таски —
    только про бизнес-логику создания записи Run в БД.
    """
    return await _create_run(deal_id=deal_id, tenant_id=tenant_id)


async def _create_run(*, deal_id: str, tenant_id: str) -> str:
    """
    Создать запись Run в БД для указанной сделки.

    Логика:
    - найти playbook, привязанный к сделке, либо глобальный default;
    - создать Run на базе найденного playbook;
    - вернуть run_id как строку.
    """
    async with db_uow() as uow:
        db: AsyncSession = uow.session

        playbook_repo = PlaybookRepository(db)
        run_repo = RunRepository(db)

        deal_uuid = uuid.UUID(deal_id)

        playbook = await playbook_repo.get_for_deal(deal_uuid)
        if playbook is None:
            logger.error(
                "Cannot create run: no playbook found for deal",
                deal_id=deal_id,
                tenant_id=tenant_id,
            )
            raise PermanentError(
                "No playbook found for deal and no global default"
            )

        run = await run_repo.create(
            deal_id=deal_uuid,
            playbook_version_id=playbook.id,
            model_config_id=playbook.model_config_id,
            bundle_id=None,
            environment_hash=None,
            profile="full",
            checks_mode="global_and_doc_type",
        )

        logger.info(
            "Run created",
            run_id=str(run.id),
            deal_id=deal_id,
            tenant_id=tenant_id,
            playbook_id=str(playbook.id),
            model_config_id=str(playbook.model_config_id)
            if playbook.model_config_id
            else None,
            profile="full",
            checks_mode="global_and_doc_type",
        )

        return str(run.id)