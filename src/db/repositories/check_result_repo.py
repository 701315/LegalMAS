# src/db/repositories/check_result_repo.py

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.result import CheckResult


class CheckResultRepository:
    """Repository for creating and querying check_results."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: dict[str, Any]) -> CheckResult:
        """
        Создать новую запись в check_results.

        Ожидает словарь с полями:
        - run_id: UUID
        - document_id: UUID
        - check_id: str
        - check_name: str
        - result: str ("fail", "pass", "unclear")
        - severity: str
        - value_text: str | None
        - evidence_ref: str | None
        - confidence: float | None
        - detector_used: str | None
        - quality_flags: dict | None
        - structured_data: dict | None
        - conditional_check_triggered: bool
        - trigger_name: str | None
        - origin: str | None
        - page: int | None
        - clause_uid: str | None
        - element_id: str | None
        - bbox: dict | None
        """
        obj = CheckResult(
            run_id=data["run_id"],
            document_id=data["document_id"],
            check_id=data["check_id"],
            check_name=data["check_name"],
            result=data["result"],
            severity=data["severity"],
            value_text=data.get("value_text"),
            evidence_ref=data.get("evidence_ref"),
            confidence=data.get("confidence"),
            detector_used=data.get("detector_used"),
            quality_flags=data.get("quality_flags") or {},
            structured_data=data.get("structured_data"),
            conditional_check_triggered=data.get("conditional_check_triggered", False),
            trigger_name=data.get("trigger_name"),
            # НОВЫЕ ПОЛЯ
            origin=data.get("origin"),
            page=data.get("page"),
            clause_uid=data.get("clause_uid"),
            element_id=data.get("element_id"),
            bbox=data.get("bbox"),
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
