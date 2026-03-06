"""
Repository for Document CRUD and classification operations.

Этот модуль инкапсулирует всю работу с таблицей документов:
- создание записей о документах сделки;
- получение документов по id, по сделке, по SHA‑256 (для дедупликации);
- обновление статуса документа (pending, classified, quarantined и т.д.);
- обновление результатов классификации (doc_type, уровень и уверенность,
  детали классификации, applicable_triggers, язык, юрисдикция, версия playbook);
- вспомогательные выборки для аналитики (количество по статусам,
  выборка по типу и минимальной уверенности).

Репозиторий используется бизнес‑логикой анализа и API‑слоем,
чтобы не работать с ORM напрямую из обработчиков HTTP и воркеров.
"""


import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import DocumentStatus
from ..models.document import Document

class DocumentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        deal_id: uuid.UUID,
        bundle_id: uuid.UUID,
        filename: str,
        folder_path: str | None = None,
        sha256_file: str | None = None,
        status: str = "pending",
    ) -> Document:
        """Create a new document record."""
        doc = Document(
            deal_id=deal_id,
            bundle_id=bundle_id,
            filename=filename,
            folder_path=folder_path,
            sha256_file=sha256_file,
            status=status,
        )
        self.session.add(doc)
        await self.session.flush()
        return doc

    async def get_by_id(self, doc_id: uuid.UUID) -> Document | None:
        """Get document by ID."""
        result = await self.session.execute(select(Document).where(Document.id == doc_id))
        return result.scalar_one_or_none()

    async def get_by_deal(
        self,
        deal_id: uuid.UUID,
        status: str | None = None,
        doc_type: str | None = None,
    ) -> list[Document]:
        """Get documents for a deal, optionally filtered."""
        stmt = select(Document).where(Document.deal_id == deal_id)
        if status is not None:
            stmt = stmt.where(Document.status == status)
        if doc_type is not None:
            stmt = stmt.where(Document.doc_type == doc_type)
        stmt = stmt.order_by(Document.folder_path, Document.filename)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_sha256(self, deal_id: uuid.UUID, sha256: str) -> Document | None:
        """Find document by SHA256 hash within a deal (for dedup)."""
        result = await self.session.execute(
            select(Document).where(
                Document.deal_id == deal_id,
                Document.sha256_file == sha256,
            )
        )
        return result.scalar_one_or_none()

    async def update_status(self, doc_id: uuid.UUID, status: str, **kwargs) -> Document | None:
        """Update document status and optional fields."""
        values = {"status": status, **kwargs}
        stmt = update(Document).where(Document.id == doc_id).values(**values).returning(Document)
        result = await self.session.execute(stmt)
        doc = result.scalar_one_or_none()
        if doc:
            await self.session.flush()
        return doc

    async def update_classification(
        self,
        doc_id: uuid.UUID,
        doc_type: str,
        classification_confidence: float,
        classification_level: str,
        classification_details: dict,
        applicable_triggers: list[str],
        language: str | None = None,  # Добавлено
        jurisdiction: str | None = None,  # Добавлено
        playbook_version_id: uuid.UUID | None = None,
    ) -> Document | None:
        """Update document classification results."""
        values = {
            "doc_type": doc_type,
            "classification_confidence": classification_confidence,
            "classification_level": classification_level,
            "classification_details": classification_details,
            "applicable_triggers": applicable_triggers,
        }

        # Обновляем язык и юрисдикцию, если они переданы
        if language:
            values["language"] = language
        if jurisdiction:
            values["jurisdiction_guess"] = jurisdiction

        if playbook_version_id is not None:
            values["playbook_version_id"] = playbook_version_id

        stmt = update(Document).where(Document.id == doc_id).values(**values).returning(Document)
        result = await self.session.execute(stmt)
        doc = result.scalar_one_or_none()
        if doc:
            await self.session.flush()
        return doc

    async def count_by_status(self, deal_id: uuid.UUID) -> dict[str, int]:
        """Count documents by status for a deal."""
        stmt = (
            select(Document.status, func.count(Document.id))
            .where(Document.deal_id == deal_id)
            .group_by(Document.status)
        )
        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def get_by_type_and_confidence(
        self,
        deal_id: uuid.UUID,
        doc_type: str,
        min_confidence: float = 0.0,
    ) -> list[Document]:
        """Get documents by type with minimum classification confidence."""
        stmt = (
            select(Document)
            .where(
                Document.deal_id == deal_id,
                Document.doc_type == doc_type,
                Document.classification_confidence >= min_confidence,
            )
            .order_by(Document.classification_confidence.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_low_confidence_docs(
        self,
        deal_id: uuid.UUID,
        threshold: float = 0.6,
    ) -> list[Document]:
        """
        Вернуть документы с низкой уверенностью классификации
        для указанной сделки.
        """
        stmt = (
            select(Document)
            .where(Document.deal_id == deal_id)
            .where(Document.classification_confidence < threshold)
            .where(Document.classification_confidence > 0)
            .order_by(Document.classification_confidence.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_quarantined(self, deal_id: uuid.UUID) -> list[Document]:
        """Get all documents in quarantine status for a deal."""
        stmt = select(Document).where(
            Document.deal_id == deal_id,
            Document.status == DocumentStatus.QUARANTINE.value,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def reset_for_reprocessing(
        self,
        doc_id: uuid.UUID,
        new_status: str = "pending",
        clear_classification: bool = True,
    ) -> Document | None:
        """
        Сбросить документ для повторной обработки:
        - статус → new_status (по умолчанию 'pending');
        - при clear_classification=True обнулить поля классификации.
        """
        values: dict[str, object] = {"status": new_status}

        if clear_classification:
            values.update(
                {
                    "doc_type": None,
                    "classification_confidence": None,
                    "classification_level": None,
                    "classification_details": None,
                    "applicable_triggers": None,
                }
            )

        stmt = (
            update(Document)
            .where(Document.id == doc_id)
            .values(**values)
            .returning(Document)
        )
        result = await self.session.execute(stmt)
        doc = result.scalar_one_or_none()
        if doc:
            await self.session.flush()
        return doc
    
    async def get_page_for_deal(
        self,
        deal_id: uuid.UUID,
        page: int,
        per_page: int,
        include_classification: bool = False,
    ) -> tuple[list[Document], int]:
        """
        Вернуть страницу документов сделки + общее количество.
        """
        offset = (page - 1) * per_page

        # 1) total
        count_stmt = select(func.count(Document.id)).where(Document.deal_id == deal_id)
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one() or 0

        if total == 0:
            return [], 0

        # 2) страница
        stmt = select(Document).where(Document.deal_id == deal_id)

        if include_classification:
            stmt = stmt.order_by(
                Document.status,
                Document.doc_type.is_(None),
                Document.doc_type,
                Document.classification_confidence.desc().nullslast(),
                Document.folder_path,
                Document.filename,
            )
        else:
            stmt = stmt.order_by(
                Document.folder_path,
                Document.filename,
            )

        stmt = stmt.offset(offset).limit(per_page)
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return items, total
