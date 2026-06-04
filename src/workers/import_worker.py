# src/workers/import_worker.py

"""
Import Worker — тонкий Celery adapter для запуска ImportBundleUseCase.

Назначение:
- Принимает Celery task вызов от брокера.
- Создаёт ImportBundleCommand из параметров таски.
- Открывает db_uow (database unit of work).
- Вызывает ImportBundleUseCase.execute(command).
- Возвращает result.to_dict() обратно в Celery.

Важно:
- Этот файл НЕ содержит бизнес-логику импорта.
- Вся логика живёт в ImportBundleUseCase (services layer).
- Worker — это только транспортный адаптер между Celery и application layer.

Архитектура:
- workers layer = транспорт (Celery task declaration, sync -> async bridge).
- services layer = use cases, application orchestration, бизнес-логика.
- db layer = repositories, models, persistence.

Для непрофессионального программиста:
- import_worker.py — это «почтальон», который принимает сообщение от Celery
  и передаёт его в ImportBundleUseCase для выполнения.
- Сам «почтальон» ничего не делает с документами — он только доставляет команду
  и возвращает результат обратно.
"""

from __future__ import annotations

from typing import Any

from core.logging import get_logger
from db.uow import db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.import_bundle_use_case import ImportBundleUseCase
from services.import_types import ImportBundleCommand

logger = get_logger(__name__)


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.import_bundle",
    track_job=False,
    queue="default",
)
def import_bundle(
    self,
    deal_id: str,
    tenant_id: str,
    source_path: str,
    idempotency_key: str | None = None,
    run_id: str | None = None,
    stage_execution_id: str | None = None,
    orchestration_strategy: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Синхронная точка входа Celery-таски импорта.

    Параметры:
    - deal_id: идентификатор сделки, в которую импортировать документы.
    - tenant_id: идентификатор tenant'а (для проверки прав доступа).
    - source_path: путь к файлу или ZIP-архиву на диске.
    - idempotency_key: опциональный ключ для идемпотентного выполнения.
    - run_id: опциональный идентификатор Run'а для audit trail.

    Возвращает:
    - dict с результатом импорта (bundle_id, document_ids, counts, etc).

    Важно:
    - Эта таска НЕ отправляет downstream-задачи напрямую.
    - Она только выполняет import и пишет outbox events в той же транзакции.
    - Публикация outbox events в Celery делается отдельным relay/dispatcher процессом.

    Для непрофессионального программиста:
    - Когда брокер Celery получает команду «импортировать файлы для сделки X»,
      он вызывает эту функцию.
    - Функция создаёт команду, передаёт её в ImportBundleUseCase и возвращает результат.
    """
    _ = self

    command = ImportBundleCommand(
        deal_id=deal_id,
        tenant_id=tenant_id,
        source_path=source_path,
        idempotency_key=idempotency_key,
        run_id=run_id,
    )

    async def _wrapper() -> dict[str, Any]:
        async with db_uow() as uow:
            use_case = ImportBundleUseCase(db=uow.session)
            result = await use_case.execute(command)
            return result.to_dict()

    result = run_async(_wrapper())

    logger.info(
        "Import bundle task finished",
        extra={
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "source_path": source_path,
            "imported_count": result.get("imported_count"),
            "quarantine_count": result.get("quarantine_count"),
            "duplicate_count": result.get("duplicate_count"),
            "skipped_count": result.get("skipped_count"),
            "bundle_id": result.get("bundle_id"),
        },
    )

    return result
