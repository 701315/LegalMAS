# src/db/repositories/run_repo.py

"""
Repository for Run and Job operations.
"""

import uuid
from datetime import UTC, datetime, timezone

from sqlalchemy import select, update, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.result import CheckResult
from ..models.run import Job, Run
from ..models.document import Document

class RunRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        deal_id: uuid.UUID,
        playbook_version_id: uuid.UUID,
        model_config_id: uuid.UUID | None = None,
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
        result = await self.session.execute(select(Run).where(Run.id == run_id))
        return result.scalar_one_or_none()

    async def update_status(self, run_id: uuid.UUID, status: str, **kwargs) -> Run | None:
        """Update run status and optional fields."""

        def _to_naive_utc(dt: datetime | None) -> datetime | None:
            if dt is None:
                return None
            if dt.tzinfo is None:
                return dt
            return dt.astimezone(timezone.utc).replace(tzinfo=None)

        values: dict = {"status": status}

        # если вызывающий явно передал started_at/completed_at — нормализуем
        if "started_at" in kwargs and kwargs["started_at"] is not None:
            values["started_at"] = _to_naive_utc(kwargs["started_at"])
        if "completed_at" in kwargs and kwargs["completed_at"] is not None:
            values["completed_at"] = _to_naive_utc(kwargs["completed_at"])

        # автозаполнение, если не передали
        if status == "running" and "started_at" not in values:
            # utcnow naive
            values["started_at"] = datetime.utcnow()
        if status in ("completed", "failed") and "completed_at" not in values:
            values["completed_at"] = datetime.utcnow()

        # остальные kwargs (total_checks, completed_checks, error_details и т.п.)
        for k, v in kwargs.items():
            if k in ("started_at", "completed_at"):
                continue
            values[k] = v

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

    async def get_counts(self, run_id: uuid.UUID) -> tuple[int, int]:
        """
        Вернуть (total_checks, completed_checks) для Run.
        """
        result = await self.session.execute(
            select(Run.total_checks, Run.completed_checks).where(Run.id == run_id)
        )
        row = result.first()
        if not row:
            return 0, 0
        total = row[0] or 0
        completed = row[1] or 0
        return total, completed

    async def get_document_ids_for_run(self, run_id: uuid.UUID) -> list[uuid.UUID]:
        """
        Вернуть уникальные document_id, для которых есть CheckResult с данным run_id.
        Используется в отчёте по классификации, чтобы ограничить выборку документов.
        """
        subq = (
            select(CheckResult.document_id)
            .where(CheckResult.run_id == run_id)
            .distinct()
        )
        result = await self.session.execute(subq)
        return [row[0] for row in result.all()]

    async def get_latest_for_deal(self, deal_id: uuid.UUID) -> Run | None:
        """
        Вернуть последний run для сделки по дате создания/ID.

        Используется, например, при ручной переклассификации, чтобы
        при необходимости переиспользовать последний run.
        """
        stmt = (
            select(Run)
            .where(Run.deal_id == deal_id)
            .order_by(desc(Run.created_at))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_deal(self, deal_id: uuid.UUID) -> list[Run]:
        """
        Вернуть все runs для указанной сделки, отсортированные по дате создания (новые сначала).
        """
        stmt = (
            select(Run)
            .where(Run.deal_id == deal_id)
            .order_by(desc(Run.created_at))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_classification_stats_for_run(self, run_id: uuid.UUID) -> dict:
        """
        Посчитать статистику классификации по всем документам,
        которые проверялись в этом run.
        """
        # все document_id, участвовавшие в run
        subq = (
            select(CheckResult.document_id)
            .where(CheckResult.run_id == run_id)
            .distinct()
            .subquery()
        )

        stmt = (
            select(
                Document.classification_level,
                Document.classification_confidence,
                Document.doc_type,
            )
            .where(Document.id.in_(select(subq)))
        )
        result = await self.session.execute(stmt)
        rows = result.all()

        stats = {
            "total_documents": len(rows),
            "l0_no_match": 0,
            "l1_filename": 0,
            "l2_keyword": 0,
            "l3_semantic": 0,
            "l4_llm": 0,
            "low_confidence_count": 0,
            "unknown_doc_type_count": 0,
        }

        level_map = {
            "L0": "l0_no_match",
            "L1": "l1_filename",
            "L2": "l2_keyword",
            "L3": "l3_semantic",
            "L4": "l4_llm",
            "LMANUAL": "l4_llm",  # manual treated as highest level
        }

        for level, confidence, doc_type in rows:
            raw_level = level or "L0"
            level_norm = raw_level.replace("_", "").upper()
            key = level_map.get(level_norm, "l0_no_match")
            stats[key] += 1

            if confidence and 0 < confidence < 0.6:
                stats["low_confidence_count"] += 1
            if not doc_type or doc_type in ("Generic", "Unknown"):
                stats["unknown_doc_type_count"] += 1

        return stats


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

    async def update_status(self, job_id: uuid.UUID, status: str, **kwargs) -> Job | None:
        """Update job status."""
        values = {"status": status, **kwargs}
        if status == "running" and "started_at" not in kwargs:
            values["started_at"] = datetime.now(UTC)
        if status in ("completed", "failed", "dlq") and "finished_at" not in kwargs:
            values["finished_at"] = datetime.now(UTC)

        stmt = update(Job).where(Job.id == job_id).values(**values).returning(Job)
        result = await self.session.execute(stmt)
        job = result.scalar_one_or_none()
        if job:
            await self.session.flush()
        return job
