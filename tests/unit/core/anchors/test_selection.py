from __future__ import annotations

from core.anchors.models import CheckAnchor, CheckAnchorMethod
from core.anchors.selection import method_strength, select_primary_anchor


def test_method_strength_ordering() -> None:
    assert method_strength(CheckAnchorMethod.EXACT_SPAN) > method_strength(CheckAnchorMethod.FUZZY_SPAN)
    assert method_strength(CheckAnchorMethod.FUZZY_SPAN) > method_strength(CheckAnchorMethod.CLAUSE_AND_LAYOUT)
    assert method_strength(CheckAnchorMethod.CLAUSE_AND_LAYOUT) > method_strength(CheckAnchorMethod.CLAUSE_ONLY)
    assert method_strength(CheckAnchorMethod.CLAUSE_ONLY) > method_strength(CheckAnchorMethod.LAYOUT_ONLY)
    assert method_strength(CheckAnchorMethod.LAYOUT_ONLY) > method_strength(CheckAnchorMethod.PAGE_ONLY)
    assert method_strength(CheckAnchorMethod.PAGE_ONLY) > method_strength(CheckAnchorMethod.RETRIEVAL_LEGACY)
    assert method_strength(CheckAnchorMethod.RETRIEVAL_LEGACY) > method_strength(CheckAnchorMethod.NONE)


def test_select_primary_empty() -> None:
    assert select_primary_anchor([]) is None


def test_select_primary_prefers_exact_span() -> None:
    fuzzy = CheckAnchor(anchor_method=CheckAnchorMethod.FUZZY_SPAN, anchor_confidence=0.95)
    exact = CheckAnchor(
        anchor_method=CheckAnchorMethod.EXACT_SPAN,
        anchor_confidence=0.8,
        anchor_validation_passed=True,
    )
    assert select_primary_anchor([fuzzy, exact]) is exact


def test_select_primary_tiebreak_by_confidence() -> None:
    low = CheckAnchor(anchor_method=CheckAnchorMethod.FUZZY_SPAN, anchor_confidence=0.6)
    high = CheckAnchor(anchor_method=CheckAnchorMethod.FUZZY_SPAN, anchor_confidence=0.95)
    assert select_primary_anchor([low, high]) is high

    