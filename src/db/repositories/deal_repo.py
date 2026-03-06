"""
Repository for Deal CRUD operations.
Thin wrapper over SQLAlchemy ORM — no business logic here.
"""

import uuid

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.deal import Deal


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
        result = await self.session.execute(select(Deal).where(Deal.id == deal_id))
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

    async def get_all(self) -> list[Deal]:
        """Вернуть все сделки (для dev / админских сценариев)."""
        stmt = select(Deal).order_by(Deal.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(self, deal_id: uuid.UUID, status: str) -> Deal | None:
        """Update deal status. Returns updated deal or None if not found."""
        stmt = update(Deal).where(Deal.id == deal_id).values(status=status).returning(Deal)
        result = await self.session.execute(stmt)
        deal = result.scalar_one_or_none()
        if deal:
            await self.session.flush()
        return deal

    async def get_page(
        self,
        page: int,
        per_page: int,
        status: str | None = None,
        tenant_id: uuid.UUID | None = None,
    ) -> tuple[list[Deal], int]:
        """
        Вернуть одну страницу сделок + общее количество, опционально фильтруя по статусу.
        """
        offset = (page - 1) * per_page

        filters = []
        if status is not None:
            filters.append(Deal.status == status)
        if tenant_id is not None:
            filters.append(Deal.tenant_id == tenant_id)

        # 1) считаем total с учётом фильтров
        count_stmt = select(func.count(Deal.id))
        if filters:
            count_stmt = count_stmt.where(*filters)

        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one() or 0

        if total == 0:
            return [], 0

        # 2) выбираем записи страницы
        stmt = (
            select(Deal)
            .where(*filters)
            .order_by(Deal.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return items, total
    
    async def set_last_run_id(
        self,
        deal_id: uuid.UUID,
        run_id: uuid.UUID,
    ) -> None:
        """Set latest run id for a deal."""
        stmt = (
            update(Deal)
            .where(Deal.id == deal_id)
            .values(last_run_id=run_id)
        )
        await self.session.execute(stmt)
        await self.session.flush()


