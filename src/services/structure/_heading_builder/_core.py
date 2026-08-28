# src/services/structure/_heading_builder/_core.py

"""Основной оркестратор сборки HeadingCandidate и StructureEvidenceBundle."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any
from ._bilingual import annotate_bilingual_heading_pairs
from core.config import settings
from core.logging import get_logger
from services.structure.heading_llm_refiner import (
    ScoredHeadingCandidate,
    refine_ambiguous_candidates,
)
from services.structure.heading_patterns import normalize_spaces, parse_raw_heading
from services.structure.heading_scoring import score_heading_candidate
from services.structure.hierarchy_builder import HeadingCandidate
from services.structure.toc_match_utils import toc_match_payload
from services.structure._heading_scoring._types import (
    AppendixMarker,
    CrossRefAnchor,
    CrossRefKind,
    GlobalStructureSignals,
    HeadingCandidate as EvidenceHeadingCandidate,
    HeadingScheme,
    NumberingSequence,
    PageStructureSignals,
    ScopeType,
    StructureEvidenceBundle,
)

from ._constants import _MAX_HEADING_RAW_TEXT_LEN
from ._logic import (
    _element_scope,
    _is_candidate_element_type_allowed,
    _is_recoverable_toc_like_element_type,
    _is_strong_structural_element_type,
    _is_weak_structural_element_type,
    _require_element_structure_contract,
)
from ._ranking import _select_best_candidates_by_uid
from ._utils import (
    _is_strict_numeric_uid,
    _looks_like_appendix_uid,
    _looks_like_root_numeric_uid,
    _normalize_reject_reason,
    _normalize_scope,
    _patched_scored_candidate,
    _safe_int,
    _scope_aware_effective_uid,
    _status_to_decision,
    _uid_depth,
)
import numpy as np
import numpy as np

logger = get_logger(__name__)

_APPENDIX_NUMBER_RE = re.compile(
    r"""
    (?:
        appendix|appendices|annex|annexure|schedule|exhibit|attachment|приложени[еяй]
    )
    \s*
    (?:
        №|n\.?|no\.?|number
    )?
    \s*
    (?P<num>[A-ZА-ЯЁ]|\d{1,3}|[IVXLCM]{1,12})
    """,
    re.IGNORECASE | re.VERBOSE,
)

_CROSSREF_ITEM_RE = re.compile(
    r"\b(?:item|clause|section|article|paragraph|п\.|ст\.|разд\.)\s*(\d+(?:\.\d+)*)\b",
    re.IGNORECASE,
)

_CROSSREF_APPENDIX_RE = re.compile(
    r"""
    \b
    (?:
        appendix|annex|annexure|schedule|exhibit|attachment|приложени[еяй]
    )
    \s*
    (?:
        №|n\.?|no\.?|number
    )?
    \s*
    ([A-ZА-ЯЁ]|\d{1,3}|[IVXLCM]{1,12})
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)


# ============================================================================
# Phase 2 canonical result type
# ============================================================================

@dataclass(slots=True)
class Phase2Result:
    """
    Результат единственного прохода Phase 2.

    Создаётся один раз через run_phase2(...).
    Содержит оба выхода — accepted headings и evidence bundle —
    как проекции одного и того же набора scored candidates.

    Поля:
    - evidence_bundle: StructureEvidenceBundle для downstream phases.
    - accepted_headings: список HeadingCandidate для иерархии.
    - scored_candidates: полный список ScoredHeadingCandidate (для diagnostics).
    - llm_refiner_applied: был ли применён LLM-refiner в этом проходе.
    """
    evidence_bundle: StructureEvidenceBundle
    accepted_headings: list[HeadingCandidate]
    scored_candidates: list[ScoredHeadingCandidate]
    llm_refiner_applied: bool = False


# ============================================================================
# Вспомогательные функции (без изменений)
# ============================================================================

def _compute_document_heading_depth(elements: list[dict[str, Any]]) -> int:
    """
    Вычислить адаптивную максимальную глубину нумерации документа.

    Алгоритм:
    1. Собираем глубины всех маркеров с recovery_confidence >= 0.7
       (подтверждённые Spatial Recovery маркеры, не шум).
    2. Если таких нет — fallback на все маркеры.
    3. Возвращаем МАКСИМУМ (не перцентиль), потому что даже один
       подтверждённый маркер глубины N означает N-уровневую иерархию.
    4. Минимальное значение — 2 (безопасный дефолт).

    Универсален: не зависит от языка, формата, типа документа,
    количества уровней вложенности.
    """
    confirmed_depths: list[int] = []
    all_depths: list[int] = []

    for el in elements:
        marker = el.get("marker") or ""
        if not marker:
            continue
        depth = _uid_depth(marker)
        if depth <= 0:
            continue
        all_depths.append(depth)
        meta = el.get("metadata") or {}
        if (
            meta.get("marker_source") == "spatial_recovery"
            and float(meta.get("recovery_confidence") or 0.0) >= 0.7
        ):
            confirmed_depths.append(depth)

    source = confirmed_depths if confirmed_depths else all_depths
    if not source:
        return 2

    return max(2, max(source))


def _has_strong_toc_confirmation(match_type: str | None, match_score: float | None) -> bool:
    """Strong TOC confirmation: exact match или сильный fuzzy match.

    Phase 13.5:
    match_score здесь — это toc bonus из scorer, а не raw fuzzy score.
    Поэтому порог 0.03 согласован с _heading_scoring._logic._toc_match_bonus().
    """
    if match_type == "exact":
        return True
    if match_type == "fuzzy" and (match_score or 0.0) >= 0.03:
        return True
    return False


