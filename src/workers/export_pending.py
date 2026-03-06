# src/workers/export_pending.py

from celery import Celery

from db.uow import db_uow
from services.export.service import process_one_pending_export

app = Celery("legalmas")


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