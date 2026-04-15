# src/services/pipeline_view/stage_chunks.py

"""
Stage builder: CHUNKS — материализованные чанки документа.

Поддерживает:
1) v2 (manifest + per-segment snapshots через ChunkCorpusReaderV2)
2) legacy snapshot (version.chunks_ref)
3) fallback через DocumentContentService
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.document_pipeline_view import (
    ChunkPreviewDTO,
    ChunksPreviewDTO,
    ChunksSegmentPreviewDTO,
    PipelineSegmentDTO,
    PipelineStageCode,
    PipelineStageKind,
    PipelineStageStatus,
    PipelineStageViewDTO,
    StageMetaDTO,
    StageViewMode,
)
from core.exceptions import PermanentError, TransientError
from core.logging import get_logger
from db.models.document import DocumentSegment
from db.repositories.document_segment_repo import DocumentSegmentRepository
from engine.content.chunk_snapshot_reader import ChunkCorpusReaderV2
from engine.content.document_content_service import DocumentContentService
from services.pipeline_view.representation import with_representation
from storage.artifact_store import ArtifactStore

logger = get_logger(__name__)

# ── Representation kwargs ───────────────────────────────────────────

_CHUNKS_REPR_KWARGS = dict(
    stage_code=PipelineStageCode.CHUNKS,
    friendly_supported=False,
    canonical_description=(
        "Показывается результат этапа CHUNKS: материализованные чанки документа."
    ),
    friendly_description=(
        "Показывается тот же набор чанков в режиме удобного просмотра. "
        "Отдельное friendly-представление для CHUNKS пока не реализовано."
    ),
)


class ChunksStageBuilder:
    """Строит стадию CHUNKS для pipeline view."""

    def __init__(self, session: AsyncSession, store: ArtifactStore):
        self._session = session
        self._store = store
        self._segment_repo = DocumentSegmentRepository(session)
        self._content_service = DocumentContentService(session=session)

    async def build(
        self,
        doc,
        version,
        base_meta: StageMetaDTO,
        view_mode: StageViewMode = StageViewMode.canonical,
    ) -> PipelineStageViewDTO:
        """Основной метод построения стадии CHUNKS."""

        # 1) v2 path
        reader_v2 = ChunkCorpusReaderV2(
            session=self._session,
            artifact_store=self._store,
        )
        raw_chunks_v2 = await reader_v2.load(doc_id=doc.id, levels=["clause"])
        segments = await self._segment_repo.list_by_version(version.id)

        chunk_previews: list[ChunkPreviewDTO] = []
        segments_preview: list[ChunksSegmentPreviewDTO] = []
        artifact_ref: str | None = version.chunks_manifest_v2_ref or version.chunks_ref

        if raw_chunks_v2:
            chunk_previews, segments_preview = self._build_v2_chunks(
                doc, version, raw_chunks_v2, segments,
            )

        # 2) legacy snapshot path
        if not chunk_previews:
            return await self._build_legacy_or_fallback(
                doc, version, base_meta, view_mode,
            )

        # v2 результат
        reconstructed_text = "\n\n".join(
            ch.text for ch in chunk_previews if ch.text.strip()
        )

        preview = ChunksPreviewDTO(
            type="chunks",
            chunks=chunk_previews,
            segments=segments_preview,
            reconstructed_text=reconstructed_text,
            raw_json=None,
        )

        meta = StageMetaDTO(
            page_count=base_meta.page_count,
            element_count=base_meta.element_count,
            chunk_count=len(chunk_previews),
            section_count=base_meta.section_count,
            source_file_name=base_meta.source_file_name,
            mime_type=base_meta.mime_type,
        )

        logger.info(
            "PIPELINE_VIEW CHUNKS (v2)",
            extra={
                "doc_id": str(doc.id),
                "version_id": str(version.id),
                "manifest_ref": version.chunks_manifest_v2_ref,
                "chunk_count": len(chunk_previews),
                "segments_count": len(segments_preview),
                "view_mode": view_mode.value,
            },
        )

        stage = PipelineStageViewDTO(
            code=PipelineStageCode.CHUNKS,
            title="CHUNKS: materialized chunks",
            description=(
                "Материализованный corpus чанков документа (segment-aware) "
                "для retrieval, checks и viewer."
            ),
            available=bool(chunk_previews),
            kind=PipelineStageKind.chunks,
            status=(
                PipelineStageStatus.ready if chunk_previews
                else PipelineStageStatus.pending
            ),
            artifact_ref=version.chunks_manifest_v2_ref or version.chunks_ref,
            meta=meta,
            preview=preview if chunk_previews else None,
        )

        return with_representation(stage, view_mode=view_mode, **_CHUNKS_REPR_KWARGS)

    # ── V2 ──────────────────────────────────────────────────────────

    def _build_v2_chunks(
        self,
        doc,
        version,
        raw_chunks_v2: list[dict[str, Any]],
        segments: list[DocumentSegment],
    ) -> tuple[list[ChunkPreviewDTO], list[ChunksSegmentPreviewDTO]]:
        """Группирует v2 чанки по сегментам."""
        chunks_by_segment_id: dict[str, list[dict[str, Any]]] = {}
        for raw_idx, ch in enumerate(raw_chunks_v2):
            meta = ch.get("metadata") or {}
            segment_id = meta.get("segment_id")
            if not segment_id:
                continue
            segment_id = str(segment_id)
            ch["_pipeline_index"] = raw_idx
            chunks_by_segment_id.setdefault(segment_id, []).append(ch)

        segment_by_id = {s.segment_id: s for s in segments}

        flat_chunks: list[ChunkPreviewDTO] = []
        segments_preview: list[ChunksSegmentPreviewDTO] = []

        for segment_id, raw_items in chunks_by_segment_id.items():
            seg = segment_by_id.get(segment_id)
            if not seg:
                logger.warning(
                    "PIPELINE_VIEW CHUNKS v2: manifest segment not found in DB",
                    extra={
                        "doc_id": str(doc.id),
                        "segment_id": segment_id,
                        "raw_items_count": len(raw_items),
                    },
                )
                continue

            pipeline_segment = PipelineSegmentDTO(
                segment_id=seg.segment_id,
                segment_type=seg.segment_type,
                segment_title=seg.segment_title,
                segment_order=seg.segment_order,
                is_primary=bool(seg.is_primary),
                page_from=seg.page_start,
                page_to=seg.page_end,
            )

            seg_chunks: list[ChunkPreviewDTO] = []

            for ch in raw_items:
                text = (ch.get("text") or "").strip()
                if not text:
                    continue

                meta = ch.get("metadata") or {}
                clause_uid = ch.get("clause_uid") or meta.get("clause_uid") or ""
                page_from = meta.get("page_from") or meta.get("start_page")
                page_to = meta.get("page_to") or meta.get("end_page")
                chunk_id = ch.get("id")
                raw_idx = ch.get("_pipeline_index")
                index = (
                    int(raw_idx) if isinstance(raw_idx, int)
                    else len(flat_chunks) + len(seg_chunks)
                )

                seg_chunks.append(
                    ChunkPreviewDTO(
                        index=index,
                        clause_uid=str(clause_uid) if clause_uid else "",
                        page_from=page_from if isinstance(page_from, int) else None,
                        page_to=page_to if isinstance(page_to, int) else None,
                        text=text[:4000],
                        segment_id=pipeline_segment.segment_id,
                        segment_type=pipeline_segment.segment_type,
                        segment_title=pipeline_segment.segment_title,
                        segment_order=pipeline_segment.segment_order,
                        is_primary_segment=pipeline_segment.is_primary,
                        chunk_id=str(chunk_id) if chunk_id else None,
                    )
                )

            if not seg_chunks:
                continue

            reconstructed = "\n\n".join(ch.text for ch in seg_chunks if ch.text.strip())
            segments_preview.append(
                ChunksSegmentPreviewDTO(
                    segment=pipeline_segment,
                    chunks=seg_chunks,
                    reconstructed_text=reconstructed,
                    raw_json=None,
                )
            )
            flat_chunks.extend(seg_chunks)

        return flat_chunks, segments_preview

    # ── Legacy / fallback ───────────────────────────────────────────

    async def _build_legacy_or_fallback(
        self,
        doc,
        version,
        base_meta: StageMetaDTO,
        view_mode: StageViewMode,
    ) -> PipelineStageViewDTO:
        """Legacy snapshot или fallback через DocumentContentService."""
        artifact_ref = version.chunks_ref
        chunks: list[ChunkPreviewDTO] = []
        raw_snapshot: dict[str, Any] | list[Any] | None = None

        if artifact_ref:
            try:
                snapshot = self._store.get_json(artifact_ref)
                raw_snapshot = snapshot
                chunks = _extract_chunks_from_snapshot(snapshot)
            except PermanentError:
                return with_representation(
                    PipelineStageViewDTO(
                        code=PipelineStageCode.CHUNKS,
                        title="CHUNKS: materialized chunks",
                        description="Snapshot чанков ожидается, но отсутствует в сторедже.",
                        available=False,
                        kind=PipelineStageKind.chunks,
                        status=PipelineStageStatus.missing,
                        artifact_ref=artifact_ref,
                        meta=base_meta,
                        preview=None,
                    ),
                    view_mode=view_mode,
                    **_CHUNKS_REPR_KWARGS,
                )
            except TransientError:
                return with_representation(
                    PipelineStageViewDTO(
                        code=PipelineStageCode.CHUNKS,
                        title="CHUNKS: materialized chunks",
                        description="Snapshot чанков временно недоступен.",
                        available=False,
                        kind=PipelineStageKind.chunks,
                        status=PipelineStageStatus.pending,
                        artifact_ref=artifact_ref,
                        meta=base_meta,
                        preview=None,
                    ),
                    view_mode=view_mode,
                    **_CHUNKS_REPR_KWARGS,
                )

        # fallback
        if not chunks:
            chunks = await _load_chunks_fallback(doc.id, self._content_service)

        if not chunks:
            meta = StageMetaDTO(
                page_count=base_meta.page_count,
                element_count=base_meta.element_count,
                chunk_count=0,
                section_count=base_meta.section_count,
                source_file_name=base_meta.source_file_name,
                mime_type=base_meta.mime_type,
            )
            return with_representation(
                PipelineStageViewDTO(
                    code=PipelineStageCode.CHUNKS,
                    title="CHUNKS: materialized chunks",
                    description="Чанки для документа пока недоступны.",
                    available=False,
                    kind=PipelineStageKind.chunks,
                    status=PipelineStageStatus.pending,
                    artifact_ref=artifact_ref,
                    meta=meta,
                    preview=None,
                ),
                view_mode=view_mode,
                **_CHUNKS_REPR_KWARGS,
            )

        reconstructed_text = "\n\n".join(ch.text for ch in chunks if ch.text.strip())

        preview = ChunksPreviewDTO(
            type="chunks",
            chunks=chunks,
            segments=[],
            reconstructed_text=reconstructed_text,
            raw_json=raw_snapshot,
        )

        meta = StageMetaDTO(
            page_count=base_meta.page_count,
            element_count=base_meta.element_count,
            chunk_count=len(chunks),
            section_count=base_meta.section_count,
            source_file_name=base_meta.source_file_name,
            mime_type=base_meta.mime_type,
        )

        logger.info(
            "PIPELINE_VIEW CHUNKS (legacy)",
            extra={
                "doc_id": str(doc.id),
                "chunks_ref": artifact_ref,
                "chunk_count": len(chunks),
                "view_mode": view_mode.value,
            },
        )

        stage = PipelineStageViewDTO(
            code=PipelineStageCode.CHUNKS,
            title="CHUNKS: materialized chunks",
            description=(
                "Материализованный snapshot чанков документа для retrieval, checks и viewer."
            ),
            available=True,
            kind=PipelineStageKind.chunks,
            status=PipelineStageStatus.ready,
            artifact_ref=artifact_ref,
            meta=meta,
            preview=preview,
        )

        return with_representation(stage, view_mode=view_mode, **_CHUNKS_REPR_KWARGS)


# ════════════════════════════════════════════════════════════════════
# Вспомогательные функции
# ════════════════════════════════════════════════════════════════════


def _extract_chunks_from_snapshot(
    snapshot: dict[str, Any] | list[Any],
) -> list[ChunkPreviewDTO]:
    """Извлекает ChunkPreviewDTO из legacy snapshot."""
    result: list[ChunkPreviewDTO] = []

    if isinstance(snapshot, dict):
        raw = snapshot.get("chunks") or snapshot
        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, dict):
            items: list[dict[str, Any]] = []
            for lvl_items in raw.values():
                if isinstance(lvl_items, list):
                    items.extend(lvl_items)
        else:
            return result
    elif isinstance(snapshot, list):
        items = snapshot
    else:
        return result

    if not isinstance(items, list):
        return result

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        text = item.get("text") or ""
        if not isinstance(text, str) or not text.strip():
            continue

        meta = item.get("metadata") or {}
        clause_uid = item.get("clause_uid") or meta.get("clause_uid") or ""
        page_from = (
            item.get("page_from") or meta.get("page_from")
            or item.get("page") or meta.get("page")
        )
        page_to = (
            item.get("page_to") or meta.get("page_to")
            or item.get("page") or meta.get("page")
        )

        result.append(
            ChunkPreviewDTO(
                index=idx,
                clause_uid=str(clause_uid) if clause_uid else "",
                page_from=page_from if isinstance(page_from, int) else None,
                page_to=page_to if isinstance(page_to, int) else None,
                text=text[:4000],
            )
        )

    return result


async def _load_chunks_fallback(
    doc_id: UUID,
    content_service: DocumentContentService,
) -> list[ChunkPreviewDTO]:
    """Загружает чанки через DocumentContentService как последний fallback."""
    result: list[ChunkPreviewDTO] = []

    try:
        if hasattr(content_service, "get_chunks"):
            payload = await content_service.get_chunks(doc_id=doc_id)
        elif hasattr(content_service, "get_sized_chunks"):
            payload = await content_service.get_sized_chunks(doc_id=doc_id)
        else:
            return result
    except Exception:
        return result

    if not isinstance(payload, list):
        return result

    for idx, item in enumerate(payload):
        if not isinstance(item, dict):
            continue
        text = item.get("text") or ""
        if not isinstance(text, str) or not text.strip():
            continue

        meta = item.get("metadata") or {}
        clause_uid = item.get("clause_uid") or meta.get("clause_uid") or ""
        page_from = (
            item.get("page_from") or meta.get("page_from")
            or item.get("page") or meta.get("page")
        )
        page_to = (
            item.get("page_to") or meta.get("page_to")
            or item.get("page") or meta.get("page")
        )

        result.append(
            ChunkPreviewDTO(
                index=idx,
                clause_uid=str(clause_uid) if clause_uid else "",
                page_from=page_from if isinstance(page_from, int) else None,
                page_to=page_to if isinstance(page_to, int) else None,
                text=text[:4000],
            )
        )

    return result

