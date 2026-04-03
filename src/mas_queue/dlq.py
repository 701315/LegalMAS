# src/mas_queue/dlq.py

"""
Менеджер Dead Letter Queue (DLQ) для фоновых задач.

Назначение:
  - централизованно хранить информацию о задачах, которые не удалось
    успешно завершить (после исчерпания ретраев или при фатальных ошибках);
  - предоставить операторам / support-команде удобный способ:
      * просматривать "упавшие" задачи с пагинацией;
      * фильтровать их по типу задачи и типу ошибки;
      * получать одну запись для ручного разбора / replay;
      * очищать старые записи после ручной обработки.

Как это используется в системе:
  - базовый класс задач MASBaseTask при финальном провале вызывает
    DLQManager.send_to_dlq(...) для записи события в БД;
  - UI/API может читать список через get_records() / get_record();
  - периодический Beat-таск может вызывать purge_old() для очистки.

Важно:
  - DLQManager НЕ делает повторный запуск задач и не принимает решений
    о дальнейшей судьбе записей — это ответственность сервисного слоя;
  - replay реализуется на уровне API / скриптов через данные из get_record().
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.models.ops import DLQRecord

logger = get_logger(__name__)

# Значение по умолчанию для поля next_action.
# Означает "ждёт ручного разбора оператором".
DLQ_NEXT_ACTION_DEFAULT = "retry_manual"


class DLQManager:
    """Менеджер записей DLQ в PostgreSQL."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def send_to_dlq(
        self,
        task_type: str,
        failure_type: str,
        job_id: uuid.UUID | None = None,
        error_details: dict | None = None,
        artifact_refs: list[str] | None = None,
        retry_count: int = 0,
        next_action: str = DLQ_NEXT_ACTION_DEFAULT,
    ) -> DLQRecord:
        """
        Записать информацию о проваленной задаче в DLQ.

        Аргументы:
            task_type:      Тип задачи ("extract", "run_deal_checks" и т.п.).
            failure_type:   Тип сбоя: "transient", "permanent", "timeout" и т.п.
            job_id:         Связанный Job ID (если есть).
            error_details:  Детали ошибки (сообщение, traceback, контекст).
            artifact_refs:  Ссылки на связанные артефакты (S3 URI и т.п.).
            retry_count:    Количество ретраев до финального провала.
            next_action:    Предлагаемое следующее действие (по умолчанию
                            DLQ_NEXT_ACTION_DEFAULT = "retry_manual").
        """
        record = DLQRecord(
            job_id=job_id,
            task_type=task_type,
            failure_type=failure_type,
            error_details=error_details or {},
            artifact_refs=artifact_refs or [],
            retry_count=retry_count,
            next_action=next_action,
        )
        self.session.add(record)
        await self.session.flush()

        logger.warning(
            "Task sent to DLQ",
            dlq_id=str(record.id),
            task_type=task_type,
            failure_type=failure_type,
            job_id=str(job_id) if job_id else None,
        )

        return record

    async def get_record(self, record_id: uuid.UUID) -> DLQRecord | None:
        """
        Получить одну запись DLQ по ID.

        Нужен для ручного разбора / replay на уровне API:
        оператор получает полный error_details и kwargs задачи,
        чтобы переотправить её вручную.
        """
        result = await self.session.execute(
            select(DLQRecord).where(DLQRecord.id == record_id)
        )
        return result.scalar_one_or_none()

    async def get_records(
        self,
        task_type: str | None = None,
        failure_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DLQRecord]:
        """
        Вернуть список записей DLQ для мониторинга с пагинацией.

        Аргументы:
            task_type:    Фильтр по типу задачи (опционально).
            failure_type: Фильтр по типу сбоя (опционально).
            limit:        Максимальное количество записей (по умолчанию 50).
            offset:       Смещение для пагинации (по умолчанию 0).
        """
        stmt = select(DLQRecord)
        if task_type:
            stmt = stmt.where(DLQRecord.task_type == task_type)
        if failure_type:
            stmt = stmt.where(DLQRecord.failure_type == failure_type)
        stmt = stmt.order_by(DLQRecord.created_at.desc()).limit(limit).offset(offset)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(
        self,
        task_type: str | None = None,
        failure_type: str | None = None,
    ) -> int:
        """
        Вернуть количество записей в DLQ.

        Принимает те же фильтры, что и get_records() — удобно для
        построения пагинации (total_count) в UI/API.
        """
        stmt = select(func.count(DLQRecord.id))
        if task_type:
            stmt = stmt.where(DLQRecord.task_type == task_type)
        if failure_type:
            stmt = stmt.where(DLQRecord.failure_type == failure_type)

        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def delete_record(self, record_id: uuid.UUID) -> bool:
        """
        Удалить одну запись DLQ (после ручного разбора).

        Возвращает True, если запись была найдена и удалена.
        """
        stmt = delete(DLQRecord).where(DLQRecord.id == record_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def purge_old(self, retention_days: int = 30) -> int:
        """
        Удалить устаревшие записи DLQ старше retention_days.

        Рекомендуется вызывать из периодической Celery Beat задачи.
        Возвращает количество удалённых записей.
        """
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        stmt = delete(DLQRecord).where(DLQRecord.created_at < cutoff)
        result = await self.session.execute(stmt)
        await self.session.flush()
        deleted = result.rowcount
        if deleted > 0:
            logger.info(
                "Purged old DLQ records",
                deleted=deleted,
                retention_days=retention_days,
            )
        return deleted
    
    