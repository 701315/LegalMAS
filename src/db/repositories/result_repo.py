# src/db/repositories/result_repo.py

"""
Repository for CheckResult operations.


Отвечает за:
- создание результатов проверок (create);
- выборку по run (с документами и без);
- пагинацию для DD Grid;
- обновление QC-статуса.


Важно:
- этот слой не решает "что такое structured_data",
  он только аккуратно отдаёт то, что записал раннер
  (ExtractionExecutor / CheckRunner) в CheckResult.structured_data.
- контракт structured_data задаётся в api/schemas/results.py
  (StructuredField / LocationField и т.п.).
"""


import uuid
from datetime import UTC, datetime
from typing import Sequence
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.result import CheckResult
from ..models.document import Document  # подтягиваем документы к результатам


def normalize_origin_type(origin: str | None) -> str | None:
    """
    Нормализует "сырое" поле origin из БД в логический тип источника.

    Возвращает одно из:
    - "global"  — глобальный плейбук;
    - "doctype" — плейбук по типу документа;
    - "custom"  — все прочие случаи / кастомные источники;
    - None      — если origin пустой.
    """
    if origin is None:
        return None

    raw = origin
    upper = raw.upper()

    # Глобальный плейбук (старые и новые варианты)
    if upper == "GLOBAL_PLAYBOOK" or raw == "global_playbook" or raw == "project_playbook":
        return "global"

    # Проверки по типу документа
    if upper == "DOCUMENT_TYPE":
        return "doctype"

    # Всё остальное считаем кастомным/прочим источником
    return "custom"


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
        origin: str | None = None,
    ) -> CheckResult:
        """Создать результат проверки.

        origin:
            Источник определения проверки. Ожидаются значения:
            - "GLOBAL_PLAYBOOK"  – глобальный плейбук,
            - "DOCUMENT_TYPE"    – инструкции по типу документа,
            - "SYSTEM"           – системные/тех. проверки.
            Если не задано, можно передать None — поле останется пустым.
        """
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
            # ВАЖНО: сюда раннер кладёт JSON формата StructuredDataDict
            structured_data=structured_data,
            conditional_check_triggered=conditional_check_triggered,
            trigger_name=trigger_name,
            origin=origin,
        )
        self.session.add(cr)
        await self.session.flush()
        return cr

    async def get_by_run(self, run_id: uuid.UUID, severity: str | None = None) -> list[CheckResult]:
        """Получить все результаты для run (без join с документами)."""
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
        - origin / origin_type (источник определения проверки);
        - document_name, doc_type;
        - doc_classification_level, doc_classification_confidence;
        - doc_requires_manual_review.
        """
        stmt = (
            select(
                CheckResult,
                Document.filename.label("document_name"),
                Document.doc_type.label("doc_type"),
                Document.classification_level.label("doc_classification_level"),
                Document.classification_confidence.label("doc_classification_confidence"),
                Document.classification_requires_review.label("doc_requires_manual_review"),
            )
            .join(Document, Document.id == CheckResult.document_id)
            .where(CheckResult.run_id == run_id)
            .order_by(CheckResult.severity, CheckResult.check_id)
        )

        result = await self.session.execute(stmt)
        rows = result.all()

        out: list[dict] = []
        for (
            cr,
            document_name,
            doc_type,
            doc_level,
            doc_conf,
            doc_requires_manual_review,
        ) in rows:
            # cr — ORM-объект CheckResult; берём его поля как есть
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
                # исходное "сырое" origin
                "origin": cr.origin,
                # нормализованный тип источника для фронта и API
                "origin_type": normalize_origin_type(cr.origin),
                # обогащение из Document
                "document_name": document_name,
                "doc_type": doc_type,
                # доп. поля, которые уже ждёт фронт (через types)
                "doc_classification_level": doc_level,
                "doc_classification_confidence": doc_conf,
                "doc_requires_manual_review": doc_requires_manual_review,
                # structured_data и conditional
                # ОЖИДАНИЕ: cr.structured_data уже в формате StructuredDataDict
                "structured_data": cr.structured_data,
                "conditional_check_triggered": cr.conditional_check_triggered,
                "trigger_name": cr.trigger_name,
            }

            out.append(item)

        return out

    async def get_by_document(self, document_id: uuid.UUID, run_id: uuid.UUID) -> list[CheckResult]:
        """Получить все результаты для документа в рамках одного run."""
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
        """Обновить QC-статус одного результата."""
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
        """Массовое обновление QC-статуса. Возвращает количество обновлённых строк."""
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
        """Посчитать количество результатов по severity для run."""
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
                Document.classification_requires_review.label("doc_requires_manual_review"),
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
        for (
            cr,
            document_name,
            doc_type_value,
            doc_level,
            doc_conf,
            doc_requires_manual_review,
        ) in rows:
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
                # исходное "сырое" origin
                "origin": cr.origin,
                # нормализованный тип источника
                "origin_type": normalize_origin_type(cr.origin),
                "document_name": document_name,
                "doc_type": doc_type_value,
                "doc_classification_level": doc_level,
                "doc_classification_confidence": doc_conf,
                "doc_requires_manual_review": doc_requires_manual_review,
                # structured_data должно быть совместимо с StructuredDataDict
                "structured_data": cr.structured_data,
                "conditional_check_triggered": cr.conditional_check_triggered,
                "trigger_name": cr.trigger_name,
            }

            items.append(item)

        return items, total