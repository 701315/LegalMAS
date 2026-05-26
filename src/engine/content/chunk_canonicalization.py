# src/engine/content/chunk_canonicalization.py

from __future__ import annotations

import re
import uuid
from typing import Any

from core.logging import get_logger
from engine.content.chunking import build_chunk_summary, split_text_to_sized_chunks
from engine.retrieval.tokenization import count_tokens
from engine.content.chunk_ids import build_subclause_chunk_id

logger = get_logger(__name__)


def normalize_clause_chunk_text(
    text: str,
    raw_uid: str | None,
    title: str | None,
) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""

    lines = [line.strip() for line in text.splitlines()]
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

    uid = (raw_uid or "").strip()
    normalized_title = (title or "").strip()

    if uid:
        first_line = cleaned[0]
        first_compact = re.sub(r"\s+", " ", first_line.strip().rstrip("."))
        uid_prefix = re.sub(r"\s+", " ", uid.strip().rstrip("."))
        looks_like_uid_heading = (
            first_compact == uid_prefix or first_compact.startswith(uid_prefix)
        )

        if looks_like_uid_heading:
            if normalized_title:
                expected_heading = f"{uid} {normalized_title.strip()}"
                expected_compact = re.sub(
                    r"\s+", " ", expected_heading.strip().rstrip(".")
                )
                if (
                    first_compact == expected_compact
                    or first_compact.startswith(uid_prefix)
                ):
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

    return "\n".join(normalized).strip()


def extract_total_pages(layout_meta: dict[str, Any] | None) -> int | None:
    if not isinstance(layout_meta, dict):
        return None

    for key in ("page_count", "pages", "num_pages", "total_pages"):
        value = layout_meta.get(key)
        if isinstance(value, int) and value > 0:
            return value

    return None


def calc_position_ratio(
    start_page: int | None,
    end_page: int | None,
    total_pages: int | None,
) -> float | None:
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


def propagate_language_filter(
    leaf_chunks: list[dict[str, Any]],
    layout_meta: dict[str, Any] | None,
) -> None:
    lf_meta = layout_meta.get("language_filter") or {} if isinstance(layout_meta, dict) else {}
    lf_degraded = lf_meta.get("degraded")
    lf_reason = lf_meta.get("degraded_reason")
    lf_target_lang = lf_meta.get("target_language")

    if lf_degraded is None and lf_target_lang is None:
        logger.debug("chunk_canonicalization: no language_filter data to propagate")
        return

    updated_count = 0

    for chunk in leaf_chunks:
        meta = chunk.get("metadata") or {}
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
            chunk["metadata"] = meta

        if lf != before:
            updated_count += 1

    logger.debug(
        "chunk_canonicalization: language_filter propagated",
        extra={
            "leaf_count": len(leaf_chunks),
            "updated_count": updated_count,
            "target_language": lf_target_lang,
            "degraded": bool(lf_degraded) if lf_degraded is not None else None,
        },
    )


def add_position_ratio(
    leaf_chunks: list[dict[str, Any]],
    total_pages: int,
) -> None:
    updated_count = 0
    skipped_count = 0

    for chunk in leaf_chunks:
        meta = chunk.get("metadata") or {}
        start_page = meta.get("start_page")
        end_page = meta.get("end_page")
        pos = calc_position_ratio(start_page, end_page, total_pages)

        if pos is not None:
            meta["position_ratio"] = pos
            chunk["metadata"] = meta
            updated_count += 1
        else:
            skipped_count += 1

    logger.debug(
        "chunk_canonicalization: position_ratio added",
        extra={
            "leaf_count": len(leaf_chunks),
            "updated_count": updated_count,
            "skipped_count": skipped_count,
            "total_pages": total_pages,
        },
    )


