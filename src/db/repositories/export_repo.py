# src/db/repositories/export_repo.py

"""
Repository for Export operations.
"""

import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.export import Export


class ExportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        deal_id: uuid.UUID,
        run_id: uuid.UUID | None,
        export_type: str,
        requested_by: str | None = None,
        requester_role: str | None = None,
        status: str = "pending",
        file_refs: dict | None = None,
        file_size_bytes: int | None = None,
    ) -> Export:
        export = Export(
            deal_id=deal_id,
            run_id=run_id,
            export_type=export_type,
            requested_by=requested_by,
            requester_role=requester_role,
            status=status,
            file_refs=file_refs,
            file_size_bytes=file_size_bytes,
        )
        self.session.add(export)
        await self.session.flush()
        return export

    async def get_by_id(self, export_id: uuid.UUID) -> Export | None:
        stmt = select(Export).where(Export.id == export_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_run(self, run_id: uuid.UUID) -> list[Export]:
        stmt = (
            select(Export)
            .where(Export.run_id == run_id)
            .order_by(Export.created_at.desc())
        )
        result = await self.session.execute(stmt)
        exports: Sequence[Export] = result.scalars().all()
        return list(exports)

    async def list_for_deal(self, deal_id: uuid.UUID) -> list[Export]:
        stmt = (
            select(Export)
            .where(Export.deal_id == deal_id)
            .order_by(Export.created_at.desc())
        )
        result = await self.session.execute(stmt)
        exports: Sequence[Export] = result.scalars().all()
        return list(exports)
