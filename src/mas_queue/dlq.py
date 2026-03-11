# src/mas_queue/dlq.py


"""
Менеджер Dead Letter Queue (DLQ) для фоновых задач.

Назначение:
  - централизованно хранить информацию о задачах, которые не удалось
    успешно завершить (после исчерпания ретраев или при фатальных ошибках);
  - предоставить операторам / support-команде удобный способ:
      * просматривать "упавшие" задачи;
      * фильтровать их по типу задачи и типу ошибки;
      * очищать старые записи после ручной обработки.

Как это используется в системе:
  - базовый класс задач MASBaseTask при финальном провале записи:
      * формирует error_details (тип ошибки, сообщение, traceback и т.п.);
      * вызывает DLQManager.send_to_dlq(...) для записи события в БД;
  - UI/админка может читать таблицу DLQRecord и показывать список
    проблемных задач (с деталями и ссылками на артефакты);
  - отдельные утилиты/cron могут:
      * периодически чистить старые записи (purge_old);
      * удалять отдельные записи после ручного решения (delete_record).

Важно:
  - сам DLQManager НЕ делает повторный запуск задач и не решает,
    что с ними делать дальше — он только пишет/читает записи в PostgreSQL;
  - логика повторного запуска или игнора реализуется на уровне сервисов
    и операторских инструментов (UI, скрипты, админ-панель).
"""


import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.models.ops import DLQRecord


logger = get_logger(__name__)


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
    ) -> DLQRecord:
        """
        Записать информацию о проваленной задаче в DLQ.

        Аргументы:
            task_type: Тип задачи (например, "extract", "run_checks").
            failure_type: Тип сбоя: "transient", "permanent", "timeout", "quota" и т.п.
            job_id: Связанный Job ID (если есть).
            error_details: Детальная информация об ошибке (сообщение, traceback, контекст).
            artifact_refs: Ссылки на связанные артефакты (например, S3 URI).
            retry_count: Количество уже выполненных ретраев перед окончательным провалом.
        """
        record = DLQRecord(
            job_id=job_id,
            task_type=task_type,
            failure_type=failure_type,
            error_details=error_details or {},
            artifact_refs=artifact_refs or [],
            retry_count=retry_count,
            next_action="retry_manual",
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

    async def get_records(
        self,
        task_type: str | None = None,
        failure_type: str | None = None,
        limit: int = 50,
    ) -> list[DLQRecord]:
        """
        Вернуть список записей DLQ для мониторинга.

        Можно отфильтровать по типу задачи и типу ошибки и ограничить количество записей.
        """
        stmt = select(DLQRecord)
        if task_type:
            stmt = stmt.where(DLQRecord.task_type == task_type)
        if failure_type:
            stmt = stmt.where(DLQRecord.failure_type == failure_type)
        stmt = stmt.order_by(DLQRecord.created_at.desc()).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(self) -> int:
        """
        Вернуть общее количество записей в DLQ.

        Удобно для метрик и дашбордов (например, grafana/pager).
        """
        from sqlalchemy import func

        result = await self.session.execute(select(func.count(DLQRecord.id)))
        return result.scalar_one()

    async def delete_record(self, record_id: uuid.UUID) -> bool:
        """
        Удалить одну запись DLQ (после ручного разбора).

        Возвращает True, если запись была удалена, иначе False.
        """
        stmt = delete(DLQRecord).where(DLQRecord.id == record_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def purge_old(self, retention_days: int = 30) -> int:
        """
        Удалить устаревшие записи DLQ старше retention_days.

        Возвращает количество удалённых записей.
        """
        from datetime import timedelta

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
