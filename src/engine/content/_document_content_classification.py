# src/engine/content/_document_content_classification.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
) -> list[dict[str, Any]]:
    if not chunks or max_chars <= 0:
        return []

    selected: list[dict[str, Any]] = []
    total_chars = 0

    for ch in chunks:
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


def select_body_chunks(
    retrieval_chunks: list[dict[str, Any]],
    *,
    max_chars: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Select canonical body chunks for document classification.

    Priority:
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

    for mode, bucket in (
        ("legal_unit_main", legal_unit_main),
        ("section_main", section_main),
        ("legal_unit_fallback", legal_unit_other),
        ("section_fallback", section_other),
    ):
        selected = _take_until_chars(bucket, max_chars=max_chars)
        if selected:
            return selected, _collect_diag(selected, mode=mode)

    return [], _collect_diag([], mode="empty")



