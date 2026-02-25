"""
Repository for DocumentRelation and Family operations.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.relation import DocumentRelation, Family


class RelationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        deal_id: uuid.UUID,
        source_doc_id: uuid.UUID,
        target_doc_id: uuid.UUID,
        relation_type: str,
        confidence: float = 1.0,
        evidence_text: str | None = None,
        family_id: uuid.UUID | None = None,
    ) -> DocumentRelation:
        """Create a document relation."""
        relation = DocumentRelation(
            deal_id=deal_id,
            source_doc_id=source_doc_id,
            target_doc_id=target_doc_id,
            relation_type=relation_type,
            confidence=confidence,
            evidence_text=evidence_text,
            family_id=family_id,
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

    async def get_by_family(self, family_id: uuid.UUID) -> list[DocumentRelation]:
        """Get all relations in a family."""
        result = await self.session.execute(
            select(DocumentRelation)
            .where(DocumentRelation.family_id == family_id)
            .order_by(DocumentRelation.relation_type)
        )
        return list(result.scalars().all())

    async def create_family(self, deal_id: uuid.UUID, master_doc_id: uuid.UUID) -> Family:
        """Create a document family."""
        family = Family(deal_id=deal_id, master_doc_id=master_doc_id)
        self.session.add(family)
        await self.session.flush()
        return family
