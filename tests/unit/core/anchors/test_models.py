from __future__ import annotations

import pytest

from core.anchors.models import CheckAnchor, CheckAnchorMethod


def test_anchor_minimal_valid() -> None:
    a = CheckAnchor(anchor_method=CheckAnchorMethod.CLAUSE_ONLY, anchor_confidence=0.5)
    assert a.anchor_method == CheckAnchorMethod.CLAUSE_ONLY
    assert a.layout_element_ids == []
    assert a.anchor_diagnostics == {}
    assert a.anchor_validation_passed is False


def test_anchor_full_exact_span() -> None:
    a = CheckAnchor(
        clause_uid="main_contract:7.3.2",
        clause_ref="п. 7.3.2",
        quoted_text="Сторона обязуется...",
        span_start=120,
        span_end=180,
        source_content_hash="a" * 64,
        page=4,
        layout_element_ids=["ru:node:4:0010"],
        bbox_union=[85.15, 304.95, 572.45, 380.38],
        segment_id="main_contract",
        anchor_method=CheckAnchorMethod.EXACT_SPAN,
        anchor_confidence=1.0,
        anchor_validation_passed=True,
    )
    assert a.span_start == 120 and a.span_end == 180


def test_anchor_extra_field_rejected() -> None:
    with pytest.raises(ValueError):
        CheckAnchor(
            anchor_method=CheckAnchorMethod.CLAUSE_ONLY,
            anchor_confidence=0.5,
            unknown_field="x",  # type: ignore[call-arg]
        )


@pytest.mark.parametrize("bad", [-0.01, 1.01, 2.0])
def test_confidence_out_of_range(bad: float) -> None:
    with pytest.raises(ValueError, match="anchor_confidence"):
        CheckAnchor(anchor_method=CheckAnchorMethod.FUZZY_SPAN, anchor_confidence=bad)


@pytest.mark.parametrize(
    "bad",
    [
        [1.0, 2.0, 3.0],
        [1.0, 2.0, 3.0, 4.0, 5.0],
        [3.0, 2.0, 1.0, 4.0],       # x0 > x1
        [1.0, 5.0, 2.0, 4.0],       # top > bottom
        [float("nan"), 2.0, 3.0, 4.0],
    ],
)
def test_bbox_invalid(bad: list[float]) -> None:
    with pytest.raises(ValueError, match="bbox_union"):
        CheckAnchor(
            anchor_method=CheckAnchorMethod.EXACT_SPAN,
            anchor_confidence=1.0,
            bbox_union=bad,
        )


def test_span_must_be_paired() -> None:
    with pytest.raises(ValueError, match="span_start and span_end"):
        CheckAnchor(
            anchor_method=CheckAnchorMethod.EXACT_SPAN,
            anchor_confidence=1.0,
            span_start=10,
        )


def test_span_end_before_start() -> None:
    with pytest.raises(ValueError, match="span_end must be"):
        CheckAnchor(
            anchor_method=CheckAnchorMethod.EXACT_SPAN,
            anchor_confidence=1.0,
            span_start=200, span_end=100,
        )


def test_span_negative_rejected() -> None:
    with pytest.raises(ValueError, match="span offsets"):
        CheckAnchor(
            anchor_method=CheckAnchorMethod.EXACT_SPAN,
            anchor_confidence=1.0,
            span_start=-1, span_end=10,
        )


def test_page_must_be_positive() -> None:
    with pytest.raises(ValueError, match="page must be"):
        CheckAnchor(
            anchor_method=CheckAnchorMethod.PAGE_ONLY,
            anchor_confidence=0.3,
            page=0,
        )


def test_none_method_requires_zero_confidence() -> None:
    with pytest.raises(ValueError, match="anchor_method=NONE"):
        CheckAnchor(anchor_method=CheckAnchorMethod.NONE, anchor_confidence=0.5)


def test_none_method_with_zero_confidence_ok() -> None:
    a = CheckAnchor(anchor_method=CheckAnchorMethod.NONE, anchor_confidence=0.0)
    assert a.anchor_method == CheckAnchorMethod.NONE


def test_source_hash_wrong_length_rejected() -> None:
    with pytest.raises(ValueError, match="source_content_hash"):
        CheckAnchor(
            anchor_method=CheckAnchorMethod.EXACT_SPAN,
            anchor_confidence=1.0,
            source_content_hash="short",
        )


def test_source_hash_non_hex_rejected() -> None:
    with pytest.raises(ValueError, match="source_content_hash"):
        CheckAnchor(
            anchor_method=CheckAnchorMethod.EXACT_SPAN,
            anchor_confidence=1.0,
            source_content_hash="z" * 64,
        )


def test_source_hash_lowercased() -> None:
    a = CheckAnchor(
        anchor_method=CheckAnchorMethod.EXACT_SPAN,
        anchor_confidence=1.0,
        source_content_hash="A" * 64,
    )
    assert a.source_content_hash == "a" * 64

    