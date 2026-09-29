# src/core/anchors/clause_ref_parser.py
"""
Universal clause reference parser.

This module extracts structural clause markers (identifiers such as
"п. 2.2", "Section A", "Приложение Б", "Appendix S") from free-form
clause_ref strings produced by LLM extraction or written by humans.
It separates clause markers from page references ("стр. 5", "page 5",
"p. 12") which are never valid identifiers.

Why this module exists
----------------------

The extraction pipeline receives a per-field clause_ref such as:

    "пункт S, СОГЛАШЕНИЕ О КОНФИДЕНЦИАЛЬНОСТИ, стр. 1"

This string contains BOTH a clause marker ("S") and a page reference
("стр. 1"). A naive digit-based regex returns ["1"] — matching the page
number, not the clause. The result is a wrong anchor pointing at
"main_contract:1" instead of "main_contract:S".

The same class of bug affects any document where the LLM formats clause
references with a page hint, in any alphabet (Latin, Cyrillic, mixed),
under any prefix vocabulary:
    RU: п., пункт, п-т, п/п, статья, ст., приложение, прил.
    EN: cl., clause, section, article, art., appendix, schedule
    symbols: §

This parser is document-agnostic. It does not encode rules specific to
one contract or one language.

Contract
--------

    parse_clause_ref(ref) -> ClauseRefParseResult
        .markers:   ordered tuple of ClauseMarker(value, kind, position)
        .page_hint: first page number found, or None

Markers are deduplicated by value while preserving first-seen order.

Marker kinds:
    NUMERIC   — digits only:                "1", "2.2", "3.2.1"
    LATIN     — uppercase Latin letters:    "A", "S", "AA"
    CYRILLIC  — uppercase Cyrillic letters: "А", "Б", "АБ"
    MIXED     — digit+letter, letter+digit: "2a", "2.2б", "S-1"
    APPENDIX  — after an appendix prefix:
                "Приложение А", "Appendix B", "Schedule 1"

Bare markers (whole ref is exactly one marker) are recognized only for
well-formed single tokens: numeric, numeric+letter, 1-3 uppercase
letters, or letter(s)-N. Free-form words like "СОГЛАШЕНИЕ" are never
interpreted as markers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

__all__ = [
    "ClauseMarker",
    "ClauseRefParseResult",
    "MarkerKind",
    "extract_clause_marker_values",
    "extract_page_hint",
    "parse_clause_ref",
]


# ──────────────────────────────────────────────────────────────────────
# Public types
# ──────────────────────────────────────────────────────────────────────

class MarkerKind(str, Enum):
    NUMERIC = "numeric"
    LATIN = "latin"
    CYRILLIC = "cyrillic"
    MIXED = "mixed"
    APPENDIX = "appendix"


@dataclass(frozen=True, slots=True)
class ClauseMarker:
    value: str
    kind: MarkerKind
    position: int


@dataclass(frozen=True, slots=True)
class ClauseRefParseResult:
    markers: tuple[ClauseMarker, ...]
    page_hint: int | None


# ──────────────────────────────────────────────────────────────────────
# Prefix vocabularies.
#   - Case-insensitive match against the prefix itself.
#   - The marker character class stays case-sensitive (uppercase only).
#   - Extend these tuples when a new prefix appears in the field; do NOT
#     hard-code one document's vocabulary into the pattern.
# ──────────────────────────────────────────────────────────────────────

_PAGE_PREFIXES: tuple[str, ...] = (
    "стр.",
    "страница",
    "страницы",
    "page",
    "p.",
    "pp.",
    "с.",
)

_CLAUSE_PREFIXES: tuple[str, ...] = (
    # Russian
    "пункт",
    "п-т",
    "п/п",
    "п.",
    "статья",
    "ст.",
    "приложение",
    "прил.",
    # English
    "clause",
    "cl.",
    "section",
    "article",
    "art.",
    "appendix",
    "schedule",
    # Symbols
    "§",
)

_APPENDIX_PREFIXES: tuple[str, ...] = (
    "appendix",
    "schedule",
    "приложение",
    "прил",
)


# ──────────────────────────────────────────────────────────────────────
# Regex construction
# ──────────────────────────────────────────────────────────────────────

def _build_alt(prefixes: Iterable[str]) -> str:
    """Build an alternation of escaped prefixes, longest first."""
    return "|".join(
        re.escape(p) for p in sorted(prefixes, key=len, reverse=True)
    )


_PAGE_ALT = _build_alt(_PAGE_PREFIXES)
_CLAUSE_ALT = _build_alt(_CLAUSE_PREFIXES)


# A marker token that may follow a clause prefix:
#   - numeric:                    2, 2.2, 3.2.1
#   - numeric with letter suffix: 2a, 2.2б
#   - 1-3 uppercase letters:      A, Б, AA, АБВ
#   - letters + hyphen + digits:  S-1, AA-2
# Followed by a "not part of a larger word" lookahead.
_MARKER_CORE = (
    r"(?:"
    r"\d+(?:\.\d+)*(?:[A-Za-zА-Яа-я])?"
    r"|[A-ZА-Я]{1,3}(?:-\d+)?"
    r")"
)

# Clause markers — prefixes are matched case-insensitively via inline (?i:),
# while the marker character class stays case-sensitive for uppercase-only.
_CLAUSE_MARKER_RE = re.compile(
    rf"(?<![A-Za-zА-Яа-я0-9])"
    rf"((?i:(?:{_CLAUSE_ALT})))"
    rf"\s*"
    rf"({_MARKER_CORE})"
    rf"(?![A-Za-zА-Яа-я0-9])"
)

# Page references — same shape, but prefix list is disjoint.
_PAGE_RE = re.compile(
    rf"(?<![A-Za-zА-Яа-я0-9])"
    rf"(?i:(?:{_PAGE_ALT}))"
    rf"\s*"
    rf"(\d+)"
)

# Bare markers — full residual string must match this exactly.
# No free-form words allowed.
_BARE_MARKER_RE = re.compile(
    r"(?:"
    r"\d+(?:\.\d+)*(?:[A-Za-zА-Яа-я])?"
    r"|[A-ZА-Я]{1,3}"
    r"|[A-ZА-Я]{1,3}-\d+"
    r")"
)


# ──────────────────────────────────────────────────────────────────────
# Classification helpers
# ──────────────────────────────────────────────────────────────────────

def _is_all_cyrillic_upper(value: str) -> bool:
    if not value:
        return False
    return all(
        ("\u0410" <= ch <= "\u042f") or ch == "\u0401"
        for ch in value
    )


def _is_all_latin_upper(value: str) -> bool:
    if not value:
        return False
    return all("A" <= ch <= "Z" for ch in value)


def _classify_marker(value: str, prefix: str) -> MarkerKind:
    prefix_lower = prefix.strip().lower()
    for ap in _APPENDIX_PREFIXES:
        if prefix_lower.startswith(ap):
            return MarkerKind.APPENDIX

    if value and value[0].isdigit():
        if re.fullmatch(r"\d+(?:\.\d+)*", value):
            return MarkerKind.NUMERIC
        return MarkerKind.MIXED

    if _is_all_cyrillic_upper(value):
        return MarkerKind.CYRILLIC
    if _is_all_latin_upper(value):
        return MarkerKind.LATIN

    return MarkerKind.MIXED


# ──────────────────────────────────────────────────────────────────────
# Main parser
# ──────────────────────────────────────────────────────────────────────

def _collect_page_ranges(
    text: str,
) -> tuple[list[tuple[int, int]], int | None]:
    ranges: list[tuple[int, int]] = []
    hint: int | None = None
    for m in _PAGE_RE.finditer(text):
        ranges.append(m.span())
        if hint is None:
            try:
                hint = int(m.group(1))
            except (TypeError, ValueError):
                pass
    return ranges, hint


def _in_ranges(pos: int, ranges: list[tuple[int, int]]) -> bool:
    for s, e in ranges:
        if s <= pos < e:
            return True
    return False


def _strip_ranges(text: str, ranges: list[tuple[int, int]]) -> str:
    if not ranges:
        return text
    result = text
    for s, e in sorted(ranges, key=lambda r: r[0], reverse=True):
        result = result[:s] + " " + result[e:]
    return result


def parse_clause_ref(ref: str | None) -> ClauseRefParseResult:
    """Parse a free-form clause reference into markers + optional page hint.

    See module docstring for the full contract.
    """
    if ref is None:
        return ClauseRefParseResult(markers=(), page_hint=None)

    text = str(ref)
    if not text.strip():
        return ClauseRefParseResult(markers=(), page_hint=None)

    page_ranges, page_hint = _collect_page_ranges(text)

    seen: set[str] = set()
    markers: list[ClauseMarker] = []

    # Pass 1 — markers after explicit clause prefixes.
    for m in _CLAUSE_MARKER_RE.finditer(text):
        marker_start = m.start(2)
        if _in_ranges(marker_start, page_ranges):
            continue
        value = m.group(2).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        markers.append(
            ClauseMarker(
                value=value,
                kind=_classify_marker(value, prefix=m.group(1)),
                position=marker_start,
            )
        )

    # Pass 2 — bare marker. Only if Pass 1 found nothing AND the residual
    # string (after stripping page references and edge separators) is
    # exactly one well-formed marker token.
    if not markers:
        residual = _strip_ranges(text, page_ranges).strip(" \t\r\n.,;:—-()")
        if residual and _BARE_MARKER_RE.fullmatch(residual):
            pos = text.find(residual)
            if pos < 0:
                pos = 0
            markers.append(
                ClauseMarker(
                    value=residual,
                    kind=_classify_marker(residual, prefix=""),
                    position=pos,
                )
            )

    markers.sort(key=lambda cm: cm.position)
    return ClauseRefParseResult(
        markers=tuple(markers),
        page_hint=page_hint,
    )


# ──────────────────────────────────────────────────────────────────────
# Backward-compatible convenience helpers
# ──────────────────────────────────────────────────────────────────────

def extract_clause_marker_values(ref: str | None) -> list[str]:
    """Return just the marker string values in order of appearance."""
    return [m.value for m in parse_clause_ref(ref).markers]


def extract_page_hint(ref: str | None) -> int | None:
    """Return the first page reference from the clause_ref, if any."""
    return parse_clause_ref(ref).page_hint


    