def _heading_scheme_from_uid(uid: str, *, is_appendix: bool = False) -> HeadingScheme:
    u = normalize_spaces(uid)
    if not u:
        return HeadingScheme.UNKNOWN
    if is_appendix:
        return HeadingScheme.APPENDIX
    if _is_strict_numeric_uid(u):
        return HeadingScheme.DECIMAL
    if re.fullmatch(r"[IVXLCM]+", u.upper()):
        return HeadingScheme.ROMAN
    if len(u) == 1 and u.isalpha():
        return HeadingScheme.ALPHABETIC
    return HeadingScheme.UNKNOWN


def _scope_type_from_scope(scope: str | None, *, is_appendix: bool = False) -> ScopeType:
    s = normalize_spaces(scope or "").lower()
    if is_appendix or "appendix" in s:
        return ScopeType.APPENDIX
    if s == "toc":
        return ScopeType.TOC
    if s == "signatures":
        return ScopeType.SIGNATURES
    if s in {"main", "contract", "agreement", ""}:
        return ScopeType.MAIN
    return ScopeType.UNKNOWN


def _appendix_number_from_text(text: str) -> str | None:
    t = normalize_spaces(text)
    if not t:
        return None
    m = _APPENDIX_NUMBER_RE.search(t)
    if not m:
        return None
    return normalize_spaces(m.group("num")) or None


def _build_numbering_sequences(
    candidates: list[EvidenceHeadingCandidate],
) -> list[NumberingSequence]:
    by_bucket: dict[tuple[ScopeType, HeadingScheme], list[EvidenceHeadingCandidate]] = defaultdict(list)

    for cand in candidates:
        if not cand.numbering:
            continue
        if cand.is_toc_entry:
            continue
        by_bucket[(cand.scope_type, cand.scheme)].append(cand)

    sequences: list[NumberingSequence] = []
    for (scope_type, scheme), items in by_bucket.items():
        items.sort(key=lambda c: ((c.page_number or 0), c.element_id))
        values = [str(c.numbering) for c in items if c.numbering]
        normalized_values = [normalize_spaces(v) for v in values]
        element_ids = [c.element_id for c in items]

        duplicates = sorted(v for v, cnt in Counter(normalized_values).items() if cnt > 1)
        gaps: list[str] = []
        continuity_ratio = 0.0
        is_contiguous = False

        if scheme == HeadingScheme.DECIMAL:
            top_level_nums: list[int] = []
            for value in normalized_values:
                if re.fullmatch(r"\d+", value):
                    top_level_nums.append(int(value))
            if top_level_nums:
                unique_sorted = sorted(set(top_level_nums))
                expected = list(range(unique_sorted[0], unique_sorted[-1] + 1))
                missing = [str(v) for v in expected if v not in unique_sorted]
                gaps = missing
                continuity_ratio = (
                    len(unique_sorted) / len(expected) if expected else 0.0
                )
                is_contiguous = len(missing) == 0

        elif scheme == HeadingScheme.APPENDIX:
            appendix_nums: list[int] = []
            for value in normalized_values:
                if re.fullmatch(r"\d+", value):
                    appendix_nums.append(int(value))
            if appendix_nums:
                unique_sorted = sorted(set(appendix_nums))
                expected = list(range(unique_sorted[0], unique_sorted[-1] + 1))
                missing = [str(v) for v in expected if v not in unique_sorted]
                gaps = missing
                continuity_ratio = (
                    len(unique_sorted) / len(expected) if expected else 0.0
                )
                is_contiguous = len(missing) == 0

        sequence = NumberingSequence(
            scope_type=scope_type,
            scheme=scheme,
            values=values,
            normalized_values=normalized_values,
            element_ids=element_ids,
            is_contiguous=is_contiguous,
            continuity_ratio=round(float(continuity_ratio), 4),
            start_value=normalized_values[0] if normalized_values else None,
            end_value=normalized_values[-1] if normalized_values else None,
            gaps=gaps,
            duplicates=duplicates,
        )
        sequences.append(sequence)

    return sequences


def _build_appendix_markers(
    candidates: list[EvidenceHeadingCandidate],
) -> list[AppendixMarker]:
    markers: list[AppendixMarker] = []
    for cand in candidates:
        raw = cand.text
        appendix_num = _appendix_number_from_text(raw)
        is_appendix = cand.scheme == HeadingScheme.APPENDIX or cand.scope_type == ScopeType.APPENDIX
        if not is_appendix and appendix_num is None:
            continue

        lowered = normalize_spaces(raw).lower()
        if "annexure" in lowered:
            kind = "annexure"
        elif "annex" in lowered:
            kind = "annex"
        elif "schedule" in lowered:
            kind = "schedule"
        elif "exhibit" in lowered:
            kind = "exhibit"
        elif "attachment" in lowered:
            kind = "attachment"
        elif "appendices" in lowered or "приложения" in lowered:
            kind = "appendices"
        elif "appendix" in lowered or "приложение" in lowered:
            kind = "appendix"
        else:
            kind = "unknown"

        markers.append(
            AppendixMarker(
                element_id=cand.element_id,
                raw_text=raw,
                normalized_text=cand.normalized_text,
                appendix_number=appendix_num or cand.numbering,
                scope_uid=f"appendix.{appendix_num}" if appendix_num else None,
                marker_kind=kind,
                page_number=cand.page_number,
                confidence=round(float(cand.score), 4),
            )
        )
    return markers


