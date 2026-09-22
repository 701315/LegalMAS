"""
B4 — anchor normalization unit tests.

Проверяет:
- _normalize_anchors: валидные entries, невалидные, не-list, пустой список
- CheckAnchor round-trip через JSON-dump
- сохранение порядка (важно для tie-break select_primary_anchor)
"""

from __future__ import annotations

from core.anchors.models import CheckAnchor, CheckAnchorMethod
from engine.checks.result_normalizer import _normalize_anchors


def _make_anchor_dict(
    *,
    method: str = "exact_span",
    confidence: float = 1.0,
    quote: str = "цитата",
    span_start: int | None = 0,
    span_end: int | None = 6,
) -> dict:
    return {
        "anchor_method": method,
        "anchor_confidence": confidence,
        "quoted_text": quote,
        "span_start": span_start,
        "span_end": span_end,
        "layout_element_ids": [],
        "anchor_validation_passed": True,
        "anchor_diagnostics": {},
    }


# ── guards ──────────────────────────────────────────────────────────────────


def test_normalize_anchors_returns_empty_for_none():
    assert _normalize_anchors(None) == []


def test_normalize_anchors_returns_empty_for_non_list():
    assert _normalize_anchors({"anchor_method": "exact_span"}) == []
    assert _normalize_anchors("not-a-list") == []


def test_normalize_anchors_returns_empty_for_empty_list():
    assert _normalize_anchors([]) == []


# ── happy path ──────────────────────────────────────────────────────────────


def test_normalize_anchors_parses_valid_entries():
    raw = [_make_anchor_dict(), _make_anchor_dict(method="fuzzy_span", confidence=0.8)]
    anchors = _normalize_anchors(raw)
    assert len(anchors) == 2
    assert isinstance(anchors[0], CheckAnchor)
    assert anchors[0].anchor_method == CheckAnchorMethod.EXACT_SPAN
    assert anchors[1].anchor_method == CheckAnchorMethod.FUZZY_SPAN
    assert anchors[1].anchor_confidence == 0.8


def test_normalize_anchors_preserves_order():
    raw = [
        _make_anchor_dict(method="page_only", confidence=0.3),
        _make_anchor_dict(method="exact_span", confidence=1.0),
        _make_anchor_dict(method="clause_only", confidence=0.5),
    ]
    anchors = _normalize_anchors(raw)
    assert [a.anchor_method for a in anchors] == [
        CheckAnchorMethod.PAGE_ONLY,
        CheckAnchorMethod.EXACT_SPAN,
        CheckAnchorMethod.CLAUSE_ONLY,
    ]


# ── skip invalid ────────────────────────────────────────────────────────────


def test_normalize_anchors_skips_non_dict_entries():
    raw = [_make_anchor_dict(), "not-a-dict", 42, _make_anchor_dict()]
    anchors = _normalize_anchors(raw)
    assert len(anchors) == 2


def test_normalize_anchors_skips_invalid_anchor_dict():
    """Невалидный CheckAnchor (например, confidence вне [0,1]) — skip без падения."""
    raw = [
        _make_anchor_dict(),
        {
            "anchor_method": "exact_span",
            "anchor_confidence": 5.0,
        },
        _make_anchor_dict(),
    ]
    anchors = _normalize_anchors(raw)
    assert len(anchors) == 2


def test_normalize_anchors_round_trip_via_model_dump():
    original = CheckAnchor(
        anchor_method=CheckAnchorMethod.EXACT_SPAN,
        anchor_confidence=1.0,
        quoted_text="стороны применяют право РФ",
        span_start=0,
        span_end=27,
        layout_element_ids=["ru:node:3:0004"],
        anchor_validation_passed=True,
        anchor_diagnostics={"ratio": 1.0},
    )
    raw = [original.model_dump(mode="json")]
    anchors = _normalize_anchors(raw)
    assert len(anchors) == 1
    assert anchors[0].quoted_text == original.quoted_text
    assert anchors[0].span_start == 0
    assert anchors[0].span_end == 27
    assert anchors[0].layout_element_ids == ["ru:node:3:0004"]
