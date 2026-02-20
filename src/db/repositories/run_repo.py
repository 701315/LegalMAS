"""
Repository for Run and Job operations.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.run import Job, Run


class RunRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        deal_id: uuid.UUID,
        playbook_version_id: uuid.UUID,
        model_config_id: uuid.UUID,
        bundle_id: uuid.UUID | None = None,
        environment_hash: str | None = None,
        profile: str = "full",
    ) -> Run:
        """Create a new analysis run."""
        run = Run(
            deal_id=deal_id,
            bundle_id=bundle_id,
            playbook_version_id=playbook_version_id,
            model_config_id=model_config_id,
            environment_hash=environment_hash,
            profile=profile,
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def get_by_id(self, run_id: uuid.UUID) -> Run | None:
        """Get run by ID."""
        result = await self.session.execute(
            select(Run).where(Run.id == run_id)
        )
        return result.scalar_one_or_none()

    async def update_status(
        self, run_id: uuid.UUID, status: str, **kwargs
    ) -> Run | None:
        """Update run status and optional fields."""
        values = {"status": status, **kwargs}
        if status == "running" and "started_at" not in kwargs:
            values["started_at"] = datetime.now(timezone.utc)
        if status in ("completed", "failed") and "completed_at" not in kwargs:
            values["completed_at"] = datetime.now(timezone.utc)

        stmt = (
            update(Run)
            .where(Run.id == run_id)
            .values(**values)
            .returning(Run)
        )
        result = await self.session.execute(stmt)
        run = result.scalar_one_or_none()
        if run:
            await self.session.flush()
        return run

    async def increment_completed_checks(self, run_id: uuid.UUID) -> int:
        """Increment completed_checks counter. Returns new value."""
        stmt = (
            update(Run)
            .where(Run.id == run_id)
            .values(completed_checks=Run.completed_checks + 1)
            .returning(Run.completed_checks)
        )
        result = await self.session.execute(stmt)
        new_count = result.scalar_one()
        await self.session.flush()
        return new_count


class JobRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        run_id: uuid.UUID,
        task_type: str,
        document_id: uuid.UUID | None = None,
    ) -> Job:
        """Create a new job."""
        job = Job(
            run_id=run_id,
            task_type=task_type,
            document_id=document_id,
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def update_status(
        self, job_id: uuid.UUID, status: str, **kwargs
    ) -> Job | None:
        """Update job status."""
        values = {"status": status, **kwargs}
        if status == "running" and "started_at" not in kwargs:
            values["started_at"] = datetime.now(timezone.utc)
        if status in ("completed", "failed", "dlq") and "finished_at" not in kwargs:
            values["finished_at"] = datetime.now(timezone.utc)

        stmt = (
            update(Job)
            .where(Job.id == job_id)
            .values(**values)
            .returning(Job)
        )
        result = await self.session.execute(stmt)
        job = result.scalar_one_or_none()
        if job:
            await self.session.flush()
        return job