def _build_crossref_anchors(elements: list[dict[str, Any]]) -> list[CrossRefAnchor]:
    anchors: list[CrossRefAnchor] = []
    seen: set[tuple[str, str, str]] = set()

    for idx, element in enumerate(elements):
        text = normalize_spaces(str(element.get("text") or ""))
        if not text:
            continue
        element_id = str(element.get("element_id") or element.get("id") or f"el-{idx}")
        page_number = _safe_int(element.get("page"))
        scope_type = _scope_type_from_scope(_element_scope(element))

        for match in _CROSSREF_ITEM_RE.finditer(text):
            raw = normalize_spaces(match.group(0))
            number = normalize_spaces(match.group(1))
            key = (element_id, "item", number)
            if key in seen:
                continue
            seen.add(key)
            anchors.append(
                CrossRefAnchor(
                    element_id=element_id,
                    raw_text=raw,
                    normalized_text=raw.lower(),
                    ref_kind=CrossRefKind.ITEM,
                    target_number=number,
                    target_scope_hint=None,
                    source_scope_type=scope_type,
                    page_number=page_number,
                    confidence=0.7,
                )
            )

        for match in _CROSSREF_APPENDIX_RE.finditer(text):
            raw = normalize_spaces(match.group(0))
            number = normalize_spaces(match.group(1))
            key = (element_id, "appendix", number)
            if key in seen:
                continue
            seen.add(key)
            anchors.append(
                CrossRefAnchor(
                    element_id=element_id,
                    raw_text=raw,
                    normalized_text=raw.lower(),
                    ref_kind=CrossRefKind.APPENDIX,
                    target_number=number,
                    target_scope_hint=f"appendix.{number}",
                    source_scope_type=scope_type,
                    page_number=page_number,
                    confidence=0.75,
                )
            )

    return anchors


def _page_signals_from_candidates(
    candidates: list[EvidenceHeadingCandidate],
    appendix_markers: list[AppendixMarker],
    crossref_anchors: list[CrossRefAnchor],
    elements: list[dict[str, Any]] | None = None,
) -> list[PageStructureSignals]:
    by_page: dict[int, PageStructureSignals] = {}

    def get_page(page: int) -> PageStructureSignals:
        if page not in by_page:
            by_page[page] = PageStructureSignals(page_number=page)
        return by_page[page]

    for cand in candidates:
        if cand.page_number is None:
            continue
        page = get_page(cand.page_number)
        page.heading_candidate_ids.append(cand.element_id)
        if cand.is_toc_entry:
            page.toc_entry_ids.append(cand.element_id)
            page.has_toc_title = page.has_toc_title or (
                "table of contents" in cand.normalized_text.lower()
            )

    for marker in appendix_markers:
        if marker.page_number is None:
            continue
        page = get_page(marker.page_number)
        page.appendix_marker_ids.append(marker.element_id)
        page.has_appendix_marker = True

    for anchor in crossref_anchors:
        if anchor.page_number is None:
            continue
        page = get_page(anchor.page_number)
        page.crossref_anchor_ids.append(anchor.element_id)

    # Считаем per-page element counts из raw elements если доступны.
    # Это нужно для корректного вычисления heading density:
    # density = heading_candidates / total_non_artifact_elements_on_page.
    _NON_CONTENT_TYPES_FOR_DENSITY = frozenset({
        "page_artifact",
        "signature_block",
        "requisites_block",
    })
    page_element_counts: dict[int, int] = {}
    if elements:
        for el in elements:
            try:
                p = int(el.get("page") or 1)
            except Exception:
                p = 1
            et = str(el.get("element_type") or "").strip().lower()
            if et not in _NON_CONTENT_TYPES_FOR_DENSITY:
                page_element_counts[p] = page_element_counts.get(p, 0) + 1

    for page in by_page.values():
        heading_count = len(page.heading_candidate_ids)
        total_elements = max(1, page_element_counts.get(page.page_number, heading_count))
        page.page_top_heading_density = round(heading_count / total_elements, 4)
        page.numbering_density = round(heading_count / total_elements, 4)

    return [by_page[p] for p in sorted(by_page)]


# ── B2: Heading Density Guard ─────────────────────────────────────────────────

# Порог heading density: если больше половины non-artifact элементов страницы
# являются heading-кандидатами — страница подозрительно плотная.
_HEADING_DENSITY_GUARD_THRESHOLD: float = 0.50

# Минимальное количество heading-кандидатов на странице для активации guard.
# Защита от ложных срабатываний на очень коротких страницах (1-2 элемента).
_HEADING_DENSITY_GUARD_MIN_CANDIDATES: int = 4


def _replace_scored_candidate_status(
    candidate: "ScoredHeadingCandidate",
    *,
    new_status,
    extra_reason: str,
):
    """
    Safe replacement helper for scored heading candidates.

    Primary path:
    - if candidate is a dataclass instance, use dataclasses.replace()
      to preserve immutability semantics of the normal production path.

    Defensive fallback:
    - if candidate is not a dataclass (e.g. test doubles / mocks),
      shallow-copy it and update status/reasons.
    - if copying fails, mutate in-place as last resort.

    This keeps B2 heading-density guard robust without tying it
    to one concrete container implementation.
    """
    import copy
    import dataclasses

    new_reasons = list(getattr(candidate, "reasons", []) or [])
    if extra_reason not in new_reasons:
        new_reasons.append(extra_reason)

    if dataclasses.is_dataclass(candidate) and not isinstance(candidate, type):
        return dataclasses.replace(
            candidate,
            status=new_status,
            reasons=new_reasons,
        )

    try:
        cloned = copy.copy(candidate)
        setattr(cloned, "status", new_status)
        setattr(cloned, "reasons", new_reasons)
        return cloned
    except Exception:
        setattr(candidate, "status", new_status)
        setattr(candidate, "reasons", new_reasons)
        return candidate


