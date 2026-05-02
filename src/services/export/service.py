# src/services/export/service.py

"""
Export service for processing Export records and generating output files.

Сервис запускает экспорт для уже созданной записи `Export`, переводит её
по жизненному циклу статусов и сохраняет ссылки на сгенерированные файлы.

Основные функции:
- run_export_for_record(export, db, tenant_id):
  - переводит запись Export в статус `processing`;
  - вызывает `export_core(...)`, который строит экспортные файлы и возвращает refs;
  - обновляет поля записи Export:
    `status`, `file_ref`, `file_refs` (и при необходимости `file_size_bytes`);
  - при успехе ставит `status="completed"`;
  - при ошибке логирует исключение, ставит `status="failed"` и возвращает пустой результат;
  - не делает commit — это ответственность вызывающего кода.

- process_one_pending_export(db, tenant_id):
  - выбирает одну самую раннюю запись Export со статусом `pending`;
  - обрабатывает её через `run_export_for_record(...)`;
  - коммитит изменения в БД;
  - возвращает `True`, если запись была найдена и обработана,
    иначе `False`.

Назначение:
- быть тонким orchestration-слоем вокруг `export_core`,
  который управляет статусами Export и сохранением refs в БД;
- использоваться воркером/джобой, которая последовательно обрабатывает
  pending-экспорты из очереди.

Audit trail:
- EXPORT_COMPLETED — успешный экспорт конкретной записи Export.
- EXPORT_FAILED — экспорт упал на уровне run_export_for_record.
- Audit logging best-effort: ошибки аудита не ломают основной флоу.
"""

from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.models.export import Export
from db.repositories import AuditRepository
from services.export.core import export_core

logger = get_logger(__name__)


async def run_export_for_record(
    export: Export,
    db: AsyncSession,
    tenant_id: str,
) -> Dict[str, Any]:
    """
    Выполнить экспорт для уже существующей записи Export.

    Ожидается, что:
      - export.status сейчас 'pending' (или 'queued');
      - export.run_id и export.deal_id заполнены.

    Делает:
      - меняет статус Export на 'processing';
      - вызывает export_core(...), который генерирует файлы и возвращает refs;
      - обновляет поля Export:
          - status: 'completed' или 'failed',
          - file_ref: основной файл,
          - file_refs: словарь всех файлов,
          - file_size_bytes: при желании можно посчитать суммарный размер.
      - НЕ коммитит транзакцию — это ответственность вызывающего кода.

    Дополнительно:
      - пишет EXPORT_COMPLETED / EXPORT_FAILED в audit trail (best-effort).
    """
    logger.info(
        "Запуск run_export_for_record",
        export_id=str(export.id),
        run_id=str(export.run_id),
        deal_id=str(export.deal_id),
        tenant_id=str(export.tenant_id),
        status=export.status,
    )

    audit_repo = AuditRepository(db)

    export.status = "processing"
    await db.flush()

    try:
        result = await export_core(
            run_id=str(export.run_id),
            deal_id=str(export.deal_id),
            tenant_id=tenant_id,
            db=db,
        )

        export.file_ref = result.get("export_ref")
        export.file_refs = result.get("all_refs") or result.get("refs")
        export.status = "completed"

        logger.info(
            "Экспорт для записи Export завершён",
            export_id=str(export.id),
            tenant_id=str(export.tenant_id),
            status=export.status,
        )

        try:
            await audit_repo.log(
                tenant_id=export.tenant_id,
                deal_id=export.deal_id,
                action="EXPORT_COMPLETED",
                actor="system",
                actor_role="worker",
                details={
                    "export_id": str(export.id),
                    "run_id": str(export.run_id),
                    "deal_id": str(export.deal_id),
                    "tenant_id": str(export.tenant_id),
                    "status": export.status,
                    "file_ref": export.file_ref,
                    "file_refs": export.file_refs,
                },
            )
        except Exception:
            logger.warning(
                "Export service: failed to write audit log for EXPORT_COMPLETED",
                export_id=str(export.id),
            )

        return result

    except Exception as e:  # noqa: BLE001
        logger.exception(
            "Ошибка при выполнении run_export_for_record",
            export_id=str(export.id),
            tenant_id=str(export.tenant_id),
            error=str(e),
        )
        export.status = "failed"
        await db.flush()

        try:
            await audit_repo.log(
                tenant_id=export.tenant_id,
                deal_id=export.deal_id,
                action="EXPORT_FAILED",
                actor="system",
                actor_role="worker",
                details={
                    "export_id": str(export.id),
                    "run_id": str(export.run_id),
                    "deal_id": str(export.deal_id),
                    "tenant_id": str(export.tenant_id),
                    "status": export.status,
                    "error": str(e),
                },
            )
        except Exception:
            logger.warning(
                "Export service: failed to write audit log for EXPORT_FAILED",
                export_id=str(export.id),
            )

        return {}


async def process_one_pending_export(
    db: AsyncSession,
    tenant_id: str,
) -> bool:
    """
    Найти одну pending-запись Export и обработать её атомарно.

    Использует FOR UPDATE SKIP LOCKED для исключения race condition
    при параллельных воркерах: каждый воркер возьмёт свою уникальную запись.

    Возвращает:
      - True, если запись была найдена и обработана (успешно или с ошибкой);
      - False, если pending-записей не было.
    """
    stmt = (
        select(Export)
        .where(Export.status == "pending")
        .where(Export.tenant_id == tenant_id)
        .order_by(Export.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )

    try:
        result = await db.execute(stmt)
        export: Export | None = result.scalars().first()

        if export is None:
            logger.debug(
                "process_one_pending_export: no pending exports available",
                tenant_id=tenant_id,
            )
            return False

        logger.info(
            "process_one_pending_export: claimed pending export",
            export_id=str(export.id),
            tenant_id=tenant_id,
            status=export.status,
        )

        await run_export_for_record(export, db=db, tenant_id=tenant_id)
        await db.commit()
        return True

    except Exception as e:  # noqa: BLE001
        await db.rollback()
        logger.exception(
            "process_one_pending_export failed",
            tenant_id=tenant_id,
            error=str(e),
        )
        raise


