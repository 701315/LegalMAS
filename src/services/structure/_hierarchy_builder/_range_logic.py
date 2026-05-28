# src/services/structure/_hierarchy_builder/_range_logic.py

"""Вычисление границ владения элементами (Geometry) с исправлением ошибок None vs int."""

from __future__ import annotations
from typing import Any
from services.structure._models._nodes import ClauseNode
from ._types import HeadingCandidate, OwnRangeComputation
from ._utils import (
    _heading_scope, _heading_raw_uid, _normalize_uid, 
    _is_strict_numeric_uid, level_from_uid
)

def _collect_own_text(
    elements: list[dict[str, Any]],
    start_elem_i: int,
    end_elem_i: int,
) -> str:
    """Сбор текста элементов, принадлежащих только этому узлу."""
    parts: list[str] = []
    # end_elem_i теперь всегда int
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

    for heading in headings[idx + 1:]:
        if _heading_scope(heading) != scope:
            continue
        h_uid = _heading_raw_uid(heading)
        if not h_uid:
            continue
        # Исправление mypy: уровень вычисляем только для валидных numeric uid
        h_level = level_from_uid(h_uid) if _is_strict_numeric_uid(h_uid) else 1
        if h_level <= node_level:
            return int(heading.elem_i)
    return None

def _compute_own_range(
    *,
    raw_uid: str,
    node: ClauseNode,
    headings: list[HeadingCandidate],
    elements: list[dict[str, Any]],
    key_to_elem_i: dict[tuple[str, str], int],
    key_to_heading_index: dict[tuple[str, str], int],
    scope: str,
    scope_boundaries: dict[str, tuple[int, int]],
) -> OwnRangeComputation:
    """Вычисление диапазона [start, end). Исправляет ошибку mypy 806/843."""
    key = (scope, raw_uid)
    heading_elem_i = key_to_elem_i.get(key, -1)

    if heading_elem_i < 0:
        return OwnRangeComputation(heading_elem_i, len(elements), "unbounded_error")

    # 1. Сбор кандидатов на конец диапазона
    candidates: list[tuple[int, str]] = []

    # Первый ребенок
    first_child_elem_i: int | None = None
    for child in node.children:
        c_uid = _normalize_uid(child.raw_uid)
        c_key = (scope, c_uid)
        c_elem_i = key_to_elem_i.get(c_key)
        if c_elem_i is not None and (first_child_elem_i is None or c_elem_i < first_child_elem_i):
            first_child_elem_i = c_elem_i
    
    if first_child_elem_i is not None and first_child_elem_i > heading_elem_i:
        candidates.append((first_child_elem_i, "first_child"))

    # Следующий заголовок того же уровня
    next_same_or_higher = _find_next_same_or_higher_level_elem_i(
        raw_uid=raw_uid, node_level=node.level, scope=scope,
        headings=headings, key_to_heading_index=key_to_heading_index
    )
    if next_same_or_higher is not None and next_same_or_higher > heading_elem_i:
        candidates.append((next_same_or_higher, "next_same_or_higher"))

    # Конец scope
    scope_boundary = scope_boundaries.get(scope)
    if scope_boundary is not None and scope_boundary[1] > heading_elem_i:
        candidates.append((scope_boundary[1], "segment_end"))
    
    # 2. Обязательный fallback: конец списка элементов.
    # Это гарантирует, что candidates никогда не пуст и min() не получит None.
    candidates.append((len(elements), "fallback_boundary"))

    # Исправление mypy: min() по списку кортежей (int, str)
    end_elem_i, reason = min(candidates, key=lambda item: item[0])

    return OwnRangeComputation(
        start_elem_i=heading_elem_i,
        end_elem_i=end_elem_i,
        range_end_reason=reason,
    )


