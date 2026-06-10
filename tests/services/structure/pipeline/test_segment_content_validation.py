"""
Tests for B1: Segment Content Validation.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from services.structure._pipeline._segment_content_validation import (
    validate_segment_content,
    _MIN_MEANINGFUL_CHARS,
    _count_meaningful_chars,
)


def _make_segment(
    *,
    segment_id: str = "seg-1",
    segment_order: int = 0,
    segment_type: str = "contract",
    element_start: int = 0,
    element_end: int = 5,
) -> MagicMock:
    seg = MagicMock()
    seg.segment_id = segment_id
    seg.segment_order = segment_order
    seg.segment_type = segment_type
    seg.element_start = element_start
    seg.element_end = element_end
    return seg


def _make_element(text: str = "", element_type: str = "body_text") -> dict:
    return {"text": text, "element_type": element_type}


def _make_elements(texts: list[str], element_type: str = "body_text") -> list[dict]:
    return [_make_element(text=t, element_type=element_type) for t in texts]


class TestCountMeaningfulChars:
    def test_counts_body_text(self):
        seg = _make_segment(element_start=0, element_end=2)
        elements = _make_elements(["Hello world", "Another line"])
        assert _count_meaningful_chars(seg, elements) == len("Hello world") + len("Another line")

    def test_excludes_page_artifacts(self):
        seg = _make_segment(element_start=0, element_end=2)
        elements = [
            _make_element("Page 1", element_type="page_artifact"),
            _make_element("Real content", element_type="body_text"),
        ]
        assert _count_meaningful_chars(seg, elements) == len("Real content")

    def test_excludes_signature_block(self):
        seg = _make_segment(element_start=0, element_end=1)
        elements = [_make_element("Подпись", element_type="signature_block")]
        assert _count_meaningful_chars(seg, elements) == 0

    def test_excludes_toc_elements(self):
        seg = _make_segment(element_start=0, element_end=3)
        elements = [
            _make_element("Contents", element_type="toc_header"),
            _make_element("1. Introduction ... 1", element_type="toc_line"),
            _make_element("Real clause text", element_type="body_text"),
        ]
        assert _count_meaningful_chars(seg, elements) == len("Real clause text")

    def test_empty_elements(self):
        seg = _make_segment(element_start=0, element_end=3)
        elements = _make_elements(["", "  ", ""])
        assert _count_meaningful_chars(seg, elements) == 0

    def test_partial_slice(self):
        seg = _make_segment(element_start=1, element_end=3)
        elements = _make_elements(["ignored", "counted", "also counted", "ignored"])
        expected = len("counted") + len("also counted")
        assert _count_meaningful_chars(seg, elements) == expected


class TestValidateSegmentContent:

    def test_valid_segments_no_warnings(self):
        texts = ["A" * 100, "B" * 100, "C" * 100, "D" * 100, "E" * 100]
        elements = _make_elements(texts)
        seg = _make_segment(element_start=0, element_end=5)
        result = validate_segment_content([seg], elements, document_id="doc-1")
        assert result.all_valid is True
        assert result.has_warnings is False
        assert result.empty_segments == []
        assert result.short_segments == []

    def test_empty_segment_detected(self):
        elements = _make_elements(["", "", ""])
        seg = _make_segment(segment_id="seg-empty", element_start=0, element_end=3)
        result = validate_segment_content([seg], elements, document_id="doc-1")
        assert "seg-empty" in result.empty_segments
        assert result.has_warnings is True

    def test_short_segment_detected(self):
        short_text = "x" * (_MIN_MEANINGFUL_CHARS - 1)
        elements = _make_elements([short_text])
        seg = _make_segment(segment_id="seg-short", element_start=0, element_end=1)
        result = validate_segment_content([seg], elements, document_id="doc-1")
        assert "seg-short" in result.short_segments
        assert result.has_warnings is True
        assert result.empty_segments == []

    def test_segment_at_exact_threshold_not_short(self):
        text = "x" * _MIN_MEANINGFUL_CHARS
        elements = _make_elements([text])
        seg = _make_segment(element_start=0, element_end=1)
        result = validate_segment_content([seg], elements, document_id="doc-1")
        assert result.short_segments == []
        assert result.has_warnings is False

    def test_all_empty_segments_sets_all_valid_false(self):
        elements = _make_elements(["", "", ""])
        seg1 = _make_segment(segment_id="s1", element_start=0, element_end=1)
        seg2 = _make_segment(segment_id="s2", element_start=1, element_end=2)
        seg3 = _make_segment(segment_id="s3", element_start=2, element_end=3)
        result = validate_segment_content([seg1, seg2, seg3], elements, document_id="doc-1")
        assert result.all_valid is False

    def test_one_empty_among_valid_keeps_all_valid_true(self):
        elements = _make_elements(["", "A" * 100])
        seg1 = _make_segment(segment_id="s1", element_start=0, element_end=1)
        seg2 = _make_segment(segment_id="s2", element_start=1, element_end=2)
        result = validate_segment_content([seg1, seg2], elements, document_id="doc-1")
        assert result.all_valid is True
        assert "s1" in result.empty_segments
        assert result.has_warnings is True

    def test_duplicate_segment_ids_detected(self):
        elements = _make_elements(["A" * 100, "B" * 100])
        seg1 = _make_segment(segment_id="same-id", element_start=0, element_end=1)
        seg2 = _make_segment(segment_id="same-id", element_start=1, element_end=2)
        result = validate_segment_content([seg1, seg2], elements, document_id="doc-1")
        assert "same-id" in result.duplicate_ids
        assert result.has_warnings is True

    def test_no_duplicate_ids_for_unique_ids(self):
        elements = _make_elements(["A" * 100, "B" * 100])
        seg1 = _make_segment(segment_id="seg-1", element_start=0, element_end=1)
        seg2 = _make_segment(segment_id="seg-2", element_start=1, element_end=2)
        result = validate_segment_content([seg1, seg2], elements, document_id="doc-1")
        assert result.duplicate_ids == []

    def test_overlapping_ranges_detected(self):
        elements = _make_elements(["A" * 50] * 5)
        seg1 = _make_segment(segment_id="seg-1", element_start=0, element_end=3)
        seg2 = _make_segment(segment_id="seg-2", element_start=2, element_end=5)
        result = validate_segment_content([seg1, seg2], elements, document_id="doc-1")
        assert ("seg-1", "seg-2") in result.overlapping_ranges
        assert result.has_warnings is True

    def test_adjacent_ranges_not_overlapping(self):
        elements = _make_elements(["A" * 50] * 4)
        seg1 = _make_segment(segment_id="seg-1", element_start=0, element_end=2)
        seg2 = _make_segment(segment_id="seg-2", element_start=2, element_end=4)
        result = validate_segment_content([seg1, seg2], elements, document_id="doc-1")
        assert result.overlapping_ranges == []

    def test_empty_segments_list_returns_valid(self):
        result = validate_segment_content([], [], document_id="doc-1")
        assert result.all_valid is True
        assert result.has_warnings is False

    def test_to_dict_has_expected_keys(self):
        elements = _make_elements(["A" * 100])
        seg = _make_segment(element_start=0, element_end=1)
        result = validate_segment_content([seg], elements, document_id="doc-1")
        d = result.to_dict()
        assert "all_valid" in d
        assert "has_warnings" in d
        assert "empty_segments" in d
        assert "short_segments" in d
        assert "duplicate_ids" in d
        assert "overlapping_ranges" in d
        assert "diagnostics_count" in d


        