# src/services/structure/_heading_builder/_bilingual.py

"""Deterministic bilingual heading pair annotation."""

from __future__ import annotations

import re
from dataclasses import replace

from services.structure.heading_llm_refiner import ScoredHeadingCandidate
from services.structure.heading_patterns import normalize_spaces

from ._utils import _normalize_scope, _safe_int

_MAX_PAIR_ELEM_DISTANCE = 3
_MAX_PAIR_PAGE_DISTANCE = 1
_MAX_HEADING_TEXT_LEN = 160
_MAX_HEADING_WORDS = 18
_MIN_ALPHA_CHARS = 3
_SCRIPT_DOMINANCE_THRESHOLD = 0.60

_CYRILLIC_RE = re.compile(r"[А-ЯЁа-яё]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def _candidate_scope(candidate: ScoredHeadingCandidate) -> str:
    return _normalize_scope(candidate.scope)


def _candidate_raw_uid(candidate: ScoredHeadingCandidate) -> str:
    meta = candidate.metadata or {}
    return normalize_spaces(str(meta.get("raw_uid") or candidate.uid or ""))


def _candidate_element_id(candidate: ScoredHeadingCandidate) -> str:
    meta = candidate.metadata or {}
    return str(meta.get("element_id") or f"el-{_safe_int(candidate.elem_i)}")


def _candidate_text(candidate: ScoredHeadingCandidate) -> str:
    meta = candidate.metadata or {}
    title = normalize_spaces(str(meta.get("normalized_title") or candidate.title or ""))
    if title:
        return title
    return normalize_spaces(str(candidate.raw_text or ""))


def _dominant_script(text: str) -> str:
    """
    Returns:
      - "latin"
      - "cyrillic"
      - "mixed"
      - "other"
    """
    prepared = normalize_spaces(text)
    if not prepared:
        return "other"

    cyr = len(_CYRILLIC_RE.findall(prepared))
    lat = len(_LATIN_RE.findall(prepared))
    total = cyr + lat

    if total < _MIN_ALPHA_CHARS:
        return "other"

    cyr_ratio = cyr / total
    lat_ratio = lat / total

    if cyr_ratio >= _SCRIPT_DOMINANCE_THRESHOLD:
        return "cyrillic"
    if lat_ratio >= _SCRIPT_DOMINANCE_THRESHOLD:
        return "latin"
    return "mixed"


def _is_heading_like_text(text: str) -> bool:
    prepared = normalize_spaces(text)
    if not prepared:
        return False
    if len(prepared) > _MAX_HEADING_TEXT_LEN:
        return False
    if len(prepared.split()) > _MAX_HEADING_WORDS:
        return False

    alpha_chars = sum(ch.isalpha() for ch in prepared)
    if alpha_chars < _MIN_ALPHA_CHARS:
        return False

    # Conservative body-like guards
    if prepared.count(",") >= 2:
        return False
    if ". " in prepared and len(prepared) > 48:
        return False

    return True


def _is_complementary_script_pair(script_a: str, script_b: str) -> bool:
    return {script_a, script_b} == {"latin", "cyrillic"}


def _is_bilingual_pair_candidate(
    left: ScoredHeadingCandidate,
    right: ScoredHeadingCandidate,
) -> bool:
    if _candidate_scope(left) != _candidate_scope(right):
        return False

    if _candidate_raw_uid(left) != _candidate_raw_uid(right):
        return False

    if not _candidate_raw_uid(left):
        return False

    if abs(_safe_int(left.elem_i) - _safe_int(right.elem_i)) > _MAX_PAIR_ELEM_DISTANCE:
        return False

    if abs(_safe_int(left.page) - _safe_int(right.page)) > _MAX_PAIR_PAGE_DISTANCE:
        return False

    left_text = _candidate_text(left)
    right_text = _candidate_text(right)

    if not _is_heading_like_text(left_text):
        return False
    if not _is_heading_like_text(right_text):
        return False

    left_script = _dominant_script(left_text)
    right_script = _dominant_script(right_text)

    return _is_complementary_script_pair(left_script, right_script)


def annotate_bilingual_heading_pairs(
    candidates: list[ScoredHeadingCandidate],
) -> list[ScoredHeadingCandidate]:
    """
    Annotates adjacent bilingual heading duplicates.

    Non-destructive:
    - keeps both candidates;
    - marks one as primary and the other as translation;
    - lets ranking layer deterministically prefer primary.
    """
    if not candidates:
        return []

    by_key: dict[tuple[str, str], list[tuple[int, ScoredHeadingCandidate]]] = {}

    for idx, candidate in enumerate(candidates):
        raw_uid = _candidate_raw_uid(candidate)
        if not raw_uid:
            continue
        key = (_candidate_scope(candidate), raw_uid)
        by_key.setdefault(key, []).append((idx, candidate))

    annotations: dict[int, dict] = {}

    for _, grouped in by_key.items():
        # Conservative rule: only pair clean two-item duplicates.
        if len(grouped) != 2:
            continue

        grouped = sorted(grouped, key=lambda item: (_safe_int(item[1].page), _safe_int(item[1].elem_i)))
        (left_idx, left), (right_idx, right) = grouped

        if not _is_bilingual_pair_candidate(left, right):
            continue

        left_text = _candidate_text(left)
        right_text = _candidate_text(right)

        left_script = _dominant_script(left_text)
        right_script = _dominant_script(right_text)

        primary = left
        primary_idx = left_idx
        secondary = right
        secondary_idx = right_idx

        primary_id = _candidate_element_id(primary)
        secondary_id = _candidate_element_id(secondary)

        annotations[primary_idx] = {
            "bilingual_heading_pair": True,
            "bilingual_pair_role": "primary",
            "bilingual_pair_partner_element_id": secondary_id,
            "bilingual_pair_primary_script": left_script,
            "bilingual_pair_secondary_script": right_script,
        }

        annotations[secondary_idx] = {
            "bilingual_heading_pair": True,
            "bilingual_pair_role": "translation",
            "bilingual_pair_partner_element_id": primary_id,
            "heading_translation_of": primary_id,
            "bilingual_pair_primary_script": left_script,
            "bilingual_pair_secondary_script": right_script,
        }

    if not annotations:
        return candidates

    result: list[ScoredHeadingCandidate] = []
    for idx, candidate in enumerate(candidates):
        if idx not in annotations:
            result.append(candidate)
            continue

        new_meta = dict(candidate.metadata or {})
        new_meta.update(annotations[idx])
        result.append(replace(candidate, metadata=new_meta))

    return result


    