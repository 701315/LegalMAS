# src/engine/content/_document_content_classification.py

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class ClassificationContentBundle:
    """
    Canonical source bundle for document-level classification.

    header_text:
      - preferred: canonical preamble chunk from semantic corpus
      - fallback: layout title+preamble (outside this helper module)

    body_text:
      - preferred: legal_unit chunks from main contract semantic scope
      - fallback: section chunks from main contract semantic scope
      - fallback: retrieval-safe legal_unit/section chunks from other scopes
    """

    header_text: str | None
    body_text: str | None

    header_source: str
    body_source: str

    header_refs: list[str]
    body_refs: list[str]

    body_levels: list[str]
    body_scopes: list[str]

    diagnostics: dict[str, Any]


def get_chunk_meta(chunk: dict[str, Any]) -> dict[str, Any]:
    meta = chunk.get("metadata")
    return meta if isinstance(meta, dict) else {}


def get_chunk_kind(chunk: dict[str, Any]) -> str:
    meta = get_chunk_meta(chunk)
    return str(meta.get("chunk_kind") or "").strip().lower()


def get_effective_uid(chunk: dict[str, Any]) -> str:
    meta = get_chunk_meta(chunk)
    return str(meta.get("effective_uid") or "").strip()


def get_chunk_ref(chunk: dict[str, Any]) -> str:
    uid = get_effective_uid(chunk)
    if uid:
        return uid
    chunk_id = chunk.get("id")
    return str(chunk_id or "").strip()


def infer_semantic_scope(chunk: dict[str, Any]) -> str:
    """
    Universal semantic scope inference.

    Audit-proven fact:
    - for section chunks metadata.scope may already be semantic (e.g. main_contract)
    - for legal_unit chunks metadata.scope may contain segment_id instead of semantic scope
    - effective_uid has canonical form like `main_contract:1.4`

    Therefore:
    - prefer scope inferred from effective_uid prefix
    - fallback to metadata.scope only if effective_uid is absent
    """
    uid = get_effective_uid(chunk)
    if ":" in uid:
        return uid.split(":", 1)[0].strip()

    meta = get_chunk_meta(chunk)
    return str(meta.get("scope") or "").strip()


def is_preamble_chunk(chunk: dict[str, Any]) -> bool:
    uid = get_effective_uid(chunk)
    if "__preamble__" in uid:
        return True

    chunk_id = str(chunk.get("id") or "").strip()
    return "__preamble__" in chunk_id


def is_main_contract_chunk(chunk: dict[str, Any]) -> bool:
    return infer_semantic_scope(chunk) == "main_contract"


def truncate_text(text: str | None, max_chars: int) -> str | None:
    if not text:
        return None

    text = str(text).strip()
    if not text:
        return None

    if max_chars <= 0:
        return None

    if len(text) <= max_chars:
        return text

    text = text[:max_chars]
    text = text.rsplit(" ", 1)[0].strip()
    return text or None


def _header_kind_rank(chunk: dict[str, Any]) -> int:
    """
    Prefer larger/coherent structural header carriers first.

    section > clause > legal_unit > other
    """
    kind = get_chunk_kind(chunk)
    if kind == "section":
        return 0
    if kind == "clause":
        return 1
    if kind == "legal_unit":
        return 2
    return 3


