# src/workers/export_pending.py

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

Audit trail:
  - Если pending export обработан, пишет EXPORT_PENDING_PROCESSED.
  - Если pending export не найден, пишет EXPORT_PENDING_IDLE.
  - Если произошла ошибка, пишет EXPORT_PENDING_FAILED.
  - Audit logging best-effort: проблемы аудита не должны ломать воркер.

Таким образом, этот воркер постепенно «разгрызает» очередь отложенных экспортов.
Для пользователя это означает: если экспорт находится в ожидании, именно этот
воркер со временем его подхватит и либо успешно завершит, либо зафейлит с
понятным статусом и ошибкой в логах.
"""

from __future__ import annotations

import time
import uuid

from core.logging import get_logger
from db.repositories import AuditRepository
from db.uow import db_uow
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from mas_queue.async_helpers import run_async
from services.export.service import process_one_pending_export

logger = get_logger(__name__)


async def _export_process_pending_async(tenant_id: str) -> bool:
    """
    Асинхронная реализация обработки одной "ожидающей" задачи экспорта.

    Здесь вся работа с БД и бизнес‑логика.
    """
    start = time.time()
    tenant_uuid: uuid.UUID | None = None

    try:
        try:
            tenant_uuid = uuid.UUID(tenant_id)
        except Exception:
            tenant_uuid = None

        async with db_uow() as uow:
            processed = await process_one_pending_export(
                db=uow.session,
                tenant_id=tenant_id,
            )

            duration_ms = int((time.time() - start) * 1000)

            try:
                if tenant_uuid is not None:
                    audit_repo = AuditRepository(uow.session)
                    await audit_repo.log(
                        tenant_id=tenant_uuid,
                        deal_id=uuid.UUID(int=0),
                        action=(
                            "EXPORT_PENDING_PROCESSED"
                            if processed
                            else "EXPORT_PENDING_IDLE"
                        ),
                        actor="system",
                        actor_role="worker",
                        details={
                            "tenant_id": tenant_id,
                            "processed": bool(processed),
                            "duration_ms": duration_ms,
                        },
                    )
            except Exception:
                logger.warning(
                    "Export pending worker: failed to write audit log",
                    tenant_id=tenant_id,
                    processed=bool(processed),
                )

            logger.info(
                "Export pending worker finished",
                tenant_id=tenant_id,
                processed=bool(processed),
                duration_ms=duration_ms,
            )

            return processed

    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)

        logger.exception(
            "Export pending worker failed",
            tenant_id=tenant_id,
            duration_ms=duration_ms,
            error=str(e),
        )

        if tenant_uuid is not None:
            try:
                async with db_uow() as uow_status:
                    audit_repo = AuditRepository(uow_status.session)
                    await audit_repo.log(
                        tenant_id=tenant_uuid,
                        deal_id=uuid.UUID(int=0),
                        action="EXPORT_PENDING_FAILED",
                        actor="system",
                        actor_role="worker",
                        details={
                            "tenant_id": tenant_id,
                            "duration_ms": duration_ms,
                            "error": str(e),
                        },
                    )
            except Exception:
                logger.warning(
                    "Export pending worker: failed to write failure audit log",
                    tenant_id=tenant_id,
                )

        raise


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
    _ = self
    return run_async(_export_process_pending_async(tenant_id))


