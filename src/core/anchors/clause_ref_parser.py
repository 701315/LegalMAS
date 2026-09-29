# src/core/anchors/clause_ref_parser.py
"""
Universal clause reference parser (B7.9.2).

Extracts structural clause markers ("п. 2.2", "Section A",
"Приложение Б", "Appendix S") from free-form clause_ref strings.
Separates clause markers from page references ("стр. 5", "page 5",
"p. 12"), which are never valid identifiers.
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
    "пункт",
    "п-т",
    "п/п",
    "п.",
    "статья",
    "ст.",
    "приложение",
    "прил.",
    "clause",
    "cl.",
    "section",
    "article",
    "art.",
    "appendix",
    "schedule",
    "§",
)

_APPENDIX_PREFIXES: tuple[str, ...] = (
    "appendix",
    "schedule",
    "приложение",
    "прил",
)


def _build_alt(prefixes: Iterable[str]) -> str:
    return "|".join(
        re.escape(p) for p in sorted(prefixes, key=len, reverse=True)
    )


_PAGE_ALT = _build_alt(_PAGE_PREFIXES)
_CLAUSE_ALT = _build_alt(_CLAUSE_PREFIXES)


_MARKER_CORE = (
    r"(?:"
    r"\d+(?:\.\d+)*(?:[A-Za-zА-Яа-я])?"
    r"|[A-ZА-Я]{1,3}(?:-\d+)?"
    r")"
)

# Clause markers — prefix + one or more markers separated by , or ;
#   "п. 7.1.1"           -> ["7.1.1"]
#   "п. 7.1.1, 7.1.2"     -> ["7.1.1", "7.1.2"]
#   "Appendix A, B"       -> ["A", "B"]
#   "п. 2.2, стр. 3"      -> ["2.2"]   (page ref breaks the list)
_CLAUSE_MARKER_LIST_RE = re.compile(
    rf"(?<![A-Za-zА-Яа-я0-9])"
    rf"((?i:(?:{_CLAUSE_ALT})))"
    rf"\s*"
    rf"({_MARKER_CORE}(?:\s*[,;]\s*{_MARKER_CORE})*)"
    rf"(?![A-Za-zА-Яа-я0-9])"
)

_MARKER_IN_LIST_RE = re.compile(_MARKER_CORE)

_PAGE_RE = re.compile(
    rf"(?<![A-Za-zА-Яа-я0-9])"
    rf"(?i:(?:{_PAGE_ALT}))"
    rf"\s*"
    rf"(\d+)"
)

_BARE_MARKER_RE = re.compile(
    r"(?:"
    r"\d+(?:\.\d+)*(?:[A-Za-zА-Яа-я])?"
    r"|[A-ZА-Я]{1,3}"
    r"|[A-ZА-Я]{1,3}-\d+"
    r")"
)


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
    if ref is None:
        return ClauseRefParseResult(markers=(), page_hint=None)

    text = str(ref)
    if not text.strip():
        return ClauseRefParseResult(markers=(), page_hint=None)

    page_ranges, page_hint = _collect_page_ranges(text)

    seen: set[str] = set()
    markers: list[ClauseMarker] = []

    for m in _CLAUSE_MARKER_LIST_RE.finditer(text):
        prefix = m.group(1)
        markers_blob = m.group(2)
        blob_start = m.start(2)

        for inner in _MARKER_IN_LIST_RE.finditer(markers_blob):
            value = inner.group(0).strip()
            if not value or value in seen:
                continue
            pos = blob_start + inner.start()
            if _in_ranges(pos, page_ranges):
                continue
            seen.add(value)
            markers.append(
                ClauseMarker(
                    value=value,
                    kind=_classify_marker(value, prefix=prefix),
                    position=pos,
                )
            )

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


def extract_clause_marker_values(ref: str | None) -> list[str]:
    return [m.value for m in parse_clause_ref(ref).markers]


def extract_page_hint(ref: str | None) -> int | None:
    return parse_clause_ref(ref).page_hint
