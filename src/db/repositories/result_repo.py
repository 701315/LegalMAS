"""
Repository for CheckResult operations.
"""

import uuid
from datetime import UTC, datetime
from typing import Sequence
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.result import CheckResult


class ResultRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        run_id: uuid.UUID,
        document_id: uuid.UUID,
        check_id: str,
        check_name: str,
        result: str,
        severity: str,
        value_text: str | None = None,
        evidence_ref: str | None = None,
        confidence: float | None = None,
        detector_used: str | None = None,
        quality_flags: dict | None = None,
        structured_data: dict | None = None,
        conditional_check_triggered: bool = False,
        trigger_name: str | None = None,
    ) -> CheckResult:
        """Create a check result."""
        cr = CheckResult(
            run_id=run_id,
            document_id=document_id,
            check_id=check_id,
            check_name=check_name,
            result=result,
            severity=severity,
            value_text=value_text,
            evidence_ref=evidence_ref,
            confidence=confidence,
            detector_used=detector_used,
            quality_flags=quality_flags or {},
            structured_data=structured_data,
            conditional_check_triggered=conditional_check_triggered,
            trigger_name=trigger_name,
        )
        self.session.add(cr)
        await self.session.flush()
        return cr

    async def get_by_run(self, run_id: uuid.UUID, severity: str | None = None) -> list[CheckResult]:
        """Get all results for a run, optionally filtered by severity."""
        stmt = select(CheckResult).where(CheckResult.run_id == run_id)
        if severity is not None:
            stmt = stmt.where(CheckResult.severity == severity)
        stmt = stmt.order_by(CheckResult.severity, CheckResult.check_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_document(self, document_id: uuid.UUID, run_id: uuid.UUID) -> list[CheckResult]:
        """Get all results for a document within a run."""
        result = await self.session.execute(
            select(CheckResult).where(
                CheckResult.document_id == document_id,
                CheckResult.run_id == run_id,
            )
        )
        return list(result.scalars().all())

    async def update_qc(
        self,
        result_id: uuid.UUID,
        qc_status: str,
        qc_by: str,
        qc_comment: str | None = None,
    ) -> CheckResult | None:
        """Update QC status on a single result."""
        stmt = (
            update(CheckResult)
            .where(CheckResult.id == result_id)
            .values(
                qc_status=qc_status,
                qc_by=qc_by,
                qc_comment=qc_comment,
                qc_at=datetime.now(UTC),
            )
            .returning(CheckResult)
        )
        result = await self.session.execute(stmt)
        cr = result.scalar_one_or_none()
        if cr:
            await self.session.flush()
        return cr

    async def bulk_update_qc(
        self,
        result_ids: list[uuid.UUID],
        qc_status: str,
        qc_by: str,
        qc_comment: str | None = None,
    ) -> int:
        """Bulk update QC status. Returns number of updated rows."""
        stmt = (
            update(CheckResult)
            .where(CheckResult.id.in_(result_ids))
            .values(
                qc_status=qc_status,
                qc_by=qc_by,
                qc_comment=qc_comment,
                qc_at=datetime.now(UTC),
            )
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def count_by_severity(self, run_id: uuid.UUID) -> dict[str, int]:
        """Count results by severity for a run."""
        stmt = (
            select(CheckResult.severity, func.count(CheckResult.id))
            .where(CheckResult.run_id == run_id)
            .group_by(CheckResult.severity)
        )
        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def get_page_for_run(
        self,
        run_id: UUID,
        page: int,
        per_page: int,
        doc_type: str | None = None,
        severity: str | None = None,
        conditional_only: bool | None = None,
        has_structured_data: bool | None = None,
    ) -> tuple[Sequence[CheckResult], int]:
        """
        Пагинированный список результатов для одного run с фильтрами.
        Возвращает (items, total).
        """
        stmt = select(CheckResult).where(CheckResult.run_id == run_id)

        if doc_type is not None:
            stmt = stmt.where(CheckResult.doc_type == doc_type)

        if severity is not None:
            stmt = stmt.where(CheckResult.severity == severity)

        if conditional_only is True:
            stmt = stmt.where(CheckResult.conditional_check_triggered.is_(True))

        if has_structured_data is True:
            stmt = stmt.where(CheckResult.structured_data.isnot(None))

        # total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()

        # сортировка + пагинация
        stmt = stmt.order_by(CheckResult.created_at.desc())
        stmt = stmt.offset((page - 1) * per_page).limit(per_page)

        result = await self.session.execute(stmt)
        items = result.scalars().all()

        return items, total