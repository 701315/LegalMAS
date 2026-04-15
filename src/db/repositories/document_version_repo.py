# src/db/repositories/document_version_repo.py

"""
Repository for DocumentVersion CRUD operations.

...

- Здесь мы храним не только legacy refs (raw/sanitized), но и новые refs
  для одноязычного пайплайна:
  - layout_primary_ref;
  - layout_primary_sanitized_ref;
  - file_graph_ref, segments_count — структура файла (v2);
  - chunks_manifest_v2_ref — file-level манифест чанков (CHUNKS v2);
  - segment_chunks_ref — ссылки на чанки сегментов лежат в DocumentSegment.
- Поле chunks_ref считается LEGACY и используется только старым кодом
  (ChunkSnapshotReader v1, старый Retrieval/CheckRunner).
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

    async def update_chunks_v2_ref(
        self,
        version_id: uuid.UUID,
        chunks_manifest_v2_ref: str,
    ) -> DocumentVersion | None:
        """
        Update only CHUNKS v2 file-level manifest reference.

        Используется CHUNKS v2 worker-ом после успешной записи
        chunks_manifest_v2.json в artifact storage.
        """
        return await self.update_refs(
            version_id=version_id,
            chunks_manifest_v2_ref=chunks_manifest_v2_ref,
        )

    async def update_chunks_legacy_ref(
        self,
        version_id: uuid.UUID,
        chunks_ref: str,
    ) -> DocumentVersion | None:
        """
        Update only legacy chunks_ref.
        """
        return await self.update_refs(
            version_id=version_id,
            chunks_ref=chunks_ref,
        )

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
        primary_source_ref: str | None = None,
        chunks_ref: str | None = None,
        file_graph_ref: str | None = None,
        segments_count: int | None = None,
        chunks_manifest_v2_ref: str | None = None,
    ) -> DocumentVersion | None:
        """
        Update artifact references and processing metadata on a document version.

        Используется разными стадиями:
        - convert_worker:
            converted_pdf_ref
        - build_primary_language_source:
            primary_source_ref
        - extract_worker:
            raw_ref, layout_primary_ref, extraction_strategy,
            ocr_confidence, pipeline_strategy
        - pii_sanitizer:
            sanitized_ref, layout_primary_sanitized_ref
        - structure_builder:
            clause_tree_ref, file_graph_ref, segments_count
        - chunk_builder:
            chunks_ref (LEGACY), chunks_manifest_v2_ref (v2)
        - chunks_ref и chunks_manifest_v2_ref обновляются независимо:
          * legacy path может писать только chunks_ref;
          * v2 path может писать только chunks_manifest_v2_ref;
          * transitional dual-write режим может писать оба поля.

        Важно:
        - raw_ref / sanitized_ref оставляем для backward compatibility;
        - layout_primary_ref / layout_primary_sanitized_ref — это новый основной
          контракт для одноязычного downstream-пайплайна;
        - primary_source_ref — одноязычный source (PDF) до extract;
        - chunks_ref — LEGACY snapshot чанков (section/clause/subclause)
          для старого Retrieval/CheckRunner;
        - chunks_manifest_v2_ref — новый file-level манифест чанков (CHUNKS v2);
        - None означает "не обновлять это поле";
        - если version_id не найден, метод возвращает None.
        """
        values: dict[str, str | float | int] = {}

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

        if primary_source_ref is not None:
            values["primary_source_ref"] = primary_source_ref

        if chunks_ref is not None:
            values["chunks_ref"] = chunks_ref

        if file_graph_ref is not None:
            values["file_graph_ref"] = file_graph_ref

        if segments_count is not None:
            values["segments_count"] = segments_count

        if chunks_manifest_v2_ref is not None:
            values["chunks_manifest_v2_ref"] = chunks_manifest_v2_ref

        if not values:
            return await self.get_by_id(version_id)

        existing = await self.get_by_id(version_id)
        if not existing:
            return None

        stmt = (
            update(DocumentVersion)
            .where(DocumentVersion.id == version_id)
            .values(**values)
            .returning(DocumentVersion)
        )
        result = await self.session.execute(stmt)
        version = result.scalar_one_or_none()

        if version:
            await self.session.flush()

        return version
    
    