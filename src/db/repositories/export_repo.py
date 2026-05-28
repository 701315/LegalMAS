"""
Repository for Export operations.
"""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.export import Export


class ExportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        deal_id: uuid.UUID,
        run_id: uuid.UUID,
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
        await self.session.refresh(export)
        return export

    async def get_by_id(self, export_id: uuid.UUID) -> Export | None:
        stmt = select(Export).where(Export.id == export_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update(
        self,
        export_id: uuid.UUID,
        values: dict[str, Any],
    ) -> Export | None:
        """
        Обновляет запись Export по id.

        Использует UPDATE ... RETURNING для атомарного обновления без
        дополнительного SELECT. После обновления возвращает актуальный объект.

        Пример:
            await repo.update(export_id, {"status": "processing"})
            await repo.update(export_id, {
                "status": "completed",
                "file_ref": "exports/run-123/report.docx",
                "file_size_bytes": 245760,
            })
            await repo.update(export_id, {
                "status": "failed",
                "error_message": "export_core raised ValueError: ...",
            })
        """
        if not values:
            return await self.get_by_id(export_id)

        stmt = (
            update(Export)
            .where(Export.id == export_id)
            .values(**values)
            .execution_options(synchronize_session="fetch")
        )
        await self.session.execute(stmt)

        # Инвалидируем кэш identity map, чтобы refresh получил свежие данные
        export = await self.get_by_id(export_id)
        if export is not None:
            await self.session.refresh(export)
        return export

    async def list_for_run(self, run_id: uuid.UUID) -> list[Export]:
        stmt = select(Export).where(Export.run_id == run_id).order_by(Export.created_at.desc())
        result = await self.session.execute(stmt)
        exports: Sequence[Export] = result.scalars().all()
        return list(exports)

    async def list_for_deal(self, deal_id: uuid.UUID) -> list[Export]:
        stmt = select(Export).where(Export.deal_id == deal_id).order_by(Export.created_at.desc())
        result = await self.session.execute(stmt)
        exports: Sequence[Export] = result.scalars().all()
        return list(exports)
