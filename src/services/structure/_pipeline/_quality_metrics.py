# src/services/structure/pipeline/_quality_metrics.py

"""
Метрики качества структуры и вспомогательные summary-функции.

Содержит:
- расчёт coverage узлов
- вычисление structural confidence
- сводки по headings
- сводки по element_type
"""

from __future__ import annotations

from typing import Any

from core.config import settings
from services.structure.models import (
    ClauseNode,
    STRUCTURE_CONFIDENCE_FAILED,
    STRUCTURE_CONFIDENCE_HIGH,
    STRUCTURE_CONFIDENCE_LOW,
    STRUCTURE_CONFIDENCE_MEDIUM,
)
from services.structure.hierarchy_builder import HeadingCandidate

from ._utils import stable_element_id, is_numeric_uid


def calculate_node_coverage(
    *,
    nodes: dict[str, ClauseNode],
    elements: list[dict],
) -> float:
    """
    Доля элементов body, покрытых own_element_ids.
    """
    if not elements:
        return 0.0

    all_ids: set[str] = set()
    covered_ids: set[str] = set()

    for idx, el in enumerate(elements):
        all_ids.add(stable_element_id(el, idx))

    for node in nodes.values():
        covered_ids.update(node.own_element_ids or [])

    if not all_ids:
        return 0.0

    return len(all_ids & covered_ids) / len(all_ids)


def summarize_headings(headings: list[HeadingCandidate]) -> dict[str, Any]:
    """
    Лёгкая quality summary по принятым headings.
    """
    total = len(headings)
    if not total:
        return {
            "total": 0,
            "numeric_count": 0,
            "numeric_ratio": 0.0,
            "empty_title_count": 0,
            "scope_distribution": {},
        }

    numeric_count = 0
    empty_title_count = 0
    scope_distribution: dict[str, int] = {}

    for h in headings:
        raw_uid = str(getattr(h, "raw_uid", None) or h.uid or "").strip()
        title = str(h.title or "").strip()
        scope = str(getattr(h, "scope", None) or "unknown").strip() or "unknown"

        scope_distribution[scope] = scope_distribution.get(scope, 0) + 1

        if is_numeric_uid(raw_uid):
            numeric_count += 1
        if not title:
            empty_title_count += 1

    return {
        "total": total,
        "numeric_count": numeric_count,
        "numeric_ratio": numeric_count / total,
        "empty_title_count": empty_title_count,
        "scope_distribution": scope_distribution,
    }


def summarize_element_types(elements: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Сводка по element_type.
    """
    counts: dict[str, int] = {}

    for el in elements:
        element_type = str(el.get("element_type") or "unknown").strip() or "unknown"
        counts[element_type] = counts.get(element_type, 0) + 1

    total = len(elements)
    toc_total = (
        counts.get("toc_header", 0)
        + counts.get("toc_line", 0)
        + counts.get("possible_toc", 0)
        + counts.get("toc_false_positive", 0)
    )

    return {
        "total": total,
        "counts": counts,
        "heading_candidates": counts.get("heading_candidate", 0),
        "body_text": counts.get("body_text", 0),
        "list_items": counts.get("list_item", 0),
        "toc_header": counts.get("toc_header", 0),
        "toc_line": counts.get("toc_line", 0),
        "possible_toc": counts.get("possible_toc", 0),
        "toc_false_positive": counts.get("toc_false_positive", 0),
        "toc_total": toc_total,
        "signature_blocks": counts.get("signature_block", 0),
        "requisites_blocks": counts.get("requisites_block", 0),
        "page_artifacts": counts.get("page_artifact", 0),
        "unknown_layout": counts.get("unknown_layout", 0),
    }


def confidence_and_mode(
    coverage: float,
    *,
    layout_degraded: bool = False,
    headings_count: int = 0,
    numeric_ratio: float = 1.0,
    empty_title_count: int = 0,
    structure_degraded: bool = False,
) -> tuple[str, bool]:
    """
    Возвращает (structural_confidence, degraded_flag).
    """
    threshold = settings.STRUCTURE_MIN_CLAUSE_COVERAGE

    if layout_degraded:
        threshold *= 0.7

    if structure_degraded:
        return STRUCTURE_CONFIDENCE_LOW, True

    if headings_count == 0:
        return STRUCTURE_CONFIDENCE_FAILED, True

    if headings_count < 3:
        return STRUCTURE_CONFIDENCE_LOW, True

    if numeric_ratio < 0.3:
        return STRUCTURE_CONFIDENCE_LOW, True

    if empty_title_count >= max(2, headings_count // 2):
        return STRUCTURE_CONFIDENCE_LOW, True

    if coverage < threshold:
        return STRUCTURE_CONFIDENCE_LOW, True

    if coverage < 0.80:
        return STRUCTURE_CONFIDENCE_MEDIUM, False

    return STRUCTURE_CONFIDENCE_HIGH, False

