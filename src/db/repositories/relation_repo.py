# src/db/repositories/relation_repo.py

"""
Repository for DocumentRelation and document families operations.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.relation import (
    DocumentFamily,
    DocumentFamilyMember,
    DocumentRelation,
)


class RelationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ---------- Relations ----------

    async def create(
        self,
        deal_id: uuid.UUID,
        source_doc_id: uuid.UUID,
        target_doc_id: uuid.UUID,
        relation_type: str,
        confidence: float = 1.0,
        evidence_text: str | None = None,
        family_id: uuid.UUID | None = None,  # оставляем в сигнатуре для совместимости
    ) -> DocumentRelation:
        """Create a document relation."""
        relation = DocumentRelation(
            deal_id=deal_id,
            source_doc_id=source_doc_id,
            target_doc_id=target_doc_id,
            relation_type=relation_type,
            confidence=confidence,
            evidence_text=evidence_text,
            # family_id=family_id,  # поле в модели сейчас нет, так что параметр игнорируем
        )
        self.session.add(relation)
        await self.session.flush()
        return relation

    async def get_related(
        self,
        deal_id: uuid.UUID,
        doc_id: uuid.UUID,
        relation_types: list[str] | None = None,
    ) -> list[DocumentRelation]:
        """Get all relations where doc_id is source OR target."""
        stmt = select(DocumentRelation).where(
            DocumentRelation.deal_id == deal_id,
            (DocumentRelation.source_doc_id == doc_id) | (DocumentRelation.target_doc_id == doc_id),
        )
        if relation_types:
            stmt = stmt.where(DocumentRelation.relation_type.in_(relation_types))
        stmt = stmt.order_by(DocumentRelation.confidence.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # get_by_family пока оставим как заглушку или уберём совсем,
    # потому что family_id в DocumentRelation у нас нет.
    # Если он тебе не нужен — проще удалить метод, чтобы не вводить в заблуждение.

    # ---------- Families ----------

    async def create_family(
        self,
        deal_id: uuid.UUID,
        master_doc_id: uuid.UUID,
        master_classification_level: str | None = None,
    ) -> DocumentFamily:
        """Create a document family."""
        family = DocumentFamily(
            deal_id=deal_id,
            master_doc_id=master_doc_id,
            master_classification_level=master_classification_level,
        )
        self.session.add(family)
        await self.session.flush()
        return family

    async def create_family_member(
        self,
        family_id: uuid.UUID,
        document_id: uuid.UUID,
        relation_to_master: str | None = None,
    ) -> DocumentFamilyMember:
        """Add a document as member of a family."""
        member = DocumentFamilyMember(
            family_id=family_id,
            doc_id=document_id,
            relation_to_master=relation_to_master,
        )
        self.session.add(member)
        await self.session.flush()
        return member

    async def get_families_for_deal(
        self,
        deal_id: uuid.UUID,
        include_members: bool = True,
    ) -> list[DocumentFamily]:
        """Get all families for a deal."""
        stmt = select(DocumentFamily).where(DocumentFamily.deal_id == deal_id)
        if include_members:
            stmt = stmt.options(selectinload(DocumentFamily.members))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_document_family_id(
        self,
        document_id: uuid.UUID,
    ) -> uuid.UUID | None:
        """
        Вернуть family_id для документа, если он состоит в каком‑то семействе.
        """
        stmt = (
            select(DocumentFamilyMember.family_id)
            .where(DocumentFamilyMember.doc_id == document_id)
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


