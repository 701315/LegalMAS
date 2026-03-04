"""
Orchestrator — creates Run and chains all workers.
Simplified version for vertical slice.
"""

import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from workers.import_worker import import_bundle
from db.repositories import PlaybookRepository, RunRepository
from core.logging import get_logger
from db.uow import db_uow

logger = get_logger(__name__)


def start_pipeline(deal_id: str, tenant_id: str, source_path: str) -> dict:
    """
    Sync entrypoint: создает Run через async run_async и
    ставит в очередь начальный импорт документов.
    """

    # 1. Создаём Run в async-уровне
    run_id = asyncio.run(run_async(deal_id, tenant_id))

    # 2. Стартуем импорт как первую Celery-таску пайплайна
    import_bundle.delay(
        deal_id=deal_id,
        tenant_id=tenant_id,
        source_path=source_path,
        run_id=run_id,
    )

    logger.info(
        "Pipeline started",
        deal_id=deal_id,
        tenant_id=tenant_id,
        run_id=run_id,
        source_path=source_path,
    )

    return {"status": "started", "run_id": run_id}


async def run_async(deal_id: str, tenant_id: str) -> str:
    """
    Async entrypoint: создает Run и возвращает run_id.

    Не знает про Celery/импорт — только про бизнес-логику создания Run.
    """
    return await _create_run(deal_id, tenant_id)


async def _create_run(deal_id: str, tenant_id: str) -> str:
    """
    Внутренний helper: создает Run запись в БД для сделки.
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