def _apply_heading_density_guard(
    scored: list["ScoredHeadingCandidate"],
    elements: list[dict[str, Any]],
) -> list["ScoredHeadingCandidate"]:
    """
    B2: Heading Density Guard — post-scoring demotion pass.

    Проблема:
    TOC / catalog pages, которые не были распознаны как TOC,
    могут иметь аномально высокую плотность heading-like элементов.
    Если их не подавить, они превращаются в ложные разделы clause tree.

    Решение:
    После scoring, для страниц с высокой heading density
    И без TOC-подтверждения — демотировать ACCEPTED → AMBIGUOUS.

    Важно:
    - Guard НЕ применяется если страница имеет TOC-entries.
    - Guard НЕ применяется если density ниже порога.
    - Guard НЕ применяется если кандидатов < MIN_CANDIDATES.
    - Guard НЕ удаляет кандидатов — только понижает статус.
    - Guard deterministic: никакого LLM, никаких внешних зависимостей.

    Args:
        scored: список ScoredHeadingCandidate после основного scoring pass.
        elements: raw layout elements для вычисления per-page element counts.

    Returns:
        Тот же список, возможно с изменёнными статусами.
    """
    from services.structure.heading_scoring import CandidateStatus

    if not scored or not elements:
        return scored

    # ── 1. Считаем per-page element counts ───────────────────────────────────
    _NON_CONTENT = frozenset({"page_artifact", "signature_block", "requisites_block"})
    page_total_counts: dict[int, int] = {}
    for el in elements:
        try:
            p = int(el.get("page") or 1)
        except Exception:
            p = 1
        et = str(el.get("element_type") or "").strip().lower()
        if et not in _NON_CONTENT:
            page_total_counts[p] = page_total_counts.get(p, 0) + 1

    # ── 2. Считаем per-page heading candidate counts и TOC presence ──────────
    page_heading_counts: dict[int, int] = {}
    page_has_toc_entries: dict[int, bool] = {}

    for s in scored:
        try:
            p = int(getattr(s, "page", None) or 1)
        except Exception:
            p = 1
        page_heading_counts[p] = page_heading_counts.get(p, 0) + 1
        if getattr(s, "is_toc_entry", False):
            page_has_toc_entries[p] = True

    # ── 3. Определяем страницы, требующие demotion ───────────────────────────
    dense_pages: set[int] = set()
    for page, heading_count in page_heading_counts.items():
        if heading_count < _HEADING_DENSITY_GUARD_MIN_CANDIDATES:
            continue
        if page_has_toc_entries.get(page, False):
            # Страница уже помечена как TOC — не трогаем.
            continue
        total = max(1, page_total_counts.get(page, heading_count))
        density = heading_count / total
        if density > _HEADING_DENSITY_GUARD_THRESHOLD:
            dense_pages.add(page)

    if not dense_pages:
        return scored

    logger.info(
        "STRUCTURE heading_density_guard_activated",
        extra={
            "dense_pages": sorted(dense_pages),
            "total_scored": len(scored),
        },
    )

    # ── 4. Demotion pass: ACCEPTED → AMBIGUOUS на плотных страницах ──────────
    result: list[ScoredHeadingCandidate] = []
    demoted_count = 0

    for s in scored:
        try:
            p = int(getattr(s, "page", None) or 1)
        except Exception:
            p = 1

        if p in dense_pages and getattr(s, "status", None) == CandidateStatus.ACCEPTED:
            # Не демотируем элементы с подтверждённым spatial_recovery.
            # Это компенсирующий контроль для апстрим-бага Docling;
            # его результаты имеют приоритет над density heuristics.
            _meta = getattr(s, "metadata", None) or {}
            _ms = _meta.get("marker_source") or ""
            _rc = float(_meta.get("recovery_confidence") or 0.0)
            if _ms == "spatial_recovery" and _rc >= 0.7:
                result.append(s)
                continue

            s = _replace_scored_candidate_status(
                s,
                new_status=CandidateStatus.AMBIGUOUS,
                extra_reason="heading_density_guard",
            )
            demoted_count += 1

        result.append(s)

    if demoted_count:
        logger.info(
            "STRUCTURE heading_density_guard_demoted",
            extra={
                "demoted_count": demoted_count,
                "dense_pages": sorted(dense_pages),
            },
        )

    return result



def _global_signals_from_bundle(
    *,
    evidence_candidates: list[EvidenceHeadingCandidate],
    numbering_sequences: list[NumberingSequence],
    toc_detected: bool,
    crossref_anchors: list[CrossRefAnchor],
    elements: list[dict[str, Any]],
) -> GlobalStructureSignals:
    main_len = 0
    appendix_len = 0

    for seq in numbering_sequences:
        if seq.scope_type == ScopeType.MAIN and seq.scheme == HeadingScheme.DECIMAL:
            top_level = [v for v in seq.normalized_values if re.fullmatch(r"\d+", v)]
            main_len = max(main_len, len(top_level))
        if seq.scheme == HeadingScheme.APPENDIX:
            appendix_len = max(appendix_len, len(seq.normalized_values))

    extraction_quality_score = 1.0 if elements else 0.0

    return GlobalStructureSignals(
        toc_detected=toc_detected,
        toc_confidence=0.9 if toc_detected else 0.0,
        main_section_chain_length=main_len,
        appendix_chain_length=appendix_len,
        crossref_anchor_count=len(crossref_anchors),
        heading_candidates_count=len(evidence_candidates),
        extraction_quality_score=extraction_quality_score,
        document_quality_signals={
            "elements_count": len(elements),
            "has_candidates": bool(evidence_candidates),
        },
        notes=[],
    )


