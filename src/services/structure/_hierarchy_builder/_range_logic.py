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
    key_to_heading_index: dict[tuple[str, str], int],
) -> int | None:
    """Поиск следующего заголовка такого же или более высокого уровня в том же scope."""
    key = (scope, raw_uid)
    idx = key_to_heading_index.get(key)
    if idx is None:
        return None

    for heading in headings[idx + 1 :]:
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
    heading_elem_i = key_to_elem_i.get(key, -1)

    if heading_elem_i < 0:
        return OwnRangeComputation(heading_elem_i, len(elements), "unbounded_error")

    candidates: list[tuple[int, str]] = []

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
            candidates.append((soft_next_root, "soft_next_root_from_layout"))

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


