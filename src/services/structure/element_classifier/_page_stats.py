# src/services/structure/element_classifier/_page_stats.py

"""Утилиты для вычисления статистики по страницам документа.

Используется для определения положения элементов на странице
(близость к верхнему/нижнему краю) при детекции page artifacts.
"""

from __future__ import annotations

from typing import Any

from ._text_utils import _safe_bbox, _safe_int


def _build_page_stats(elements: list[dict[str, Any]]) -> dict[int, dict[str, float]]:
    """Вычисляет статистику по страницам (min_top, max_bottom, span).

    Args:
        elements: Список элементов документа

    Returns:
        Словарь {page_number: {"min_top": float, "max_bottom": float, "span": float}}
    """
    page_to_tops: dict[int, list[float]] = {}
    page_to_bottoms: dict[int, list[float]] = {}

    for el in elements:
        page = _safe_int(el.get("page"), default=1)
        bbox = _safe_bbox(el.get("bbox"))
        top = bbox[1]
        bottom = bbox[3]
        page_to_tops.setdefault(page, []).append(top)
        page_to_bottoms.setdefault(page, []).append(bottom)

    stats: dict[int, dict[str, float]] = {}
    for page in set(page_to_tops) | set(page_to_bottoms):
        tops = page_to_tops.get(page, [0.0])
        bottoms = page_to_bottoms.get(page, [0.0])
        min_top = min(tops) if tops else 0.0
        max_bottom = max(bottoms) if bottoms else 0.0
        span = max(max_bottom - min_top, 1.0)
        stats[page] = {
            "min_top": float(min_top),
            "max_bottom": float(max_bottom),
            "span": float(span),
        }

    return stats


def _relative_page_position(
    element: dict[str, Any],
    page_stats: dict[int, dict[str, float]],
) -> tuple[float, float]:
    """Вычисляет относительное положение элемента на странице.

    Args:
        element: Элемент документа
        page_stats: Статистика по страницам из _build_page_stats

    Returns:
        Кортеж (top_ratio, bottom_ratio) где:
        - top_ratio: расстояние от верхнего края (0-1)
        - bottom_ratio: расстояние от нижнего края (0-1)
    """
    page = _safe_int(element.get("page"), default=1)
    bbox = _safe_bbox(element.get("bbox"))
    top = bbox[1]
    bottom = bbox[3]

    stats = page_stats.get(page) or {
        "min_top": 0.0,
        "max_bottom": max(bottom, 1.0),
        "span": 1.0,
    }
    min_top = stats["min_top"]
    max_bottom = stats["max_bottom"]
    span = max(stats["span"], 1.0)

    top_ratio = (top - min_top) / span
    bottom_ratio = (max_bottom - bottom) / span
    return top_ratio, bottom_ratio