def _scored_to_evidence_candidate(
    scored: ScoredHeadingCandidate,
) -> EvidenceHeadingCandidate | None:
    meta = dict(scored.metadata or {})
    raw_uid = normalize_spaces(str(meta.get("raw_uid") or scored.uid or ""))
    if not raw_uid:
        return None

    normalized_title = normalize_spaces(str(meta.get("normalized_title") or scored.title or ""))
    raw_text = normalize_spaces(str(scored.raw_text or ""))
    is_appendix = bool(meta.get("is_appendix_uid"))
    scope_type = _scope_type_from_scope(scored.scope, is_appendix=is_appendix)
    numbering = _appendix_number_from_text(raw_text) if is_appendix else raw_uid
    scheme = _heading_scheme_from_uid(raw_uid, is_appendix=is_appendix)

    features: dict[str, float | bool | str | int | None] = {
        "decision": str(scored.decision),
        "reason": str(scored.reason),
        "uid_depth": _safe_int(meta.get("uid_depth")),
        "toc_match_type": meta.get("toc_match_type"),
        "toc_match_score": float(meta.get("toc_match_score") or 0.0),
        "strong_toc_confirmation": bool(meta.get("strong_toc_confirmation")),
        "continuity_bonus": float(meta.get("continuity_bonus") or 0.0),
        "semantic_element_type": meta.get("semantic_element_type"),
        "element_type": meta.get("element_type"),
        "possible_toc": bool(meta.get("possible_toc")),
    }

    return EvidenceHeadingCandidate(
        element_id=str(meta.get("element_id") or f"elem_{scored.elem_i}"),
        text=raw_text,
        normalized_text=normalized_title or raw_text,
        level_hint=_uid_depth(raw_uid),
        scheme=scheme,
        score=float(scored.score),
        features=features,
        numbering=numbering,
        scope_type=scope_type,
        is_toc_entry=bool(meta.get("possible_toc")) and bool(meta.get("strong_toc_confirmation")),
        page_number=_safe_int(scored.page),
        evidence_refs=[],
    )


def _scored_to_heading_candidate(scored: ScoredHeadingCandidate) -> HeadingCandidate | None:
    """
    Конвертирует ScoredHeadingCandidate в HeadingCandidate для иерархии.

    Выделена из build_heading_candidates в отдельную функцию,
    чтобы оба вывода run_phase2 использовали один и тот же код преобразования.
    Возвращает None если у кандидата нет raw_uid — такие кандидаты пропускаются.
    """
    if str(scored.decision).lower() != "accepted":
        return None

    meta = scored.metadata or {}
    raw_uid = str(meta.get("raw_uid") or scored.uid or "")
    if not raw_uid:
        return None

    scope = _normalize_scope(scored.scope)
    normalized_title = normalize_spaces(str(meta.get("normalized_title") or scored.title or ""))
    toc_match_type = str(meta.get("toc_match_type") or "")
    toc_match_score = float(meta.get("toc_match_score") or 0.0)
    strong_toc = bool(meta.get("strong_toc_confirmation"))
    is_appendix_uid = bool(meta.get("is_appendix_uid"))

    return HeadingCandidate(
        elem_i=_safe_int(scored.elem_i),
        uid=raw_uid,
        page=_safe_int(scored.page),
        title=normalized_title,
        scope=scope,
        raw_uid=raw_uid,
        effective_uid=str(meta.get("effective_uid") or ""),
        metadata=dict(meta),
        normalized_title=normalized_title,
        toc_entry=strong_toc,
        toc_match_type=toc_match_type or None,
        toc_match_score=toc_match_score if toc_match_score > 0 else None,
        is_appendix=is_appendix_uid,
        is_toc_like=bool(meta.get("possible_toc")),
    )


def _apply_llm_refiner(
    scored: list[ScoredHeadingCandidate],
    elements: list[dict[str, Any]],
    document_id: str,
    *,
    log_context: str = "phase2",
) -> list[ScoredHeadingCandidate]:
    """
    Применяет LLM-refiner к списку scored candidates.

    Выделена в отдельную функцию чтобы:
    1. Не дублировать блок try/except в двух местах.
    2. Использовать корректный вызов refine_ambiguous_candidates
       через keyword arguments (сигнатура функции требует это).
    3. Применять post-refine patching в одном месте.

    Возвращает обновлённый список (или исходный при ошибке).
    """
    try:
        # ВАЖНО: refine_ambiguous_candidates требует keyword-only аргументы.
        # Старый вызов refine_ambiguous_candidates(scored, elements, document_id)
        # был неправильным (positional args) и упал бы с TypeError.
        # Здесь исправлен на keyword аргументы.
        refined = refine_ambiguous_candidates(
            scored_candidates=scored,
            elements=elements,
            document_id=document_id,
        )

        patched: list[ScoredHeadingCandidate] = []
        for c in refined:
            m = dict(c.metadata or {})
            m["raw_uid"] = normalize_spaces(str(m.get("raw_uid") or c.uid or ""))
            m["effective_uid"] = m.get("effective_uid") or _scope_aware_effective_uid(
                _normalize_scope(c.scope),
                m["raw_uid"],
            )
            m["normalized_title"] = normalize_spaces(
                str(m.get("normalized_title") or c.title or "")
            )
            patched.append(_patched_scored_candidate(c, metadata_updates=m))

        return patched

    except Exception:
        logger.exception(
            "STRUCTURE heading_llm_refiner_failed",
            extra={"document_id": document_id, "context": log_context},
        )
        # При ошибке возвращаем исходный список без изменений.
        # Pipeline не должен падать из-за LLM-refiner.
        return scored


