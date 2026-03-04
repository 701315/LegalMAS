"""
Repository for DocumentVersion CRUD operations.
"""

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.document import DocumentVersion


class DocumentVersionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        document_id: uuid.UUID,
        version_num: int = 1,
        original_ref: str | None = None,
    ) -> DocumentVersion:
        """Create a new document version."""
        version = DocumentVersion(
            document_id=document_id,
            version_num=version_num,
            original_ref=original_ref,
        )
        self.session.add(version)
        await self.session.flush()
        return version

    async def get_by_id(self, version_id: uuid.UUID) -> DocumentVersion | None:
        """Get document version by ID."""
        result = await self.session.execute(
            select(DocumentVersion).where(DocumentVersion.id == version_id)
        )
        return result.scalar_one_or_none()

    async def get_latest(self, document_id: uuid.UUID) -> DocumentVersion | None:
        """Get the latest version of a document."""
        result = await self.session.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_num.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def update_refs(
        self,
        version_id: uuid.UUID,
        raw_ref: str | None = None,
        sanitized_ref: str | None = None,
        clause_tree_ref: str | None = None,
        extraction_strategy: str | None = None,
        ocr_confidence: float | None = None,
    ) -> DocumentVersion | None:
        """
        Update S3 references on a document version.
        Used by Stage 4 (raw), Stage 5 (sanitized), and Stage 6 (clause_tree).
        """
        values = {}
        if raw_ref is not None:
            values["text_layout_raw_ref"] = raw_ref
        if sanitized_ref is not None:
            values["text_layout_sanitized_ref"] = sanitized_ref
        if clause_tree_ref is not None:
            values["clause_tree_ref"] = clause_tree_ref
        if extraction_strategy is not None:
            values["extraction_strategy"] = extraction_strategy
        if ocr_confidence is not None:
            values["ocr_confidence"] = ocr_confidence

        if not values:
            return await self.get_by_id(version_id)

        stmt = (
            update(DocumentVersion)
            .where(DocumentVersion.id == version_id)
            .values(**values)
            .returning(DocumentVersion)
        )
        result = await self.session.execute(stmt)
        ver = result.scalar_one_or_none()
        if ver:
            await self.session.flush()
        return ver
