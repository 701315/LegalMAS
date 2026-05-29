# src/services/structure/toc_matcher.py

"""
TOC-to-heading matching слой для Sprint 2 structural pipeline.

Роль модуля:
- матчить ParsedTOC entries с body headings;
- поддерживать exact matching после нормализации;
- поддерживать fuzzy matching с OCR tolerance;
- проставлять match_type: exact / fuzzy / no_match;
- готовить TOC match index для heading scoring и diagnostics.

Главный принцип:
matcher не решает, насколько TOC надёжен в целом.
Он только сообщает, какие TOC entries нашли подтверждение в body headings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from core.logging import get_logger
from services.structure.heading_patterns import normalize_spaces
from services.structure.hierarchy_builder import HeadingCandidate
from services.structure.toc_match_utils import normalize_toc_match_title
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
PAGE_NEAR_THRESHOLD = 2
PAGE_WEAK_THRESHOLD = 1


@dataclass(slots=True)
class TOCMatch:
    """
    Результат сопоставления одной TOC entry с body heading.
    """

    match_type: str
    matched_heading_uid: str | None
    matched_heading_title: str | None
    matched_heading_page: int | None
    match_score: float | None
    strategy: str = "unknown"


@lru_cache(maxsize=4096)
def normalize_match_text(text: str) -> str:
    """
    Нормализует строку для exact/fuzzy matching.

    Используется для matcher-level string similarity.
    Для deterministic TOC index lookup используется
    toc_match_utils.normalize_toc_match_title().
    """
    t = normalize_spaces(text or "").casefold()
    t = _NON_ALNUM_RE.sub(" ", t)
    t = _WHITESPACE_RE.sub(" ", t).strip()
    return t


def _safe_page(value: Any) -> int | None:
    try:
        page = int(value)
    except Exception:
        return None
    return page if page >= 1 else None


def _heading_raw_uid(heading: HeadingCandidate) -> str:
    return normalize_spaces(str(getattr(heading, "raw_uid", None) or heading.uid or ""))


def _heading_title(heading: HeadingCandidate) -> str:
    return normalize_spaces(str(getattr(heading, "title", "") or ""))


def _heading_page(heading: HeadingCandidate) -> int | None:
    return _safe_page(getattr(heading, "page", None))


def _entry_weak_flag(entry: Any) -> bool:
    diagnostics = getattr(entry, "diagnostics", None) or {}
    return bool(
        diagnostics.get("weak_entry_no_page_hint")
        or diagnostics.get("weak_start_line")
    )


def _page_distance(entry: Any, heading: HeadingCandidate) -> int:
    entry_page = _entry_page_hint(entry)
    heading_page = _heading_page(heading)
    if entry_page is None or heading_page is None:
        return 9999
    return abs(entry_page - heading_page)


def _is_page_near(entry: Any, heading: HeadingCandidate, *, weak: bool = False) -> bool:
    distance = _page_distance(entry, heading)
    threshold = PAGE_WEAK_THRESHOLD if weak else PAGE_NEAR_THRESHOLD
    return distance <= threshold


def _is_root_numeric_uid(uid: str) -> bool:
    return bool(re.fullmatch(r"\d+", normalize_spaces(uid)))


def _is_numeric_uid(uid: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.\d+)*", normalize_spaces(uid)))


def _is_appendix_uid(uid: str) -> bool:
    u = normalize_spaces(uid).lower()
    return u.startswith("appendix-") or u.startswith("приложение-")


def _build_heading_key(heading: HeadingCandidate) -> str:
    uid = _heading_raw_uid(heading)
    title = _heading_title(heading)
    combined = f"{uid} {title}".strip()
    return normalize_match_text(combined)


def _entry_uid(entry: Any) -> str:
    return normalize_spaces(str(getattr(entry, "uid", None) or ""))


def _entry_title_for_lookup(entry: Any) -> str:
    """
    Возвращает title entry для deterministic lookup index.

    Приоритет:
    1. normalized_title, если parser уже подготовил canonical title;
    2. title;
    3. raw_text.
    """
    normalized_title = getattr(entry, "normalized_title", None)
    if normalized_title:
        return normalize_toc_match_title(str(normalized_title))

    title = getattr(entry, "title", None)
    if title:
        return normalize_toc_match_title(str(title))

    raw_text = getattr(entry, "raw_text", None)
    if raw_text:
        return normalize_toc_match_title(str(raw_text))

    return ""


def _entry_title_for_matching(entry: Any) -> str:
    """
    Возвращает title entry для exact/fuzzy matching.

    Приоритет такой же, но с matcher-level normalization.
    """
    normalized_title = getattr(entry, "normalized_title", None)
    if normalized_title:
        return normalize_match_text(str(normalized_title))

    title = getattr(entry, "title", None)
    if title:
        return normalize_match_text(str(title))

    raw_text = getattr(entry, "raw_text", None)
    if raw_text:
        return normalize_match_text(str(raw_text))

    return ""


def _build_entry_key(entry: Any) -> str:
    combined = f"{_entry_uid(entry)} {_entry_title_for_matching(entry)}".strip()
    return normalize_match_text(combined)


def _entry_page_hint(entry: Any) -> int | None:
    return _safe_page(getattr(entry, "page_hint", None))


def _candidate_sort_key_for_entry(entry: Any, heading: HeadingCandidate) -> tuple[int, int, int]:
    """
    Чем меньше ключ, тем лучше кандидат.

    Порядок:
    1. page proximity к page_hint TOC entry;
    2. preference for exact uid family;
    3. shorter normalized title distance proxy (через длину title).
    """
    entry_uid = _entry_uid(entry)
    heading_uid = _heading_raw_uid(heading)
    entry_page = _entry_page_hint(entry)
    heading_page = _heading_page(heading)

    if entry_page is not None and heading_page is not None:
        page_distance = abs(entry_page - heading_page)
    else:
        page_distance = 9999

    uid_penalty = 0
    if entry_uid and heading_uid and entry_uid != heading_uid:
        uid_penalty = 1

    title_len_penalty = abs(
        len(_entry_title_for_matching(entry)) - len(normalize_match_text(_heading_title(heading)))
    )
    return (page_distance, uid_penalty, title_len_penalty)


def _filter_headings_by_uid(entry: Any, headings: list[HeadingCandidate]) -> list[HeadingCandidate]:
    """
    Возвращает подмножество headings, релевантных по uid.

    Важно:
    - для appendix/root numeric uid стараемся быть строже;
    - для пустого uid не фильтруем.
    """
    entry_uid = _entry_uid(entry)
    if not entry_uid:
        return headings

    exact_uid = [h for h in headings if _heading_raw_uid(h) == entry_uid]
    if exact_uid:
        return sorted(exact_uid, key=lambda h: _candidate_sort_key_for_entry(entry, h))

    if _is_appendix_uid(entry_uid) or _is_root_numeric_uid(entry_uid):
        return []

    if _is_numeric_uid(entry_uid):
        same_family = [
            h for h in headings
            if _heading_raw_uid(h) and _heading_raw_uid(h).startswith(f"{entry_uid}.")
        ]
        if same_family:
            return sorted(same_family, key=lambda h: _candidate_sort_key_for_entry(entry, h))

    return headings


def _exact_match(entry: Any, headings: list[HeadingCandidate]) -> TOCMatch | None:
    filtered_headings = _filter_headings_by_uid(entry, headings)
    if not filtered_headings:
        return None

    entry_key = _build_entry_key(entry)
    if entry_key:
        exact_key_hits = [
            h for h in filtered_headings
            if _build_heading_key(h) == entry_key
        ]
        if exact_key_hits:
            heading = sorted(
                exact_key_hits,
                key=lambda h: _candidate_sort_key_for_entry(entry, h),
            )[0]
            return TOCMatch(
                match_type="exact",
                matched_heading_uid=_heading_raw_uid(heading) or None,
                matched_heading_title=_heading_title(heading) or None,
                matched_heading_page=_heading_page(heading),
                match_score=100.0,
                strategy="entry_key_exact",
            )

    entry_uid = _entry_uid(entry)
    entry_title = _entry_title_for_matching(entry)

    if entry_uid and entry_title:
        uid_title_hits = [
            h for h in filtered_headings
            if _heading_raw_uid(h) == entry_uid
            and normalize_match_text(_heading_title(h)) == entry_title
        ]
        if uid_title_hits:
            heading = sorted(
                uid_title_hits,
                key=lambda h: _candidate_sort_key_for_entry(entry, h),
            )[0]
            return TOCMatch(
                match_type="exact",
                matched_heading_uid=_heading_raw_uid(heading) or None,
                matched_heading_title=_heading_title(heading) or None,
                matched_heading_page=_heading_page(heading),
                match_score=100.0,
                strategy="uid_title_exact",
            )

    if entry_uid and (_is_root_numeric_uid(entry_uid) or _is_appendix_uid(entry_uid)):
        uid_only_hits = [h for h in filtered_headings if _heading_raw_uid(h) == entry_uid]
        if uid_only_hits:
            heading = sorted(
                uid_only_hits,
                key=lambda h: _candidate_sort_key_for_entry(entry, h),
            )[0]
            return TOCMatch(
                match_type="exact",
                matched_heading_uid=_heading_raw_uid(heading) or None,
                matched_heading_title=_heading_title(heading) or None,
                matched_heading_page=_heading_page(heading),
                match_score=99.0,
                strategy="uid_only_structural_anchor",
            )

    return None


def _uid_exact_title_close_match(entry: Any, headings: list[HeadingCandidate]) -> TOCMatch | None:
    if fuzz is None:
        return None

    entry_uid = _entry_uid(entry)
    entry_title = _entry_title_for_matching(entry)
    if not entry_uid or not entry_title:
        return None

    exact_uid_headings = [h for h in headings if _heading_raw_uid(h) == entry_uid]
    if not exact_uid_headings:
        return None

    weak = _entry_weak_flag(entry)
    threshold = DEFAULT_FUZZY_THRESHOLD if not weak else max(DEFAULT_FUZZY_THRESHOLD, 90.0)

    scored: list[tuple[float, HeadingCandidate]] = []
    for heading in exact_uid_headings:
        heading_title = normalize_match_text(_heading_title(heading))
        if not heading_title:
            continue
        score = float(fuzz.WRatio(entry_title, heading_title))
        if score >= threshold:
            scored.append((score, heading))

    if not scored:
        return None

    scored.sort(
        key=lambda item: (
            -item[0],
            *_candidate_sort_key_for_entry(entry, item[1]),
        )
    )
    score, heading = scored[0]
    return TOCMatch(
        match_type="fuzzy",
        matched_heading_uid=_heading_raw_uid(heading) or None,
        matched_heading_title=_heading_title(heading) or None,
        matched_heading_page=_heading_page(heading),
        match_score=float(score),
        strategy="uid_exact_title_close",
    )


def _title_exact_page_near_match(entry: Any, headings: list[HeadingCandidate]) -> TOCMatch | None:
    entry_uid = _entry_uid(entry)
    entry_title = _entry_title_for_matching(entry)
    if entry_uid or not entry_title:
        return None

    weak = _entry_weak_flag(entry)
    exact_title_hits = [
        h for h in headings
        if normalize_match_text(_heading_title(h)) == entry_title
    ]
    if not exact_title_hits:
        return None

    near_hits = [
        h for h in exact_title_hits
        if _is_page_near(entry, h, weak=weak)
    ]
    candidate_hits = near_hits or exact_title_hits

    heading = sorted(
        candidate_hits,
        key=lambda h: _candidate_sort_key_for_entry(entry, h),
    )[0]

    score = 98.0 if _is_page_near(entry, heading, weak=weak) else 95.0
    return TOCMatch(
        match_type="exact",
        matched_heading_uid=_heading_raw_uid(heading) or None,
        matched_heading_title=_heading_title(heading) or None,
        matched_heading_page=_heading_page(heading),
        match_score=score,
        strategy="title_exact_page_near" if _is_page_near(entry, heading, weak=weak) else "title_exact",
    )


def _fuzzy_match(
    entry: Any,
    headings: list[HeadingCandidate],
    *,
    strong_threshold: float = DEFAULT_FUZZY_THRESHOLD,
    weak_threshold: float = WEAK_FUZZY_THRESHOLD,
) -> TOCMatch | None:
    if fuzz is None or process is None:
        return None

    filtered_headings = _filter_headings_by_uid(entry, headings)
    if not filtered_headings:
        return None

    query = _build_entry_key(entry)
    if not query:
        return None

    weak_entry = _entry_weak_flag(entry)
    local_weak_threshold = max(weak_threshold, 86.0) if weak_entry else weak_threshold
    local_strong_threshold = max(strong_threshold, 90.0) if weak_entry else strong_threshold

    choices: list[tuple[str, HeadingCandidate]] = []
    for heading in filtered_headings:
        key = _build_heading_key(heading)
        if not key:
            continue
        choices.append((key, heading))

    if not choices:
        return None

    raw_choice_keys = [key for key, _ in choices]

    best = process.extract(
        query,
        raw_choice_keys,
        scorer=fuzz.WRatio,
        score_cutoff=local_weak_threshold,
        limit=5,
    )
    if not best:
        return None

    scored_candidates: list[tuple[float, HeadingCandidate]] = []
    for matched_key, score, _ in best:
        same_key_candidates = [heading for key, heading in choices if key == matched_key]
        for heading in same_key_candidates:
            scored_candidates.append((float(score), heading))

    if not scored_candidates:
        return None

    entry_uid = _entry_uid(entry)
    if entry_uid and (_is_root_numeric_uid(entry_uid) or _is_appendix_uid(entry_uid)):
        scored_candidates = [
            (score, heading)
            for score, heading in scored_candidates
            if _heading_raw_uid(heading) == entry_uid
        ]
        if not scored_candidates:
            return None

    if _entry_page_hint(entry) is not None:
        page_near_candidates = [
            (score, heading)
            for score, heading in scored_candidates
            if _is_page_near(entry, heading, weak=weak_entry)
        ]
        if page_near_candidates:
            scored_candidates = page_near_candidates

    scored_candidates.sort(
        key=lambda item: (
            -item[0],
            *_candidate_sort_key_for_entry(entry, item[1]),
        )
    )

    score, heading = scored_candidates[0]
    if score < local_strong_threshold and weak_entry and not _is_page_near(entry, heading, weak=True):
        return None

    return TOCMatch(
        match_type="fuzzy",
        matched_heading_uid=_heading_raw_uid(heading) or None,
        matched_heading_title=_heading_title(heading) or None,
        matched_heading_page=_heading_page(heading),
        match_score=float(score),
        strategy="fuzzy_page_aware" if _entry_page_hint(entry) is not None else "fuzzy_generic",
    )


def _coerce_parsed_toc(
    parsed_toc: ParsedTOC | list[ParsedTOCEntry] | list[Any],
) -> tuple[ParsedTOC, bool]:
    if isinstance(parsed_toc, ParsedTOC):
        return parsed_toc, False

    coerced = ParsedTOC(
        detected=bool(parsed_toc),
        entries=list(parsed_toc),
        start_index=None,
        end_index=0,
        reason="legacy_list_input",
        parser_diagnostics={},
    )
    return coerced, True


def attach_toc_matches(
    parsed_toc: ParsedTOC | list[ParsedTOCEntry] | list[Any],
    headings: list[HeadingCandidate],
    *,
    strong_threshold: float = DEFAULT_FUZZY_THRESHOLD,
    weak_threshold: float = WEAK_FUZZY_THRESHOLD,
) -> ParsedTOC | list[Any]:
    """
    Обогащает ParsedTOC результатами matching с body headings.

    Если на вход подан legacy list entries, возвращает тот же list,
    предварительно обогатив его полями matching-а.
    """
    parsed_toc_obj, legacy_list_mode = _coerce_parsed_toc(parsed_toc)

    if not parsed_toc_obj.detected or not parsed_toc_obj.entries:
        return parsed_toc_obj.entries if legacy_list_mode else parsed_toc_obj

    for entry in parsed_toc_obj.entries:
        diagnostics = getattr(entry, "diagnostics", None)
        if diagnostics is None:
            diagnostics = {}
            entry.diagnostics = diagnostics

        exact = _exact_match(entry, headings)
        if exact is not None:
            entry.match_status = "matched"
            entry.match_type = exact.match_type
            entry.matched_heading_uid = exact.matched_heading_uid
            entry.matched_heading_title = exact.matched_heading_title
            entry.matched_heading_page = exact.matched_heading_page
            entry.match_score = exact.match_score
            entry.toc_missing_in_body = False
            entry.diagnostics["toc_match_strategy"] = exact.strategy
            continue

        uid_close = _uid_exact_title_close_match(entry, headings)
        if uid_close is not None:
            entry.match_status = "matched"
            entry.match_type = uid_close.match_type
            entry.matched_heading_uid = uid_close.matched_heading_uid
            entry.matched_heading_title = uid_close.matched_heading_title
            entry.matched_heading_page = uid_close.matched_heading_page
            entry.match_score = uid_close.match_score
            entry.toc_missing_in_body = False
            entry.diagnostics["toc_match_strategy"] = uid_close.strategy
            continue

        title_near = _title_exact_page_near_match(entry, headings)
        if title_near is not None:
            entry.match_status = "matched"
            entry.match_type = title_near.match_type
            entry.matched_heading_uid = title_near.matched_heading_uid
            entry.matched_heading_title = title_near.matched_heading_title
            entry.matched_heading_page = title_near.matched_heading_page
            entry.match_score = title_near.match_score
            entry.toc_missing_in_body = False
            entry.diagnostics["toc_match_strategy"] = title_near.strategy
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
            entry.diagnostics["toc_match_strategy"] = fuzzy.strategy
            continue

        entry.match_status = "unmatched"
        entry.match_type = "no_match"
        entry.matched_heading_uid = None
        entry.matched_heading_title = None
        entry.matched_heading_page = None
        entry.match_score = None
        entry.toc_missing_in_body = True
        entry.diagnostics["toc_match_strategy"] = "no_match"

    logger.info(
        "STRUCTURE toc_matches_attached",
        extra={
            "entries_total": len(parsed_toc_obj.entries),
            "exact_matches": sum(1 for e in parsed_toc_obj.entries if e.match_type == "exact"),
            "fuzzy_matches": sum(1 for e in parsed_toc_obj.entries if e.match_type == "fuzzy"),
            "no_matches": sum(1 for e in parsed_toc_obj.entries if e.match_type == "no_match"),
            "appendix_entries": sum(
                1 for e in parsed_toc_obj.entries if _is_appendix_uid(_entry_uid(e))
            ),
            "root_numeric_entries": sum(
                1 for e in parsed_toc_obj.entries if _is_root_numeric_uid(_entry_uid(e))
            ),
            "weak_entries": sum(1 for e in parsed_toc_obj.entries if _entry_weak_flag(e)),
            "uid_exact_title_close_matches": sum(
                1
                for e in parsed_toc_obj.entries
                if (getattr(e, "diagnostics", {}) or {}).get("toc_match_strategy") == "uid_exact_title_close"
            ),
            "title_exact_page_near_matches": sum(
                1
                for e in parsed_toc_obj.entries
                if (getattr(e, "diagnostics", {}) or {}).get("toc_match_strategy") in {"title_exact_page_near", "title_exact"}
            ),
        },
    )

    return parsed_toc_obj.entries if legacy_list_mode else parsed_toc_obj


def build_toc_match_index(parsed_toc: ParsedTOC) -> dict[tuple[str, str], dict[str, Any]]:
    """
    Строит lookup index для TOC-aware heading scoring.

    Ключ должен быть полностью согласован с toc_match_utils.toc_match_payload():
    - normalized raw_uid
    - normalize_toc_match_title(title)

    Если несколько TOC entries дают один и тот же key, выбирается наиболее
    сильная запись:
    1. exact > fuzzy > no_match
    2. higher match_score
    3. наличие page_hint
    """
    index: dict[tuple[str, str], dict[str, Any]] = {}

    def rank(payload: dict[str, Any]) -> tuple[int, float, int]:
        match_type = str(payload.get("match_type") or "no_match")
        match_score = float(payload.get("match_score") or 0.0)
        has_page_hint = 1 if payload.get("page_hint") is not None else 0

        type_rank = {
            "exact": 3,
            "fuzzy": 2,
            "no_match": 1,
        }.get(match_type, 0)

        return (type_rank, match_score, has_page_hint)

    for entry in parsed_toc.entries:
        entry_uid = _entry_uid(entry)
        entry_title = _entry_title_for_lookup(entry)

        if not entry_uid and not entry_title:
            continue

        key = (entry_uid, entry_title)
        diagnostics = getattr(entry, "diagnostics", None) or {}
        payload = {
            "match_type": getattr(entry, "match_type", "no_match"),
            "match_score": getattr(entry, "match_score", None),
            "matched_heading_uid": getattr(entry, "matched_heading_uid", None),
            "matched_heading_title": getattr(entry, "matched_heading_title", None),
            "matched_heading_page": getattr(entry, "matched_heading_page", None),
            "page_hint": getattr(entry, "page_hint", None),
            "toc_missing_in_body": getattr(entry, "toc_missing_in_body", False),
            "toc_match_strategy": diagnostics.get("toc_match_strategy"),
            "weak_entry_no_page_hint": diagnostics.get("weak_entry_no_page_hint", False),
            "weak_start_line": diagnostics.get("weak_start_line", False),
        }

        existing = index.get(key)
        if existing is None or rank(payload) > rank(existing):
            index[key] = payload

    return index


