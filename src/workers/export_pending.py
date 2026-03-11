# src/workers/export_pending.py


"""
Export Pending Worker.

Назначение:
  - периодически проверяет наличие "ожидающих" задач экспорта в БД;
  - берёт ОДНУ такую задачу и пытается её обработать;
  - вся бизнес-логика обработки инкапсулирована в services.export.service.process_one_pending_export;
  - работает через db_uow, чтобы изменения по одному экспорту были атомарными.

Таким образом, этот воркер по шагам "разгрызает" очередь отложенных экспортов.
Для пользователя это означает: если экспорт поставлен в ожидание, именно этот
воркер со временем его подхватит и доведёт до конца.
"""

import asyncio

from db.uow import db_uow
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.export.service import process_one_pending_export


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="export.process_pending",
    track_job=False,
    queue="default",
)
def export_process_pending(self, tenant_id: str = "default") -> bool:
    """
    Синхронная Celery‑таска обработки одной "ожидающей" задачи экспорта.

    Внутри:
      - создаёт event loop;
      - открывает UnitOfWork через db_uow();
      - вызывает process_one_pending_export(db=uow.session, tenant_id=...);
      - возвращает True, если что‑то было обработано, иначе False.
    """

    async def _run() -> bool:
        async with db_uow() as uow:
            return await process_one_pending_export(
                db=uow.session,
                tenant_id=tenant_id,
            )

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_run())
    finally:
        asyncio.set_event_loop(None)
        loop.close()
