"""
Dead Letter Queue (DLQ) manager.

Failed tasks that cannot be retried are sent here.
Operations team can review, retry, or skip DLQ records.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.models.ops import DLQRecord

logger = get_logger(__name__)


class DLQManager:
    """Manages dead letter queue records in PostgreSQL."""

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
        Send a failed task to the DLQ.

        Args:
            task_type: Type of task (e.g. "extract", "run_checks")
            failure_type: "transient", "permanent", "timeout", "quota"
            job_id: Related Job ID (if exists)
            error_details: Error information for debugging
            artifact_refs: S3 URIs of related artifacts
            retry_count: Number of retries already attempted
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
        """Get DLQ records for monitoring."""
        stmt = select(DLQRecord)
        if task_type:
            stmt = stmt.where(DLQRecord.task_type == task_type)
        if failure_type:
            stmt = stmt.where(DLQRecord.failure_type == failure_type)
        stmt = stmt.order_by(DLQRecord.created_at.desc()).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(self) -> int:
        """Get total count of DLQ records."""
        from sqlalchemy import func

        result = await self.session.execute(select(func.count(DLQRecord.id)))
        return result.scalar_one()

    async def delete_record(self, record_id: uuid.UUID) -> bool:
        """Delete a DLQ record (after manual review)."""
        stmt = delete(DLQRecord).where(DLQRecord.id == record_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def purge_old(self, retention_days: int = 30) -> int:
        """Delete DLQ records older than retention_days."""
        from datetime import timedelta

        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        stmt = delete(DLQRecord).where(DLQRecord.created_at < cutoff)
        result = await self.session.execute(stmt)
        await self.session.flush()
        deleted = result.rowcount
        if deleted > 0:
            logger.info("Purged old DLQ records", deleted=deleted, retention_days=retention_days)
        return deleted
