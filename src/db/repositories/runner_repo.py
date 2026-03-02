# src/db/repositories/runner_repo.py

"""Repository for Runner integration with Stage 7 (dedup / relations / families)."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.classifiers.yaml_registry import YAMLRegistry
from src.db.models.document import Document
from src.db.models.relation import DocumentFamily, DocumentFamilyMember


class RunnerRepository:
    """Работает с non-duplicate документами и семьями документов."""

    def __init__(self, session: AsyncSession):
        self.session = session
        # Используем singleton, который сам возьмёт путь из settings.CLASSIFIER_REGISTRY_PATH
        self._registry = YAMLRegistry.get_instance()

    async def get_non_duplicate_docs(self, deal_id: uuid.UUID) -> list[Document]:
        """
        Получить документы для Runner.

        На текущем этапе:
        - файловые дубликаты по SHA256 отсекаются ещё в Import Worker,
          поэтому в таблице documents уже нет точных дублей по содержимому.
        - дополнительный Stage 7 dedup (по содержанию/семьям) работает
          через relations и DocumentFamily, а не через поле is_duplicate.

        TODO (Stage 7): если появится явный флаг/статус дубликата в documents
        или отдельная таблица, здесь можно будет добавить соответствующую
        фильтрацию.
        """
        stmt = select(Document).where(Document.deal_id == deal_id).order_by(Document.created_at)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_document_family(self, doc_id: uuid.UUID) -> list[Document] | None:
        """
        Получить семью документа (все документы семейства).

        1) Находим DocumentFamily через DocumentFamilyMember.doc_id.
        2) По списку members.doc_id вытаскиваем все Document.
        """
        # 1. Найти семью по doc_id
        stmt_family = (
            select(DocumentFamily)
            .join(DocumentFamilyMember, DocumentFamilyMember.family_id == DocumentFamily.id)
            .where(DocumentFamilyMember.doc_id == doc_id)
            .limit(1)
        )
        result_family = await self.session.execute(stmt_family)
        family = result_family.scalar_one_or_none()
        if not family:
            return None

        # 2. Получить все doc_id членов семьи
        member_ids = [m.doc_id for m in family.members]
        if not member_ids:
            return []

        stmt_docs = select(Document).where(Document.id.in_(member_ids))
        result_docs = await self.session.execute(stmt_docs)
        return list(result_docs.scalars().all())

    async def get_master_document(self, doc_id: uuid.UUID) -> Document | None:
        """
        Найти master-документ семьи.

        Приоритет:
        1) Если документ не в семье — вернуть его самого.
        2) Среди членов семьи первым делом ищем doc_type в master_doc_types (YAMLRegistry).
        3) Fallback: возвращаем первый документ семьи.
        """
        family_docs = await self.get_document_family(doc_id)
        if not family_docs:
            stmt = select(Document).where(Document.id == doc_id)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()

        master_types = self._registry.get_master_doc_types()

        for doc in family_docs:
            if doc.doc_type in master_types:
                return doc

        return family_docs[0] if family_docs else None
