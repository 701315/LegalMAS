# src/services/structure/_hierarchy_builder/_range_logic.py

# src/services/structure/_hierarchy_builder/_range_logic.py

"""Вычисление границ владения элементами (Geometry)."""

from __future__ import annotations

from typing import Any
from services.structure.heading_features import (
    looks_like_numeric_amount_continuation,
    looks_like_reference_led_clause_continuation,
)
from services.structure.heading_patterns import parse_raw_heading
from services.structure.models import MutableHierarchyNode

from ._types import HeadingCandidate, OwnRangeComputation
from ._utils import (
    _heading_raw_uid,
    _heading_scope,
    _is_strict_numeric_uid,
    _normalize_uid,
    level_from_uid,
)


_HEADINGISH_ELEMENT_TYPES = {
    "heading_candidate",
    "section_heading",
    "subsection_heading",
    "appendix_heading",
}


def _is_headingish_layout_element(element: dict[str, Any]) -> bool:
    """Элемент layout выглядит как heading по raw_type или element_type."""
    raw_type = str(element.get("type") or "").strip().lower()
    element_type = str(element.get("element_type") or "").strip().lower()
    if raw_type == "heading":
        return True
    return element_type in _HEADINGISH_ELEMENT_TYPES


def _element_scope_local(element: dict[str, Any]) -> str:
    """Извлечь scope из элемента без внешних зависимостей."""
    scope = element.get("scope")
    if scope is None:
        scope = (element.get("metadata") or {}).get("scope")
    return str(scope or "").strip()


def _find_soft_next_root_heading_from_layout(
    *,
    raw_uid: str,
    heading_elem_i: int,
    scope: str,
    elements: list[dict[str, Any]],
    scope_boundaries: dict[str, tuple[int, int]],
) -> int | None:
    """
    Soft closure fallback для root sections.

    Используется только если среди accepted headings не найден
    следующий same-or-higher-level heading. Сканирует raw layout
    внутри того же scope и ищет следующий plausibly-valid root
    numeric heading по layout-сигналам.

    Не page-cap hack — deterministic safety net против случая,
    когда scoring пропустил несколько intermediate root sections,
    а section range без ограничения поглощает весь хвост документа.

    Применяется только для root numeric sections (level == 1).
    Не ищет вложенные headings — только следующий root.

    ВАЖНО:
    это internal fallback для нахождения границы диапазона.
    Наружу он НЕ должен публиковать отдельный range_end_reason.
    По canonical structural contract такой случай нормализуется
    к "next_same_or_higher".
    """
    normalized_uid = _normalize_uid(raw_uid)
    if not normalized_uid.isdigit():
        return None

    try:
        current_root_num = int(normalized_uid)
    except Exception:
        return None

    scope_end = len(elements)
    scope_boundary = scope_boundaries.get(scope)
    if scope_boundary is not None:
        scope_end = min(scope_end, int(scope_boundary[1]))

    for j in range(max(heading_elem_i + 1, 0), scope_end):
        element = elements[j]

        el_scope = _element_scope_local(element)
        if el_scope and el_scope != scope:
            continue

        if not _is_headingish_layout_element(element):
            continue

        text = str(element.get("text") or "").strip()
        if not text:
            continue

        parsed = parse_raw_heading(text)
        if not parsed:
            continue

        candidate_uid, candidate_title = parsed
        candidate_uid = _normalize_uid(candidate_uid)

        if not _is_strict_numeric_uid(candidate_uid):
            continue

        if level_from_uid(candidate_uid) != 1:
            continue

        try:
            candidate_root_num = int(candidate_uid)
        except Exception:
            continue

        if candidate_root_num <= current_root_num:
            continue

        if looks_like_numeric_amount_continuation(candidate_title):
            continue

        if looks_like_reference_led_clause_continuation(candidate_title):
            continue

        return j

    return None


def _collect_own_text(
    elements: list[dict[str, Any]],
    start_elem_i: int,
    end_elem_i: int,
) -> str:
    """Сбор текста элементов, принадлежащих только этому узлу."""
    parts: list[str] = []
    upper_bound = min(end_elem_i, len(elements))
    for j in range(max(start_elem_i, 0), upper_bound):
        text = str(elements[j].get("text") or "").strip()
        if text:
            parts.append(text)
    return " ".join(parts)