def _build_evidence_bundle_from_scored(
    scored: list[ScoredHeadingCandidate],
    elements: list[dict[str, Any]],
) -> StructureEvidenceBundle:
    """
    Строит StructureEvidenceBundle из уже готовых scored candidates.

    Не вызывает collect_scored_heading_candidates повторно.
    Вся логика идентична build_structure_evidence_bundle,
    но получает scored candidates как готовый ввод.
    """
    evidence_candidates: list[EvidenceHeadingCandidate] = []
    for s in scored:
        ev = _scored_to_evidence_candidate(s)
        if ev is not None:
            evidence_candidates.append(ev)

    numbering_sequences = _build_numbering_sequences(evidence_candidates)
    appendix_markers = _build_appendix_markers(evidence_candidates)
    crossref_anchors = _build_crossref_anchors(elements)
    page_signals = _page_signals_from_candidates(
        evidence_candidates,
        appendix_markers,
        crossref_anchors,
        elements=elements,
    )

    toc_detected = any(c.is_toc_entry for c in evidence_candidates)
    global_signals = _global_signals_from_bundle(
        evidence_candidates=evidence_candidates,
        numbering_sequences=numbering_sequences,
        toc_detected=toc_detected,
        crossref_anchors=crossref_anchors,
        elements=elements,
    )

    return StructureEvidenceBundle(
        heading_candidates=evidence_candidates,
        numbering_sequences=numbering_sequences,
        # toc_blocks: зарезервировано, пока не реализована TOC block extraction.
        # Поле существует в контракте StructureEvidenceBundle, но всегда пустое.
        # Будет заполняться в будущих фазах.
        toc_blocks=[],
        appendix_markers=appendix_markers,
        crossref_anchors=crossref_anchors,
        page_signals=page_signals,
        global_signals=global_signals,
    )


def _build_accepted_headings_from_scored(
    scored: list[ScoredHeadingCandidate],
    document_id: str,
) -> list[HeadingCandidate]:
    """
    Извлекает accepted HeadingCandidate из уже готовых scored candidates.

    Не вызывает collect_scored_heading_candidates повторно.
    Логика конвертации идентична build_heading_candidates,
    но получает scored candidates как готовый ввод.
    """
    accepted: list[HeadingCandidate] = []
    for s in scored:
        candidate = _scored_to_heading_candidate(s)
        if candidate is not None:
            accepted.append(candidate)

    return filter_heading_sequence(accepted, document_id=document_id)


# ============================================================================
# Canonical Phase 2 entry point
# ============================================================================

