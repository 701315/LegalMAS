"""
Deterministic recovery for numbered and ordered record/list structures.

Purpose:
- rescue segments where ordinary heading detection found zero headings,
  but the body contains a strong ordered record topology:
    - Numeric: N.1, N.2 or 1), 2)
    - Alpha (Cyrillic GOST / Latin): А., Б., В. or a), b), c)
    - Parenthesized: (1), (2), (a), (b)
- avoid early technical fallback for appendices / schedules / plain-text tables
  rendered as list items or body text.

Architecture:
- deterministic only;
- no LLM;
- conservative activation with gap tolerance;
- format isolation (prevents mixing alphabets/styles);
- modifies only element_type for selected lines and preserves original metadata.

Universal applicability:
- GOST 2.105-2019 / Legal standard Cyrillic alphabet (excluding Ё, З, Й, О, Ъ, Ы, Ь)
- Latin alphabet
- Asset schedules, property registers, technical specifications
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from core.logging import get_logger
from services.structure.heading_patterns import normalize_spaces

logger = get_logger(__name__)

# GOST 2.105-2019 / Standard legal Russian enumeration sequence (27 chars, skipping Ё, З, Й, О, Ъ, Ы, Ь)
_RU_GOST_ALPHABET = "абвгдежиклмнпрстуфхцчшщэюя"
_RU_GOST_MAP = {ch: i + 1 for i, ch in enumerate(_RU_GOST_ALPHABET)}

_EN_ALPHABET = "abcdefghijklmnopqrstuvwxyz"
_EN_MAP = {ch: i + 1 for i, ch in enumerate(_EN_ALPHABET)}

_SURNAME_ENDINGS = (
    "ов", "ова", "ев", "ева", "ин", "ина", "ын", "ына",
    "ский", "ская", "цкий", "цкая", "ич", "юк", "ук"
)

_NUMERIC_RECORD_LINE_RE = re.compile(
    r"^(?P<prefix>\(?)(?P<uid>\d{1,4}(?:\.\d{1,4}){0,5})(?P<suffix>[\.\)]?)\s+(?P<title>\S.*)$"
)

_ALPHA_RECORD_LINE_RE = re.compile(
    r"^(?P<prefix>\(?)(?P<uid>[A-Za-zА-Яа-яЁё])(?P<suffix>[\.\)]?)\s+(?P<title>\S.*)$"
)

_HARD_EXCLUDED_ELEMENT_TYPES = {
    "page_artifact",
    "signature_block",
    "requisites_block",
    "toc_content",
    "toc_header",
    "toc_line",
    "possible_toc",
    "unknown_layout",
}

_REFERENCE_LIKE_TITLE_PREFIXES = (
    "см.",
    "see ",
    "согласно ",
    "pursuant to ",
    "refer to ",
)

_MIN_TOTAL_RECORD_LINES = 3
_MAX_ALLOWED_GAP = 3  # Gap tolerance (e.g. 1 -> 2 -> 4 is allowed)
_MAX_RECORD_TITLE_CHARS = 280
_MAX_RECORD_TITLE_WORDS = 28


@dataclass(frozen=True, slots=True)
class RecordHeadingRecoveryResult:
    applied: bool
    elements: list[dict[str, Any]]
    diagnostics: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _RecordLineCandidate:
    element_index: int
    uid: str
    numeric_index: int
    format_key: str
    depth: int
    title: str
    element_type: str
    has_field_separator: bool


def _parse_alpha_index(char: str) -> int | None:
    c = char.lower()
    if c in _RU_GOST_MAP:
        return _RU_GOST_MAP[c]
    if c in _EN_MAP:
        return _EN_MAP[c]
    return None


def _safe_element_type(element: dict[str, Any]) -> str:
    return str(element.get("element_type") or "").strip().lower()


def _looks_like_initials_noise(char: str, title: str) -> bool:
    """
    Rejects name initials like 'А. Иванов' or 'Б. Петров И.О.'.
    Accepts section titles like 'А. Демонтаж объектов' or 'Б. Очистка участка'.
    """
    words = [w for w in title.strip().split() if w]
    if not words:
        return False

    # Clause/section titles usually have lowercase continuation words or punctuation
    if len(words) > 3:
        return False

    if any(ch in title for ch in (":", ",", "-", "—", ";")):
        return False

    if len(title) > 35:
        return False

    first = words[0].rstrip(".")
    if first.lower().endswith(_SURNAME_ENDINGS):
        return True

    # If 1-3 words, all capitalized, and ends with surname or initial
    if all(w[0].isupper() for w in words) and len(words) <= 2:
        if len(words[0]) <= 2 or words[-1].lower().endswith(_SURNAME_ENDINGS):
            return True

    return False


def _looks_record_like_title(title: str) -> bool:
    normalized = normalize_spaces(title)
    if not normalized:
        return False

    if len(normalized) > _MAX_RECORD_TITLE_CHARS:
        return False

    words = normalized.split()
    if len(words) > _MAX_RECORD_TITLE_WORDS:
        return False

    if not any(ch.isalpha() for ch in normalized):
        return False

    if normalized[:1] in {".", ",", ";", ":"}:
        return False

    lower = normalized.lower()
    if lower.startswith(_REFERENCE_LIKE_TITLE_PREFIXES):
        return False

    return True


def _extract_record_line_candidate(
    *,
    element_index: int,
    element: dict[str, Any],
) -> _RecordLineCandidate | None:
    element_type = _safe_element_type(element)
    if element_type in _HARD_EXCLUDED_ELEMENT_TYPES:
        return None

    text = normalize_spaces(str(element.get("text") or ""))
    if not text:
        return None

    # Try numeric match
    m_num = _NUMERIC_RECORD_LINE_RE.match(text)
    if m_num:
        prefix = m_num.group("prefix") or ""
        uid = normalize_spaces(m_num.group("uid"))
        suffix = m_num.group("suffix") or ""
        title = normalize_spaces(m_num.group("title"))

        if uid and title and _looks_record_like_title(title):
            parts = uid.split(".")
            try:
                num_idx = int(parts[0])
            except ValueError:
                num_idx = None

            if num_idx is not None:
                format_key = f"num_{prefix}_{suffix}_{len(parts)}"
                return _RecordLineCandidate(
                    element_index=element_index,
                    uid=uid,
                    numeric_index=num_idx,
                    format_key=format_key,
                    depth=len(parts),
                    title=title,
                    element_type=element_type,
                    has_field_separator=":" in title,
                )

    # Try alpha match
    m_alpha = _ALPHA_RECORD_LINE_RE.match(text)
    if m_alpha:
        prefix = m_alpha.group("prefix") or ""
        raw_char = m_alpha.group("uid")
        suffix = m_alpha.group("suffix") or ""
        title = normalize_spaces(m_alpha.group("title"))

        if _looks_like_initials_noise(raw_char, title):
            return None

        num_idx = _parse_alpha_index(raw_char)
        if num_idx is not None and title and _looks_record_like_title(title):
            is_ru = raw_char.lower() in _RU_GOST_MAP
            case_str = "upper" if raw_char.isupper() else "lower"
            lang_str = "ru" if is_ru else "en"
            format_key = f"alpha_{lang_str}_{case_str}_{prefix}_{suffix}"

            return _RecordLineCandidate(
                element_index=element_index,
                uid=raw_char,
                numeric_index=num_idx,
                format_key=format_key,
                depth=1,
                title=title,
                element_type=element_type,
                has_field_separator=":" in title,
            )

    return None


def _sequence_is_monotonic(candidates: list[_RecordLineCandidate]) -> bool:
    if len(candidates) < 2:
        return True

    for i in range(len(candidates) - 1):
        prev_idx = candidates[i].numeric_index
        next_idx = candidates[i + 1].numeric_index
        diff = next_idx - prev_idx
        if diff <= 0 or diff > _MAX_ALLOWED_GAP:
            return False

    return True


def _build_recovery_diagnostics(
    *,
    attempted: bool,
    applied: bool,
    reason: str,
    candidates: list[_RecordLineCandidate],
    selected_indices: set[int],
) -> dict[str, Any]:
    type_counts = Counter(c.element_type for c in candidates)

    return {
        "attempted": attempted,
        "applied": applied,
        "mode": "numbered_or_alpha_record",
        "reason": reason,
        "matched_record_lines": len(candidates),
        "selected_record_lines": len(selected_indices),
        "candidate_element_types": dict(type_counts),
        "selected_indices_preview": sorted(selected_indices)[:20],
    }


def attempt_record_heading_recovery(
    *,
    document_id: str,
    elements: list[dict[str, Any]],
) -> RecordHeadingRecoveryResult:
    if not elements:
        return RecordHeadingRecoveryResult(
            applied=False,
            elements=elements,
            diagnostics=_build_recovery_diagnostics(
                attempted=True,
                applied=False,
                reason="empty_elements",
                candidates=[],
                selected_indices=set(),
            ),
        )

    all_candidates: list[_RecordLineCandidate] = []
    by_format: dict[str, list[_RecordLineCandidate]] = defaultdict(list)

    for index, element in enumerate(elements):
        candidate = _extract_record_line_candidate(
            element_index=index,
            element=element,
        )
        if candidate is not None:
            all_candidates.append(candidate)
            by_format[candidate.format_key].append(candidate)

    if len(all_candidates) < _MIN_TOTAL_RECORD_LINES:
        return RecordHeadingRecoveryResult(
            applied=False,
            elements=elements,
            diagnostics=_build_recovery_diagnostics(
                attempted=True,
                applied=False,
                reason="insufficient_record_lines",
                candidates=all_candidates,
                selected_indices=set(),
            ),
        )

    selected_indices: set[int] = set()

    for fmt, series in by_format.items():
        if len(series) >= 2 and _sequence_is_monotonic(series):
            for cand in series:
                selected_indices.add(cand.element_index)

    if len(selected_indices) < _MIN_TOTAL_RECORD_LINES:
        return RecordHeadingRecoveryResult(
            applied=False,
            elements=elements,
            diagnostics=_build_recovery_diagnostics(
                attempted=True,
                applied=False,
                reason="no_valid_monotonic_series_found",
                candidates=all_candidates,
                selected_indices=selected_indices,
            ),
        )

    recovered_elements = list(elements)
    promoted_count = 0

    for candidate in all_candidates:
        if candidate.element_index not in selected_indices:
            continue

        original = recovered_elements[candidate.element_index]
        cloned = dict(original)
        metadata = dict(cloned.get("metadata") or {})

        original_type = _safe_element_type(original)
        metadata["record_heading_recovery"] = True
        metadata["record_heading_recovery_uid"] = candidate.uid
        metadata["record_heading_recovery_format"] = candidate.format_key
        metadata["record_heading_recovery_original_element_type"] = original_type
        metadata["record_heading_recovery_mode"] = "ordered_record"

        cloned["metadata"] = metadata
        cloned["element_type"] = "heading_candidate"
        recovered_elements[candidate.element_index] = cloned
        promoted_count += 1

    diagnostics = _build_recovery_diagnostics(
        attempted=True,
        applied=True,
        reason="ordered_record_topology_detected",
        candidates=all_candidates,
        selected_indices=selected_indices,
    )
    diagnostics["promoted_count"] = promoted_count

    logger.info(
        "STRUCTURE record_heading_recovery_applied",
        extra={
            "document_id": document_id,
            "matched_record_lines": diagnostics["matched_record_lines"],
            "selected_record_lines": diagnostics["selected_record_lines"],
        },
    )

    return RecordHeadingRecoveryResult(
        applied=True,
        elements=recovered_elements,
        diagnostics=diagnostics,
    )
