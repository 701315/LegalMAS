"""
Orchestrator — creates Run and chains all workers.
Simplified version for vertical slice.
"""

import uuid

from src.core.logging import get_logger
from src.queue.async_helpers import get_worker_session, run_async

logger = get_logger(__name__)


def start_pipeline(deal_id: str, tenant_id: str, source_path: str) -> dict:
    run_id = run_async(_create_run(deal_id, tenant_id))
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

    async with get_worker_session() as session:
        playbook_repo = PlaybookRepository(session)
        run_repo = RunRepository(session)

        deal_uuid = uuid.UUID(deal_id)
        playbook = await playbook_repo.get_for_deal(deal_uuid)
        assert playbook is not None, "No playbook found for deal and no global default"

        run = await run_repo.create(
            deal_id=deal_uuid,
            playbook_version_id=playbook.id,
            model_config_id=playbook.model_config_id,  # либо None, если сделал опциональным
            bundle_id=None,
            environment_hash=None,
            profile="full",
        )
        return str(run.id)
