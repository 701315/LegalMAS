# src/engine/content/chunk_snapshot_builder.py

"""
ChunkSnapshotBuilder — единый сервис для построения snapshot'а чанков.

Простыми словами для непрофессионального программиста:

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

Зачем это нужно:
- В будущем RetrievalEngine / CheckRunner / LLM будут читать готовый snapshot
  из MinIO (по ссылке chunks_ref в DocumentVersion), а не пересчитывать
  чанки при каждом запросе.
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
from engine.content.chunking import (
    build_chunk_summary,
    build_section_chunks_from_clauses,
    split_text_to_sized_chunks,
)
from engine.retrieval.tokenization import count_tokens
from storage.artifact_store import ArtifactStore

logger = get_logger(__name__)


class ChunkSnapshotBuilder:
    """
    Сервис построения canonical snapshot'а чанков для документа.

    Для непрофессионального программиста:
    - На вход даём:
      * session (подключение к БД),
      * doc_id (UUID документа),
      * параметры chunking (размер, максимум, overlap).
    - Внутри:
      1) читаем из БД последнюю версию документа;
      2) по ссылкам version.layout_primary*_ref и version.clause_tree_ref
         читаем layout и clause_tree из MinIO;
      3) строим:
         - leaf clause chunks (как get_chunks в DocumentContentService),
         - sized subclause chunks (как get_sized_chunks),
         - section‑чанки (как get_hierarchical_chunks → build_section_chunks_from_clauses);
      4) собираем всё это в один dict (snapshot) и возвращаем его.
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

        leaf_chunks = ClauseTreeBuilder.build_leaf_chunks(
            doc_id=doc_id,
            tree=clause_tree,
            layout=layout,
        )

        leaf_with_uid = sum(
            1 for ch in leaf_chunks if (ch.get("metadata") or {}).get("clause_uid")
        )
        leaf_without_uid = len(leaf_chunks) - leaf_with_uid
        leaf_empty_text = sum(1 for ch in leaf_chunks if not (ch.get("text") or "").strip())

        logger.info(
            "ChunkSnapshotBuilder: leaf chunks built",
            extra={
                "doc_id": str(doc_id),
                "document_version_id": str(version.id),
                "leaf_count": len(leaf_chunks),
                "leaf_with_clause_uid": leaf_with_uid,
                "leaf_without_clause_uid": leaf_without_uid,
                "leaf_empty_text_count": leaf_empty_text,
            },
        )

        sample_leaf_uids = [
            str((ch.get("metadata") or {}).get("clause_uid"))
            for ch in leaf_chunks[:10]
            if (ch.get("metadata") or {}).get("clause_uid") is not None
        ]
        if sample_leaf_uids:
            logger.debug(
                "ChunkSnapshotBuilder: sample leaf clause uids",
                extra={
                    "doc_id": str(doc_id),
                    "sample_clause_uids": sample_leaf_uids,
                },
            )

        for ch in leaf_chunks:
            meta = ch.get("metadata") or {}
            if str(meta.get("clause_uid")) == "1.1":
                logger.debug(
                    "ChunkSnapshotBuilder: raw leaf chunk before normalization",
                    extra={
                        "doc_id": str(doc_id),
                        "clause_uid": meta.get("clause_uid"),
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
            after = _normalize_clause_chunk_text(
                text=before,
                clause_uid=str(meta.get("clause_uid")) if meta.get("clause_uid") is not None else None,
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
                        "clause_uid": meta.get("clause_uid"),
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

        total_pages = _extract_total_pages(layout_meta)

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

        _propagate_language_filter(leaf_chunks, layout_meta)

        language_filter_count = sum(
            1 for ch in leaf_chunks if (ch.get("metadata") or {}).get("language_filter")
        )

        if total_pages:
            _add_position_ratio(leaf_chunks, total_pages)

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

        sized_chunks = _build_sized_chunks_from_leaf(
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

        clause_chunks = _ensure_clause_metadata(doc_id, leaf_chunks)
        clause_chunks_with_summary = _add_summary(clause_chunks)

        subclause_chunks_with_summary = _add_summary(sized_chunks)

        clause_uid_counter = Counter(
            str((ch.get("metadata") or {}).get("clause_uid"))
            for ch in clause_chunks_with_summary
            if (ch.get("metadata") or {}).get("clause_uid") is not None
        )
        duplicate_clause_uids = {k: v for k, v in clause_uid_counter.items() if v > 1}

        if duplicate_clause_uids:
            logger.warning(
                "ChunkSnapshotBuilder: duplicate clause_uids detected in clause chunks",
                extra={
                    "doc_id": str(doc_id),
                    "document_version_id": str(version.id),
                    "duplicate_clause_uids": duplicate_clause_uids,
                },
            )

        clause_kind_counter = Counter(
            (ch.get("metadata") or {}).get("kind") for ch in clause_chunks_with_summary
        )
        subclause_kind_counter = Counter(
            (ch.get("metadata") or {}).get("kind") for ch in subclause_chunks_with_summary
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
                "duplicate_clause_uid_count": len(duplicate_clause_uids),
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
                    "ChunkSnapshotBuilder: section chunk builder returned non-list, fallback to legacy section builder",
                    extra={
                        "doc_id": str(doc.id),
                        "document_version_id": str(version.id),
                        "returned_type": type(section_chunks).__name__,
                    },
                )
                section_chunks = []

        except Exception as e:
            logger.warning(
                "ChunkSnapshotBuilder: failed to build ClauseTree-based section chunks, will try legacy fallback",
                extra={
                    "doc_id": str(doc.id),
                    "document_version_id": str(version.id),
                    "error": str(e),
                },
            )
            section_chunks = []

        if not section_chunks:
            try:
                legacy_section_chunks = build_section_chunks_from_clauses(
                    doc_id=str(doc_id),
                    clause_chunks=clause_chunks_with_summary,
                    max_tokens=1200,
                )

                if isinstance(legacy_section_chunks, list) and legacy_section_chunks:
                    logger.warning(
                        "ChunkSnapshotBuilder: using legacy build_section_chunks_from_clauses fallback",
                        extra={
                            "doc_id": str(doc.id),
                            "document_version_id": str(version.id),
                            "legacy_sections_count": len(legacy_section_chunks),
                        },
                    )
                    section_chunks = legacy_section_chunks
                else:
                    section_chunks = []

            except Exception as e:
                logger.warning(
                    "ChunkSnapshotBuilder: failed to build legacy section chunks, continuing without sections",
                    extra={
                        "doc_id": str(doc.id),
                        "document_version_id": str(version.id),
                        "error": str(e),
                    },
                )
                section_chunks = []

        section_without_clause_uid = sum(
            1 for ch in section_chunks if not ((ch.get("metadata") or {}).get("clause_uid"))
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
                "section_without_clause_uid_count": section_without_clause_uid,
                "section_empty_element_ids_count": section_empty_element_ids,
            },
        )

        invalid_clause_chunks = [
            ch
            for ch in clause_chunks_with_summary
            if not ((ch.get("metadata") or {}).get("clause_uid"))
        ]

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
                "invalid_clause_uid_count": len(invalid_clause_chunks),
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
# Вспомогательные функции: полностью совместимы с текущим DocumentContentService
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


def _normalize_clause_chunk_text(
    text: str,
    clause_uid: str | None,
    title: str | None,
) -> str:
    """
    Нормализует текст clause-чанка как ТЕЛО клаузы.

    Новый контракт:
    - заголовок ("<uid> <title>") не должен жить в chunk.text;
    - chunk.text содержит только body;
    - функция не добавляет заголовок и не реконструирует его;
    - функция выполняет только санитарную очистку текста;
    - как мягкий legacy-guard, если первая строка выглядит как heading,
      она удаляется.
    """
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""

    lines = [line.strip() for line in text.split("\n")]

    cleaned: list[str] = []
    prev_empty = True
    for line in lines:
        if not line:
            if prev_empty:
                continue
            cleaned.append("")
            prev_empty = True
            continue

        cleaned.append(line)
        prev_empty = False

    if not cleaned:
        return ""

    uid = (clause_uid or "").strip()
    normalized_title = (title or "").strip()

    if uid:
        first_line = cleaned[0]
        first_compact = re.sub(r"\s+", " ", first_line).strip().rstrip(".")
        uid_prefix = re.sub(r"\s+", " ", uid).strip().rstrip(".")

        looks_like_uid_heading = (
            first_compact == uid_prefix
            or first_compact.startswith(uid_prefix + " ")
        )

        if looks_like_uid_heading:
            if normalized_title:
                expected_heading = f"{uid} {normalized_title}".strip()
                expected_compact = re.sub(r"\s+", " ", expected_heading).strip().rstrip(".")

                if first_compact == expected_compact or first_compact.startswith(uid_prefix + " "):
                    cleaned = cleaned[1:]
            else:
                cleaned = cleaned[1:]

    while cleaned and not cleaned[0]:
        cleaned.pop(0)
    while cleaned and not cleaned[-1]:
        cleaned.pop()

    if not cleaned:
        return ""

    normalized: list[str] = []
    prev_empty = True
    for line in cleaned:
        if not line:
            if prev_empty:
                continue
            normalized.append("")
            prev_empty = True
        else:
            normalized.append(line)
            prev_empty = False

    return "\n\n".join(normalized).strip()


def _extract_total_pages(layout_meta: dict) -> int | None:
    """
    Попытаться достать общее число страниц из metadata layout.
    """
    if not isinstance(layout_meta, dict):
        return None
    for key in ("page_count", "pages", "num_pages", "total_pages"):
        value = layout_meta.get(key)
        if isinstance(value, int) and value > 0:
            return value
    return None


def _propagate_language_filter(leaf_chunks: list[dict], layout_meta: dict) -> None:
    """
    Перенести информацию о language_filter из layout в каждый чанк.
    """
    lf_meta = (layout_meta.get("language_filter") or {}) if isinstance(layout_meta, dict) else {}
    lf_degraded = lf_meta.get("degraded")
    lf_reason = lf_meta.get("degraded_reason")
    lf_target_lang = lf_meta.get("target_language")

    if lf_degraded is None and lf_target_lang is None:
        logger.debug(
            "ChunkSnapshotBuilder: no language_filter data to propagate",
        )
        return

    updated_count = 0

    for ch in leaf_chunks:
        meta = ch.get("metadata") or {}
        lf = dict(meta.get("language_filter") or {})
        before = dict(lf)

        if lf_target_lang is not None and "target_language" not in lf:
            lf["target_language"] = lf_target_lang
        if lf_degraded is not None and "degraded" not in lf:
            lf["degraded"] = bool(lf_degraded)
        if lf_reason is not None and "degraded_reason" not in lf:
            lf["degraded_reason"] = lf_reason
        if lf:
            meta["language_filter"] = lf
            ch["metadata"] = meta
            if lf != before:
                updated_count += 1

    logger.debug(
        "ChunkSnapshotBuilder: language_filter propagated",
        extra={
            "leaf_count": len(leaf_chunks),
            "updated_count": updated_count,
            "target_language": lf_target_lang,
            "degraded": bool(lf_degraded) if lf_degraded is not None else None,
        },
    )


def _calc_position_ratio(
    start_page: int | None,
    end_page: int | None,
    total_pages: int | None,
) -> float | None:
    """
    Посчитать нормализованную позицию чанка в документе.
    """
    if not total_pages or total_pages <= 0:
        return None

    if start_page is None and end_page is None:
        return None

    s = start_page if isinstance(start_page, int) else end_page
    e = end_page if isinstance(end_page, int) else start_page
    if s is None or e is None:
        return None

    mid = (s + e) / 2.0
    ratio = mid / float(total_pages)
    if ratio < 0.0:
        return 0.0
    if ratio > 1.0:
        return 1.0
    return ratio


def _add_position_ratio(leaf_chunks: list[dict], total_pages: int) -> None:
    """Добавить поле position_ratio во все листовые чанки, если можем его посчитать."""
    updated_count = 0
    skipped_count = 0

    for ch in leaf_chunks:
        meta = ch.get("metadata") or {}
        start_page = meta.get("start_page")
        end_page = meta.get("end_page")
        pos = _calc_position_ratio(start_page, end_page, total_pages)
        if pos is not None:
            meta["position_ratio"] = pos
            ch["metadata"] = meta
            updated_count += 1
        else:
            skipped_count += 1

    logger.debug(
        "ChunkSnapshotBuilder: position_ratio added",
        extra={
            "leaf_count": len(leaf_chunks),
            "updated_count": updated_count,
            "skipped_count": skipped_count,
            "total_pages": total_pages,
        },
    )


def _build_sized_chunks_from_leaf(
    *,
    doc_id: uuid.UUID,
    leaf_chunks: list[dict],
    target_tokens: int,
    max_tokens: int,
    overlap_ratio: float,
    total_pages: int | None,
) -> list[dict]:
    """
    Построить нормализованные subclause-чанки поверх листовых клауз.
    """
    SHORT_CLAUSE_MAX_TOKENS = int(target_tokens * 0.9)
    LONG_CLAUSE_MIN_TOKENS = int(max_tokens * 1.2)

    logger.debug(
        "ChunkSnapshotBuilder: sized chunks build start",
        extra={
            "doc_id": str(doc_id),
            "leaf_count": len(leaf_chunks),
            "target_tokens": target_tokens,
            "max_tokens": max_tokens,
            "overlap_ratio": overlap_ratio,
            "short_clause_max_tokens": SHORT_CLAUSE_MAX_TOKENS,
            "long_clause_min_tokens": LONG_CLAUSE_MIN_TOKENS,
        },
    )

    sized: list[dict] = []

    short_count = 0
    medium_count = 0
    long_count = 0
    split_long_count = 0
    long_fallback_whole_count = 0
    skipped_empty_leaf_count = 0

    for base in leaf_chunks:
        text = base.get("text") or ""
        metadata = base.get("metadata") or {}

        if not text.strip():
            skipped_empty_leaf_count += 1
            continue

        clause_uid = metadata.get("clause_uid")
        level = metadata.get("level")
        path_titles = metadata.get("path_titles") or []
        section_title = metadata.get("section_title")
        start_page = metadata.get("start_page")
        end_page = metadata.get("end_page")
        element_ids = metadata.get("element_ids") or []

        clause_token_count = count_tokens(text)

        if "position_ratio" in metadata:
            position_ratio = metadata.get("position_ratio")
        elif total_pages:
            position_ratio = _calc_position_ratio(start_page, end_page, total_pages)
        else:
            position_ratio = None

        def _append_whole() -> None:
            chunk_id = f"{doc_id}:{clause_uid or 'full'}:0"

            chunk_meta = {
                "doc_id": str(doc_id),
                "kind": "clause",
                "clause_uid": clause_uid,
                "title": metadata.get("title"),
                "level": level,
                "path_titles": path_titles,
                "start_page": start_page,
                "end_page": end_page,
                "element_ids": element_ids,
                "token_count": clause_token_count,
                "position_ratio": position_ratio,
            }

            if section_title:
                chunk_meta["section_title"] = section_title

            sized.append(
                {
                    "id": chunk_id,
                    "text": text,
                    "metadata": chunk_meta,
                }
            )

        if clause_token_count <= SHORT_CLAUSE_MAX_TOKENS:
            short_count += 1
            _append_whole()
            continue

        if SHORT_CLAUSE_MAX_TOKENS < clause_token_count < LONG_CLAUSE_MIN_TOKENS:
            medium_count += 1
            _append_whole()
            continue

        long_count += 1

        sub_texts = split_text_to_sized_chunks(
            text=text,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            overlap_ratio=overlap_ratio,
        )

        if not sub_texts:
            long_fallback_whole_count += 1
            _append_whole()
            continue

        split_long_count += 1

        for sub_idx, sub_text in enumerate(sub_texts):
            if not sub_text.strip():
                continue

            sub_token_count = count_tokens(sub_text)
            chunk_id = f"{doc_id}:{clause_uid or 'full'}:{sub_idx}"

            sub_meta = {
                "doc_id": str(doc_id),
                "kind": "subclause",
                "clause_uid": clause_uid,
                "title": metadata.get("title"),
                "level": level,
                "path_titles": path_titles,
                "start_page": start_page,
                "end_page": end_page,
                "element_ids": element_ids,
                "token_count": sub_token_count,
                "position_ratio": position_ratio,
            }

            if section_title:
                sub_meta["section_title"] = section_title

            sized.append(
                {
                    "id": chunk_id,
                    "text": sub_text,
                    "metadata": sub_meta,
                }
            )

    if not sized:
        logger.warning(
            "ChunkSnapshotBuilder: no sized chunks built, subclause list will be empty",
            extra={
                "doc_id": str(doc_id),
                "leaf_count": len(leaf_chunks),
            },
        )
        return sized

    logger.info(
        "ChunkSnapshotBuilder: sized chunks built",
        extra={
            "doc_id": str(doc_id),
            "leaf_count": len(leaf_chunks),
            "sized_count": len(sized),
            "short_clause_count": short_count,
            "medium_clause_count": medium_count,
            "long_clause_count": long_count,
            "split_long_count": split_long_count,
            "long_fallback_whole_count": long_fallback_whole_count,
            "skipped_empty_leaf_count": skipped_empty_leaf_count,
        },
    )

    return sized


def _ensure_clause_metadata(doc_id: uuid.UUID, leaf_chunks: list[dict]) -> list[dict]:
    """
    Привести leaf‑чанки к ожидаемому виду:
    - гарантировать doc_id, kind, token_count, section_title.
    """
    out: list[dict] = []
    dropped_empty_text = 0
    added_section_title_count = 0
    added_doc_id_count = 0
    added_kind_count = 0
    added_token_count_count = 0

    for ch in leaf_chunks:
        text = (ch.get("text") or "").strip()
        meta = ch.get("metadata") or {}

        if not text:
            dropped_empty_text += 1
            continue

        path_titles = meta.get("path_titles") or []
        section_title = path_titles[0] if path_titles else None

        if "doc_id" not in meta:
            added_doc_id_count += 1
        if "kind" not in meta:
            added_kind_count += 1
        if "token_count" not in meta:
            added_token_count_count += 1

        meta.setdefault("doc_id", str(doc_id))
        meta.setdefault("kind", "clause")
        meta.setdefault("token_count", count_tokens(text))

        if section_title is not None and "section_title" not in meta:
            meta["section_title"] = section_title
            added_section_title_count += 1

        out.append(
            {
                "id": ch.get("id") or f"{doc_id}:{meta.get('clause_uid') or 'full'}",
                "text": text,
                "metadata": meta,
            }
        )

    logger.debug(
        "ChunkSnapshotBuilder: clause metadata ensured",
        extra={
            "doc_id": str(doc_id),
            "input_count": len(leaf_chunks),
            "output_count": len(out),
            "dropped_empty_text_count": dropped_empty_text,
            "added_doc_id_count": added_doc_id_count,
            "added_kind_count": added_kind_count,
            "added_token_count_count": added_token_count_count,
            "added_section_title_count": added_section_title_count,
        },
    )

    return out


def _add_summary(chunks: list[dict]) -> list[dict]:
    """
    Добавить summary в metadata каждого чанка, если его ещё нет.
    """
    out: list[dict] = []
    added_summary_count = 0
    existing_summary_count = 0
    empty_text_count = 0

    for ch in chunks:
        text = ch.get("text") or ""
        meta = ch.get("metadata") or {}

        if not text.strip():
            empty_text_count += 1

        if not meta.get("summary"):
            path_titles = meta.get("path_titles") or []
            meta["summary"] = build_chunk_summary(path_titles, text)
            ch["metadata"] = meta
            added_summary_count += 1
        else:
            existing_summary_count += 1

        out.append(ch)

    logger.debug(
        "ChunkSnapshotBuilder: summaries added",
        extra={
            "chunk_count": len(chunks),
            "added_summary_count": added_summary_count,
            "existing_summary_count": existing_summary_count,
            "empty_text_count": empty_text_count,
        },
    )

    return out

