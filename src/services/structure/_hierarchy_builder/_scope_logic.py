# src/services/structure/_hierarchy_builder/_scope_logic.py

"""Логика обработки пространств нумерации (scopes)."""

from __future__ import annotations
from typing import Any
from ._types import HeadingCandidate
from ._utils import _normalize_scope, _heading_scope, _heading_raw_uid

def _group_headings_by_scope(
    headings: list[HeadingCandidate],
) -> dict[str, list[HeadingCandidate]]:
    """Группирует кандидатов по scope и сортирует по elem_i."""
    grouped: dict[str, list[HeadingCandidate]] = {}
    for heading in headings:
        scope = _heading_scope(heading)
        grouped.setdefault(scope, []).append(heading)

    for scope in grouped:
        grouped[scope].sort(key=lambda h: (int(h.elem_i), int(h.page)))
    return grouped

def _build_scope_boundaries(
    elements: list[dict[str, Any]],
) -> dict[str, tuple[int, int]]:
    """Определяет индексы элементов [start, end), в которых живет каждый scope."""
    bounds: dict[str, list[int]] = {}
    for idx, element in enumerate(elements):
        scope = _normalize_scope(element.get("scope"))
        if scope not in bounds:
            bounds[scope] = [idx, idx + 1]
        else:
            bounds[scope][1] = idx + 1
    return {scope: (start, end) for scope, (start, end) in bounds.items()}

def _build_heading_positions(
    headings: list[HeadingCandidate],
) -> tuple[dict[tuple[str, str], int], dict[tuple[str, str], int]]:
    """Строит индексы для быстрого поиска elem_i и позиции кандидата в списке."""
    key_to_elem_i: dict[tuple[str, str], int] = {}
    key_to_heading_index: dict[tuple[str, str], int] = {}

    for idx, heading in enumerate(headings):
        raw_uid = _heading_raw_uid(heading)
        if not raw_uid:
            continue
        scope = _heading_scope(heading)
        key = (scope, raw_uid)
        if key not in key_to_elem_i:
            key_to_elem_i[key] = int(heading.elem_i)
            key_to_heading_index[key] = idx
    return key_to_elem_i, key_to_heading_index