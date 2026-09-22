# src/db/repositories/runner_repo.py

"""
Repository for Runner integration (Stage 7–10).

Этот репозиторий инкапсулирует работу Runner-слоя с документами:

- для Stage 7:
  - получение non-duplicate документов для запуска пайплайна;
  - работа с семьями документов (DocumentFamily / DocumentFamilyMember);
  - поиск master-документа в семье.

- для Stage 9–10:
  - загрузка документов и результатов проверок по run_id
    в удобном для Aggregator формате;
  - подготовка данных для UI-API (обзор сделки, грид проверок,
    условные проверки, извлечённые значения).

Источник истины для dedup/master selection:
- persisted DocumentFamily.master_doc_id;
- fallback только при неконсистентных family data.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.logging import get_logger
from services.document_family_dedup import (
    filter_non_duplicate_documents,
    select_family_representative,
    sort_documents_stably,
)

from ..models.document import Document
from ..models.relation import DocumentFamily, DocumentFamilyMember
from ..models.result import CheckResult

logger = get_logger(__name__)


class RunnerRepository:
    """Работает с non-duplicate документами и семьями документов."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _get_family_by_doc_id(self, doc_id: uuid.UUID) -> DocumentFamily | None:
        """
        Найти семью документа и сразу подгрузить members.
        """
        stmt = (
            select(DocumentFamily)
            .options(selectinload(DocumentFamily.members))
            .join(DocumentFamilyMember, DocumentFamilyMember.family_id == DocumentFamily.id)
            .where(DocumentFamilyMember.doc_id == doc_id)
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _load_family_documents(self, family: DocumentFamily) -> list[Document]:
        """
        Загрузить документы одной семьи в детерминированном порядке.
        """
        member_ids = [
            member.doc_id
            for member in (family.members or [])
            if getattr(member, "doc_id", None) is not None
        ]
        if not member_ids:
            return []

        stmt = (
            select(Document)
            .where(Document.id.in_(member_ids))
            .order_by(Document.created_at.asc(), Document.id.asc())
        )
        result = await self.session.execute(stmt)
        docs = list(result.scalars().all())
        return sort_documents_stably(docs)

    async def get_non_duplicate_docs(self, deal_id: uuid.UUID) -> list[Document]:
        """
        Получить non-duplicate документы сделки.

        Правила:
        - документы вне family возвращаются как есть;
        - из каждой family остаётся ровно один representative/master;
        - primary truth = DocumentFamily.master_doc_id;
        - если family неконсистентна и master отсутствует среди документов сделки,
          применяется детерминированный fallback и пишется warning.

        Порядок результата детерминированный:
        created_at ASC, id ASC.
        """
        docs_stmt = (
            select(Document)
            .where(Document.deal_id == deal_id)
            .order_by(Document.created_at.asc(), Document.id.asc())
        )
        docs_result = await self.session.execute(docs_stmt)
        documents = list(docs_result.scalars().all())

        if not documents:
            return []

        families_stmt = (
            select(DocumentFamily)
            .options(selectinload(DocumentFamily.members))
            .where(DocumentFamily.deal_id == deal_id)
            .order_by(DocumentFamily.created_at.asc(), DocumentFamily.id.asc())
        )
        families_result = await self.session.execute(families_stmt)
        families = list(families_result.scalars().all())

        if not families:
            return documents

        doc_ids = {doc.id for doc in documents}

        for family in families:
            present_member_ids = {
                member.doc_id
                for member in (family.members or [])
                if getattr(member, "doc_id", None) in doc_ids
            }
            if present_member_ids and family.master_doc_id not in doc_ids:
                logger.warning(
                    "RunnerRepository.get_non_duplicate_docs: family master_doc_id "
                    "missing from deal documents, deterministic fallback will be used",
                    extra={
                        "deal_id": str(deal_id),
                        "family_id": str(family.id),
                        "master_doc_id": str(family.master_doc_id),
                        "present_member_ids": sorted(str(doc_id) for doc_id in present_member_ids),
                    },
                )

        return filter_non_duplicate_documents(
            documents=documents,
            families=families,
        )

    async def get_document_family(self, doc_id: uuid.UUID) -> list[Document] | None:
        """
        Получить все документы семьи указанного документа.

        Возвращает:
        - None, если документ не состоит в семье;
        - список документов семьи в детерминированном порядке — иначе.
        """
        family = await self._get_family_by_doc_id(doc_id)
        if family is None:
            return None

        return await self._load_family_documents(family)

    async def get_master_document(self, doc_id: uuid.UUID) -> Document | None:
        """
        Найти master-документ семьи.

        Правила:
        1) Если документ не в семье — вернуть его самого.
        2) Если семья есть и master_doc_id присутствует — вернуть master.
        3) Если family data неконсистентны — warning + детерминированный fallback.
        """
        family = await self._get_family_by_doc_id(doc_id)

        if family is None:
            stmt = select(Document).where(Document.id == doc_id)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()

        family_docs = await self._load_family_documents(family)
        if not family_docs:
            logger.warning(
                "RunnerRepository.get_master_document: family found but no family documents loaded",
                extra={
                    "doc_id": str(doc_id),
                    "family_id": str(family.id),
                    "master_doc_id": str(family.master_doc_id),
                },
            )
            stmt = select(Document).where(Document.id == doc_id)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()

        docs_by_id = {doc.id: doc for doc in family_docs}
        master_doc = docs_by_id.get(family.master_doc_id)
        if master_doc is not None:
            return master_doc

        logger.warning(
            "RunnerRepository.get_master_document: master_doc_id missing from family documents, "
            "using deterministic fallback",
            extra={
                "doc_id": str(doc_id),
                "family_id": str(family.id),
                "master_doc_id": str(family.master_doc_id),
                "family_doc_ids": [str(doc.id) for doc in family_docs],
            },
        )

        return select_family_representative(
            family_documents=family_docs,
            master_doc_id=None,
        )

    async def load_documents_for_run(self, run_id: uuid.UUID) -> dict[str, dict]:
        """
        Вернуть словарь {document_id: {...}} для всех документов,
        участвовавших в указанном run_id.

        Эти данные используются Aggregator'ом и UI-API для построения
        обзора сделки.

        Spec v2:
        - дополнительно возвращаем classification_requires_review,
          потому что deal_review_service.py уже использует этот флаг
          для requires_manual_review на уровне row DTO.
        """
        stmt = (
            select(Document)
            .join(CheckResult, CheckResult.document_id == Document.id)
            .where(CheckResult.run_id == run_id)
            .distinct()
            .order_by(Document.created_at.asc(), Document.id.asc())
        )
        result = await self.session.execute(stmt)
        docs = result.scalars().all()

        docs_dict: dict[str, dict] = {}
        for d in docs:
            docs_dict[str(d.id)] = {
                "name": d.filename,
                "folder_path": d.folder_path or None,
                "doc_type": d.doc_type or "",
                "status": d.status or "",
                "classification_level": d.classification_level or "",
                "classification_confidence": d.classification_confidence or 0.0,
                "classification_requires_review": bool(
                    getattr(d, "classification_requires_review", False) or False
                ),
                "applicable_triggers": d.applicable_triggers or [],
            }
        return docs_dict

    async def load_check_results_for_run(self, run_id: uuid.UUID) -> list[dict]:
        """
        Вернуть список словарей с результатами проверок для run_id
        в формате, который ожидает Aggregator (Stage 9).

        Эти данные затем передаются в aggregate_results(...).

        Spec v2:
        - дополнительно прокидываем canonical display semantics поля,
          которые уже были сохранены в CheckResult:
            * ui_mode
            * display_text
            * machine_reason_code
            * review_status
            * review_message
            * needs_manual_review
        """
        stmt = select(CheckResult).where(CheckResult.run_id == run_id)
        result = await self.session.execute(stmt)
        rows = result.scalars().all()

        out: list[dict] = []

        for r in rows:
            out.append(
                {
                    "id": str(r.id),
                    "check_id": r.check_id,
                    "check_name": r.check_name,
                    "result": r.result,
                    "severity": r.severity,
                    "value_text": r.value_text,
                    "confidence": r.confidence,
                    "detector_used": r.detector_used or "",
                    "quality_flags": r.quality_flags,
                    "qc_status": r.qc_status or "pending",
                    "document_id": str(r.document_id),
                    "structured_data": r.structured_data or {},
                    "conditional_check_triggered": r.conditional_check_triggered or False,
                    "trigger_name": r.trigger_name or "",
                    "origin": r.origin or None,
                    "page": r.page,
                    "clause_uid": r.clause_uid or "",
                    "element_id": r.element_id,
                    "bbox": r.bbox,
                    # ── B5: anchor denormalization (populated by B4) ──────
                    "primary_anchor_id": (
                        str(r.primary_anchor_id) if r.primary_anchor_id is not None else None
                    ),
                    "primary_anchor_method": r.primary_anchor_method,
                    "primary_anchor_confidence": r.primary_anchor_confidence,
                    "anchor_stale": bool(r.anchor_stale or False),
                    "segment_id": r.segment_id,
                    "segment_type": r.segment_type,
                    "segment_title": r.segment_title,
                    "segment_order": r.segment_order,
                    "is_primary_segment": r.is_primary_segment,
                    "chunk_id": r.chunk_id,
                    "chunk_index": r.chunk_index,
                    "context_trace": r.context_trace,
                    "ui_mode": r.ui_mode,
                    "display_text": r.display_text,
                    "machine_reason_code": r.machine_reason_code,
                    "review_status": r.review_status,
                    "review_message": r.review_message,
                    "needs_manual_review": bool(r.needs_manual_review or False),
                    "execution_status": r.execution_status or "PENDING",
                    "qc_by": r.qc_by,
                    "qc_at": r.qc_at,
                    "qc_comment": r.qc_comment,
                    "started_at": r.started_at,
                    "finished_at": r.finished_at,
                }
            )

        return out

        

    
