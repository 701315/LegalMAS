# src/db/repositories/document_version_repo.py

"""
Repository for DocumentVersion CRUD operations.

- Здесь мы храним не только legacy refs (raw/sanitized), но и новые refs
  для одноязычного пайплайна:
  - layout_primary_ref;
  - layout_primary_sanitized_ref;
  - pii_mapping_ref — зашифрованный PII-маппинг для reveal;
  - file_graph_ref, segments_count — структура файла (v2);
  - chunks_manifest_v2_ref — file-level манифест чанков (CHUNKS v2);
  - segment_chunks_ref — ссылки на чанки сегментов лежат в DocumentSegment.
- Сейчас основным источником истины являются:
  - DocumentSegment.segment_chunks_ref
  - DocumentVersion.chunks_manifest_v2_ref
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any
from sqlalchemy import func, select, update
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
        """
        Get the latest version of a document.

        Для непрофессионального программиста:
        - у одного документа может быть несколько технических версий;
        - нам обычно нужна самая новая (с максимальным version_num);
        - этот метод возвращает одну последнюю версию для одного document_id.
        """
        result = await self.session.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_num.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest_for_documents(
        self,
        document_ids: Sequence[uuid.UUID],
    ) -> dict[uuid.UUID, DocumentVersion]:
        """
        Вернуть последние версии сразу для набора документов.

        Формат результата:
            {
                <document_id>: <latest DocumentVersion>,
                ...
            }

        Для непрофессионального программиста:
        - этот метод нужен, когда у нас есть страница документов в UI;
        - если для каждого документа отдельно вызывать get_latest(...),
          получится N+1 запросов к базе, а это плохой production-паттерн;
        - поэтому мы делаем один batch-запрос и сразу получаем latest version
          для всех document_id.

        Как работает логика:
        1. Во внутреннем подзапросе берём максимальный version_num
           для каждого document_id.
        2. Затем соединяем этот подзапрос с таблицей document_versions,
           чтобы получить полные ORM-объекты DocumentVersion.
        3. Возвращаем словарь, где ключ — document_id, а значение —
           соответствующая latest версия.

        Важно:
        - если для какого-то документа версий ещё нет, он просто не попадёт
          в результат;
        - метод ничего не изменяет в БД, он только читает данные.
        """
        if not document_ids:
            return {}

        unique_document_ids = list(dict.fromkeys(document_ids))

        latest_versions_subquery = (
            select(
                DocumentVersion.document_id.label("document_id"),
                func.max(DocumentVersion.version_num).label("max_version_num"),
            )
            .where(DocumentVersion.document_id.in_(unique_document_ids))
            .group_by(DocumentVersion.document_id)
            .subquery()
        )

        stmt = select(DocumentVersion).join(
            latest_versions_subquery,
            (DocumentVersion.document_id == latest_versions_subquery.c.document_id)
            & (DocumentVersion.version_num == latest_versions_subquery.c.max_version_num),
        )

        result = await self.session.execute(stmt)
        versions = list(result.scalars().all())

        return {version.document_id: version for version in versions}

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
        file_graph_ref: str | None = None,
        segments_count: int | None = None,
        chunks_manifest_v2_ref: str | None = None,
        chunk_plan_ref: str | None = None,
        pii_mapping_ref: str | None = None,
        # ── v2/v3 Layout Pipeline (canonical + language inventory) ──
        canonical_layout_ref: str | None = None,
        detected_languages: Sequence[str] | None = None,
    ) -> DocumentVersion | None:
        """
        Update artifact references and processing metadata on a document version.

        Используется разными стадиями:
        - convert_worker:
            converted_pdf_ref
        - build_primary_language_source (v2/v3):
            canonical_layout_ref, detected_languages, layout_primary_ref
        - extract_worker:
            raw_ref, layout_primary_ref, extraction_strategy,
            ocr_confidence, pipeline_strategy
        - pii_sanitizer:
            sanitized_ref, layout_primary_sanitized_ref, pii_mapping_ref
        - structure_builder:
            clause_tree_ref, file_graph_ref, segments_count
        - chunk_builder:
            chunks_manifest_v2_ref

        Важно:
        - canonical_layout_ref — S3 URI канонического многоязычного макета;
        - detected_languages — authoritative список языков документа (конвертируется в list для PG ARRAY);
        - None означает "не обновлять это поле";
        - если version_id не найден, метод возвращает None.
        """
        values: dict[str, Any] = {}  # Изменено на Any для поддержки списков (detected_languages)

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

        if file_graph_ref is not None:
            values["file_graph_ref"] = file_graph_ref

        if segments_count is not None:
            values["segments_count"] = segments_count

        if chunks_manifest_v2_ref is not None:
            values["chunks_manifest_v2_ref"] = chunks_manifest_v2_ref

        if chunk_plan_ref is not None:
            values["chunk_plan_ref"] = chunk_plan_ref

        if pii_mapping_ref is not None:
            values["pii_mapping_ref"] = pii_mapping_ref

        # ── v2/v3 Layout Pipeline fields ──────────────────────────────
        if canonical_layout_ref is not None:
            values["canonical_layout_ref"] = canonical_layout_ref

        if detected_languages is not None:
            # Предотвращает ошибки сериализации: SQLAlchemy PG_ARRAY строго требует list, а не tuple
            values["detected_languages"] = list(detected_languages)

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
    

    