def _find_next_same_or_higher_level_elem_i(
    *,
    raw_uid: str,
    node_level: int,
    scope: str,
    headings: list[HeadingCandidate],
    key_to_heading_index: dict[tuple[str, str], int] | None = None,
    heading_elem_i: int | None = None,
) -> int | None:
    """
    Поиск следующего заголовка такого же или более высокого уровня в том же scope.

    ВАЖНО:
    - headings здесь уже scope-local список (headings_by_scope[scope]).
    - key_to_heading_index исторически строился по глобальному списку headings.
      Использовать его как local index нельзя: это приводит к пропуску ближайших
      sibling headings и огромным overlapping own ranges.
    - Поэтому primary path здесь — найти local index внутри ПЕРЕДАННОГО списка
      по anchor position (heading_elem_i) и raw_uid.
    - key_to_heading_index остаётся только как guarded legacy fallback.
    """
    normalized_uid = _normalize_uid(raw_uid)

    local_idx: int | None = None

    # ── Primary path: exact local match by source anchor elem_i ────────────
    if heading_elem_i is not None:
        for i, heading in enumerate(headings):
            if _heading_scope(heading) != scope:
                continue

            h_uid = _normalize_uid(_heading_raw_uid(heading))
            if h_uid != normalized_uid:
                continue

            try:
                h_elem_i = int(heading.elem_i)
            except Exception:
                continue

            if h_elem_i == int(heading_elem_i):
                local_idx = i
                break

    # ── Secondary path: fallback by raw_uid inside local scope list ────────
    if local_idx is None:
        for i, heading in enumerate(headings):
            if _heading_scope(heading) != scope:
                continue
            h_uid = _normalize_uid(_heading_raw_uid(heading))
            if h_uid == normalized_uid:
                local_idx = i
                break

    # ── Legacy fallback: guarded use of old index only if it is local-valid ─
    # Не preferred path. Используется только если local search не сработал.
    if local_idx is None and key_to_heading_index is not None:
        key = (scope, raw_uid)
        legacy_idx = key_to_heading_index.get(key)
        if isinstance(legacy_idx, int) and 0 <= legacy_idx < len(headings):
            local_idx = legacy_idx

    if local_idx is None:
        return None

    for heading in headings[local_idx + 1 :]:
        if _heading_scope(heading) != scope:
            continue
        h_uid = _heading_raw_uid(heading)
        if not h_uid:
            continue
        h_level = level_from_uid(h_uid) if _is_strict_numeric_uid(h_uid) else 1
        if h_level <= node_level:
            return int(heading.elem_i)

    return None