def run_phase2(
    elements: list[dict[str, Any]],
    *,
    document_id: str,
    toc_match_index: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> Phase2Result:
    """
    Единственная точка входа Phase 2.

    Выполняет ровно один проход scoring + optional LLM-refiner.
    Возвращает Phase2Result с двумя проекциями одного результата:
    - evidence_bundle: для downstream Phase 3+ (иерархия, assessment).
    - accepted_headings: для build_clause_hierarchy.

    Заменяет парный вызов build_heading_candidates + build_structure_evidence_bundle.
    Оба старых вызова сохранены как backward-compatible адаптеры.
    """
    # Шаг 1: единственный проход scoring
    scored = collect_scored_heading_candidates(
        elements,
        document_id=document_id,
        toc_match_index=toc_match_index,
    )

    # Шаг 2: optional LLM-refiner (один раз, не два)
    llm_applied = False
    if bool(getattr(settings, "STRUCTURE_ENABLE_HEADING_LLM_REFINER", False)) and scored:
        scored = _apply_llm_refiner(scored, elements, document_id)
        llm_applied = True

    # Шаг 2.5: B2 Heading Density Guard
    # Post-scoring demotion pass: демотирует ACCEPTED → AMBIGUOUS
    # на страницах с аномально высокой heading density без TOC confirmation.
    scored = _apply_heading_density_guard(scored, elements)

    # Шаг 3: evidence bundle из готовых scored candidates
    evidence_bundle = _build_evidence_bundle_from_scored(scored, elements)

    # Шаг 4: accepted headings из тех же готовых scored candidates
    accepted_headings = _build_accepted_headings_from_scored(scored, document_id)

    return Phase2Result(
        evidence_bundle=evidence_bundle,
        accepted_headings=accepted_headings,
        scored_candidates=scored,
        llm_refiner_applied=llm_applied,
    )


# ============================================================================
# Scoring pipeline (без изменений)
# ============================================================================

def collect_scored_heading_candidates(
    elements: list[dict[str, Any]],
    *,
    document_id: str,
    toc_match_index: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> list[ScoredHeadingCandidate]:
    """
    Собирает ScoredHeadingCandidate из layout-элементов, учитывая:
    - parse_raw_heading;
    - heading scoring;
    - TOC match index;
    - continuity context по scope.
    """
    parsed_by_scope: dict[str | None, list[tuple[int, str]]] = defaultdict(list)
    for i, el in enumerate(elements):
        try:
            txt = normalize_spaces(str(el.get("text") or ""))
            if not txt:
                continue
            p = parse_raw_heading(txt)
            if p and p[0]:
                parsed_by_scope[_element_scope(el)].append((i, normalize_spaces(str(p[0]))))
        except Exception:
            continue

    context_map: dict[int, dict[str, Any]] = {}
    for scope, items in parsed_by_scope.items():
        items.sort(key=lambda x: x[0])
        for pos, (elem_i, r_uid) in enumerate(items):
            context_map[elem_i] = {
                "prev_heading_uid": items[pos - 1][1] if pos > 0 else None,
                "next_heading_uid": items[pos + 1][1] if pos + 1 < len(items) else None,
            }

    scored_candidates: list[ScoredHeadingCandidate] = []
    reject_stats: Counter[str] = Counter()

    for elem_i, element in enumerate(elements):
        _require_element_structure_contract(element, elem_i, document_id)

        raw_text = normalize_spaces(str(element.get("text") or ""))
        if not raw_text or len(raw_text) > _MAX_HEADING_RAW_TEXT_LEN:
            continue

        el_type = normalize_spaces(str(element.get("element_type") or ""))
        if not _is_candidate_element_type_allowed(el_type):
            continue

        parsed = parse_raw_heading(raw_text)
        if not parsed or not parsed[0]:
            continue

        p_uid = normalize_spaces(str(parsed[0]))
        p_title = normalize_spaces(str(parsed[1]))

        el_meta = dict(element.get("metadata") or {})
        scope = _element_scope(element)
        ctx = context_map.get(elem_i, {})

        t_match = toc_match_payload(
            raw_uid=p_uid,
            title=p_title,
            toc_match_index=toc_match_index,
        )

        recovery_confidence = float(el_meta.get("recovery_confidence") or 0.0)
        marker_source = el_meta.get("marker_source") or ""
        
        recovery_confidence = float(el_meta.get("recovery_confidence") or 0.0)
        marker_source = el_meta.get("marker_source") or ""
        
        res = score_heading_candidate(
            uid=p_uid,
            title=p_title,
            raw_text=raw_text,
            toc_match=t_match,
            element_type=el_type,
            semantic_element_type=el_meta.get("semantic_element_type"),
            continuity_signals=el_meta.get("continuity_signals"),
            prev_heading_uid=ctx.get("prev_heading_uid"),
            next_heading_uid=ctx.get("next_heading_uid"),
        )
        
        if marker_source == "spatial_recovery" and recovery_confidence >= 0.7:
            res.score = max(res.score, recovery_confidence)
            res.accept_reasons.append("spatial_recovery_high_confidence")
        
        if marker_source == "spatial_recovery" and recovery_confidence >= 0.7:
            res.score = max(res.score, recovery_confidence)
            res.accept_reasons.append("spatial_recovery_high_confidence")

        decision = _status_to_decision(res.status)
        reason = _normalize_reject_reason(res.primary_reason)
        score = float(res.score)

        is_strong = _is_strong_structural_element_type(el_type)
        is_weak = _is_weak_structural_element_type(el_type)
        is_rec_toc = _is_recoverable_toc_like_element_type(el_type)

        strong_toc = _has_strong_toc_confirmation(res.toc_match_type, res.toc_match_score)
        is_root_numeric = _looks_like_root_numeric_uid(p_uid)
        is_appendix_uid = _looks_like_appendix_uid(p_uid)

        # 1. Корректировки по element_type / TOC / uid
        if is_strong and decision == "ambiguous" and score >= 0.55:
            decision, reason = "accepted", "strong_structural_element_type"

        if is_weak and decision == "accepted" and score < 0.70:
            decision, reason = "ambiguous", "weak_structural_element_type_requires_stronger_score"

        if is_rec_toc:
            has_strong_t = strong_toc
            if decision == "accepted" and score < 0.85 and not has_strong_t:
                decision, reason = "ambiguous", "recoverable_toc_like_requires_stronger_evidence"
            if (
                decision == "ambiguous"
                and not el_meta.get("body_recoverable_from_toc")
                and el_meta.get("toc_guard_decision") == "reject_toc"
            ):
                decision, reason = "rejected", "recoverable_toc_like_rejected_by_toc_guard"

        if el_type == "list_item" and decision == "accepted":
            # Universal rule 1: spatial recovery signal has priority
            if marker_source == "spatial_recovery" and recovery_confidence >= 0.7:
                decision, reason = "accepted", "spatial_recovery_list_item"
            # Universal rule 2: numeric markers with document-adaptive depth
            elif _is_strict_numeric_uid(p_uid):
                doc_max_depth = _compute_document_heading_depth(elements)
                uid_depth = _uid_depth(p_uid)
                if uid_depth <= doc_max_depth:
                    if score >= 0.55:
                        decision, reason = "accepted", "numeric_list_item_in_depth"
                    else:
                        decision, reason = "ambiguous", "numeric_list_item_low_score"
                else:
                    if score >= 0.85:
                        decision, reason = "accepted", "numeric_list_item_exceptional"
                    else:
                        decision, reason = "ambiguous", "numeric_list_item_beyond_depth"
            elif _uid_depth(p_uid) > 4 and score < 0.85:
                decision, reason = (
                    "ambiguous",
                    "list_item_deep_uid_requires_stronger_evidence",
                )
            else:
                # Alpha/roman/paren list markers are not section headings by themselves.
                # Ordered alpha/numeric series are recovered via record_heading_recovery
                # (promote to heading_candidate), not via bare list_item accept.
                decision, reason = "rejected", "list_item_non_numeric_uid"

        if el_type == "definition_item" and decision == "accepted":
            if not _is_strict_numeric_uid(p_uid):
                decision, reason = "rejected", "definition_item_non_numeric_uid"
            elif _uid_depth(p_uid) >= 3 and score < 0.90:
                decision, reason = (
                    "ambiguous",
                    "definition_item_requires_stronger_structural_evidence",
                )
            else:
                decision, reason = "ambiguous", "definition_item_prefer_non_section_interpretation"

        if el_type == "enumerated_clause" and decision == "accepted":
            if not _is_strict_numeric_uid(p_uid):
                decision, reason = "rejected", "enumerated_clause_non_numeric_uid"
            elif _uid_depth(p_uid) > 4 and score < 0.90:
                decision, reason = (
                    "ambiguous",
                    "enumerated_clause_deep_uid_requires_stronger_evidence",
                )

        # Phase 13.5: score/decision alignment after builder overrides.
        # Builder может изменить decision после scorer'а, поэтому
        # финальный score калибруем под итоговый decision.
        if decision == "accepted" and score < 0.65:
            score = 0.65
        elif decision == "ambiguous" and score >= 0.85:
            score = 0.84
        elif decision == "rejected" and score >= 0.50:
            score = 0.49

        # 2. Metadata для дальнейших фаз
        metadata: dict[str, Any] = {
            "element_id": str(element.get("element_id") or element.get("id") or f"el-{elem_i}"),
            "accept_reasons": list(res.accept_reasons),
            "reject_reasons": list(res.reject_reasons),
            "parsed_uid": p_uid,
            "raw_uid": p_uid,
            "effective_uid": _scope_aware_effective_uid(scope, p_uid),
            "parsed_title": p_title,
            "normalized_title": p_title,
            "freeze_structural_fields": _is_strict_numeric_uid(p_uid),
            "scope": scope,
            "segment_id": element.get("segment_id"),
            "segment_type": element.get("segment_type"),
            "segment_order": element.get("segment_order"),
            "element_type": el_type,
            "uid_depth": _uid_depth(p_uid),
            "page": element.get("page"),
            "toc_match": t_match,
            "toc_match_type": res.toc_match_type,
            "toc_match_score": float(res.toc_match_score),
            "semantic_element_type": res.semantic_element_type
                or el_meta.get("semantic_element_type"),
            "continuity_bonus": float(res.continuity_bonus),
            "legal_negative_signals": list(res.legal_negative_signals),
            "heading_confidence_from_classifier": float(el_meta.get("heading_confidence") or 0.0),
            "heading_reject_reasons_from_classifier": list(
                el_meta.get("heading_reject_reasons") or []
            ),
            "toc_guard_decision": str(el_meta.get("toc_guard_decision") or ""),
            "body_recoverable_from_toc": bool(el_meta.get("body_recoverable_from_toc")),
            "possible_toc": bool(el_meta.get("possible_toc")),
            "strong_toc_confirmation": strong_toc,
            "is_root_numeric_uid": is_root_numeric,
            "is_appendix_uid": is_appendix_uid,
            "decision_before_element_type_adjustment": _status_to_decision(res.status),
            "decision_after_element_type_adjustment": decision,
            "_preamble_zone": str(element.get("_preamble_zone") or "").strip().lower(),
        }

        candidate = ScoredHeadingCandidate(
            elem_i=elem_i,
            page=_safe_int(element.get("page")),
            raw_text=raw_text,
            uid=p_uid,
            title=p_title,
            decision=decision,
            reason=reason,
            score=score,
            decision_source="rules",
            metadata=metadata,
            scope=scope,
        )
        scored_candidates.append(candidate)

        if decision not in {"accepted", "ambiguous"}:
            reject_stats[reason] += 1

    try:
        scored_candidates = annotate_bilingual_heading_pairs(scored_candidates)
    except Exception:
        logger.exception(
            "STRUCTURE bilingual_heading_pair_annotation_failed",
            extra={"document_id": document_id},
        )

    return _select_best_candidates_by_uid(scored_candidates, document_id)


# ============================================================================
# Dedup (без изменений)
# ============================================================================

def filter_heading_sequence(
    candidates: list[HeadingCandidate],
    *,
    document_id: str,
) -> list[HeadingCandidate]:
    """Дедупликация финального списка HeadingCandidate с разделением TOC и Body."""
    if not candidates:
        return []

    filtered: list[HeadingCandidate] = []
    seen: set[tuple[str, str, bool]] = set()

    for cand in candidates:
        is_toc = (cand.metadata or {}).get("_preamble_zone") == "in_toc" or bool(cand.toc_entry) or bool(cand.is_toc_like)
        key = (str(cand.scope), str(cand.raw_uid), is_toc)
        if key not in seen:
            seen.add(key)
            filtered.append(cand)

    return filtered


# ============================================================================
# Backward-compatible adapters
# ============================================================================

def build_heading_candidates(
    elements: list[dict[str, Any]],
    *,
    document_id: str,
    toc_match_index: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> list[HeadingCandidate]:
    """
    Backward-compatible адаптер.

    Внутри вызывает run_phase2(...) и возвращает только accepted headings.
    Scoring проходит ровно один раз, а не два как раньше.

    Используйте run_phase2(...) напрямую если нужны оба артефакта —
    это избегает повторного вызова scoring при необходимости и bundle.
    """
    result = run_phase2(
        elements,
        document_id=document_id,
        toc_match_index=toc_match_index,
    )
    return result.accepted_headings


def build_structure_evidence_bundle(
    elements: list[dict[str, Any]],
    *,
    document_id: str,
    toc_match_index: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> StructureEvidenceBundle:
    """
    Backward-compatible адаптер.

    Внутри вызывает run_phase2(...) и возвращает только evidence bundle.
    Scoring проходит ровно один раз, а не два как раньше.

    Используйте run_phase2(...) напрямую если нужны оба артефакта.
    """
    result = run_phase2(
        elements,
        document_id=document_id,
        toc_match_index=toc_match_index,
    )
    return result.evidence_bundle





