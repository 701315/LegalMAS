"""
Orchestrator — creates Run and chains all workers.
Simplified version for vertical slice.
"""

import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.db.uow import db_uow

logger = get_logger(__name__)


def start_pipeline(deal_id: str, tenant_id: str, source_path: str) -> dict:
    """
    Sync entrypoint: creates Run and kicks off import worker.
    """
    run_id = asyncio.run(_create_run(deal_id, tenant_id))

    from src.workers.import_worker import import_bundle

    import_bundle.delay(
        deal_id=deal_id,
        tenant_id=tenant_id,
        source_path=source_path,
        run_id=run_id,
    )
    return {"status": "started", "run_id": run_id}


async def _create_run(deal_id: str, tenant_id: str) -> str:
    from src.db.repositories import PlaybookRepository, RunRepository

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
        return str(run.id)
