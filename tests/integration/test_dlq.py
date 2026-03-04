"""
Integration tests for DLQManager.
Requires PostgreSQL (make up).
"""

import uuid

import pytest
from sqlalchemy import delete

from src.db.models.ops import DLQRecord
from src.mas_queue.dlq import DLQManager


@pytest.fixture(autouse=True)
async def cleanup_dlq(db_session):
    """Clean up DLQ records before each test."""
    await db_session.execute(delete(DLQRecord))
    await db_session.commit()


class TestDLQManager:
    @pytest.mark.asyncio
    async def test_send_to_dlq(self, db_session):
        """Should create a DLQ record."""
        dlq = DLQManager(db_session)

        record = await dlq.send_to_dlq(
            task_type="test.extract",
            failure_type="permanent",
            error_details={"message": "Invalid PDF format"},
        )

        assert record.id is not None
        assert record.task_type == "test.extract"
        assert record.failure_type == "permanent"
        assert record.next_action == "retry_manual"

    @pytest.mark.asyncio
    async def test_send_with_job_id(self, db_session):
        """Should store job_id reference."""
        dlq = DLQManager(db_session)
        job_id = uuid.uuid4()

        record = await dlq.send_to_dlq(
            task_type="test.run_checks",
            failure_type="transient",
            job_id=job_id,
            error_details={"retries": 3},
            artifact_refs=["s3://bucket/doc.pdf"],
        )

        assert record.job_id == job_id
        assert record.artifact_refs == ["s3://bucket/doc.pdf"]

    @pytest.mark.asyncio
    async def test_get_records(self, db_session):
        """Should retrieve DLQ records with filters."""
        dlq = DLQManager(db_session)

        await dlq.send_to_dlq(task_type="extract", failure_type="permanent")
        await dlq.send_to_dlq(task_type="extract", failure_type="transient")
        await dlq.send_to_dlq(task_type="classify", failure_type="permanent")

        all_records = await dlq.get_records()
        assert len(all_records) == 3

        extract_only = await dlq.get_records(task_type="extract")
        assert len(extract_only) == 2

        permanent_only = await dlq.get_records(failure_type="permanent")
        assert len(permanent_only) == 2

    @pytest.mark.asyncio
    async def test_count(self, db_session):
        """Should return total DLQ count."""
        dlq = DLQManager(db_session)

        await dlq.send_to_dlq(task_type="t1", failure_type="permanent")
        await dlq.send_to_dlq(task_type="t2", failure_type="transient")

        count = await dlq.count()
        assert count == 2

    @pytest.mark.asyncio
    async def test_delete_record(self, db_session):
        """Should delete a DLQ record."""
        dlq = DLQManager(db_session)

        record = await dlq.send_to_dlq(task_type="t1", failure_type="permanent")

        deleted = await dlq.delete_record(record.id)
        assert deleted is True

        count = await dlq.count()
        assert count == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, db_session):
        """Deleting nonexistent record should return False."""
        dlq = DLQManager(db_session)

        deleted = await dlq.delete_record(uuid.uuid4())
        assert deleted is False
