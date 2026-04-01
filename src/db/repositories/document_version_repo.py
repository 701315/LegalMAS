"""
Repository for DocumentVersion CRUD operations.

Для непрофессионального программиста:

- Этот репозиторий — единственная "официальная точка", через которую стадии
  пайплайна должны обновлять ссылки на артефакты DocumentVersion.
- Здесь мы храним не только legacy refs (raw/sanitized), но и новые refs
  для одноязычного пайплайна:
  - layout_primary_ref;
  - layout_primary_sanitized_ref.
- Благодаря этому downstream-стадии (PII, structure, content service, checks)
  могут брать нужный layout из БД, а не вычислять путь в MinIO вручную.
"""

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.document import DocumentVersion


class DocumentVersionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        document_id: uuid.UUID,
        version_num: int = 1,
        original_ref: str | None = None,
        origin_filetype: str | None = None,
        origin_extension: str | None = None,
    ) -> DocumentVersion:
        """Create a new document version."""
        version = DocumentVersion(
            document_id=document_id,
            version_num=version_num,
            original_ref=original_ref,
            origin_filetype=origin_filetype,
            origin_extension=origin_extension,
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
        layout_primary_ref: str | None = None,
        sanitized_ref: str | None = None,
        layout_primary_sanitized_ref: str | None = None,
        clause_tree_ref: str | None = None,
        extraction_strategy: str | None = None,
        ocr_confidence: float | None = None,
        pipeline_strategy: str | None = None,
        converted_pdf_ref: str | None = None,
    ) -> DocumentVersion | None:
        """
        Update artifact references and processing metadata on a document version.

        Используется разными стадиями:
        - convert_worker:
            converted_pdf_ref
        - extract_worker:
            raw_ref, layout_primary_ref, extraction_strategy, ocr_confidence, pipeline_strategy
        - pii_sanitizer:
            sanitized_ref, layout_primary_sanitized_ref
        - structure_builder:
            clause_tree_ref

        Важно:
        - raw_ref / sanitized_ref оставляем для backward compatibility;
        - layout_primary_ref / layout_primary_sanitized_ref — это новый основной
          контракт для одноязычного downstream-пайплайна.
        """
        values: dict[str, object] = {}

        if raw_ref is not None:
            values["text_layout_raw_ref"] = raw_ref

        if layout_primary_ref is not None:
            values["layout_primary_ref"] = layout_primary_ref

        if sanitized_ref is not None:
            values["text_layout_sanitized_ref"] = sanitized_ref

        if layout_primary_sanitized_ref is not None:
            values["layout_primary_sanitized_ref"] = layout_primary_sanitized_ref

        if clause_tree_ref is not None:
            values["clause_tree_ref"] = clause_tree_ref

        if extraction_strategy is not None:
            values["extraction_strategy"] = extraction_strategy

        if ocr_confidence is not None:
            values["ocr_confidence"] = ocr_confidence

        if pipeline_strategy is not None:
            values["pipeline_strategy"] = pipeline_strategy

        if converted_pdf_ref is not None:
            values["converted_pdf_ref"] = converted_pdf_ref

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
    