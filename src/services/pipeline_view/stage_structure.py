# src/services/pipeline_view/stage_structure.py

"""
Stage builder: STRUCTURE — дерево секций/пунктов документа.

Самый сложный stage: поддерживает v2 (per-segment) и legacy (single tree),
обогащение текстом из CHUNKS, source mapping, наследование от детей.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.document_pipeline_view import (
    ChunkRefDTO,
    PipelineSegmentDTO,
    PipelineStageCode,
    PipelineStageKind,
    PipelineStageStatus,
    PipelineStageViewDTO,
    SectionSourceMappingDTO,
    StageMetaDTO,
    StageViewMode,
    StructurePreviewDTO,
    StructureSectionPreviewDTO,
    StructureSegmentPreviewDTO,
)
from core.exceptions import PermanentError, TransientError
from core.logging import get_logger
from db.models.document import DocumentSegment
from engine.content.chunk_snapshot_reader import (
    ChunkCorpusReaderV2,
    ChunkSnapshotReader,
)
from services.pipeline_view.normalizers import (
    chunk_sort_key,
    extract_clause_tree_text,
    normalize_int,
    normalize_title,
    normalize_uid,
)
from services.pipeline_view.representation import with_representation
from storage.artifact_store import ArtifactStore

logger = get_logger(__name__)

# ── Константы representation для STRUCTURE ──────────────────────────

_STRUCTURE_CANONICAL_DESC = (
    "Показывается чистый результат этапа STRUCTURE: "
    "дерево секций и пунктов без обогащения текстом из CHUNKS."
)
_STRUCTURE_FRIENDLY_DESC = (
    "Показывается удобное для чтения представление дерева STRUCTURE, "
    "обогащённое текстом из canonical snapshot CHUNKS."
)
_STRUCTURE_REPR_KWARGS = dict(
    stage_code=PipelineStageCode.STRUCTURE,
    friendly_supported=True,
    canonical_description=_STRUCTURE_CANONICAL_DESC,
    friendly_description=_STRUCTURE_FRIENDLY_DESC,
    derived_from_stages=[PipelineStageCode.CHUNKS],
    preview_source_label="Текстовое превью из CHUNKS",
)


class StructureStageBuilder:
    """Строит стадию STRUCTURE для pipeline view."""

    def __init__(self, session: AsyncSession, store: ArtifactStore):
        self._session = session
        self._store = store

    async def build(
        self,
        doc,
        version,
        base_meta: StageMetaDTO,
        segments: list[DocumentSegment],
        view_mode: StageViewMode = StageViewMode.canonical,
    ) -> PipelineStageViewDTO:
        """Основной метод построения стадии STRUCTURE."""
        has_v2_segments = bool(segments)
        legacy_artifact_ref = version.clause_tree_ref

        if not has_v2_segments and not legacy_artifact_ref:
            return with_representation(
                PipelineStageViewDTO(
                    code=PipelineStageCode.STRUCTURE,
                    title="STRUCTURE: дерево документа",
                    description="Структурированное дерево секций, пунктов и подпунктов документа.",
                    available=False,
                    kind=PipelineStageKind.structure,
                    status=PipelineStageStatus.pending,
                    artifact_ref=None,
                    meta=base_meta,
                    preview=None,
                ),
                view_mode=view_mode,
                **_STRUCTURE_REPR_KWARGS,
            )

        sections: list[StructureSectionPreviewDTO] = []
        segment_previews: list[StructureSegmentPreviewDTO] = []

        # v2 path: per-segment clause trees
        if has_v2_segments:
            self._load_v2_segments(
                doc, version, segments, sections, segment_previews,
            )

        # legacy path: один tree на весь document
        if not sections and legacy_artifact_ref:
            result = self._load_legacy_tree(
                doc, version, legacy_artifact_ref, sections, base_meta, view_mode,
            )
            if result is not None:
                # Вернул ранний выход (ошибка загрузки)
                return result

        # Обогащение
        source_mapped = await self._try_attach_source_mapping(doc.id, sections)

        text_enriched = False
        if view_mode == StageViewMode.friendly:
            text_enriched = await self._try_enrich_text(doc.id, sections)

        self._inherit_from_children(sections)

        # Финальный text_preview
        for s in sections:
            if view_mode == StageViewMode.canonical:
                s.text_preview = s.structure_text or ""
            else:
                s.text_preview = (s.enriched_text or s.structure_text or "").strip()

        preview = StructurePreviewDTO(
            type="structure",
            sections=sections,
            segments=segment_previews,
            raw_json=None,
        )

        meta = StageMetaDTO(
            page_count=base_meta.page_count,
            element_count=base_meta.element_count,
            chunk_count=base_meta.chunk_count,
            section_count=len(sections),
            source_file_name=base_meta.source_file_name,
            mime_type=base_meta.mime_type,
            text_enriched=text_enriched,
        )

        artifact_ref = version.file_graph_ref or legacy_artifact_ref

        logger.info(
            "PIPELINE_VIEW STRUCTURE",
            extra={
                "doc_id": str(doc.id),
                "version_id": str(version.id),
                "artifact_ref": artifact_ref,
                "sections_len": len(sections),
                "segments_len": len(segment_previews),
                "text_enriched": text_enriched,
                "source_mapped": source_mapped,
                "view_mode": view_mode.value,
                "has_v2_segments": has_v2_segments,
            },
        )

        stage = PipelineStageViewDTO(
            code=PipelineStageCode.STRUCTURE,
            title="STRUCTURE: дерево документа",
            description="Структурированное дерево секций, пунктов и подпунктов документа.",
            available=bool(sections),
            kind=PipelineStageKind.structure,
            status=PipelineStageStatus.ready if sections else PipelineStageStatus.pending,
            artifact_ref=artifact_ref,
            meta=meta,
            preview=preview if sections else None,
        )

        return with_representation(stage, view_mode=view_mode, **_STRUCTURE_REPR_KWARGS)

    # ── V2 segments ─────────────────────────────────────────────────

    def _load_v2_segments(
        self,
        doc,
        version,
        segments: list[DocumentSegment],
        sections: list[StructureSectionPreviewDTO],
        segment_previews: list[StructureSegmentPreviewDTO],
    ) -> None:
        for seg in segments:
            seg_ref = seg.segment_clause_tree_ref
            if not seg_ref:
                logger.warning(
                    "PIPELINE_VIEW STRUCTURE: segment has no segment_clause_tree_ref",
                    extra={
                        "doc_id": str(doc.id),
                        "version_id": str(version.id),
                        "segment_id": seg.segment_id,
                    },
                )
                continue

            try:
                payload = self._store.get_json(seg_ref)
            except (PermanentError, TransientError):
                logger.warning(
                    "PIPELINE_VIEW STRUCTURE: segment clause tree unavailable",
                    extra={
                        "doc_id": str(doc.id),
                        "segment_id": seg.segment_id,
                        "ref": seg_ref,
                    },
                )
                continue

            pipeline_segment = _make_segment_dto(seg)
            root_nodes = iter_structure_root_nodes(payload)

            before_count = len(sections)
            for idx, node in enumerate(root_nodes):
                flatten_clause_tree(
                    node, sections,
                    level=1,
                    path_indices=[seg.segment_order, idx],
                    segment=pipeline_segment,
                )
            seg_sections = sections[before_count:]

            segment_previews.append(
                StructureSegmentPreviewDTO(
                    segment=pipeline_segment,
                    sections=seg_sections,
                    raw_json=payload,
                )
            )

    # ── Legacy tree ─────────────────────────────────────────────────

    def _load_legacy_tree(
        self,
        doc,
        version,
        artifact_ref: str,
        sections: list[StructureSectionPreviewDTO],
        base_meta: StageMetaDTO,
        view_mode: StageViewMode,
    ) -> PipelineStageViewDTO | None:
        """Загружает legacy clause tree. Возвращает стадию-ошибку или None при успехе."""
        try:
            payload = self._store.get_json(artifact_ref)
        except PermanentError:
            return with_representation(
                PipelineStageViewDTO(
                    code=PipelineStageCode.STRUCTURE,
                    title="STRUCTURE: дерево документа",
                    description="Артефакт clause tree ожидается, но отсутствует в сторедже.",
                    available=False,
                    kind=PipelineStageKind.structure,
                    status=PipelineStageStatus.missing,
                    artifact_ref=artifact_ref,
                    meta=base_meta,
                    preview=None,
                ),
                view_mode=view_mode,
                **_STRUCTURE_REPR_KWARGS,
            )
        except TransientError:
            return with_representation(
                PipelineStageViewDTO(
                    code=PipelineStageCode.STRUCTURE,
                    title="STRUCTURE: дерево документа",
                    description="Структурированный артефакт временно недоступен.",
                    available=False,
                    kind=PipelineStageKind.structure,
                    status=PipelineStageStatus.pending,
                    artifact_ref=artifact_ref,
                    meta=base_meta,
                    preview=None,
                ),
                view_mode=view_mode,
                **_STRUCTURE_REPR_KWARGS,
            )

        root_nodes = iter_structure_root_nodes(payload)
        for idx, node in enumerate(root_nodes):
            flatten_clause_tree(node, sections, level=1, path_indices=[idx], segment=None)

        return None  # Успех — ранний выход не нужен

    # ── Source mapping ──────────────────────────────────────────────

    async def _try_attach_source_mapping(
        self,
        doc_id: UUID,
        sections: list[StructureSectionPreviewDTO],
    ) -> bool:
        try:
            return await attach_structure_source_mapping(
                doc_id=doc_id,
                sections=sections,
                session=self._session,
                store=self._store,
            )
        except Exception as e:
            logger.warning(
                "PIPELINE_VIEW STRUCTURE: source mapping attach failed",
                extra={"doc_id": str(doc_id), "error": str(e)},
            )
            return False

    # ── Text enrichment ─────────────────────────────────────────────

    async def _try_enrich_text(
        self,
        doc_id: UUID,
        sections: list[StructureSectionPreviewDTO],
    ) -> bool:
        try:
            return await enrich_structure_with_text(
                doc_id=doc_id,
                sections=sections,
                session=self._session,
                store=self._store,
            )
        except Exception as e:
            logger.warning(
                "PIPELINE_VIEW STRUCTURE: text enrichment failed",
                extra={"doc_id": str(doc_id), "error": str(e)},
            )
            return False

    # ── Inherit from children ───────────────────────────────────────

    @staticmethod
    def _inherit_from_children(
        sections: list[StructureSectionPreviewDTO],
    ) -> None:
        try:
            inherit_structure_from_children(sections)
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════════
# Автономные функции (используются также из stage_chunks)
# ════════════════════════════════════════════════════════════════════


def _make_segment_dto(seg: DocumentSegment) -> PipelineSegmentDTO:
    return PipelineSegmentDTO(
        segment_id=seg.segment_id,
        segment_type=seg.segment_type,
        segment_title=seg.segment_title,
        segment_order=seg.segment_order,
        is_primary=bool(seg.is_primary),
        page_from=seg.page_start,
        page_to=seg.page_end,
    )


def iter_structure_root_nodes(payload: Any) -> list[dict[str, Any]]:
    """
    Нормализованный доступ к корневым узлам clause tree.

    Поддерживает форматы:
    - {"root": [ {...}, {...} ]}
    - {"root": { "children": [ {...}, ... ] }}
    - [ {...}, {...} ]
    - fallback: одиночный dict как один узел.
    """
    nodes: list[dict[str, Any]] = []

    if isinstance(payload, dict):
        raw_root = payload.get("root")
        if isinstance(raw_root, list):
            nodes = [n for n in raw_root if isinstance(n, dict)]
        elif isinstance(raw_root, dict):
            children = raw_root.get("children")
            if isinstance(children, list):
                nodes = [n for n in children if isinstance(n, dict)]
        else:
            nodes = [payload]
    elif isinstance(payload, list):
        nodes = [n for n in payload if isinstance(n, dict)]

    return nodes


def flatten_clause_tree(
    node: dict[str, Any],
    acc: list[StructureSectionPreviewDTO],
    *,
    level: int,
    path_indices: list[int],
    segment: PipelineSegmentDTO | None = None,
) -> None:
    """Рекурсивно сплющивает узел clause tree в плоский список секций."""
    clause_uid = normalize_uid(node.get("clauseUid") or node.get("clause_uid"))
    title = normalize_title(node.get("title") or node.get("label") or node.get("name"))

    page_from = normalize_int(
        node.get("startPage") or node.get("start_page") or node.get("page_from")
    )
    page_to = normalize_int(
        node.get("endPage") or node.get("end_page") or node.get("page_to")
    )

    if page_from is not None and page_to is None:
        page_to = page_from
    if page_to is not None and page_from is None:
        page_from = page_to
    if page_from is not None and page_to is not None and page_to < page_from:
        page_from, page_to = page_to, page_from

    text = extract_clause_tree_text(node)

    node_level = normalize_int(node.get("level"))
    effective_level = node_level if node_level is not None else level

    path_str = ".".join(str(i) for i in path_indices) if path_indices else "0"
    base_id = clause_uid or "noid"
    node_id = f"{base_id}#{path_str}"

    acc.append(
        StructureSectionPreviewDTO(
            id=node_id,
            title=title,
            level=effective_level,
            page_from=page_from,
            page_to=page_to,
            structure_text=text,
            enriched_text="",
            text_preview=text,
            clause_uid=clause_uid,
            segment_id=segment.segment_id if segment else None,
            segment_type=segment.segment_type if segment else None,
            segment_title=segment.segment_title if segment else None,
            segment_order=segment.segment_order if segment else None,
            is_primary_segment=segment.is_primary if segment else None,
        )
    )

    children = node.get("children")
    if not isinstance(children, list):
        return

    for idx, child in enumerate(children):
        if isinstance(child, dict):
            flatten_clause_tree(
                child, acc,
                level=effective_level + 1,
                path_indices=path_indices + [idx],
                segment=segment,
            )


def inherit_structure_from_children(
    sections: list[StructureSectionPreviewDTO],
) -> None:
    """
    Обогащает групповые секции (типа 6.1) за счёт дочерних пунктов,
    если у родителя нет enriched_text / source_mapping.
    """
    if not sections:
        return

    section_by_uid: dict[str, StructureSectionPreviewDTO] = {}
    for s in sections:
        if s.clause_uid:
            section_by_uid[s.clause_uid] = s

    children_by_parent_uid: dict[str, list[StructureSectionPreviewDTO]] = defaultdict(list)
    for s in sections:
        uid = s.clause_uid
        if not uid:
            continue
        parts = uid.split(".")
        if len(parts) <= 1:
            continue
        parent_uid = ".".join(parts[:-1])
        children_by_parent_uid[parent_uid].append(s)

    for parent_uid, child_sections in children_by_parent_uid.items():
        parent = section_by_uid.get(parent_uid)
        if not parent:
            continue

        has_enriched = bool(parent.enriched_text and parent.enriched_text.strip())
        has_mapping = parent.source_mapping is not None

        if has_enriched and has_mapping:
            continue

        child_texts: list[str] = []
        all_indices: list[int] = []

        for child in child_sections:
            if child.enriched_text and child.enriched_text.strip():
                child_texts.append(child.enriched_text.strip())
            elif child.structure_text and child.structure_text.strip():
                child_texts.append(child.structure_text.strip())

            if child.source_mapping and child.source_mapping.chunk_indices:
                all_indices.extend(child.source_mapping.chunk_indices)

        if not child_texts and not all_indices:
            continue

        aggregated_text = "\n\n".join(child_texts).strip() if child_texts else None

        if not has_enriched and aggregated_text:
            parent.enriched_text = aggregated_text

        if not has_mapping and all_indices:
            unique_indices = sorted(set(all_indices))
            parent.source_mapping = SectionSourceMappingDTO(
                source_stage=PipelineStageCode.CHUNKS,
                page_from=parent.page_from,
                page_to=parent.page_to,
                chunk_indices=unique_indices,
                match_text=aggregated_text,
                match_strategy="chunk_refs",
            )


async def _load_clause_chunks(
    doc_id: UUID,
    session: AsyncSession,
    store: ArtifactStore,
) -> list[dict[str, Any]]:
    """Загружает clause-level чанки: сначала v2, потом legacy."""
    reader_v2 = ChunkCorpusReaderV2(session=session, artifact_store=store)
    chunks = await reader_v2.load(doc_id=doc_id, levels=["clause"])
    if chunks:
        return chunks

    logger.info(
        "No v2 clause chunks, falling back to legacy snapshot",
        extra={"doc_id": str(doc_id)},
    )
    legacy_reader = ChunkSnapshotReader(session=session, artifact_store=store)
    return await legacy_reader.load(doc_id=doc_id, levels=["clause"])


async def attach_structure_source_mapping(
    *,
    doc_id: UUID,
    sections: list[StructureSectionPreviewDTO],
    session: AsyncSession,
    store: ArtifactStore,
) -> bool:
    """Привязывает STRUCTURE-секции к canonical clause-chunks по clause_uid."""
    if not sections:
        return False

    clause_chunks = await _load_clause_chunks(doc_id, session, store)
    if not clause_chunks:
        logger.warning(
            "Structure source mapping skipped: no clause chunks",
            extra={"doc_id": str(doc_id)},
        )
        return False

    chunks_by_uid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw_idx, ch in enumerate(clause_chunks):
        meta = ch.get("metadata") or {}
        uid = normalize_uid(meta.get("clause_uid") or ch.get("clause_uid"))
        if not uid:
            continue
        ch["_pipeline_index"] = raw_idx
        chunks_by_uid[uid].append(ch)

    for items in chunks_by_uid.values():
        items.sort(key=chunk_sort_key)

    mapped_any = False

    for section in sections:
        section_uid = normalize_uid(section.clause_uid)
        if not section_uid:
            continue

        chunks = chunks_by_uid.get(section_uid)
        if not chunks:
            continue

        chunk_indices: list[int] = []
        chunk_refs: list[ChunkRefDTO] = []
        parts: list[str] = []
        seen_chunk_ids: set[str] = set()
        seen_ref_keys: set[tuple[str | None, int | None, str | None]] = set()
        page_values: list[int] = []

        for ch in chunks:
            chunk_id = str(ch.get("id") or "").strip()
            if chunk_id and chunk_id in seen_chunk_ids:
                continue

            text = (ch.get("text") or "").strip()
            if not text:
                continue

            parts.append(text)
            if chunk_id:
                seen_chunk_ids.add(chunk_id)

            raw_idx = ch.get("_pipeline_index")
            if isinstance(raw_idx, int):
                chunk_indices.append(raw_idx)

            meta = ch.get("metadata") or {}
            start_page = meta.get("start_page")
            end_page = meta.get("end_page")
            segment_id_raw = meta.get("segment_id")
            segment_id = str(segment_id_raw).strip() if segment_id_raw is not None else None
            if segment_id == "":
                segment_id = None

            if isinstance(start_page, int):
                page_values.append(start_page)
            if isinstance(end_page, int):
                page_values.append(end_page)

            if segment_id or chunk_id:
                ref_key = (segment_id, raw_idx, chunk_id or None)
                if ref_key not in seen_ref_keys:
                    chunk_refs.append(
                        ChunkRefDTO(
                            segment_id=segment_id,
                            chunk_index=raw_idx,
                            chunk_id=chunk_id or None,
                        )
                    )
                    seen_ref_keys.add(ref_key)

        unique_indices = sorted(set(chunk_indices))
        if not unique_indices:
            continue

        full_text = "\n\n".join(parts).strip()
        if not full_text:
            continue

        if not section.source_mapping or not section.source_mapping.chunk_indices:
            section.source_mapping = SectionSourceMappingDTO(
                source_stage=PipelineStageCode.CHUNKS,
                page_from=min(page_values) if page_values else section.page_from,
                page_to=max(page_values) if page_values else section.page_to,
                chunk_indices=unique_indices,
                chunk_refs=chunk_refs,
                segment_id=None,
                match_text=full_text[:400],
                match_strategy="chunk_refs",
            )
            mapped_any = True

    return mapped_any


async def enrich_structure_with_text(
    *,
    doc_id: UUID,
    sections: list[StructureSectionPreviewDTO],
    session: AsyncSession,
    store: ArtifactStore,
) -> bool:
    """Обогащает STRUCTURE-секции canonical текстом из clause-level чанков."""
    if not sections:
        return False

    clause_chunks = await _load_clause_chunks(doc_id, session, store)
    if not clause_chunks:
        return False

    chunks_by_uid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw_idx, ch in enumerate(clause_chunks):
        meta = ch.get("metadata") or {}
        uid = normalize_uid(meta.get("clause_uid") or ch.get("clause_uid"))
        if not uid:
            continue
        ch["_pipeline_index"] = raw_idx
        chunks_by_uid[uid].append(ch)

    for items in chunks_by_uid.values():
        items.sort(key=chunk_sort_key)

    enriched_any = False

    for section in sections:
        section_uid = normalize_uid(section.clause_uid)
        if not section_uid:
            continue

        chunks = chunks_by_uid.get(section_uid)
        if not chunks:
            continue

        parts: list[str] = []
        seen_ids: set[str] = set()

        for ch in chunks:
            chunk_id = str(ch.get("id") or "").strip()
            if chunk_id and chunk_id in seen_ids:
                continue
            text = (ch.get("text") or "").strip()
            if not text:
                continue
            parts.append(text)
            if chunk_id:
                seen_ids.add(chunk_id)

        full_text = "\n\n".join(parts).strip()
        if not full_text:
            continue

        section.enriched_text = full_text
        section.text_preview = full_text
        enriched_any = True

    return enriched_any

    