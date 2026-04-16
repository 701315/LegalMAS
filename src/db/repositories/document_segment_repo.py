# src/db/repositories/document_segment_repo.py

"""
Repository for DocumentSegment CRUD operations.

Для непрофессионального программиста:

- Этот репозиторий управляет logical segments внутри одного физического файла.
- Используется в multi-document режиме (v2), когда structure stage
  строит file_graph и отдельные clause trees по сегментам.
- На первом этапе нам нужен простой и безопасный контракт:
  delete old segments for version -> insert fresh segments from file_graph.

Важно:
- Все операции выполняются в рамках текущей транзакции UoW.
- replace_segments() не делает commit — commit остаётся на уровне worker/service.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.document import DocumentSegment


class DocumentSegmentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_version(
        self,
        document_version_id: uuid.UUID,
    ) -> list[DocumentSegment]:
        result = await self.session.execute(
            select(DocumentSegment)
            .where(DocumentSegment.document_version_id == document_version_id)
            .order_by(DocumentSegment.segment_order.asc())
        )
        return list(result.scalars().all())
    
    async def all_segments_have_chunk_refs(
        self,
        document_version_id: uuid.UUID,
    ) -> bool:
        summary = await self.get_chunk_refs_summary(document_version_id)
        return (
            summary["total_segments"] > 0
            and summary["segments_with_chunks"] == summary["total_segments"]
        )

    async def delete_by_version(
        self,
        document_version_id: uuid.UUID,
    ) -> None:
        await self.session.execute(
            delete(DocumentSegment).where(
                DocumentSegment.document_version_id == document_version_id
            )
        )

    async def bulk_create(
        self,
        items: Sequence[dict],
    ) -> list[DocumentSegment]:
        rows: list[DocumentSegment] = []

        required_keys = {
            "document_version_id",
            "document_id",
            "segment_id",
            "segment_order",
            "segment_type",
            "page_start",
            "page_end",
            "is_primary",
            "confidence",
        }

        for index, item in enumerate(items):
            missing = required_keys.difference(item.keys())
            if missing:
                raise ValueError(
                    f"DocumentSegment item at index {index} is missing keys: {sorted(missing)}"
                )

            row = DocumentSegment(**item)
            self.session.add(row)
            rows.append(row)

        return rows

    async def replace_segments(
        self,
        *,
        document_version_id: uuid.UUID,
        items: Sequence[dict],
    ) -> list[DocumentSegment]:
        await self.delete_by_version(document_version_id)

        if not items:
            await self.session.flush()
            return []

        rows = await self.bulk_create(items)
        await self.session.flush()
        return rows
    
    
    async def get_chunk_refs_summary(
        self,
        document_version_id: uuid.UUID,
    ) -> dict[str, int]:
        total_stmt = select(func.count()).select_from(DocumentSegment).where(
            DocumentSegment.document_version_id == document_version_id
        )
        total = (await self.session.execute(total_stmt)).scalar_one()

        with_chunks_stmt = select(func.count()).select_from(DocumentSegment).where(
            DocumentSegment.document_version_id == document_version_id,
            DocumentSegment.segment_chunks_ref.is_not(None),
        )
        with_chunks = (await self.session.execute(with_chunks_stmt)).scalar_one()

        return {
            "total_segments": int(total or 0),
            "segments_with_chunks": int(with_chunks or 0),
        }