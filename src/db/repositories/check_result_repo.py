import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.result import CheckResult


class CheckResultRepository:
    """Repository for creating and querying check_results."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
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
        quality_flags: dict[str, Any] | None = None,
        structured_data: dict[str, Any] | None = None,
        conditional_check_triggered: bool = False,
        trigger_name: str | None = None,
        origin: str | None = None,
        playbook_version_id: uuid.UUID | None = None,
        page: int | None = None,
        clause_uid: str | None = None,
        element_id: str | None = None,
        bbox: dict[str, Any] | None = None,
    ) -> CheckResult:
        """
        Создать новую запись в check_results.

        Все параметры передаются именованно (как в CheckRunner),
        без обёртки в dict.
        """
        obj = CheckResult(
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
            origin=origin,
            playbook_version_id=playbook_version_id,
            page=page,
            clause_uid=clause_uid,
            element_id=element_id,
            bbox=bbox,
        )

        self.session.add(obj)
        # commit делает UnitOfWork; здесь только flush/refresh
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def for_doc(
        self,
        run_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> list[CheckResult]:
        """Получить все результаты для документа в рамках одного run."""
        stmt = (
            select(CheckResult)
            .where(
                CheckResult.run_id == run_id,
                CheckResult.document_id == document_id,
            )
            .order_by(CheckResult.check_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def for_deal(
        self,
        run_id: uuid.UUID,
        document_ids: list[uuid.UUID],
    ) -> list[CheckResult]:
        """
        Получить результаты по списку документов сделки
        в рамках одного run.
        """
        if not document_ids:
            return []

        stmt = select(CheckResult).where(
            CheckResult.run_id == run_id,
            CheckResult.document_id.in_(document_ids),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
