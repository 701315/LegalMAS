# src/workers/export_pending.py

"""
Export Pending Worker.

Этот модуль содержит Celery‑воркер, который по одному обрабатывает
отложенные (pending) задачи экспорта из базы данных.

Назначение:
  - периодически проверять наличие задач экспорта в состоянии "ожидание";
  - брать одну такую задачу и пытаться её обработать до конца;
  - обеспечивать атомарность изменений по одному экспорту через db_uow;
  - инкапсулировать всю бизнес‑логику обработки в
    services.export.service.process_one_pending_export.

Поведение:
  - если в БД есть хотя бы один экспорт в статусе "pending",
    воркер берёт его, выполняет все шаги обработки и возвращает True;
  - если подходящих задач нет, воркер ничего не делает и возвращает False;
  - если во время работы происходит временная ошибка (БД, сеть и т.п.),
    MASBaseTask помечает её как транзиентную и инициирует повторный запуск.

Архитектура:
  - снаружи — синхронная Celery‑таска export_process_pending (def),
    зарегистрированная в общем приложении mas_queue.celery_app.celery_app;
  - внутри — один переход sync → async через run_async(), который запускает
    асинхронную функцию _export_process_pending_async(...);
  - _export_process_pending_async открывает UnitOfWork через db_uow(),
    вызывает process_one_pending_export(db=uow.session, tenant_id=...),
    и возвращает булево значение "что‑то обработано / нет".

Таким образом, этот воркер постепенно «разгрызает» очередь отложенных экспортов.
Для пользователя это означает: если экспорт находится в ожидании, именно этот
воркер со временем его подхватит и либо успешно завершит, либо зафейлит с
понятным статусом и ошибкой в логах.
"""

from db.uow import db_uow
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from mas_queue.async_helpers import run_async
from services.export.service import process_one_pending_export


async def _export_process_pending_async(tenant_id: str) -> bool:
    """
    Асинхронная реализация обработки одной "ожидающей" задачи экспорта.

    Здесь вся работа с БД и бизнес‑логика.
    """
    async with db_uow() as uow:
        return await process_one_pending_export(
            db=uow.session,
            tenant_id=tenant_id,
        )


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
      - вызывает асинхронную функцию _export_process_pending_async(...)
        через общий мост run_async();
      - возвращает True, если что‑то было обработано, иначе False.
    """
    return run_async(_export_process_pending_async(tenant_id))
