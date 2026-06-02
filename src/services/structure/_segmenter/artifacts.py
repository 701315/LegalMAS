# src/services/structure/_segmenter/artifacts.py

"""
Детекция повторяющихся page-артефактов и running headers.

Running header — текст, идентично повторяющийся вверху нескольких страниц.
Такой текст не должен порождать boundary candidate, кроме, возможно,
первого вхождения (если оно само выглядит как boundary marker).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from services.structure.heading_patterns import normalize_spaces

from .config import MAX_HEADER_LINES_TO_CHECK, MIN_PAGES_FOR_ARTIFACT
from .element_utils import (
    element_type,
    is_list_item_element,
    safe_page,
)
from .heuristics import (
    is_boundary_position,
    is_heading_like,
    looks_like_non_boundary_block,
)
from .patterns import match_boundary_marker


def _should_preserve_first_repeated_boundary_occurrence(
    elements: list[dict[str, Any]],
    index: int,
) -> bool:
    """Сохраняет первое вхождение повторяющегося текста, если оно
    выглядит как настоящий boundary marker в boundary-позиции.
    """
    if index < 0 or index >= len(elements):
        return False

    element = elements[index]
    raw_text = element.get("text", "")
    text = normalize_spaces(str(raw_text or ""))
    if not text:
        return False

    if not match_boundary_marker(text):
        return False

    if looks_like_non_boundary_block(text):
        return False

    return is_boundary_position(elements, index, text)


def detect_repeated_page_artifacts(
    elements: list[dict[str, Any]],
) -> set[int]:
    """Определяет индексы элементов, являющихся running headers / page artifacts.

    Возвращает множество индексов, которые следует игнорировать при сборе
    boundary candidates.
    """
    page_first_indices: dict[int, list[int]] = defaultdict(list)
    repeated_indices: set[int] = set()

    for idx, el in enumerate(elements):
        page = safe_page(el)
        if len(page_first_indices[page]) < MAX_HEADER_LINES_TO_CHECK:
            page_first_indices[page].append(idx)

        if element_type(el) == "page_artifact":
            repeated_indices.add(idx)

    signature_hits: dict[str, list[int]] = defaultdict(list)
    for _, idx_list in page_first_indices.items():
        for idx in idx_list:
            if idx in repeated_indices:
                continue

            raw_text = elements[idx].get("text", "")
            text = normalize_spaces(str(raw_text or ""))
            if not text:
                continue

            signature_hits[text].append(idx)

    for _, idx_list in signature_hits.items():
        if len(idx_list) < MIN_PAGES_FOR_ARTIFACT:
            continue

        ordered = sorted(idx_list)
        preserve_idx: int | None = None

        first_idx = ordered[0]
        if _should_preserve_first_repeated_boundary_occurrence(elements, first_idx):
            preserve_idx = first_idx

        for idx in ordered:
            if preserve_idx is not None and idx == preserve_idx:
                continue
            repeated_indices.add(idx)

    return repeated_indices


