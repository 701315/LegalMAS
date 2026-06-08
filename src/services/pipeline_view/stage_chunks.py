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

Два режима:

canonical:
    Полный stage artifact (section + clause + subclause + legal_unit).
    Для pipeline audit — позволяет увидеть результат этапа CHUNKS
    как он материализован в artifact store.

friendly:
    Retrieval-visible corpus.
    Ровно те чанки (legal_unit + section), которые используются в
    retrieval/checks при анализе рисков.
    Строится через DocumentContentService.get_retrieval_chunks_for_checks()
    — тот же path, что у CheckRunner.
    Это default-режим для пользователя.

P8.8d:
- Retrieval truth переключён с blind sized split (`subclause`)
  на exact legal units (`legal_unit`).
- Friendly mode теперь должен показывать новый retrieval corpus,
  а canonical mode — весь materialized artifact, включая legal_unit layer.
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
from engine.content.document_content_service import DocumentContentService
from services.pipeline_view.representation import with_representation
from storage.artifact_store import ArtifactStore

logger = get_logger(__name__)

# ── Representation kwargs ───────────────────────────────────────────

_CHUNKS_REPR_KWARGS = dict(
    stage_code=PipelineStageCode.CHUNKS,
    friendly_supported=True,
    canonical_description=(
        "Canonical CHUNKS artifact: полный набор materialized чанков "
        "всех уровней (section, clause, subclause, legal_unit) из stage snapshot. "
        "Это результат этапа CHUNKS как части pipeline."
    ),
    friendly_description=(
        "RAG-visible corpus: именно те чанки (legal_unit + section), "
        "на основе которых система анализирует риски документа. "
        "Тот же corpus, что использует CheckRunner при проверках."
    ),
)

# ── Описания стадии по режиму ───────────────────────────────────────

_STAGE_DESCRIPTION_FRIENDLY = (
    "RAG-visible corpus: чанки, на основе которых система "
    "анализирует риски и принимает решения. "
    "После retrieval migration это legal_unit + section corpus. "
    "Именно это видит retrieval при проверках документа."
)

_STAGE_DESCRIPTION_CANONICAL = (
    "Canonical CHUNKS artifact: полный набор materialized чанков "
    "всех уровней (section, clause, subclause, legal_unit). "
    "Это pipeline artifact — для аудита этапа CHUNKS."
)

_CHUNK_KIND_LABELS: dict[str, str] = {
    "section": "Раздел",
    "clause": "Пункт",
    "subclause": "Подпункт",
    "legal_unit": "Положение",
}


def _normalize_label_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _resolve_chunk_role(chunk_kind: str | None) -> str:
    kind = _normalize_label_value(chunk_kind).lower()
    return "context" if kind == "section" else "evidence"


def _resolve_kind_label(chunk_kind: str | None) -> str:
    kind = _normalize_label_value(chunk_kind).lower()
    return _CHUNK_KIND_LABELS.get(kind, "Фрагмент")


def _format_pages_label(
    page_from: int | None,
    page_to: int | None,
) -> str:
    if isinstance(page_from, int) and isinstance(page_to, int):
        return f"стр. {page_from}" if page_from == page_to else f"стр. {page_from}–{page_to}"
    if isinstance(page_from, int):
        return f"стр. {page_from}"
    if isinstance(page_to, int):
        return f"стр. {page_to}"
    return ""


def _build_segment_label(
    *,
    segment_type: str | None,
    segment_title: str | None,
    is_primary_segment: bool | None,
) -> str:
    normalized_type = _normalize_label_value(segment_type)
    normalized_title = _normalize_label_value(segment_title)
    prefix = "основной сегмент" if bool(is_primary_segment) else "сегмент"

    if normalized_title and normalized_type:
        return f"{prefix}: {normalized_title} ({normalized_type})"
    if normalized_title:
        return f"{prefix}: {normalized_title}"
    if normalized_type:
        return f"{prefix}: {normalized_type}"
    return ""


def _build_chunk_display_title(
    *,
    chunk_kind: str | None,
    uid: str | None,
    segment_title: str | None,
) -> str:
    kind_label = _resolve_kind_label(chunk_kind)
    normalized_uid = _normalize_label_value(uid)
    normalized_segment_title = _normalize_label_value(segment_title)

    if normalized_uid:
        return f"{kind_label} {normalized_uid}"
    if normalized_segment_title:
        return f"{kind_label}: {normalized_segment_title}"
    return f"{kind_label} документа"


