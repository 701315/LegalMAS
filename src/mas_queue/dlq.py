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

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.models.ops import DLQRecord


logger = get_logger(__name__)

# Значение по умолчанию для поля next_action.
DLQ_NEXT_ACTION_DEFAULT = "retry_manual"
DLQ_MAX_PAGE_SIZE = 500


class DLQManager:
    """Менеджер записей DLQ в PostgreSQL."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def send_to_dlq(
        self,
        task_type: str,
        failure_type: str,
        job_id: uuid.UUID | None = None,
        *,
        source_task_id: str | None = None,
        dedupe_key: str | None = None,
        error_details: dict | None = None,
        artifact_refs: list[str] | None = None,
        retry_count: int = 0,
        next_action: str = DLQ_NEXT_ACTION_DEFAULT,
    ) -> DLQRecord:
        """
        Записать информацию о проваленной задаче в DLQ.
        """
        if not task_type:
            raise ValueError("task_type must not be empty")
        if not failure_type:
            raise ValueError("failure_type must not be empty")
        if retry_count < 0:
            raise ValueError("retry_count must be >= 0")
        if not next_action:
            raise ValueError("next_action must not be empty")

        record = DLQRecord(
            job_id=job_id,
            source_task_id=source_task_id,
            task_type=task_type,
            failure_type=failure_type,
            dedupe_key=dedupe_key,
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
            source_task_id=source_task_id,
            dedupe_key=dedupe_key,
            retry_count=retry_count,
            next_action=next_action,
        )

        return record

    async def get_record(self, record_id: uuid.UUID) -> DLQRecord | None:
        """
        Получить одну запись DLQ по ID.
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
        """
        if limit <= 0:
            raise ValueError("limit must be > 0")
        if offset < 0:
            raise ValueError("offset must be >= 0")

        limit = min(limit, DLQ_MAX_PAGE_SIZE)

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
        """
        stmt = select(func.count(DLQRecord.id))
        if task_type:
            stmt = stmt.where(DLQRecord.task_type == task_type)
        if failure_type:
            stmt = stmt.where(DLQRecord.failure_type == failure_type)

        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def delete_record(self, record_id: uuid.UUID) -> bool:
        """
        Удалить одну запись DLQ (после ручного разбора).
        """
        stmt = delete(DLQRecord).where(DLQRecord.id == record_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return bool(result.rowcount and result.rowcount > 0)

    async def purge_old(self, retention_days: int = 30) -> int:
        """
        Удалить устаревшие записи DLQ старше retention_days.
        """
        if retention_days < 0:
            raise ValueError("retention_days must be >= 0")

        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        stmt = delete(DLQRecord).where(DLQRecord.created_at < cutoff)
        result = await self.session.execute(stmt)
        await self.session.flush()

        deleted = int(result.rowcount or 0)
        if deleted > 0:
            logger.info(
                "Purged old DLQ records",
                deleted=deleted,
                retention_days=retention_days,
                cutoff=cutoff.isoformat(),
            )
        return deleted
    
    