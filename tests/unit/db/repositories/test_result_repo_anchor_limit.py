"""
B4 — _apply_anchor_limit unit tests.
"""

from __future__ import annotations

import pytest

from core.anchors.models import CheckAnchor, CheckAnchorMethod
from db.repositories.result_repo import (
    _MAX_ANCHORS_PER_CHECK_RESULT,
    ResultRepository,
)


def _a(method: str, conf: float = 1.0, quote: str = "q") -> CheckAnchor:
    kwargs: dict = {
        "anchor_method": method,
        "anchor_confidence": conf,
        "quoted_text": quote,
    }
    if method in ("exact_span", "fuzzy_span"):
        kwargs["span_start"] = 0
        kwargs["span_end"] = len(quote)
    return CheckAnchor(**kwargs)


def test_limit_noop_for_small_list():
    anchors = [_a("exact_span"), _a("fuzzy_span", 0.8)]
    assert ResultRepository._apply_anchor_limit(anchors) == anchors


def test_limit_noop_for_exact_size():
    anchors = [_a("exact_span", quote=f"q{i}") for i in range(_MAX_ANCHORS_PER_CHECK_RESULT)]
    out = ResultRepository._apply_anchor_limit(anchors)
    assert len(out) == _MAX_ANCHORS_PER_CHECK_RESULT


def test_limit_truncates_to_max():
    # 10 anchors: 3 exact, 4 fuzzy, 3 page_only
    anchors = (
        [_a("exact_span", quote=f"e{i}") for i in range(3)]
        + [_a("fuzzy_span", 0.85, quote=f"f{i}") for i in range(4)]
        + [_a("page_only", 0.3, quote=f"p{i}") for i in range(3)]
    )
    out = ResultRepository._apply_anchor_limit(anchors)
    assert len(out) == _MAX_ANCHORS_PER_CHECK_RESULT
    # Топ-5: все exact (3) + 2 fuzzy (по confidence)
    methods = [a.anchor_method for a in out]
    assert methods.count(CheckAnchorMethod.EXACT_SPAN) == 3
    assert methods.count(CheckAnchorMethod.FUZZY_SPAN) == 2
    assert methods.count(CheckAnchorMethod.PAGE_ONLY) == 0


def test_limit_orders_by_method_strength_then_confidence():
    anchors = [
        _a("page_only", 0.9, quote="p1"),
        _a("exact_span", 1.0, quote="e1"),
        _a("clause_only", 0.5, quote="c1"),
        _a("fuzzy_span", 0.75, quote="f1"),
        _a("exact_span", 0.95, quote="e2"),
        _a("page_only", 0.95, quote="p2"),
    ]
    out = ResultRepository._apply_anchor_limit(anchors)
    assert len(out) == 5
    # strongest first: 2 exact, 1 fuzzy, 1 clause_only, 1 page_only (0.95 vs 0.9)
    assert out[0].anchor_method == CheckAnchorMethod.EXACT_SPAN
    assert out[0].anchor_confidence == 1.0
    assert out[1].anchor_method == CheckAnchorMethod.EXACT_SPAN
    assert out[1].anchor_confidence == 0.95
    assert out[2].anchor_method == CheckAnchorMethod.FUZZY_SPAN
    assert out[3].anchor_method == CheckAnchorMethod.CLAUSE_ONLY
    assert out[4].anchor_method == CheckAnchorMethod.PAGE_ONLY
    assert out[4].anchor_confidence == 0.95


def test_limit_empty_list():
    assert ResultRepository._apply_anchor_limit([]) == []

    