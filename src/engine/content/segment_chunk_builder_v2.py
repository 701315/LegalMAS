# src/engine/content/segment_chunk_builder_v2.py

"""
SegmentChunkBuilderV2 — построение чанков по логическим сегментам (CHUNKS v2).

Простыми словами для непрофессионального программиста:

- Вход:
  * document_version_id (конкретная версия документа),
  * session (подключение к БД),
  * настройки chunking (target_tokens, max_tokens, overlap_ratio).

- Что делает:
  1) Читает из БД:
     - DocumentVersion (layout_primary_sanitized_ref, file_graph_ref);
     - все DocumentSegment для этой версии.
  2) Для каждого сегмента:
     - грузит segment_clause_tree_ref и общий layout;
     - строит leaf‑чанки по дереву ТОЛЬКО этого сегмента;
     - нормализует текст, добавляет метаданные (segment_id, segment_type, и т.п.);
     - строит subclause‑чанки;
     - собирает snapshot чанков сегмента.
  3) Строит file-level манифест чанков:
     - перечисление сегментов и их будущих segment_chunks_ref;
     - aggregate‑статистика по чанкам;
     - aggregate‑статистика покрытия чанкинга.

Важно:
- Этот builder НЕ пишет в MinIO и НЕ обновляет БД.
- Сохранение segment_chunks_ref и chunks_manifest_v2_ref делает worker.
- Этот builder НЕ использует legacy file-level refs старого chunking/structure контракта.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import PermanentError
from core.logging import get_logger
from db.models.document import DocumentSegment
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_segment_repo import DocumentSegmentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from engine.content.chunk_canonicalization import (
    add_position_ratio,
    add_summary,
    build_sized_chunks_from_leaf,
    ensure_clause_metadata,
    extract_total_pages,
    normalize_clause_chunk_text,
    propagate_language_filter,
)
from engine.content.clause_tree_builder import ClauseTreeBuilder
from services.structure.legal_unit_builder import LegalUnitBuilder
from services.structure.legal_unit_models import LegalUnitsSnapshot
from storage.artifact_store import ArtifactStore

logger = get_logger(__name__)


@dataclass
class SegmentChunkSnapshotV2:
    """
    Snapshot чанков одного логического сегмента.

    Для непрофессионального программиста:
    - Один physical file может содержать несколько logical segments.
    - Для каждого сегмента строится отдельный snapshot.
    - Это позволяет не смешивать чанки договора и приложения в одном JSON.

    Этап 3:
    - Мы дополнительно сохраняем coverage‑метрики по leaf-узлам.
    - Это нужно, чтобы downstream видел не только "сколько чанков получилось",
      но и "сколько leaf-узлов потерялось по дороге".
    """

    document_id: uuid.UUID
    document_version_id: uuid.UUID
    segment_id: str
    segment_type: str
    segment_title: str | None
    segment_order: int
    is_primary_segment: bool
    segment_page_start: int
    segment_page_end: int
    layout_ref: str
    file_graph_ref: str
    segment_clause_tree_ref: str
    params: dict[str, Any]
    section_chunks: list[dict[str, Any]]
    clause_chunks: list[dict[str, Any]]
    subclause_chunks: list[dict[str, Any]]
    degraded: bool = False
    degradation_reason: str | None = None

    # Этап 3: coverage‑метрики сегмента.
    total_leaf_nodes: int | None = None
    leaf_nodes_without_chunks: int | None = None
    leaf_nodes_without_element_ids: int | None = None
    leaf_nodes_empty_after_filtering: int | None = None
    chunking_incomplete: bool = False

    # ── Этап 4: новые счётчики из ClauseTreeBuilder ───────────────────────────
    # heading_only_leaf_nodes: leaf узлы которые содержали только heading
    # без body — правильно пропускаются, не создают шумных чанков.
    heading_only_leaf_nodes: int = 0
    # best_effort_leaf_nodes: leaf узлы прикреплённые через best-effort recovery.
    best_effort_leaf_nodes: int = 0

    # ── Этап 5: legal units snapshot (опциональный dual-write) ───────────────
    # None если legal unit builder был отключён или упал с ошибкой.
    # Это НЕ ломает основной chunk pipeline — всегда опциональный.
    legal_units_snapshot: LegalUnitsSnapshot | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "scope": "segment",
            "document_id": str(self.document_id),
            "document_version_id": str(self.document_version_id),
            "segment": {
                "segment_id": self.segment_id,
                "segment_type": self.segment_type,
                "segment_title": self.segment_title,
                "segment_order": self.segment_order,
                "is_primary_segment": self.is_primary_segment,
                "page_start": self.segment_page_start,
                "page_end": self.segment_page_end,
            },
            "built_at": datetime.now(tz=UTC).isoformat(),
            "source": {
                "layout_ref": self.layout_ref,
                "file_graph_ref": self.file_graph_ref,
                "segment_clause_tree_ref": self.segment_clause_tree_ref,
            },
            "params": self.params,
            "degraded": self.degraded,
            "degradation_reason": self.degradation_reason,
            "coverage": {
                "total_leaf_nodes": self.total_leaf_nodes,
                "leaf_nodes_without_chunks": self.leaf_nodes_without_chunks,
                "leaf_nodes_without_element_ids": self.leaf_nodes_without_element_ids,
                "leaf_nodes_empty_after_filtering": self.leaf_nodes_empty_after_filtering,
                "chunking_incomplete": self.chunking_incomplete,
                # ── Этап 4 ───────────────────────────────────────────────────
                "heading_only_leaf_nodes": self.heading_only_leaf_nodes,
                "best_effort_leaf_nodes": self.best_effort_leaf_nodes,
            },
            "chunks": {
                "section": self.section_chunks,
                "clause": self.clause_chunks,
                "subclause": self.subclause_chunks,
            },
        }


@dataclass
class FileChunkManifestSegmentV2:
    """
    Один элемент file-level manifest: описание сегмента и его чанков.
    """

    segment_id: str
    segment_type: str
    segment_title: str | None
    segment_order: int
    is_primary: bool
    page_start: int
    page_end: int
    segment_clause_tree_ref: str
    segment_chunks_ref: str | None
    section_count: int
    clause_count: int
    subclause_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FileChunkManifestV2:
    """
    File-level манифест чанков для всей версии документа.

    Для непрофессионального программиста:
    - Это один JSON на весь файл.
    - Он не хранит весь текст чанков.
    - Он говорит:
      * какие сегменты есть,
      * какой из них primary,
      * где лежат чанки каждого сегмента,
      * сколько там чанков,
      * и есть ли проблемы покрытия чанкинга.
    """

    document_id: uuid.UUID
    document_version_id: uuid.UUID
    layout_ref: str
    file_graph_ref: str
    primary_segment_id: str
    segments: list[FileChunkManifestSegmentV2]
    degraded: bool = False
    degradation_reason: str | None = None

    # Этап 3: aggregate coverage‑метрики по всему файлу.
    total_leaf_nodes: int | None = None
    leaf_nodes_without_chunks: int | None = None
    leaf_nodes_without_element_ids: int | None = None
    leaf_nodes_empty_after_filtering: int | None = None
    chunking_incomplete: bool = False
    # ── Этап 4: агрегированные счётчики по всем сегментам ────────────────────
    heading_only_leaf_nodes: int = 0
    best_effort_leaf_nodes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "scope": "file",
            "document_id": str(self.document_id),
            "document_version_id": str(self.document_version_id),
            "built_at": datetime.now(tz=UTC).isoformat(),
            "source": {
                "layout_ref": self.layout_ref,
                "file_graph_ref": self.file_graph_ref,
            },
            "primary_segment_id": self.primary_segment_id,
            "degraded": self.degraded,
            "degradation_reason": self.degradation_reason,
            "segments": [s.to_dict() for s in self.segments],
            "totals": {
                "segment_count": len(self.segments),
                "section_count": sum(s.section_count for s in self.segments),
                "clause_count": sum(s.clause_count for s in self.segments),
                "subclause_count": sum(s.subclause_count for s in self.segments),
                "total_leaf_nodes": self.total_leaf_nodes,
                "leaf_nodes_without_chunks": self.leaf_nodes_without_chunks,
                "leaf_nodes_without_element_ids": self.leaf_nodes_without_element_ids,
                "leaf_nodes_empty_after_filtering": self.leaf_nodes_empty_after_filtering,
                "chunking_incomplete": self.chunking_incomplete,
                # ── Этап 4 ───────────────────────────────────────────────────
                "heading_only_leaf_nodes": self.heading_only_leaf_nodes,
                "best_effort_leaf_nodes": self.best_effort_leaf_nodes,
            },
        }


class SegmentChunkBuilderV2:
    """
    Основной сервис CHUNKS v2 (segment-aware).

    Важно:
    - Работает только через:
      * layout_primary_sanitized_ref,
      * file_graph_ref,
      * DocumentSegment.segment_clause_tree_ref.
    - Не использует legacy:
      * DocumentVersion.clause_tree_ref
      * legacy file-level chunk snapshot (schema v1)
    """

    def __init__(self, store: ArtifactStore | None = None) -> None:
        self.store = store or ArtifactStore()

    async def build_for_version(
        self,
        *,
        session: AsyncSession,
        document_version_id: uuid.UUID,
        target_tokens: int = 300,
        max_tokens: int = 800,
        overlap_ratio: float = 0.15,
    ) -> tuple[FileChunkManifestV2, list[SegmentChunkSnapshotV2]]:
        logger.info(
            "SegmentChunkBuilderV2: build_for_version start",
            extra={
                "document_version_id": str(document_version_id),
                "target_tokens": target_tokens,
                "max_tokens": max_tokens,
                "overlap_ratio": overlap_ratio,
            },
        )

        doc_repo = DocumentRepository(session)
        ver_repo = DocumentVersionRepository(session)
        seg_repo = DocumentSegmentRepository(session)

        version = await ver_repo.get_by_id(document_version_id)
        if not version:
            raise PermanentError(f"DocumentVersion {document_version_id} not found")

        doc = await doc_repo.get_by_id(version.document_id)
        if not doc:
            raise PermanentError(
                f"Document {version.document_id} not found for version {document_version_id}"
            )

        layout_ref = getattr(version, "layout_primary_sanitized_ref", None)
        if not layout_ref:
            raise PermanentError(
                f"No layout_primary_sanitized_ref for version {document_version_id}. "
                f"CHUNKS v2 requires sanitized primary layout."
            )

        file_graph_ref = getattr(version, "file_graph_ref", None)
        if not file_graph_ref:
            raise PermanentError(
                f"No file_graph_ref for version {document_version_id}. "
                f"STRUCTURE v2 must be completed before CHUNKS v2."
            )

        logger.info(
            "SegmentChunkBuilderV2: version source refs resolved",
            extra={
                "document_id": str(doc.id),
                "document_version_id": str(version.id),
                "layout_ref": layout_ref,
                "file_graph_ref": file_graph_ref,
            },
        )

        segments = await seg_repo.list_by_version(version.id)
        if not segments:
            raise PermanentError(
                f"No DocumentSegment rows found for version {document_version_id}. "
                f"CHUNKS v2 requires materialized segments."
            )

        primary_segments = [s for s in segments if bool(getattr(s, "is_primary", False))]
        if len(primary_segments) != 1:
            raise PermanentError(
                f"Invalid DocumentSegment state for version {document_version_id}: "
                f"expected exactly 1 primary segment, got {len(primary_segments)}"
            )

        logger.info(
            "SegmentChunkBuilderV2: segments loaded",
            extra={
                "document_id": str(doc.id),
                "document_version_id": str(version.id),
                "segments_count": len(segments),
                "primary_segment_id": primary_segments[0].segment_id,
                "segments": [
                    {
                        "segment_id": s.segment_id,
                        "segment_type": s.segment_type,
                        "segment_order": s.segment_order,
                        "is_primary": bool(s.is_primary),
                    }
                    for s in segments
                ],
            },
        )

        layout = self.store.get_json(layout_ref)
        if not isinstance(layout, dict):
            raise PermanentError(
                f"Layout artifact {layout_ref} is invalid for version {document_version_id}: expected dict"
            )

        layout_meta = layout.get("metadata") or {}
        total_pages = extract_total_pages(layout_meta)

        logger.debug(
            "SegmentChunkBuilderV2: layout loaded",
            extra={
                "document_id": str(doc.id),
                "document_version_id": str(version.id),
                "layout_has_metadata": isinstance(layout_meta, dict),
                "total_pages": total_pages,
            },
        )

        params = {
            "target_tokens": target_tokens,
            "max_tokens": max_tokens,
            "overlap_ratio": overlap_ratio,
        }

        segment_snapshots: list[SegmentChunkSnapshotV2] = []

        for segment in sorted(segments, key=lambda s: int(s.segment_order)):
            snapshot = self._build_single_segment_snapshot(
                document_id=doc.id,
                document_version_id=version.id,
                segment=segment,
                layout=layout,
                layout_meta=layout_meta if isinstance(layout_meta, dict) else {},
                layout_ref=layout_ref,
                file_graph_ref=file_graph_ref,
                params=params,
                target_tokens=target_tokens,
                max_tokens=max_tokens,
                overlap_ratio=overlap_ratio,
                total_pages=total_pages,
            )
            segment_snapshots.append(snapshot)

        primary_segment_id = primary_segments[0].segment_id

        manifest_segments: list[FileChunkManifestSegmentV2] = []
        by_segment_id = {s.segment_id: s for s in segment_snapshots}

        for segment in sorted(segments, key=lambda s: int(s.segment_order)):
            snap = by_segment_id.get(segment.segment_id)
            if snap is None:
                raise PermanentError(
                    f"Internal error: snapshot for segment {segment.segment_id} was not built"
                )

            manifest_segments.append(
                FileChunkManifestSegmentV2(
                    segment_id=segment.segment_id,
                    segment_type=segment.segment_type,
                    segment_title=segment.segment_title,
                    segment_order=segment.segment_order,
                    is_primary=bool(segment.is_primary),
                    page_start=segment.page_start,
                    page_end=segment.page_end,
                    segment_clause_tree_ref=segment.segment_clause_tree_ref or "",
                    segment_chunks_ref=None,
                    section_count=len(snap.section_chunks),
                    clause_count=len(snap.clause_chunks),
                    subclause_count=len(snap.subclause_chunks),
                )
            )

        # Этап 3 + Этап 4: агрегированные coverage‑метрики по всем сегментам.
        total_leaf_nodes = 0
        leaf_nodes_without_chunks = 0
        leaf_nodes_without_element_ids = 0
        leaf_nodes_empty_after_filtering = 0
        any_chunking_incomplete = False
        # ── Этап 4 ───────────────────────────────────────────────────────────
        total_heading_only_leaf_nodes = 0
        total_best_effort_leaf_nodes = 0

        for snap in segment_snapshots:
            if snap.total_leaf_nodes is not None:
                total_leaf_nodes += snap.total_leaf_nodes
            if snap.leaf_nodes_without_chunks is not None:
                leaf_nodes_without_chunks += snap.leaf_nodes_without_chunks
            if snap.leaf_nodes_without_element_ids is not None:
                leaf_nodes_without_element_ids += snap.leaf_nodes_without_element_ids
            if snap.leaf_nodes_empty_after_filtering is not None:
                leaf_nodes_empty_after_filtering += snap.leaf_nodes_empty_after_filtering
            if snap.chunking_incomplete:
                any_chunking_incomplete = True
            # ── Этап 4 ───────────────────────────────────────────────────────
            total_heading_only_leaf_nodes += snap.heading_only_leaf_nodes or 0
            total_best_effort_leaf_nodes += snap.best_effort_leaf_nodes or 0

        file_manifest = FileChunkManifestV2(
            document_id=doc.id,
            document_version_id=version.id,
            layout_ref=layout_ref,
            file_graph_ref=file_graph_ref,
            primary_segment_id=primary_segment_id,
            segments=manifest_segments,
            degraded=any_chunking_incomplete,
            degradation_reason="chunking_incomplete_in_segments"
            if any_chunking_incomplete
            else None,
            total_leaf_nodes=total_leaf_nodes,
            leaf_nodes_without_chunks=leaf_nodes_without_chunks,
            leaf_nodes_without_element_ids=leaf_nodes_without_element_ids,
            leaf_nodes_empty_after_filtering=leaf_nodes_empty_after_filtering,
            chunking_incomplete=any_chunking_incomplete,
            # ── Этап 4 ───────────────────────────────────────────────────────
            heading_only_leaf_nodes=total_heading_only_leaf_nodes,
            best_effort_leaf_nodes=total_best_effort_leaf_nodes,
        )

        logger.info(
            "SegmentChunkBuilderV2: build_for_version done",
            extra={
                "document_id": str(doc.id),
                "document_version_id": str(version.id),
                "segments_count": len(segment_snapshots),
                "primary_segment_id": primary_segment_id,
                "total_section_count": sum(len(s.section_chunks) for s in segment_snapshots),
                "total_clause_count": sum(len(s.clause_chunks) for s in segment_snapshots),
                "total_subclause_count": sum(len(s.subclause_chunks) for s in segment_snapshots),
                "total_leaf_nodes": total_leaf_nodes,
                "leaf_nodes_without_chunks": leaf_nodes_without_chunks,
                "leaf_nodes_without_element_ids": leaf_nodes_without_element_ids,
                "leaf_nodes_empty_after_filtering": leaf_nodes_empty_after_filtering,
                "chunking_incomplete": any_chunking_incomplete,
            },
        )

        return file_manifest, segment_snapshots

    def _build_single_segment_snapshot(
        self,
        *,
        document_id: uuid.UUID,
        document_version_id: uuid.UUID,
        segment: DocumentSegment,
        layout: dict[str, Any],
        layout_meta: dict[str, Any],
        layout_ref: str,
        file_graph_ref: str,
        params: dict[str, Any],
        target_tokens: int,
        max_tokens: int,
        overlap_ratio: float,
        total_pages: int | None,
    ) -> SegmentChunkSnapshotV2:
        segment_clause_tree_ref = getattr(segment, "segment_clause_tree_ref", None)
        if not segment_clause_tree_ref:
            raise PermanentError(
                f"No segment_clause_tree_ref for segment {segment.segment_id} "
                f"(document_version_id={document_version_id}). "
                f"This is a STRUCTURE stage bug, not a CHUNKS bug."
            )

        logger.info(
            "SegmentChunkBuilderV2: build single segment start",
            extra={
                "document_id": str(document_id),
                "document_version_id": str(document_version_id),
                "segment_id": segment.segment_id,
                "segment_type": segment.segment_type,
                "segment_order": segment.segment_order,
                "segment_clause_tree_ref": segment_clause_tree_ref,
            },
        )

        clause_tree = self.store.get_json(segment_clause_tree_ref)
        if not isinstance(clause_tree, dict):
            raise PermanentError(
                f"Segment clause tree artifact {segment_clause_tree_ref} is invalid: expected dict"
            )

        clause_root = clause_tree.get("root") or []
        if not isinstance(clause_root, list):
            raise PermanentError(
                f"Segment clause tree {segment_clause_tree_ref} has invalid root: expected list"
            )

        leaf_result = ClauseTreeBuilder.build_leaf_chunks(
            doc_id=document_id,
            tree=clause_tree,
            layout=layout,
        )
        leaf_chunks = leaf_result.chunks

        # ── Этап 4: читаем новые счётчики ────────────────────────────────────
        heading_only_leaf_nodes = getattr(leaf_result, "heading_only_leaf_nodes", 0) or 0
        best_effort_leaf_nodes = getattr(leaf_result, "best_effort_leaf_nodes", 0) or 0

        logger.info(
            "SegmentChunkBuilderV2: leaf chunks built",
            extra={
                "document_id": str(document_id),
                "document_version_id": str(document_version_id),
                "segment_id": segment.segment_id,
                "leaf_count": len(leaf_chunks),
                "clause_tree_root_count": len(clause_root),
                "total_leaf_nodes": leaf_result.total_leaf_nodes,
                "leaf_nodes_without_element_ids": leaf_result.leaf_nodes_without_element_ids,
                "leaf_nodes_empty_after_filtering": leaf_result.leaf_nodes_empty_after_filtering,
                # ── Этап 4 ───────────────────────────────────────────────────
                "heading_only_leaf_nodes": heading_only_leaf_nodes,
                "best_effort_leaf_nodes": best_effort_leaf_nodes,
            },
        )

        for ch in leaf_chunks:
            meta = ch.get("metadata") or {}
            before = ch.get("text") or ""
            after = normalize_clause_chunk_text(
                text=before,
                raw_uid=str(meta.get("raw_uid")) if meta.get("raw_uid") is not None else None,
                title=meta.get("title"),
            )
            ch["text"] = after

        propagate_language_filter(leaf_chunks, layout_meta)
        if total_pages:
            add_position_ratio(leaf_chunks, total_pages)

        clause_chunks = ensure_clause_metadata(document_id, leaf_chunks)

        invalid_clause_chunks = [
            ch for ch in clause_chunks if not ((ch.get("metadata") or {}).get("effective_uid"))
        ]
        if invalid_clause_chunks:
            logger.warning(
                "SegmentChunkBuilderV2: clause chunks without effective_uid after ensure",
                extra={
                    "document_id": str(document_id),
                    "document_version_id": str(document_version_id),
                    "segment_id": segment.segment_id,
                    "invalid_count": len(invalid_clause_chunks),
                },
            )

        invalid_clause_kinds = [
            ch for ch in clause_chunks if (ch.get("metadata") or {}).get("chunk_kind") != "clause"
        ]
        if invalid_clause_kinds:
            logger.warning(
                "SegmentChunkBuilderV2: non-clause chunks detected in clause collection",
                extra={
                    "document_id": str(document_id),
                    "document_version_id": str(document_version_id),
                    "segment_id": segment.segment_id,
                    "invalid_count": len(invalid_clause_kinds),
                },
            )

        clause_chunks = self._enrich_segment_metadata(
            chunks=clause_chunks,
            segment=segment,
            file_graph_ref=file_graph_ref,
            layout_ref=layout_ref,
            segment_clause_tree_ref=segment_clause_tree_ref,
            total_pages=total_pages,
        )
        clause_chunks = add_summary(clause_chunks)

        subclause_chunks = build_sized_chunks_from_leaf(
            doc_id=document_id,
            leaf_chunks=leaf_chunks,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            overlap_ratio=overlap_ratio,
            total_pages=total_pages,
        )

        invalid_subclause_kinds = [
            ch
            for ch in subclause_chunks
            if (ch.get("metadata") or {}).get("chunk_kind") != "subclause"
        ]
        if invalid_subclause_kinds:
            logger.warning(
                "SegmentChunkBuilderV2: non-subclause chunks detected in subclause collection",
                extra={
                    "document_id": str(document_id),
                    "document_version_id": str(document_version_id),
                    "segment_id": segment.segment_id,
                    "invalid_count": len(invalid_subclause_kinds),
                },
            )

        subclause_chunks = self._enrich_segment_metadata(
            chunks=subclause_chunks,
            segment=segment,
            file_graph_ref=file_graph_ref,
            layout_ref=layout_ref,
            segment_clause_tree_ref=segment_clause_tree_ref,
            total_pages=total_pages,
        )
        subclause_chunks = add_summary(subclause_chunks)

        section_chunks = self._build_section_chunks_safe(
            document_id=document_id,
            document_version_id=document_version_id,
            segment=segment,
            clause_tree=clause_tree,
            layout=layout,
            file_graph_ref=file_graph_ref,
            layout_ref=layout_ref,
            segment_clause_tree_ref=segment_clause_tree_ref,
            total_pages=total_pages,
        )

        total_leaf_nodes = leaf_result.total_leaf_nodes
        leaf_nodes_without_element_ids = leaf_result.leaf_nodes_without_element_ids
        leaf_nodes_empty_after_filtering = leaf_result.leaf_nodes_empty_after_filtering

        # Coverage считается по leaf -> clause chunk mapping.
        # leaf_nodes_without_chunks = сколько leaf узлов не дали ни одного clause chunk.
        #
        # Этап 4: heading_only_leaf_nodes правильно пропускаются (без body текста
        # они не создают чанк — это нормально, не деградация).
        # Поэтому вычитаем их из расчёта чтобы не получить ложный chunking_incomplete.
        #
        # Пример: 10 leaf узлов, 2 heading-only, 8 реальных.
        # clause_chunks = 8. Без вычитания: 10 - 8 = 2 > 0 -> chunking_incomplete=True.
        # С вычитанием: (10 - 2) - 8 = 0 -> chunking_incomplete=False. Правильно.
        effective_leaf_nodes = max(0, total_leaf_nodes - heading_only_leaf_nodes)
        leaf_nodes_without_chunks = max(0, effective_leaf_nodes - len(clause_chunks))

        # chunking_incomplete = True только если есть реальные потери,
        # не считая нормально пропущенных heading-only узлов.
        chunking_incomplete = any(
            (
                leaf_nodes_without_chunks > 0,
                leaf_nodes_without_element_ids > 0,
                # leaf_nodes_empty_after_filtering уже не включает heading-only
                # (они считаются отдельно в heading_only_leaf_nodes).
                # Поэтому этот счётчик = реальные потери текста.
                leaf_nodes_empty_after_filtering > 0,
            )
        )

        degradation_reasons: list[str] = []
        if leaf_nodes_without_chunks > 0:
            degradation_reasons.append("leaf_nodes_without_chunks>0")
        if leaf_nodes_without_element_ids > 0:
            degradation_reasons.append("leaf_nodes_without_element_ids>0")
        if leaf_nodes_empty_after_filtering > 0:
            degradation_reasons.append("leaf_nodes_empty_after_filtering>0")

        degradation_reason = ",".join(degradation_reasons) if degradation_reasons else None

        logger.info(
            "SegmentChunkBuilderV2: segment coverage stats",
            extra={
                "document_id": str(document_id),
                "document_version_id": str(document_version_id),
                "segment_id": segment.segment_id,
                "total_leaf_nodes": total_leaf_nodes,
                "effective_leaf_nodes": effective_leaf_nodes,
                "leaf_nodes_without_chunks": leaf_nodes_without_chunks,
                "leaf_nodes_without_element_ids": leaf_nodes_without_element_ids,
                "leaf_nodes_empty_after_filtering": leaf_nodes_empty_after_filtering,
                "chunking_incomplete": chunking_incomplete,
                "degradation_reason": degradation_reason,
                # ── Этап 4 ───────────────────────────────────────────────────
                "heading_only_leaf_nodes": heading_only_leaf_nodes,
                "best_effort_leaf_nodes": best_effort_leaf_nodes,
            },
        )

        logger.info(
            "SegmentChunkBuilderV2: single segment snapshot built",
            extra={
                "document_id": str(document_id),
                "document_version_id": str(document_version_id),
                "segment_id": segment.segment_id,
                "section_count": len(section_chunks),
                "clause_count": len(clause_chunks),
                "subclause_count": len(subclause_chunks),
                "chunking_incomplete": chunking_incomplete,
            },
        )

        # ── Этап 5: dual-write legal units (опциональный) ────────────────────
        # Строим LegalUnitsSnapshot параллельно с chunk snapshot.
        # Ошибка здесь НЕ должна ломать основной chunk pipeline.
        legal_units_snapshot: LegalUnitsSnapshot | None = None
        try:
            lu_builder = LegalUnitBuilder()
            legal_units_snapshot = lu_builder.build_from_clause_tree(
                clause_tree=clause_tree,
                segment_id=segment.segment_id,
                segment_type=segment.segment_type,
                segment_order=segment.segment_order,
                is_primary_segment=bool(segment.is_primary),
                document_id=str(document_id),
                document_version_id=str(document_version_id),
            )
            logger.info(
                "SegmentChunkBuilderV2: legal units snapshot built",
                extra={
                    "document_id": str(document_id),
                    "document_version_id": str(document_version_id),
                    "segment_id": segment.segment_id,
                    "total_units": len(legal_units_snapshot.units),
                    "units_with_known_type": legal_units_snapshot.units_with_known_type,
                },
            )
        except Exception as lu_exc:
            logger.warning(
                "SegmentChunkBuilderV2: legal unit builder failed, continuing without legal units",
                extra={
                    "document_id": str(document_id),
                    "document_version_id": str(document_version_id),
                    "segment_id": segment.segment_id,
                    "error": str(lu_exc),
                },
            )

        return SegmentChunkSnapshotV2(
            document_id=document_id,
            document_version_id=document_version_id,
            segment_id=segment.segment_id,
            segment_type=segment.segment_type,
            segment_title=segment.segment_title,
            segment_order=segment.segment_order,
            is_primary_segment=bool(segment.is_primary),
            segment_page_start=segment.page_start,
            segment_page_end=segment.page_end,
            layout_ref=layout_ref,
            file_graph_ref=file_graph_ref,
            segment_clause_tree_ref=segment_clause_tree_ref,
            params=params,
            section_chunks=section_chunks,
            clause_chunks=clause_chunks,
            subclause_chunks=subclause_chunks,
            degraded=chunking_incomplete,
            degradation_reason=degradation_reason,
            total_leaf_nodes=total_leaf_nodes,
            leaf_nodes_without_chunks=leaf_nodes_without_chunks,
            leaf_nodes_without_element_ids=leaf_nodes_without_element_ids,
            leaf_nodes_empty_after_filtering=leaf_nodes_empty_after_filtering,
            chunking_incomplete=chunking_incomplete,
            # ── Этап 4 ───────────────────────────────────────────────────────
            heading_only_leaf_nodes=heading_only_leaf_nodes,
            best_effort_leaf_nodes=best_effort_leaf_nodes,
            legal_units_snapshot=legal_units_snapshot,
        )

    def _build_section_chunks_safe(
        self,
        *,
        document_id: uuid.UUID,
        document_version_id: uuid.UUID,
        segment: DocumentSegment,
        clause_tree: dict[str, Any],
        layout: dict[str, Any],
        file_graph_ref: str,
        layout_ref: str,
        segment_clause_tree_ref: str,
        total_pages: int | None,
    ) -> list[dict[str, Any]]:
        """
        Построить section chunks для сегмента.

        Важно:
        - Если section chunks не удалось построить, это не ломает весь сегмент.
        - Мы продолжаем с пустым списком section chunks.
        """
        try:
            section_chunks = ClauseTreeBuilder.build_section_chunks(
                doc_id=document_id,
                tree=clause_tree,
                layout=layout,
            )
            if not isinstance(section_chunks, list):
                logger.warning(
                    "SegmentChunkBuilderV2: section builder returned non-list, using empty sections",
                    extra={
                        "document_id": str(document_id),
                        "document_version_id": str(document_version_id),
                        "segment_id": segment.segment_id,
                        "returned_type": type(section_chunks).__name__,
                    },
                )
                return []

            invalid_section_kinds = [
                ch
                for ch in section_chunks
                if (ch.get("metadata") or {}).get("chunk_kind") != "section"
            ]
            if invalid_section_kinds:
                logger.warning(
                    "SegmentChunkBuilderV2: non-section chunks detected in section collection",
                    extra={
                        "document_id": str(document_id),
                        "document_version_id": str(document_version_id),
                        "segment_id": segment.segment_id,
                        "invalid_count": len(invalid_section_kinds),
                    },
                )

            enriched = self._enrich_segment_metadata(
                chunks=section_chunks,
                segment=segment,
                file_graph_ref=file_graph_ref,
                layout_ref=layout_ref,
                segment_clause_tree_ref=segment_clause_tree_ref,
                total_pages=total_pages,
            )
            return add_summary(enriched)

        except Exception as e:
            logger.warning(
                "SegmentChunkBuilderV2: failed to build section chunks, continuing without sections",
                extra={
                    "document_id": str(document_id),
                    "document_version_id": str(document_version_id),
                    "segment_id": segment.segment_id,
                    "error": str(e),
                },
            )
            return []

    def _enrich_segment_metadata(
        self,
        *,
        chunks: list[dict[str, Any]],
        segment: DocumentSegment,
        file_graph_ref: str,
        layout_ref: str,
        segment_clause_tree_ref: str,
        total_pages: int | None,
    ) -> list[dict[str, Any]]:
        """
        Добавить в metadata каждого чанка segment-aware поля.

        Это ключевая часть CHUNKS v2:
        - downstream должен понимать, из какого logical segment пришёл чанк;
        - по какому tree он построен;
        - primary это сегмент или secondary;
        - каков его page-range в контексте сегмента и файла.
        """
        out: list[dict[str, Any]] = []

        for ch in chunks:
            if not isinstance(ch, dict):
                continue

            text = ch.get("text") or ""
            if not text.strip():
                continue

            meta = dict(ch.get("metadata") or {})
            start_page = meta.get("start_page")
            end_page = meta.get("end_page")

            position_ratio_within_file = meta.get("position_ratio")
            position_ratio_within_segment = self._calc_position_ratio_within_segment(
                start_page=start_page,
                end_page=end_page,
                segment_page_start=segment.page_start,
                segment_page_end=segment.page_end,
            )

            meta["segment_id"] = segment.segment_id
            meta["segment_type"] = segment.segment_type
            meta["segment_title"] = segment.segment_title
            meta["segment_order"] = segment.segment_order
            meta["is_primary_segment"] = bool(segment.is_primary)
            meta["segment_page_start"] = segment.page_start
            meta["segment_page_end"] = segment.page_end

            meta["layout_ref"] = layout_ref
            meta["file_graph_ref"] = file_graph_ref
            meta["segment_clause_tree_ref"] = segment_clause_tree_ref

            meta["position_ratio_within_file"] = position_ratio_within_file
            meta["position_ratio_within_segment"] = position_ratio_within_segment

            if total_pages is not None and "total_pages" not in meta:
                meta["total_pages"] = total_pages

            enriched = dict(ch)
            enriched["metadata"] = meta
            out.append(enriched)

        return out

    def _calc_position_ratio_within_segment(
        self,
        *,
        start_page: int | None,
        end_page: int | None,
        segment_page_start: int,
        segment_page_end: int,
    ) -> float | None:
        """
        Нормализованная позиция чанка внутри сегмента.

        Пример:
        - если сегмент занимает страницы 10..20,
        - а чанк находится на 15..16,
        - то позиция считается относительно диапазона 10..20, а не всего файла.
        """
        if segment_page_end < segment_page_start:
            return None

        span = segment_page_end - segment_page_start + 1
        if span <= 0:
            return None

        if start_page is None and end_page is None:
            return None

        s = start_page if isinstance(start_page, int) else end_page
        e = end_page if isinstance(end_page, int) else start_page
        if s is None or e is None:
            return None

        mid = (s + e) / 2.0
        relative = (mid - segment_page_start + 1.0) / float(span)

        if relative < 0.0:
            return 0.0
        if relative > 1.0:
            return 1.0
        return relative
