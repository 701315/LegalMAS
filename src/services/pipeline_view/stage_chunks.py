# src/services/pipeline_view/stage_chunks.py

"""
Stage builder: CHUNKS — материализованные чанки документа.

V2_ONLY contract:
1) canonical source — version.chunks_manifest_v2_ref
2) segment-level completeness required:
   - segments exist
   - every segment has segment_chunks_ref
3) no legacy snapshot path
4) no fallback through DocumentContentService
"""

from __future__ import annotations

from typing import Any

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
    """Строит стадию CHUNKS для pipeline view в режиме V2_ONLY."""

    def __init__(self, session: AsyncSession, store: ArtifactStore):
        self._session = session
        self._store = store
        self._segment_repo = DocumentSegmentRepository(session)

    async def build(
        self,
        doc,
        version,
        base_meta: StageMetaDTO,
        view_mode: StageViewMode = StageViewMode.canonical,
    ) -> PipelineStageViewDTO:
        """Основной метод построения стадии CHUNKS."""

        manifest_ref = getattr(version, "chunks_manifest_v2_ref", None)
        if not manifest_ref:
            logger.info(
                "PIPELINE_VIEW CHUNKS pending: no chunks_manifest_v2_ref",
                extra={
                    "doc_id": str(doc.id),
                    "version_id": str(version.id),
                    "view_mode": view_mode.value,
                },
            )
            return with_representation(
                PipelineStageViewDTO(
                    code=PipelineStageCode.CHUNKS,
                    title="CHUNKS: materialized chunks",
                    description=(
                        "V2 manifest чанков ещё не записан. " "Стадия CHUNKS пока не готова."
                    ),
                    available=False,
                    kind=PipelineStageKind.chunks,
                    status=PipelineStageStatus.pending,
                    artifact_ref=None,
                    meta=StageMetaDTO(
                        page_count=base_meta.page_count,
                        element_count=base_meta.element_count,
                        chunk_count=0,
                        section_count=base_meta.section_count,
                        source_file_name=base_meta.source_file_name,
                        mime_type=base_meta.mime_type,
                    ),
                    preview=None,
                ),
                view_mode=view_mode,
                **_CHUNKS_REPR_KWARGS,
            )

        segments = await self._segment_repo.list_by_version(version.id)
        if not segments:
            logger.warning(
                "PIPELINE_VIEW CHUNKS pending: no persisted segments for v2 manifest",
                extra={
                    "doc_id": str(doc.id),
                    "version_id": str(version.id),
                    "manifest_ref": manifest_ref,
                    "view_mode": view_mode.value,
                },
            )
            return with_representation(
                PipelineStageViewDTO(
                    code=PipelineStageCode.CHUNKS,
                    title="CHUNKS: materialized chunks",
                    description=(
                        "V2 manifest найден, но сегменты документа ещё не "
                        "материализованы. Стадия CHUNKS пока не согласована."
                    ),
                    available=False,
                    kind=PipelineStageKind.chunks,
                    status=PipelineStageStatus.pending,
                    artifact_ref=manifest_ref,
                    meta=StageMetaDTO(
                        page_count=base_meta.page_count,
                        element_count=base_meta.element_count,
                        chunk_count=0,
                        section_count=base_meta.section_count,
                        source_file_name=base_meta.source_file_name,
                        mime_type=base_meta.mime_type,
                    ),
                    preview=None,
                ),
                view_mode=view_mode,
                **_CHUNKS_REPR_KWARGS,
            )

        summary = await self._segment_repo.get_chunk_refs_summary(version.id)
        total_segments = summary["total_segments"]
        segments_with_chunks = summary["segments_with_chunks"]

        if total_segments <= 0:
            logger.warning(
                "PIPELINE_VIEW CHUNKS pending: total_segments=0",
                extra={
                    "doc_id": str(doc.id),
                    "version_id": str(version.id),
                    "manifest_ref": manifest_ref,
                    "view_mode": view_mode.value,
                },
            )
            return with_representation(
                PipelineStageViewDTO(
                    code=PipelineStageCode.CHUNKS,
                    title="CHUNKS: materialized chunks",
                    description=(
                        "V2 manifest найден, но materialized segments отсутствуют. "
                        "Стадия CHUNKS пока не готова."
                    ),
                    available=False,
                    kind=PipelineStageKind.chunks,
                    status=PipelineStageStatus.pending,
                    artifact_ref=manifest_ref,
                    meta=StageMetaDTO(
                        page_count=base_meta.page_count,
                        element_count=base_meta.element_count,
                        chunk_count=0,
                        section_count=base_meta.section_count,
                        source_file_name=base_meta.source_file_name,
                        mime_type=base_meta.mime_type,
                    ),
                    preview=None,
                ),
                view_mode=view_mode,
                **_CHUNKS_REPR_KWARGS,
            )

        if segments_with_chunks != total_segments:
            logger.warning(
                "PIPELINE_VIEW CHUNKS pending: incomplete segment chunk refs",
                extra={
                    "doc_id": str(doc.id),
                    "version_id": str(version.id),
                    "manifest_ref": manifest_ref,
                    "total_segments": total_segments,
                    "segments_with_chunks": segments_with_chunks,
                    "view_mode": view_mode.value,
                },
            )
            return with_representation(
                PipelineStageViewDTO(
                    code=PipelineStageCode.CHUNKS,
                    title="CHUNKS: materialized chunks",
                    description=(
                        "V2 manifest найден, но не у всех сегментов заполнен "
                        "segment_chunks_ref. Стадия CHUNKS пока не готова."
                    ),
                    available=False,
                    kind=PipelineStageKind.chunks,
                    status=PipelineStageStatus.pending,
                    artifact_ref=manifest_ref,
                    meta=StageMetaDTO(
                        page_count=base_meta.page_count,
                        element_count=base_meta.element_count,
                        chunk_count=0,
                        section_count=base_meta.section_count,
                        source_file_name=base_meta.source_file_name,
                        mime_type=base_meta.mime_type,
                    ),
                    preview=None,
                ),
                view_mode=view_mode,
                **_CHUNKS_REPR_KWARGS,
            )

        reader_v2 = ChunkCorpusReaderV2(
            session=self._session,
            artifact_store=self._store,
        )

        try:
            raw_chunks_v2 = await reader_v2.load(doc_id=doc.id, levels=["clause"])
        except PermanentError:
            logger.warning(
                "PIPELINE_VIEW CHUNKS missing: manifest declared but payload not found",
                extra={
                    "doc_id": str(doc.id),
                    "version_id": str(version.id),
                    "manifest_ref": manifest_ref,
                    "view_mode": view_mode.value,
                },
            )
            return with_representation(
                PipelineStageViewDTO(
                    code=PipelineStageCode.CHUNKS,
                    title="CHUNKS: materialized chunks",
                    description=(
                        "V2 manifest чанков указан, но соответствующий артефакт "
                        "отсутствует в сторедже."
                    ),
                    available=False,
                    kind=PipelineStageKind.chunks,
                    status=PipelineStageStatus.missing,
                    artifact_ref=manifest_ref,
                    meta=StageMetaDTO(
                        page_count=base_meta.page_count,
                        element_count=base_meta.element_count,
                        chunk_count=0,
                        section_count=base_meta.section_count,
                        source_file_name=base_meta.source_file_name,
                        mime_type=base_meta.mime_type,
                    ),
                    preview=None,
                ),
                view_mode=view_mode,
                **_CHUNKS_REPR_KWARGS,
            )
        except TransientError:
            logger.warning(
                "PIPELINE_VIEW CHUNKS pending: storage temporarily unavailable",
                extra={
                    "doc_id": str(doc.id),
                    "version_id": str(version.id),
                    "manifest_ref": manifest_ref,
                    "view_mode": view_mode.value,
                },
            )
            return with_representation(
                PipelineStageViewDTO(
                    code=PipelineStageCode.CHUNKS,
                    title="CHUNKS: materialized chunks",
                    description=(
                        "V2 manifest чанков временно недоступен. "
                        "Попробуйте обновить представление позже."
                    ),
                    available=False,
                    kind=PipelineStageKind.chunks,
                    status=PipelineStageStatus.pending,
                    artifact_ref=manifest_ref,
                    meta=StageMetaDTO(
                        page_count=base_meta.page_count,
                        element_count=base_meta.element_count,
                        chunk_count=0,
                        section_count=base_meta.section_count,
                        source_file_name=base_meta.source_file_name,
                        mime_type=base_meta.mime_type,
                    ),
                    preview=None,
                ),
                view_mode=view_mode,
                **_CHUNKS_REPR_KWARGS,
            )

        if not raw_chunks_v2:
            logger.warning(
                "PIPELINE_VIEW CHUNKS missing: manifest exists but chunk corpus is empty",
                extra={
                    "doc_id": str(doc.id),
                    "version_id": str(version.id),
                    "manifest_ref": manifest_ref,
                    "total_segments": total_segments,
                    "segments_with_chunks": segments_with_chunks,
                    "view_mode": view_mode.value,
                },
            )
            return with_representation(
                PipelineStageViewDTO(
                    code=PipelineStageCode.CHUNKS,
                    title="CHUNKS: materialized chunks",
                    description=(
                        "V2 manifest чанков существует, но materialized chunk corpus "
                        "пуст или не может быть восстановлен."
                    ),
                    available=False,
                    kind=PipelineStageKind.chunks,
                    status=PipelineStageStatus.missing,
                    artifact_ref=manifest_ref,
                    meta=StageMetaDTO(
                        page_count=base_meta.page_count,
                        element_count=base_meta.element_count,
                        chunk_count=0,
                        section_count=base_meta.section_count,
                        source_file_name=base_meta.source_file_name,
                        mime_type=base_meta.mime_type,
                    ),
                    preview=None,
                ),
                view_mode=view_mode,
                **_CHUNKS_REPR_KWARGS,
            )

        chunk_previews, segments_preview = self._build_v2_chunks(
            doc=doc,
            version=version,
            raw_chunks_v2=raw_chunks_v2,
            segments=segments,
        )

        if not chunk_previews:
            logger.warning(
                "PIPELINE_VIEW CHUNKS missing: v2 corpus loaded but no valid chunk previews built",
                extra={
                    "doc_id": str(doc.id),
                    "version_id": str(version.id),
                    "manifest_ref": manifest_ref,
                    "raw_chunks_count": len(raw_chunks_v2),
                    "segments_count": len(segments),
                    "view_mode": view_mode.value,
                },
            )
            return with_representation(
                PipelineStageViewDTO(
                    code=PipelineStageCode.CHUNKS,
                    title="CHUNKS: materialized chunks",
                    description=(
                        "V2 chunk corpus загружен, но не удалось построить "
                        "валидное segment-aware preview."
                    ),
                    available=False,
                    kind=PipelineStageKind.chunks,
                    status=PipelineStageStatus.missing,
                    artifact_ref=manifest_ref,
                    meta=StageMetaDTO(
                        page_count=base_meta.page_count,
                        element_count=base_meta.element_count,
                        chunk_count=0,
                        section_count=base_meta.section_count,
                        source_file_name=base_meta.source_file_name,
                        mime_type=base_meta.mime_type,
                    ),
                    preview=None,
                ),
                view_mode=view_mode,
                **_CHUNKS_REPR_KWARGS,
            )

        reconstructed_text = "\n\n".join(ch.text for ch in chunk_previews if ch.text.strip())

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
            "PIPELINE_VIEW CHUNKS ready (v2_only)",
            extra={
                "doc_id": str(doc.id),
                "version_id": str(version.id),
                "manifest_ref": manifest_ref,
                "chunk_count": len(chunk_previews),
                "segments_count": len(segments_preview),
                "total_segments": total_segments,
                "segments_with_chunks": segments_with_chunks,
                "view_mode": view_mode.value,
            },
        )

        stage = PipelineStageViewDTO(
            code=PipelineStageCode.CHUNKS,
            title="CHUNKS: materialized chunks",
            description=(
                "Материализованный segment-aware corpus чанков документа "
                "для retrieval, checks и viewer."
            ),
            available=True,
            kind=PipelineStageKind.chunks,
            status=PipelineStageStatus.ready,
            artifact_ref=manifest_ref,
            meta=meta,
            preview=preview,
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
                    "PIPELINE_VIEW CHUNKS v2_only: manifest segment not found in DB",
                    extra={
                        "doc_id": str(doc.id),
                        "version_id": str(version.id),
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
                    int(raw_idx) if isinstance(raw_idx, int) else len(flat_chunks) + len(seg_chunks)
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
                logger.warning(
                    "PIPELINE_VIEW CHUNKS v2_only: segment has no valid chunk previews",
                    extra={
                        "doc_id": str(doc.id),
                        "version_id": str(version.id),
                        "segment_id": segment_id,
                    },
                )
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
