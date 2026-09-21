# src/core/anchors/selection.py

"""
Правила выбора primary anchor.

Порядок силы соответствует плану, раздел 3.B4:
    exact_span > fuzzy_span > clause_and_layout > clause_only >
    layout_only > page_only > retrieval_legacy > none
"""

from __future__ import annotations

from core.anchors.models import CheckAnchor, CheckAnchorMethod

_METHOD_STRENGTH: dict[CheckAnchorMethod, int] = {
    CheckAnchorMethod.EXACT_SPAN: 8,
    CheckAnchorMethod.FUZZY_SPAN: 7,
    CheckAnchorMethod.CLAUSE_AND_LAYOUT: 6,
    CheckAnchorMethod.CLAUSE_ONLY: 5,
    CheckAnchorMethod.LAYOUT_ONLY: 4,
    CheckAnchorMethod.PAGE_ONLY: 3,
    CheckAnchorMethod.RETRIEVAL_LEGACY: 2,
    CheckAnchorMethod.NONE: 1,
}


def method_strength(method: CheckAnchorMethod) -> int:
    """Числовой ранг метода. Больше = сильнее."""
    return _METHOD_STRENGTH[method]


def select_primary_anchor(anchors: list[CheckAnchor]) -> CheckAnchor | None:
    """
    Выбрать primary anchor по правилу силы метода.

    Tie-break: при равной силе — по большей anchor_confidence.
    Возвращает None для пустого входа.
    """
    if not anchors:
        return None

    def _key(a: CheckAnchor) -> tuple[int, float]:
        return (method_strength(a.anchor_method), a.anchor_confidence)

    return max(anchors, key=_key)

