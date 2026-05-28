# src/services/structure/toc_matcher.py

"""
TOC-to-heading matching слой для Sprint 2 structural pipeline.

Роль модуля:
- матчить ParsedTOC entries с body headings;
- поддерживать exact matching после нормализации;
- поддерживать fuzzy matching с OCR tolerance;
- кэшировать нормализованные строки для repeated matching;
- проставлять match_type: exact / fuzzy / no_match;
- готовить TOC match index для heading scoring и diagnostics.

Главный принцип:
matcher не решает, насколько TOC надёжен в целом.
Он только сообщает, какие TOC entries нашли подтверждение в body headings.

Важно:
- reliability считается в toc_parser.py на основе уже выполненного matching;
- TOC entry может быть unmatched и при этом не ломать pipeline;
- no_match трактуется как structural diagnostics, а не как исключение.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from core.logging import get_logger
from services.structure.heading_patterns import normalize_spaces
from services.structure.hierarchy_builder import HeadingCandidate
from services.structure.toc_parser import ParsedTOC, ParsedTOCEntry

logger = get_logger(__name__)

try:
    from rapidfuzz import fuzz, process
except Exception:  # pragma: no cover
    fuzz = None
    process = None

_NON_ALNUM_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")

DEFAULT_FUZZY_THRESHOLD = 87.0
WEAK_FUZZY_THRESHOLD = 82.0


@dataclass(slots=True)
class TOCMatch:
    """
    Результат сопоставления одной TOC entry с body heading.

    Attributes:
        match_type: exact / fuzzy.
        matched_heading_uid: UID найденного heading.
        matched_heading_title: Title найденного heading.
        matched_heading_page: Page найденного heading.
        match_score: Similarity score.
    """

    match_type: str
    matched_heading_uid: str | None
    matched_heading_title: str | None
    matched_heading_page: int | None
    match_score: float | None


@lru_cache(maxsize=4096)
def normalize_match_text(text: str) -> str:
    """
    Нормализует строку для exact/fuzzy matching.

    Поведение:
    - casefold;
    - удаление punctuation noise;
    - collapse whitespace;
    - стабильный deterministic output для кеширования.
    """
    t = normalize_spaces(text or "").casefold()
    t = _NON_ALNUM_RE.sub(" ", t)
    t = _WHITESPACE_RE.sub(" ", t).strip()
    return t


def _heading_raw_uid(heading: HeadingCandidate) -> str:
    """Возвращает raw_uid heading-а в нормализованной форме."""
    return normalize_spaces(str(getattr(heading, "raw_uid", None) or heading.uid or ""))


def _heading_title(heading: HeadingCandidate) -> str:
    """Возвращает title heading-а в нормализованной форме."""
    return normalize_spaces(str(getattr(heading, "title", "") or ""))


def _build_heading_key(heading: HeadingCandidate) -> str:
    """
    Строит канонический matching key для body heading.

    Использует:
    - raw_uid;
    - title;
    - общую matcher-level нормализацию.
    """
    uid = _heading_raw_uid(heading)
    title = _heading_title(heading)
    combined = f"{uid} {title}".strip()
    return normalize_match_text(combined)


def _build_entry_key(entry: ParsedTOCEntry) -> str:
    """
    Строит канонический matching key для TOC entry.

    Использует:
    - uid, если он извлечён parser-ом;
    - normalized_title;
    - общую matcher-level нормализацию.
    """
    combined = f"{entry.uid or ''} {entry.normalized_title}".strip()
    return normalize_match_text(combined)


def _exact_match(entry: ParsedTOCEntry, headings: list[HeadingCandidate]) -> TOCMatch | None:
    """
    Пытается найти exact match для TOC entry.

    Exact match проверяется:
    1. по полному key (uid + title);
    2. по uid + normalized title.

    Возвращает TOCMatch или None.
    """
    entry_key = _build_entry_key(entry)
    if not entry_key:
        return None

    for heading in headings:
        if _build_heading_key(heading) == entry_key:
            return TOCMatch(
                match_type="exact",
                matched_heading_uid=_heading_raw_uid(heading) or None,
                matched_heading_title=_heading_title(heading) or None,
                matched_heading_page=getattr(heading, "page", None),
                match_score=100.0,
            )

    if entry.uid:
        uid = normalize_spaces(entry.uid)
        title = normalize_match_text(entry.normalized_title)
        for heading in headings:
            if (
                _heading_raw_uid(heading) == uid
                and normalize_match_text(_heading_title(heading)) == title
            ):
                return TOCMatch(
                    match_type="exact",
                    matched_heading_uid=_heading_raw_uid(heading) or None,
                    matched_heading_title=_heading_title(heading) or None,
                    matched_heading_page=getattr(heading, "page", None),
                    match_score=100.0,
                )

    return None


def _fuzzy_match(
    entry: ParsedTOCEntry,
    headings: list[HeadingCandidate],
    *,
    strong_threshold: float = DEFAULT_FUZZY_THRESHOLD,
    weak_threshold: float = WEAK_FUZZY_THRESHOLD,
) -> TOCMatch | None:
    """
    Пытается найти fuzzy match для TOC entry с OCR tolerance.

    Использует RapidFuzz WRatio:
    - strong_threshold задаёт уверенный fuzzy match;
    - weak_threshold задаёт минимальный порог допуска.

    Возвращает:
    - TOCMatch при успешном fuzzy match;
    - None, если match не найден или RapidFuzz недоступен.
    """
    if fuzz is None or process is None:
        return None

    query = _build_entry_key(entry)
    if not query:
        return None

    choices: list[str] = []
    index_map: dict[str, HeadingCandidate] = {}

    for heading in headings:
        key = _build_heading_key(heading)
        if not key:
            continue
        choices.append(key)
        index_map[key] = heading

    if not choices:
        return None

    best = process.extractOne(
        query,
        choices,
        scorer=fuzz.WRatio,
        score_cutoff=weak_threshold,
    )
    if not best:
        return None

    matched_key, score, _ = best
    heading = index_map[matched_key]

    match_type = "fuzzy"
    if score < strong_threshold:
        match_type = "fuzzy"

    return TOCMatch(
        match_type=match_type,
        matched_heading_uid=_heading_raw_uid(heading) or None,
        matched_heading_title=_heading_title(heading) or None,
        matched_heading_page=getattr(heading, "page", None),
        match_score=float(score),
    )


def attach_toc_matches(
    parsed_toc: ParsedTOC,
    headings: list[HeadingCandidate],
    *,
    strong_threshold: float = DEFAULT_FUZZY_THRESHOLD,
    weak_threshold: float = WEAK_FUZZY_THRESHOLD,
) -> ParsedTOC:
    """
    Обогащает ParsedTOC результатами matching с body headings.

    Поведение:
    - сначала exact matching;
    - затем fuzzy matching;
    - если match не найден, entry помечается как no_match;
    - stale entries помечаются через toc_missing_in_body=True.

    Важно:
    - функция модифицирует entries внутри ParsedTOC in-place;
    - возвращает тот же ParsedTOC для удобства chaining.
    """
    if not parsed_toc.detected or not parsed_toc.entries:
        return parsed_toc

    for entry in parsed_toc.entries:
        exact = _exact_match(entry, headings)
        if exact is not None:
            entry.match_status = "matched"
            entry.match_type = exact.match_type
            entry.matched_heading_uid = exact.matched_heading_uid
            entry.matched_heading_title = exact.matched_heading_title
            entry.matched_heading_page = exact.matched_heading_page
            entry.match_score = exact.match_score
            entry.toc_missing_in_body = False
            continue

        fuzzy = _fuzzy_match(
            entry,
            headings,
            strong_threshold=strong_threshold,
            weak_threshold=weak_threshold,
        )
        if fuzzy is not None:
            entry.match_status = "matched"
            entry.match_type = fuzzy.match_type
            entry.matched_heading_uid = fuzzy.matched_heading_uid
            entry.matched_heading_title = fuzzy.matched_heading_title
            entry.matched_heading_page = fuzzy.matched_heading_page
            entry.match_score = fuzzy.match_score
            entry.toc_missing_in_body = False
            continue

        entry.match_status = "unmatched"
        entry.match_type = "no_match"
        entry.match_score = None
        entry.toc_missing_in_body = True

    logger.info(
        "STRUCTURE toc_matches_attached",
        extra={
            "entries_total": len(parsed_toc.entries),
            "exact_matches": sum(1 for e in parsed_toc.entries if e.match_type == "exact"),
            "fuzzy_matches": sum(1 for e in parsed_toc.entries if e.match_type == "fuzzy"),
            "no_matches": sum(1 for e in parsed_toc.entries if e.match_type == "no_match"),
        },
    )

    return parsed_toc


def build_toc_match_index(parsed_toc: ParsedTOC) -> dict[tuple[str, str], dict[str, Any]]:
    """
    Строит lookup index для TOC-aware heading scoring.

    Ключ:
    - normalized uid
    - normalized title

    Значение:
    - match_type
    - match_score
    - matched heading fields
    - page_hint
    - toc_missing_in_body

    Индекс предназначен для быстрого доступа из heading_builder / scorer.
    """
    index: dict[tuple[str, str], dict[str, Any]] = {}

    for entry in parsed_toc.entries:
        if not entry.uid and not entry.normalized_title:
            continue

        key = (
            normalize_spaces(entry.uid or ""),
            normalize_match_text(entry.normalized_title),
        )
        index[key] = {
            "match_type": entry.match_type,
            "match_score": entry.match_score,
            "matched_heading_uid": entry.matched_heading_uid,
            "matched_heading_title": entry.matched_heading_title,
            "matched_heading_page": entry.matched_heading_page,
            "page_hint": entry.page_hint,
            "toc_missing_in_body": entry.toc_missing_in_body,
        }

    return index