def _compute_own_range(
    *,
    raw_uid: str,
    node: MutableHierarchyNode,
    headings: list[HeadingCandidate],
    elements: list[dict[str, Any]],
    key_to_elem_i: dict[tuple[str, str], int],
    key_to_heading_index: dict[tuple[str, str], int],
    scope: str,
    scope_boundaries: dict[str, tuple[int, int]],
) -> OwnRangeComputation:
    """Вычисление диапазона [start, end)."""
    key = (scope, raw_uid)

    # ── Prefer exact source anchor from node diagnostics ────────────────────
    # Это более надёжно чем key_to_elem_i, потому что key_to_elem_i
    # исторически строился по first occurrence ключа (scope, raw_uid),
    # а в документе могут существовать дубли того же raw_uid в других
    # представлениях/кандидатах. source_elem_i пришёл из реального heading node.
    heading_elem_i = -1

    diagnostics = getattr(node, "diagnostics", None) or {}
    source_elem_i = diagnostics.get("source_elem_i")

    if isinstance(source_elem_i, int):
        heading_elem_i = source_elem_i
    else:
        try:
            if source_elem_i is not None:
                heading_elem_i = int(source_elem_i)
        except Exception:
            heading_elem_i = -1

    if heading_elem_i < 0:
        heading_elem_i = key_to_elem_i.get(key, -1)

    if heading_elem_i < 0:
        return OwnRangeComputation(heading_elem_i, len(elements), "unbounded_error")

    candidates: list[tuple[int, str]] = []

    # ── TOC boundary barrier ────────────────────────────────────────────────
    # Heading, physically located before or inside TOC, must NOT own content
    # from post-TOC zone. Otherwise TOC-derived headings (e.g. 7.1 from contents)
    # swallow the actual legal preamble that starts after TOC.
    #
    # Universal rule:
    # - no language assumptions
    # - no document-type assumptions
    # - purely structural/layout-based barrier
    if 0 <= heading_elem_i < len(elements):
        heading_zone = str(elements[heading_elem_i].get("_preamble_zone") or "").strip().lower()

        # B7.2: heading в ToC-зоне с детьми — это маркер оглавления,
        # а не начало клаузы. Его own_range = только сам элемент.
        # Иначе ToC-строки попадают в own_element_ids/own_text, и legal_unit
        # становится retrieval-target с неверной start_page (см. кейс
        # quality_completeness_warranty: page=2 вместо page=6).
        # Дочерние узлы (7.3.1..7.3.5) привязываются через subtree_element_ids
        # и остаются retrievable независимо.
        # Универсально: опирается на структурный _preamble_zone, не на язык.
        if heading_zone in {"pre_toc", "in_toc"} and node.children:
            return OwnRangeComputation(
                start_elem_i=heading_elem_i,
                end_elem_i=heading_elem_i + 1,
                range_end_reason="toc_zone_heading_isolated",
            )

        if heading_zone in {"pre_toc", "in_toc"}:
            for barrier_i in range(heading_elem_i + 1, len(elements)):
                barrier_zone = str(elements[barrier_i].get("_preamble_zone") or "").strip().lower()

                # pre_toc heading cannot cross TOC boundary at all
                if heading_zone == "pre_toc" and barrier_zone in {"in_toc", "post_toc"}:
                    candidates.append((barrier_i, "segment_end"))
                    break

                # in_toc heading cannot own post_toc body
                if heading_zone == "in_toc" and barrier_zone == "post_toc":
                    candidates.append((barrier_i, "segment_end"))
                    break

    first_child_elem_i: int | None = None
    for child in node.children:
        c_uid = _normalize_uid(child.raw_uid)
        c_key = (scope, c_uid)
        c_elem_i = key_to_elem_i.get(c_key)
        if c_elem_i is not None and (first_child_elem_i is None or c_elem_i < first_child_elem_i):
            first_child_elem_i = c_elem_i

    if first_child_elem_i is not None and first_child_elem_i > heading_elem_i:
        candidates.append((first_child_elem_i, "first_child"))

    next_same_or_higher = _find_next_same_or_higher_level_elem_i(
        raw_uid=raw_uid,
        node_level=node.level,
        scope=scope,
        headings=headings,
        key_to_heading_index=key_to_heading_index,
        heading_elem_i=heading_elem_i,
    )
    if next_same_or_higher is not None and next_same_or_higher > heading_elem_i:
        candidates.append((next_same_or_higher, "next_same_or_higher"))

    if node.level == 1 and _normalize_uid(raw_uid).isdigit():
        soft_next_root = _find_soft_next_root_heading_from_layout(
            raw_uid=raw_uid,
            heading_elem_i=heading_elem_i,
            scope=scope,
            elements=elements,
            scope_boundaries=scope_boundaries,
        )
        if soft_next_root is not None and soft_next_root > heading_elem_i:
            candidates.append((soft_next_root, "next_same_or_higher"))

    scope_boundary = scope_boundaries.get(scope)
    if scope_boundary is not None and scope_boundary[1] > heading_elem_i:
        candidates.append((scope_boundary[1], "segment_end"))

    candidates.append((len(elements), "fallback_boundary"))

    end_elem_i, reason = min(candidates, key=lambda item: item[0])

    return OwnRangeComputation(
        start_elem_i=heading_elem_i,
        end_elem_i=end_elem_i,
        range_end_reason=reason,
    )


