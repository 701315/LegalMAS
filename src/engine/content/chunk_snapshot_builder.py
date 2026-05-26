# src/engine/content/chunk_snapshot_builder.py

"""
ChunkSnapshotBuilder — единый сервис для построения snapshot'а чанков (LEGACY, v1).

Простыми словами для непрофессионального программиста:

Ограничения (важно для новой архитектуры):
- Этот builder работает только с одним clause_tree_ref на весь документ.
- Он не знает ничего про FileGraph и DocumentSegment.
- CHUNKS v2 (segment-aware) будут реализованы в отдельном модуле и НЕ должны
  использовать этот класс, только переиспользовать его вспомогательные функции.

- В MinIO у нас уже есть:
  * layout (layout_primary / layout_primary_sanitized) — список маленьких кусочков текста;
  * clause_tree — дерево пунктов договора (1., 1.1., 1.2. и т.п.).

- DocumentContentService сейчас на лету строит чанки:
  * листовые клаузы (clause),
  * нормализованные под‑чанки (subclause),
  * крупные разделы (section).

- Этот класс делает то же самое, но:
  * собирает ВСЮ эту структуру в один JSON‑объект (snapshot),
  * возвращает его как dict, чтобы воркер chunk_builder сохранил его в MinIO.

Зачем это нужно (исторически):
- В старой архитектуре RetrievalEngine / CheckRunner / LLM читали готовый snapshot
  из MinIO по ссылке из DocumentVersion.
- Сейчас основной контракт для чтения чанков — CHUNKS v2 (chunks_manifest_v2_ref
  + segment_chunks_ref), а этот builder остался как утилита и источник
  вспомогательных функций.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import PermanentError
from core.logging import get_logger
from db.repositories.document_repo import DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from engine.content.clause_tree_builder import ClauseTreeBuilder
from storage.artifact_store import ArtifactStore
from engine.content.chunk_canonicalization import (
    add_position_ratio,
    add_summary,
    build_sized_chunks_from_leaf,
    ensure_clause_metadata,
    extract_total_pages,
    normalize_clause_chunk_text,
    propagate_language_filter,
)

logger = get_logger(__name__)


class ChunkSnapshotBuilder:
    """
    LEGACY: сервис построения canonical snapshot'а чанков для документа
    в режиме "один clause_tree_ref на весь файл".

    Для непрофессионального программиста:
    - Этот класс:
      * читает layout_primary(_sanitized) и clause_tree_ref;
      * строит чанки по ВЕСЕМУ документу, не деля его на сегменты;
      * возвращает snapshot schema_version=1.

    Ограничения:
    - Не умеет работать с несколькими логическими документами внутри файла.
    - Новая архитектура CHUNKS v2 должна использовать FileGraph + DocumentSegment
      и жить в отдельном builder-е (segment_chunk_builder_v2.py).
    """

    def __init__(self, store: ArtifactStore | None = None) -> None:
        self.store = store or ArtifactStore()

    async def build_snapshot(
        self,
        *,
        session: AsyncSession,
        doc_id: uuid.UUID,
        target_tokens: int = 300,
        max_tokens: int = 800,
        overlap_ratio: float = 0.15,
    ) -> dict[str, Any]:
        logger.info(
            "ChunkSnapshotBuilder: build_snapshot start",
            extra={
                "doc_id": str(doc_id),
                "target_tokens": target_tokens,
                "max_tokens": max_tokens,
                "overlap_ratio": overlap_ratio,
            },
        )

        doc_repo = DocumentRepository(session)
        ver_repo = DocumentVersionRepository(session)

        doc = await doc_repo.get_by_id(doc_id)
        if not doc:
            raise PermanentError(f"Document {doc_id} not found")

        version = await ver_repo.get_latest(doc_id)
        if not version:
            raise PermanentError(f"DocumentVersion for doc {doc_id} not found")

        layout_ref = (
            getattr(version, "layout_primary_sanitized_ref", None)
            or getattr(version, "layout_primary_ref", None)
        )
        if not layout_ref:
            raise PermanentError(
                f"No primary layout for doc {doc_id} "
                f"(layout_primary_sanitized_ref/layout_primary_ref missing)"
            )

        layout_kind = (
            "layout_primary_sanitized_ref"
            if getattr(version, "layout_primary_sanitized_ref", None)
            else "layout_primary_ref"
        )

        clause_tree_ref = getattr(version, "clause_tree_ref", None)
        if not clause_tree_ref:
            raise PermanentError(
                f"No clause_tree_ref for doc {doc_id}, structure must be built first"
            )

        logger.info(
            "ChunkSnapshotBuilder: source refs resolved",
            extra={
                "doc_id": str(doc_id),
                "document_version_id": str(version.id),
                "layout_ref": layout_ref,
                "layout_kind": layout_kind,
                "clause_tree_ref": clause_tree_ref,
            },
        )

        layout = self.store.get_json(layout_ref)
        clause_tree = self.store.get_json(clause_tree_ref)

        layout_meta = layout.get("metadata") or {}
        clause_root = clause_tree.get("root") or []

        logger.debug(
            "ChunkSnapshotBuilder: source artifacts loaded",
            extra={
                "doc_id": str(doc_id),
                "document_version_id": str(version.id),
                "layout_has_metadata": isinstance(layout_meta, dict),
                "layout_metadata_keys": sorted(layout_meta.keys()) if isinstance(layout_meta, dict) else [],
                "clause_tree_root_count": len(clause_root) if isinstance(clause_root, list) else 0,
                "clause_tree_has_references_index": isinstance(clause_tree.get("references_index"), list),
                "clause_tree_structure_confidence": clause_tree.get("structure_confidence"),
                "clause_tree_degraded": clause_tree.get("degraded"),
            },
        )

        if not clause_root:
            logger.warning(
                "ChunkSnapshotBuilder: clause tree root is empty",
                extra={
                    "doc_id": str(doc_id),
                    "document_version_id": str(version.id),
                    "clause_tree_ref": clause_tree_ref,
                    "layout_ref": layout_ref,
                },
            )

        leaf_result = ClauseTreeBuilder.build_leaf_chunks(
            doc_id=doc_id,
            tree=clause_tree,
            layout=layout,
        )
        leaf_chunks = leaf_result.chunks

        leaf_with_effective_uid = sum(
            1 for ch in leaf_chunks if (ch.get("metadata") or {}).get("effective_uid")
        )
        leaf_without_effective_uid = len(leaf_chunks) - leaf_with_effective_uid

        leaf_empty_text = sum(1 for ch in leaf_chunks if not (ch.get("text") or "").strip())

        logger.info(
            "ChunkSnapshotBuilder: leaf chunks built",
            extra={
                "doc_id": str(doc_id),
                "document_version_id": str(version.id),
                "leaf_count": len(leaf_chunks),
                "leaf_with_effective_uid": leaf_with_effective_uid,
                "leaf_without_effective_uid": leaf_without_effective_uid,
                "leaf_empty_text_count": leaf_empty_text,
                "total_leaf_nodes": getattr(leaf_result, "total_leaf_nodes", None),
                "leaf_nodes_without_element_ids": getattr(leaf_result, "leaf_nodes_without_element_ids", None),
                "leaf_nodes_empty_after_filtering": getattr(leaf_result, "leaf_nodes_empty_after_filtering", None),
            },
        )

        sample_leaf_uids = [
            str((ch.get("metadata") or {}).get("effective_uid"))
            for ch in leaf_chunks[:10]
            if (ch.get("metadata") or {}).get("effective_uid") is not None
        ]

        if sample_leaf_uids:
            logger.debug(
                "ChunkSnapshotBuilder: sample_effective_uids",
                extra={
                    "doc_id": str(doc_id),
                    "sample_effective_uids": sample_leaf_uids,
                },
            )

        for ch in leaf_chunks:
            meta = ch.get("metadata") or {}
            if str(meta.get("raw_uid")) == "1.1":
                logger.debug(
                    "ChunkSnapshotBuilder: raw leaf chunk before normalization",
                    extra={
                        "doc_id": str(doc_id),
                        "effective_uid": meta.get("effective_uid"),
                        "raw_uid": meta.get("raw_uid"),
                        "raw_text_preview": (ch.get("text") or "")[:500],
                        "raw_text_len": len(ch.get("text") or ""),
                    },
                )
                break

        normalized_changed_count = 0
        normalized_to_empty_count = 0

        for ch in leaf_chunks:
            meta = ch.get("metadata") or {}
            before = ch.get("text") or ""
            after = normalize_clause_chunk_text(
                text=before,
                raw_uid=str(meta.get("raw_uid")) if meta.get("raw_uid") is not None else None,
                title=meta.get("title"),
            )

            if before != after:
                normalized_changed_count += 1
            if before.strip() and not after.strip():
                normalized_to_empty_count += 1
                logger.warning(
                    "ChunkSnapshotBuilder: normalization produced empty clause text",
                    extra={
                        "doc_id": str(doc_id),
                        "effective_uid": meta.get("effective_uid"),
                        "raw_uid": meta.get("raw_uid"),
                        "title": meta.get("title"),
                        "before_len": len(before),
                    },
                )
            ch["text"] = after

        logger.info(
            "ChunkSnapshotBuilder: clause text normalization stats",
            extra={
                "doc_id": str(doc_id),
                "normalized_changed_count": normalized_changed_count,
                "normalized_to_empty_count": normalized_to_empty_count,
                "leaf_count": len(leaf_chunks),
            },
        )

        if not leaf_chunks:
            logger.warning(
                "ChunkSnapshotBuilder: clause tree produced no leaf chunks",
                extra={
                    "doc_id": str(doc_id),
                    "document_version_id": str(version.id),
                    "clause_tree_ref": clause_tree_ref,
                    "layout_ref": layout_ref,
                },
            )
            return _build_empty_snapshot(
                doc_id=str(doc.id),
                document_version_id=str(version.id),
                layout_ref=layout_ref,
                layout_kind=layout_kind,
                clause_tree_ref=clause_tree_ref,
                target_tokens=target_tokens,
                max_tokens=max_tokens,
                overlap_ratio=overlap_ratio,
            )

        total_pages = extract_total_pages(layout_meta)

        logger.debug(
            "ChunkSnapshotBuilder: layout metadata extracted",
            extra={
                "doc_id": str(doc_id),
                "document_version_id": str(version.id),
                "total_pages": total_pages,
                "has_language_filter": bool((layout_meta.get("language_filter") or {}))
                if isinstance(layout_meta, dict)
                else False,
            },
        )

        propagate_language_filter(leaf_chunks, layout_meta)

        language_filter_count = sum(
            1 for ch in leaf_chunks if (ch.get("metadata") or {}).get("language_filter")
        )

        if total_pages:
            add_position_ratio(leaf_chunks, total_pages)

        position_ratio_count = sum(
            1 for ch in leaf_chunks if (ch.get("metadata") or {}).get("position_ratio") is not None
        )

        logger.info(
            "ChunkSnapshotBuilder: metadata propagation stats",
            extra={
                "doc_id": str(doc_id),
                "document_version_id": str(version.id),
                "leaf_count": len(leaf_chunks),
                "language_filter_count": language_filter_count,
                "position_ratio_count": position_ratio_count,
                "total_pages": total_pages,
            },
        )

        sized_chunks = build_sized_chunks_from_leaf(
            doc_id=doc_id,
            leaf_chunks=leaf_chunks,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            overlap_ratio=overlap_ratio,
            total_pages=total_pages,
        )

        if not sized_chunks:
            logger.warning(
                "ChunkSnapshotBuilder: no sized chunks built from leaf chunks",
                extra={
                    "doc_id": str(doc_id),
                    "document_version_id": str(version.id),
                    "clause_tree_ref": clause_tree_ref,
                    "layout_ref": layout_ref,
                    "leaf_chunk_count": len(leaf_chunks),
                },
            )
            return _build_empty_snapshot(
                doc_id=str(doc.id),
                document_version_id=str(version.id),
                layout_ref=layout_ref,
                layout_kind=layout_kind,
                clause_tree_ref=clause_tree_ref,
                target_tokens=target_tokens,
                max_tokens=max_tokens,
                overlap_ratio=overlap_ratio,
            )

        clause_chunks = ensure_clause_metadata(doc_id, leaf_chunks)
        clause_chunks_with_summary = add_summary(clause_chunks)

        invalid_clause_chunks = [
            ch
            for ch in clause_chunks_with_summary
            if not ((ch.get("metadata") or {}).get("effective_uid"))
        ]
        if invalid_clause_chunks:
            logger.warning(
                "ChunkSnapshotBuilder: clause chunks without effective_uid after ensure",
                extra={
                    "doc_id": str(doc_id),
                    "document_version_id": str(version.id),
                    "invalid_count": len(invalid_clause_chunks),
                },
            )

        invalid_clause_kinds = [
            ch
            for ch in clause_chunks_with_summary
            if (ch.get("metadata") or {}).get("chunk_kind") != "clause"
        ]
        if invalid_clause_kinds:
            logger.warning(
                "ChunkSnapshotBuilder: non-clause chunks detected in clause collection",
                extra={
                    "doc_id": str(doc_id),
                    "document_version_id": str(version.id),
                    "invalid_count": len(invalid_clause_kinds),
                },
            )

        subclause_chunks_with_summary = add_summary(sized_chunks)

        invalid_subclause_kinds = [
            ch
            for ch in subclause_chunks_with_summary
            if (ch.get("metadata") or {}).get("chunk_kind") != "subclause"
        ]
        if invalid_subclause_kinds:
            logger.warning(
                "ChunkSnapshotBuilder: non-subclause chunks detected in subclause collection",
                extra={
                    "doc_id": str(doc_id),
                    "document_version_id": str(version.id),
                    "invalid_count": len(invalid_subclause_kinds),
                },
            )

        effective_uid_counter = Counter(
            str((ch.get("metadata") or {}).get("effective_uid"))
            for ch in clause_chunks_with_summary
            if (ch.get("metadata") or {}).get("effective_uid") is not None
        )
        duplicate_effective_uids = {k: v for k, v in effective_uid_counter.items() if v > 1}

        if duplicate_effective_uids:
            logger.warning(
                "ChunkSnapshotBuilder: duplicate effective_uids detected in clause chunks",
                extra={
                    "doc_id": str(doc_id),
                    "document_version_id": str(version.id),
                    "duplicate_effective_uids": duplicate_effective_uids,
                },
            )

        clause_kind_counter = Counter(
            (ch.get("metadata") or {}).get("chunk_kind") for ch in clause_chunks_with_summary
        )
        subclause_kind_counter = Counter(
            (ch.get("metadata") or {}).get("chunk_kind") for ch in subclause_chunks_with_summary
        )

        logger.info(
            "ChunkSnapshotBuilder: clause/subclause stats",
            extra={
                "doc_id": str(doc_id),
                "document_version_id": str(version.id),
                "clause_count": len(clause_chunks_with_summary),
                "subclause_count": len(subclause_chunks_with_summary),
                "clause_kind_distribution": dict(clause_kind_counter),
                "subclause_kind_distribution": dict(subclause_kind_counter),
                "duplicate_effective_uid_count": len(duplicate_effective_uids),
            },
        )

        try:
            section_chunks = ClauseTreeBuilder.build_section_chunks(
                doc_id=doc_id,
                tree=clause_tree,
                layout=layout,
            )

            if not isinstance(section_chunks, list):
                logger.warning(
                    "ChunkSnapshotBuilder: section chunk builder returned non-list, using empty section chunks",
                    extra={
                        "doc_id": str(doc.id),
                        "document_version_id": str(version.id),
                        "returned_type": type(section_chunks).__name__,
                    },
                )
                section_chunks = []

        except Exception as e:
            logger.warning(
                "ChunkSnapshotBuilder: failed to build ClauseTree-based section chunks, continuing with empty section chunks",
                extra={
                    "doc_id": str(doc.id),
                    "document_version_id": str(version.id),
                    "error": str(e),
                },
            )
            section_chunks = []

        invalid_section_kinds = [
            ch
            for ch in section_chunks
            if (ch.get("metadata") or {}).get("chunk_kind") != "section"
        ]
        if invalid_section_kinds:
            logger.warning(
                "ChunkSnapshotBuilder: non-section chunks detected in section collection",
                extra={
                    "doc_id": str(doc_id),
                    "document_version_id": str(version.id),
                    "invalid_count": len(invalid_section_kinds),
                },
            )

        section_without_effective_uid = sum(
            1 for ch in section_chunks if not ((ch.get("metadata") or {}).get("effective_uid"))
        )

        section_empty_element_ids = sum(
            1 for ch in section_chunks if not ((ch.get("metadata") or {}).get("element_ids") or [])
        )

        logger.info(
            "ChunkSnapshotBuilder: section stats",
            extra={
                "doc_id": str(doc.id),
                "document_version_id": str(version.id),
                "section_count": len(section_chunks),
                "section_without_effective_uid_count": section_without_effective_uid,
                "section_empty_element_ids_count": section_empty_element_ids,
            },
        )

        clause_empty_element_ids = sum(
            1 for ch in clause_chunks_with_summary
            if not ((ch.get("metadata") or {}).get("element_ids") or [])
        )
        clause_missing_section_title = sum(
            1 for ch in clause_chunks_with_summary
            if not ((ch.get("metadata") or {}).get("section_title"))
        )
        subclause_empty_element_ids = sum(
            1 for ch in subclause_chunks_with_summary
            if not ((ch.get("metadata") or {}).get("element_ids") or [])
        )

        logger.info(
            "ChunkSnapshotBuilder: chunk quality stats",
            extra={
                "doc_id": str(doc.id),
                "document_version_id": str(version.id),
                "clause_count": len(clause_chunks_with_summary),
                "invalid_effective_uid_count": len(invalid_clause_chunks),
                "clause_empty_element_ids_count": clause_empty_element_ids,
                "clause_missing_section_title_count": clause_missing_section_title,
                "subclause_count": len(subclause_chunks_with_summary),
                "subclause_empty_element_ids_count": subclause_empty_element_ids,
                "section_count": len(section_chunks),
            },
        )

        snapshot: dict[str, Any] = {
            "schema_version": 1,
            "doc_id": str(doc.id),
            "document_version_id": str(version.id),
            "built_at": datetime.now(tz=timezone.utc).isoformat(),
            "source": {
                "layout_ref": layout_ref,
                "layout_kind": layout_kind,
                "clause_tree_ref": clause_tree_ref,
            },
            "params": {
                "target_tokens": target_tokens,
                "max_tokens": max_tokens,
                "overlap_ratio": overlap_ratio,
            },
            "chunks": {
                "section": section_chunks,
                "clause": clause_chunks_with_summary,
                "subclause": subclause_chunks_with_summary,
            },
        }

        logger.info(
            "ChunkSnapshotBuilder: build_snapshot done",
            extra={
                "doc_id": str(doc.id),
                "document_version_id": str(version.id),
                "layout_ref": layout_ref,
                "layout_kind": layout_kind,
                "clause_tree_ref": clause_tree_ref,
                "clause_count": len(clause_chunks_with_summary),
                "subclause_count": len(subclause_chunks_with_summary),
                "section_count": len(section_chunks),
                "schema_version": snapshot["schema_version"],
            },
        )

        return snapshot


# ---------------------------------------------------------------------------
# Вспомогательные функции для работы с чанками.
# ВАЖНО:
# - Эти функции НЕ привязаны к clause_tree_ref и могут использоваться
#   в новой архитектуре CHUNKS v2 (segment-aware).
# - Новый код должен импортировать их как утилиты, а не использовать
#   ChunkSnapshotBuilder целиком.
# ---------------------------------------------------------------------------


def _build_empty_snapshot(
    *,
    doc_id: str,
    document_version_id: str,
    layout_ref: str,
    layout_kind: str,
    clause_tree_ref: str,
    target_tokens: int,
    max_tokens: int,
    overlap_ratio: float,
) -> dict[str, Any]:
    logger.warning(
        "ChunkSnapshotBuilder: building empty snapshot",
        extra={
            "doc_id": doc_id,
            "document_version_id": document_version_id,
            "layout_ref": layout_ref,
            "layout_kind": layout_kind,
            "clause_tree_ref": clause_tree_ref,
            "target_tokens": target_tokens,
            "max_tokens": max_tokens,
            "overlap_ratio": overlap_ratio,
        },
    )
    return {
        "schema_version": 1,
        "doc_id": doc_id,
        "document_version_id": document_version_id,
        "built_at": datetime.now(tz=timezone.utc).isoformat(),
        "source": {
            "layout_ref": layout_ref,
            "layout_kind": layout_kind,
            "clause_tree_ref": clause_tree_ref,
        },
        "params": {
            "target_tokens": target_tokens,
            "max_tokens": max_tokens,
            "overlap_ratio": overlap_ratio,
        },
        "chunks": {
            "section": [],
            "clause": [],
            "subclause": [],
        },
    }


