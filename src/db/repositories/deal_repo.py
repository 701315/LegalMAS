"""
Repository for Deal CRUD operations.
Thin wrapper over SQLAlchemy ORM — no business logic here.
"""

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.deal import Deal


class DealRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        tenant_id: uuid.UUID,
        name: str,
        deal_type: str | None = None,
        jurisdiction: str | None = None,
        languages: list[str] | None = None,
        pii_mode: str = "local_only",
        profile: str = "full",
        playbook_version_id: uuid.UUID | None = None,
        metadata_: dict | None = None,
    ) -> Deal:
        """Create a new deal."""
        deal = Deal(
            tenant_id=tenant_id,
            name=name,
            deal_type=deal_type,
            jurisdiction=jurisdiction,
            languages=languages,
            pii_mode=pii_mode,
            profile=profile,
            playbook_version_id=playbook_version_id,
            metadata_=metadata_ or {},
        )
        self.session.add(deal)
        await self.session.flush()
        return deal

    async def get_by_id(self, deal_id: uuid.UUID) -> Deal | None:
        """Get deal by ID. Returns None if not found."""
        result = await self.session.execute(
            select(Deal).where(Deal.id == deal_id)
        )
        return result.scalar_one_or_none()

    async def get_by_tenant(
        self,
        tenant_id: uuid.UUID,
        status: str | None = None,
    ) -> list[Deal]:
        """Get all deals for a tenant, optionally filtered by status."""
        stmt = select(Deal).where(Deal.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(Deal.status == status)
        stmt = stmt.order_by(Deal.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(self, deal_id: uuid.UUID, status: str) -> Deal | None:
        """Update deal status. Returns updated deal or None if not found."""
        stmt = (
            update(Deal)
            .where(Deal.id == deal_id)
            .values(status=status)
            .returning(Deal)
        )
        result = await self.session.execute(stmt)
        deal = result.scalar_one_or_none()
        if deal:
            await self.session.flush()
        return deal