def select_header_chunk(chunks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """
    Select the best canonical header/preamble carrier from semantic corpus.
    """
    if not chunks:
        return None

    candidates = [
        ch for ch in chunks
        if is_preamble_chunk(ch) and (ch.get("text") or "").strip()
    ]
    if not candidates:
        return None

    candidates = sorted(
        candidates,
        key=lambda ch: (
            0 if is_main_contract_chunk(ch) else 1,
            _header_kind_rank(ch),
        ),
    )
    return candidates[0]


def _take_until_chars(
    chunks: list[dict[str, Any]],
    *,
    max_chars: int,
    exclude_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    if not chunks or max_chars <= 0:
        return []

    selected: list[dict[str, Any]] = []
    total_chars = 0

    for ch in chunks:
        if exclude_ids and id(ch) in exclude_ids:
            continue

        text = str(ch.get("text") or "").strip()
        if not text:
            continue

        selected.append(ch)
        total_chars += len(text)

        if total_chars >= max_chars:
            break

    return selected


def _collect_diag(
    selected: list[dict[str, Any]],
    *,
    mode: str,
) -> dict[str, Any]:
    levels: list[str] = []
    scopes: list[str] = []
    refs: list[str] = []

    for ch in selected:
        kind = get_chunk_kind(ch)
        scope = infer_semantic_scope(ch)
        ref = get_chunk_ref(ch)

        if kind and kind not in levels:
            levels.append(kind)
        if scope and scope not in scopes:
            scopes.append(scope)
        if ref and ref not in refs:
            refs.append(ref)

    return {
        "body_selection_mode": mode,
        "body_chunk_count": len(selected),
        "body_levels": levels,
        "body_scopes": scopes,
        "body_refs": refs,
    }


def _extract_hot_chunks(
    chunks: list[dict[str, Any]],
    hot_patterns: list[re.Pattern[str]],
    *,
    hot_budget: int,
    max_hot_chunks: int,
) -> tuple[list[dict[str, Any]], set[int], list[dict[str, Any]]]:
    """
    Phase 3.2: Scan all chunks against hot keyword patterns.

    Returns (selected_hot_chunks, selected_object_ids, hit_details).
    Fail-safe: any exception → empty result, no crash.
    """
    if not hot_patterns or not chunks:
        return [], set(), []

    hit_indices: list[int] = []
    hit_details: list[dict[str, Any]] = []

    try:
        for idx, ch in enumerate(chunks):
            text = str(ch.get("text") or "").strip()
            if not text or len(text) < 10:
                continue
            for pat in hot_patterns:
                if pat.search(text):
                    hit_indices.append(idx)
                    hit_details.append({
                        "chunk_index": idx,
                        "matched_pattern": pat.pattern[:80],
                        "chunk_len": len(text),
                        "effective_uid": get_effective_uid(ch),
                    })
                    break  # один hit на чанк достаточно
    except Exception as exc:
        logger.warning(
            "select_body_chunks: hot keyword scan failed",
            extra={"error": str(exc)},
        )
        return [], set(), []

    # Greedy take in original order within hot_budget
    selected: list[dict[str, Any]] = []
    selected_ids: set[int] = set()
    chars_used = 0

    for idx in hit_indices:
        if len(selected) >= max_hot_chunks:
            break
        ch = chunks[idx]
        chunk_len = len(str(ch.get("text") or "").strip())
        if chars_used + chunk_len > hot_budget:
            continue  # skip, не break — следующий может влезть
        selected.append(ch)
        selected_ids.add(id(ch))
        chars_used += chunk_len

    return selected, selected_ids, hit_details


def select_body_chunks(
    retrieval_chunks: list[dict[str, Any]],
    *,
    max_chars: int,
    hot_keyword_patterns: list[re.Pattern[str]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Select canonical body chunks for document classification.

    Phase 3.2 — Hot Keywords Pass:
      If hot_keyword_patterns provided and feature flag enabled,
      reserve a fraction of max_chars for chunks matching high-distinctiveness
      patterns from YAML configs. This prevents quota crowding where
      sequential top-down sampling monopolises the budget on early chapters.

    Priority (sequential pass, unchanged):
      1. legal_unit chunks from main_contract semantic scope
      2. section chunks from main_contract semantic scope
      3. legal_unit chunks from other scopes
      4. section chunks from other scopes

    Rules:
      - preamble chunks are excluded from body (header already carries them)
      - preserve input order within each priority group
      - stop when accumulated chars reach max_chars
    """
    if not retrieval_chunks:
        return [], _collect_diag([], mode="empty")

    # ── Phase 3.2: Hot Keywords Pass ────────────────────────────────
    hot_selected: list[dict[str, Any]] = []
    hot_ids: set[int] = set()
    hot_diag_details: list[dict[str, Any]] = []
    hot_chars_used = 0
    hot_enabled = bool(
        hot_keyword_patterns
        and getattr(settings, "CLASSIFICATION_BODY_HOT_KEYWORDS_ENABLED", True)
    )

    if hot_enabled and hot_keyword_patterns:
        hot_budget = int(
            max_chars
            * getattr(settings, "CLASSIFICATION_BODY_HOT_RESERVE_FRACTION", 0.20)
        )
        hot_max = int(
            getattr(settings, "CLASSIFICATION_BODY_HOT_MAX_CHUNKS", 8)
        )
        hot_selected, hot_ids, hot_diag_details = _extract_hot_chunks(
            retrieval_chunks,
            hot_keyword_patterns,
            hot_budget=hot_budget,
            max_hot_chunks=hot_max,
        )
        hot_chars_used = sum(
            len(str(ch.get("text") or "").strip()) for ch in hot_selected
        )
        if hot_selected:
            logger.info(
                "select_body_chunks: hot keywords pass",
                extra={
                    "hits": len(hot_selected),
                    "chars_used": hot_chars_used,
                    "budget": hot_budget,
                },
            )

    remaining_budget = max(0, max_chars - hot_chars_used)

    # ── Bucket partitioning (unchanged logic) ───────────────────────
    legal_unit_main: list[dict[str, Any]] = []
    section_main: list[dict[str, Any]] = []
    legal_unit_other: list[dict[str, Any]] = []
    section_other: list[dict[str, Any]] = []

    for ch in retrieval_chunks:
        text = str(ch.get("text") or "").strip()
        if not text:
            continue

        if is_preamble_chunk(ch):
            continue

        kind = get_chunk_kind(ch)
        if kind not in {"legal_unit", "section"}:
            continue

        is_main = is_main_contract_chunk(ch)

        if kind == "legal_unit" and is_main:
            legal_unit_main.append(ch)
        elif kind == "section" and is_main:
            section_main.append(ch)
        elif kind == "legal_unit":
            legal_unit_other.append(ch)
        elif kind == "section":
            section_other.append(ch)

    # ── Sequential pass with reduced budget, excluding hot chunks ───
    sequential_selected: list[dict[str, Any]] = []
    sequential_mode = "empty"

    for mode, bucket in (
        ("legal_unit_main", legal_unit_main),
        ("section_main", section_main),
        ("legal_unit_fallback", legal_unit_other),
        ("section_fallback", section_other),
    ):
        selected = _take_until_chars(
            bucket,
            max_chars=remaining_budget,
            exclude_ids=hot_ids if hot_ids else None,
        )
        if selected:
            sequential_selected = selected
            sequential_mode = mode
            break

    # ── Merge hot + sequential, preserving document order ───────────
    if hot_selected:
        # Build position map from original corpus
        position_map: dict[int, int] = {
            id(ch): pos for pos, ch in enumerate(retrieval_chunks)
        }
        seen: set[int] = set()
        merged: list[dict[str, Any]] = []
        for ch in hot_selected + sequential_selected:
            cid = id(ch)
            if cid not in seen:
                seen.add(cid)
                merged.append(ch)
        merged.sort(key=lambda c: position_map.get(id(c), 999_999))
        final_mode = f"hot+{sequential_mode}" if sequential_selected else "hot_only"
    else:
        merged = sequential_selected
        final_mode = sequential_mode

    # ── Diagnostics ─────────────────────────────────────────────────
    diag = _collect_diag(merged, mode=final_mode)
    diag["hot_keywords_enabled"] = hot_enabled
    diag["hot_keywords_hits"] = len(hot_diag_details)
    diag["hot_keywords_chars"] = hot_chars_used
    diag["hot_keywords_details"] = hot_diag_details[:5]
    diag["effective_sequential_budget"] = remaining_budget

    return merged, diag


