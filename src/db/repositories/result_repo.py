# src/db/repositories/result_repo.py

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
from ..models.document import Document  # НОВОЕ: подтягиваем документы


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
        """Get all results for a run, optionally filtered by severity (без join с документами)."""
        stmt = select(CheckResult).where(CheckResult.run_id == run_id)
        if severity is not None:
            stmt = stmt.where(CheckResult.severity == severity)
        stmt = stmt.order_by(CheckResult.severity, CheckResult.check_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_run_with_docs(self, run_id: uuid.UUID) -> list[dict]:
        """
        Получить результаты для run с джойном документов.

        Возвращает список dict'ов, совместимых с CheckResultResponse:
        - поля из CheckResult;
        - document_name, doc_type;
        - doc_classification_level, doc_classification_confidence.
        """
        stmt = (
            select(
                CheckResult,
                Document.filename.label("document_name"),
                Document.doc_type.label("doc_type"),
                Document.classification_level.label("doc_classification_level"),
                Document.classification_confidence.label("doc_classification_confidence"),
            )
            .join(Document, Document.id == CheckResult.document_id)
            .where(CheckResult.run_id == run_id)
            .order_by(CheckResult.severity, CheckResult.check_id)
        )

        result = await self.session.execute(stmt)
        rows = result.all()

        out: list[dict] = []
        for cr, document_name, doc_type, doc_level, doc_conf in rows:
            # cr — это ORM-объект CheckResult; берем его attr'ы как есть
            item = {
                "id": cr.id,
                "run_id": cr.run_id,
                "document_id": cr.document_id,
                "check_id": cr.check_id,
                "check_name": cr.check_name,
                "result": cr.result,
                "severity": cr.severity,
                "value_text": cr.value_text,
                "confidence": cr.confidence,
                "detector_used": cr.detector_used,
                "quality_flags": cr.quality_flags,
                "qc_status": cr.qc_status,
                "qc_by": cr.qc_by,
                "qc_comment": cr.qc_comment,
                "qc_at": cr.qc_at,
                "created_at": cr.created_at,
                # обогащение из Document
                "document_name": document_name,
                "doc_type": doc_type,
                # доп. поля, которые уже ждёт фронт (через types)
                "doc_classification_level": doc_level,
                "doc_classification_confidence": doc_conf,
                # structured_data и conditional
                "structured_data": cr.structured_data,
                "conditional_check_triggered": cr.conditional_check_triggered,
                "trigger_name": cr.trigger_name,
            }
            out.append(item)

        return out

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
    ) -> tuple[Sequence[dict], int]:
        """
        Пагинированный список результатов для одного run с фильтрами.
        Возвращает (items, total), где items — dict'ы, совместимые с CheckResultResponse.
        """
        base_stmt = (
            select(
                CheckResult,
                Document.filename.label("document_name"),
                Document.doc_type.label("doc_type"),
                Document.classification_level.label("doc_classification_level"),
                Document.classification_confidence.label("doc_classification_confidence"),
            )
            .join(Document, Document.id == CheckResult.document_id)
            .where(CheckResult.run_id == run_id)
        )

        if doc_type is not None:
            base_stmt = base_stmt.where(Document.doc_type == doc_type)

        if severity is not None:
            base_stmt = base_stmt.where(CheckResult.severity == severity)

        if conditional_only is True:
            base_stmt = base_stmt.where(CheckResult.conditional_check_triggered.is_(True))

        if has_structured_data is True:
            base_stmt = base_stmt.where(CheckResult.structured_data.isnot(None))

        # total
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()

        # сортировка + пагинация
        stmt = (
            base_stmt.order_by(CheckResult.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )

        result = await self.session.execute(stmt)
        rows = result.all()

        items: list[dict] = []
        for cr, document_name, doc_type_value, doc_level, doc_conf in rows:
            item = {
                "id": cr.id,
                "run_id": cr.run_id,
                "document_id": cr.document_id,
                "check_id": cr.check_id,
                "check_name": cr.check_name,
                "result": cr.result,
                "severity": cr.severity,
                "value_text": cr.value_text,
                "confidence": cr.confidence,
                "detector_used": cr.detector_used,
                "quality_flags": cr.quality_flags,
                "qc_status": cr.qc_status,
                "qc_by": cr.qc_by,
                "qc_comment": cr.qc_comment,
                "qc_at": cr.qc_at,
                "created_at": cr.created_at,
                "document_name": document_name,
                "doc_type": doc_type_value,
                "doc_classification_level": doc_level,
                "doc_classification_confidence": doc_conf,
                "structured_data": cr.structured_data,
                "conditional_check_triggered": cr.conditional_check_triggered,
                "trigger_name": cr.trigger_name,
            }
            items.append(item)

        return items, total
