# tasks/export_pending.py

import os
from celery import Celery

from src.db.uow import db_uow
from src.services.export.service import process_one_pending_export

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

app = Celery(
    "legalmas",
    broker=REDIS_URL,
)


@app.task(name="export.process_pending")
def export_process_pending(tenant_id: str = "default") -> bool:
    import asyncio

    async def _run() -> bool:
        async with db_uow() as uow:
            return await process_one_pending_export(
                db=uow.session,
                tenant_id=tenant_id,
            )

    return asyncio.run(_run())