def _build_chunk_display_subtitle(
    *,
    role: str,
    page_from: int | None,
    page_to: int | None,
    segment_type: str | None,
    segment_title: str | None,
    is_primary_segment: bool | None,
) -> str:
    role_label = (
        "контекстный раздел"
        if role == "context"
        else "фрагмент для анализа"
    )

    parts: list[str] = [role_label]

    pages_label = _format_pages_label(page_from, page_to)
    if pages_label:
        parts.append(pages_label)

    segment_label = _build_segment_label(
        segment_type=segment_type,
        segment_title=segment_title,
        is_primary_segment=is_primary_segment,
    )
    if segment_label:
        parts.append(segment_label)

    return " · ".join(parts)


class ChunksStageBuilder:
    """
    Строит стадию CHUNKS для pipeline view в режиме V2_ONLY.

    canonical:
        Загружает все уровни (section + clause + subclause) из
        ChunkCorpusReaderV2. Для pipeline audit.

    friendly:
        Загружает retrieval-visible corpus через
        DocumentContentService.get_retrieval_chunks_for_checks().
        Тот же path, что у CheckRunner.
        Default для пользователя.
    """

    def __init__(self, session: AsyncSession, store: ArtifactStore):
        self._session = session
        self._store = store
        self._segment_repo = DocumentSegmentRepository(session)

    async def build(
        self,
        doc,
        version,
        base_meta: StageMetaDTO,
        view_mode: StageViewMode = StageViewMode.friendly,
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
                        "V2 manifest чанков ещё не записан. "
                        "Стадия CHUNKS пока не готова."
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
                        "V2 manifest найден, но materialized segments "
                        "отсутствуют. Стадия CHUNKS пока не готова."
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

        # ── Загрузка chunks по режиму ───────────────────────────────
        raw_chunks_v2 = await self._load_chunks_for_mode(
            doc=doc,
            view_mode=view_mode,
        )

        if raw_chunks_v2 is None:
            # PermanentError при canonical-mode (artifact missing in storage)
            return with_representation(
                PipelineStageViewDTO(
                    code=PipelineStageCode.CHUNKS,
                    title="CHUNKS: materialized chunks",
                    description=(
                        "V2 manifest чанков указан, но соответствующий "
                        "артефакт отсутствует в сторедже."
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
                        "V2 manifest чанков существует, но materialized "
                        "chunk corpus пуст или не может быть восстановлен."
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

        stage_description = (
            _STAGE_DESCRIPTION_FRIENDLY
            if view_mode == StageViewMode.friendly
            else _STAGE_DESCRIPTION_CANONICAL
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
            description=stage_description,
            available=True,
            kind=PipelineStageKind.chunks,
            status=PipelineStageStatus.ready,
            artifact_ref=manifest_ref,
            meta=meta,
            preview=preview,
        )

        return with_representation(stage, view_mode=view_mode, **_CHUNKS_REPR_KWARGS)

    # ── Загрузка по режиму ──────────────────────────────────────────

    async def _load_chunks_for_mode(
        self,
        doc,
        view_mode: StageViewMode,
    ) -> list[dict[str, Any]] | None:
        """
        Загрузить chunks в зависимости от режима.

        friendly:
            DocumentContentService.get_retrieval_chunks_for_checks()
            Тот же path, что у CheckRunner.
            После P8.8d default retrieval levels = ["legal_unit", "section"].

        canonical:
            ChunkCorpusReaderV2.load() с levels=["section", "clause", "subclause", "legal_unit"].
            Полный stage artifact.

        Возвращает:
            list[dict] — нормально загруженные чанки
            []         — corpus пуст (valid, но нечего показывать)
            None       — PermanentError (artifact missing in storage)
        """
        if view_mode == StageViewMode.friendly:
            return await self._load_retrieval_chunks(doc)
        else:
            return await self._load_canonical_chunks(doc)

    async def _load_retrieval_chunks(
        self,
        doc,
    ) -> list[dict[str, Any]]:
        """
        Загрузить retrieval-visible corpus через DocumentContentService.

        Это ровно тот corpus, который используется CheckRunner при анализе рисков.
        После P8.8d retrieval truth = ["legal_unit", "section"].
        filter_unsafe_chunks=False — показываем всё, включая unsafe chunks,
        чтобы пользователь видел полную картину (unsafe будет помечен флагом).
        """
        content_svc = DocumentContentService(
            session=self._session,
            artifact_store=self._store,
        )

        try:
            chunks = await content_svc.get_retrieval_chunks_for_checks(
                doc_id=doc.id,
                # default: ["legal_unit", "section"] — retrieval truth (P8.8d)
                filter_unsafe_chunks=False,
            )
        except Exception as e:
            logger.warning(
                "PIPELINE_VIEW CHUNKS friendly: get_retrieval_chunks_for_checks failed",
                extra={
                    "doc_id": str(doc.id),
                    "error": str(e),
                },
            )
            return []

        return chunks or []

    async def _load_canonical_chunks(
        self,
        doc,
    ) -> list[dict[str, Any]] | None:
        """
        Загрузить полный canonical corpus через ChunkCorpusReaderV2.

        Все materialized уровни:
        - section
        - clause
        - subclause
        - legal_unit

        Возвращает None при PermanentError (artifact missing).
        """
        reader_v2 = ChunkCorpusReaderV2(
            session=self._session,
            artifact_store=self._store,
        )

        try:
            chunks = await reader_v2.load(
                doc_id=doc.id,
                levels=["section", "clause", "subclause", "legal_unit"],
            )
        except PermanentError:
            logger.warning(
                "PIPELINE_VIEW CHUNKS canonical missing: artifact not found in storage",
                extra={"doc_id": str(doc.id)},
            )
            return None
        except TransientError:
            logger.warning(
                "PIPELINE_VIEW CHUNKS canonical pending: storage temporarily unavailable",
                extra={"doc_id": str(doc.id)},
            )
            return []
        except Exception as e:
            logger.warning(
                "PIPELINE_VIEW CHUNKS canonical: unexpected error loading chunks",
                extra={
                    "doc_id": str(doc.id),
                    "error": str(e),
                },
            )
            return []

        return chunks or []

    # ── V2 chunk preview builder ────────────────────────────────────

    def _build_v2_chunks(
        self,
        doc,
        version,
        raw_chunks_v2: list[dict[str, Any]],
        segments: list[DocumentSegment],
    ) -> tuple[list[ChunkPreviewDTO], list[ChunksSegmentPreviewDTO]]:
        """
        Группирует v2 чанки по сегментам и строит ChunkPreviewDTO.

        Ключевое изменение vs. старой версии:
        - chunk_kind, effective_uid, retrieval_safe берутся из metadata
          и пробрасываются в ChunkPreviewDTO.
        - Больше не теряем тип чанка на этом слое.
        """
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

                page_from_raw = (
                    meta.get("page_from")
                    or meta.get("start_page")
                )
                page_to_raw = (
                    meta.get("page_to")
                    or meta.get("end_page")
                )

                page_from = (
                    page_from_raw if isinstance(page_from_raw, int) else None
                )
                page_to = (
                    page_to_raw if isinstance(page_to_raw, int) else None
                )

                clause_uid = (
                    ch.get("clause_uid")
                    or meta.get("clause_uid")
                    or meta.get("effective_uid")
                    or meta.get("raw_uid")
                    or ""
                )

                chunk_kind = _normalize_label_value(
                    meta.get("chunk_kind")
                ).lower() or None
                effective_uid = _normalize_label_value(
                    meta.get("effective_uid")
                ) or None
                retrieval_safe = meta.get("retrieval_safe")

                chunk_id = ch.get("id")
                raw_idx = ch.get("_pipeline_index")
                index = (
                    int(raw_idx)
                    if isinstance(raw_idx, int)
                    else len(flat_chunks) + len(seg_chunks)
                )

                resolved_uid = (
                    effective_uid
                    or (_normalize_label_value(clause_uid) or None)
                )
                role = _resolve_chunk_role(chunk_kind)
                display_title = _build_chunk_display_title(
                    chunk_kind=chunk_kind,
                    uid=resolved_uid,
                    segment_title=pipeline_segment.segment_title,
                )
                display_subtitle = _build_chunk_display_subtitle(
                    role=role,
                    page_from=page_from,
                    page_to=page_to,
                    segment_type=pipeline_segment.segment_type,
                    segment_title=pipeline_segment.segment_title,
                    is_primary_segment=pipeline_segment.is_primary,
                )

                seg_chunks.append(
                    ChunkPreviewDTO(
                        index=index,
                        clause_uid=str(clause_uid) if clause_uid else "",
                        page_from=page_from,
                        page_to=page_to,
                        text=text[:4000],
                        segment_id=pipeline_segment.segment_id,
                        segment_type=pipeline_segment.segment_type,
                        segment_title=pipeline_segment.segment_title,
                        segment_order=pipeline_segment.segment_order,
                        is_primary_segment=pipeline_segment.is_primary,
                        chunk_id=str(chunk_id) if chunk_id else None,
                        chunk_kind=chunk_kind,
                        effective_uid=effective_uid,
                        retrieval_safe=(
                            bool(retrieval_safe)
                            if retrieval_safe is not None
                            else None
                        ),
                        display_title=display_title,
                        display_subtitle=display_subtitle,
                        role=role,
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

            reconstructed = "\n\n".join(
                ch.text for ch in seg_chunks if ch.text.strip()
            )
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


        