def ensure_clause_metadata(
    doc_id: uuid.UUID,
    leaf_chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    str_doc_id = str(doc_id)
    out: list[dict[str, Any]] = []

    dropped_empty_text = 0
    dropped_without_effective_uid = 0

    for chunk in leaf_chunks:
        text = (chunk.get("text") or "").strip()
        meta = dict(chunk.get("metadata") or {})

        if not text:
            dropped_empty_text += 1
            continue

        effective_uid = meta.get("effective_uid")
        raw_uid = meta.get("raw_uid")
        scope = meta.get("scope")

        if not effective_uid:
            dropped_without_effective_uid += 1
            logger.warning(
                "chunk_canonicalization: dropping clause chunk without effective_uid",
                extra={
                    "doc_id": str_doc_id,
                    "raw_uid": raw_uid,
                    "scope": scope,
                    "title": meta.get("title"),
                },
            )
            continue

        path_titles = list(meta.get("path_titles") or [])
        section_title = meta.get("section_title") or (path_titles[0] if path_titles else None)
        expected_token_count = count_tokens(text)

        meta["doc_id"] = str_doc_id
        meta["chunk_kind"] = "clause"
        meta["node_kind"] = meta.get("node_kind") or "leaf"
        meta["effective_uid"] = effective_uid
        meta["raw_uid"] = raw_uid
        meta["scope"] = scope
        meta["token_count"] = expected_token_count

        if section_title is not None:
            meta["section_title"] = section_title

        chunk_identity = meta.get("effective_uid") or meta.get("raw_uid") or "full"

        out.append(
            {
                "id": chunk.get("id") or f"{doc_id}:{effective_uid}",
                "text": text,
                "metadata": meta,
            }
        )

    logger.debug(
        "chunk_canonicalization: clause metadata ensured",
        extra={
            "doc_id": str_doc_id,
            "input_count": len(leaf_chunks),
            "output_count": len(out),
            "dropped_empty_text_count": dropped_empty_text,
            "dropped_without_effective_uid_count": dropped_without_effective_uid,
        },
    )

    return out


def build_sized_chunks_from_leaf(
    doc_id: uuid.UUID,
    leaf_chunks: list[dict[str, Any]],
    target_tokens: int,
    max_tokens: int,
    overlap_ratio: float,
    total_pages: int | None = None,
) -> list[dict[str, Any]]:
    short_clause_max_tokens = int(target_tokens * 0.9)
    long_clause_min_tokens = int(max_tokens * 1.2)

    logger.debug(
        "chunk_canonicalization: sized chunks build start",
        extra={
            "doc_id": str(doc_id),
            "leaf_count": len(leaf_chunks),
            "target_tokens": target_tokens,
            "max_tokens": max_tokens,
            "overlap_ratio": overlap_ratio,
            "short_clause_max_tokens": short_clause_max_tokens,
            "long_clause_min_tokens": long_clause_min_tokens,
        },
    )

    sized: list[dict[str, Any]] = []

    for base in leaf_chunks:
        text = (base.get("text") or "").strip()
        metadata = base.get("metadata") or {}

        if not text:
            continue

        effective_uid = metadata.get("effective_uid")
        raw_uid = metadata.get("raw_uid")
        scope = metadata.get("scope")
        node_kind = metadata.get("node_kind") or "leaf"

        if not effective_uid:
            logger.warning(
                "chunk_canonicalization: skipping leaf chunk without effective_uid during subchunk build",
                extra={
                    "doc_id": str(doc_id),
                    "raw_uid": raw_uid,
                    "scope": scope,
                    "title": metadata.get("title"),
                },
            )
            continue

        level = metadata.get("level")
        path_titles = list(metadata.get("path_titles") or [])
        section_title = metadata.get("section_title")
        start_page = metadata.get("start_page")
        end_page = metadata.get("end_page")
        element_ids = [str(e) for e in metadata.get("element_ids") or []]

        if "position_ratio" in metadata:
            position_ratio = metadata.get("position_ratio")
        elif total_pages:
            position_ratio = calc_position_ratio(start_page, end_page, total_pages)
        else:
            position_ratio = None

        clause_token_count = count_tokens(text)

        if clause_token_count <= short_clause_max_tokens:
            subtexts = [text]
        elif short_clause_max_tokens < clause_token_count <= long_clause_min_tokens:
            subtexts = [text]
        else:
            split_candidate = split_text_to_sized_chunks(
                text=text,
                target_tokens=target_tokens,
                max_tokens=max_tokens,
                overlap_ratio=overlap_ratio,
            )
            if not split_candidate:
                subtexts = [text]
            else:
                subtexts = [part for part in split_candidate if part.strip()]

        if not subtexts:
            logger.warning(
                "chunk_canonicalization: no non-empty subchunks produced for leaf chunk",
                extra={
                    "doc_id": str(doc_id),
                    "effective_uid": effective_uid,
                    "raw_uid": raw_uid,
                    "scope": scope,
                    "title": metadata.get("title"),
                },
            )
            continue

        subchunk_count = len(subtexts)

        for sub_idx, subtext in enumerate(subtexts):
            sub_token_count = count_tokens(subtext)
            chunk_id = build_subclause_chunk_id(
                doc_id=doc_id,
                effective_uid=effective_uid,
                subchunk_index=sub_idx,
            )

            sub_meta: dict[str, Any] = {
                "doc_id": str(doc_id),
                "chunk_kind": "subclause",
                "node_kind": node_kind,
                "effective_uid": effective_uid,
                "raw_uid": raw_uid,
                "scope": scope,
                "title": metadata.get("title"),
                "level": level,
                "path_titles": path_titles,
                "start_page": start_page,
                "end_page": end_page,
                "element_ids": element_ids,
                "token_count": sub_token_count,
                "position_ratio": position_ratio,
                "subchunk_index": sub_idx,
                "subchunk_count": subchunk_count,
            }

            if section_title:
                sub_meta["section_title"] = section_title

            if "language_filter" in metadata:
                sub_meta["language_filter"] = metadata["language_filter"]

            if "range_end_reason" in metadata:
                sub_meta["range_end_reason"] = metadata["range_end_reason"]

            for key in (
                "segment_id",
                "segment_type",
                "segment_title",
                "segment_order",
                "segment_page_range",
                "is_primary_segment",
            ):
                if key in metadata:
                    sub_meta[key] = metadata[key]

            sized.append(
                {
                    "id": chunk_id,
                    "text": subtext,
                    "metadata": sub_meta,
                }
            )

    logger.info(
        "chunk_canonicalization: sized chunks built",
        extra={
            "doc_id": str(doc_id),
            "leaf_count": len(leaf_chunks),
            "sized_count": len(sized),
        },
    )

    return sized


def add_summary(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    for chunk in chunks:
        text = chunk.get("text") or ""
        meta = dict(chunk.get("metadata") or {})

        if not meta.get("summary"):
            path_titles = meta.get("path_titles") or []
            summary = build_chunk_summary(path_titles, text)
            if summary:
                meta["summary"] = summary

        out.append(
            {
                **chunk,
                "metadata": meta,
            }
        )

    return out


