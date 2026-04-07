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
"""


from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.logging import get_logger
from db.models.export import Export
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
          - file_refs: словарь всех файлов (включая None или только не-None — см. ниже),
          - file_size_bytes: при желании можно посчитать суммарный размер.
      - НЕ коммитит транзакцию — это ответственность вызывающего кода.
    """
    logger.info(
        "Запуск run_export_for_record",
        export_id=str(export.id),
        run_id=str(export.run_id),
        deal_id=str(export.deal_id),
        status=export.status,
    )

    # 1. Переводим в processing
    export.status = "processing"
    await db.flush()

    try:
        result = await export_core(
            run_id=str(export.run_id),
            deal_id=str(export.deal_id),
            tenant_id=tenant_id,
            db=db,
        )

        # 2. Обновляем поля Export по результатам
        export.file_ref = result.get("export_ref")
        # Хранить полную структуру all_refs или только refs — на твой выбор.
        # Я бы рекомендовал all_refs, чтобы видеть и "провалившиеся" файлы.
        export.file_refs = result.get("all_refs") or result.get("refs")

        # TODO: если нужно, можно здесь же посчитать суммарный размер
        # export.file_size_bytes = ...

        export.status = "completed"

        logger.info(
            "Экспорт для записи Export завершён",
            export_id=str(export.id),
            status=export.status,
        )

        # Возвращаем result на случай, если вызывающему коду нужны детали
        return result

    except Exception as e:  # noqa: BLE001
        logger.exception(
            "Ошибка при выполнении run_export_for_record",
            export_id=str(export.id),
            error=str(e),
        )
        export.status = "failed"
        await db.flush()
        # Можно вернуть частичный результат или пустой dict
        return {}


async def process_one_pending_export(
    db: AsyncSession,
    tenant_id: str,
) -> bool:
    """
    Найти одну pending-запись Export и обработать её.

    Возвращает:
      - True, если запись была найдена и обработана (успешно или с ошибкой);
      - False, если pending-записей не было.
    """
    # 1. Найти одну pending-запись
    stmt = (
        select(Export)
        .where(Export.status == "pending")
        .order_by(Export.created_at)
        .limit(1)
    )
    result = await db.execute(stmt)
    export: Export | None = result.scalars().first()

    if export is None:
        return False

    # 2. Обработать её через run_export_for_record
    await run_export_for_record(export, db=db, tenant_id=tenant_id)

    # Коммитим изменения по Export и, возможно, связанным сущностям
    await db.commit()

    return True
