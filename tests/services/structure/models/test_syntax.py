# tests/services/structure/models/test_syntax.py

"""Tests for Phase 2 — SyntaxHeadingCandidate and HierarchyTokenType."""

from __future__ import annotations

import pytest

from services.structure.models import (
    HEADING_CONFIDENCE_THRESHOLD,
    HierarchyTokenType,
    SyntaxHeadingCandidate,
    scored_to_syntax_candidate,
)


def _make_candidate(**kwargs) -> SyntaxHeadingCandidate:
    defaults = dict(
        element_index=0,
        element_id="el_001",
        raw_text="1. Предмет договора",
        raw_uid="1",
        title="Предмет договора",
        page=1,
        token_type=HierarchyTokenType.NUMERIC,
        heading_confidence=0.85,
        scope="main_contract",
    )
    defaults.update(kwargs)
    return SyntaxHeadingCandidate(**defaults)


class TestHierarchyTokenType:
    def test_all_values_exist(self):
        types = {t.value for t in HierarchyTokenType}
        assert types == {"numeric", "roman", "alpha", "keyword", "bullet", "unknown"}

    def test_string_comparison(self):
        assert HierarchyTokenType.NUMERIC == "numeric"


class TestSyntaxHeadingCandidate:
    def test_basic_creation(self):
        c = _make_candidate()
        assert c.raw_uid == "1"
        assert c.title == "Предмет договора"
        assert c.token_type == HierarchyTokenType.NUMERIC
        assert c.heading_confidence == 0.85

    def test_participates_in_hierarchy_above_threshold(self):
        c = _make_candidate(heading_confidence=0.85)
        assert c.participates_in_hierarchy is True

    def test_participates_in_hierarchy_at_threshold(self):
        c = _make_candidate(heading_confidence=0.5)
        assert c.participates_in_hierarchy is True

    def test_does_not_participate_below_threshold(self):
        c = _make_candidate(heading_confidence=0.49)
        assert c.participates_in_hierarchy is False

    def test_zero_confidence_is_body_text(self):
        c = _make_candidate(heading_confidence=0.0)
        assert c.participates_in_hierarchy is False

    def test_confidence_out_of_range_raises(self):
        with pytest.raises(ValueError, match="heading_confidence"):
            _make_candidate(heading_confidence=1.1)

    def test_confidence_negative_raises(self):
        with pytest.raises(ValueError, match="heading_confidence"):
            _make_candidate(heading_confidence=-0.1)

    def test_uid_alias(self):
        c = _make_candidate(raw_uid="3.1")
        assert c.uid == "3.1"

    def test_optional_pdf_fields(self):
        c = _make_candidate(font_size=14.0, is_bold=True, indent=28.5)
        assert c.font_size == 14.0
        assert c.is_bold is True
        assert c.indent == 28.5

    def test_to_dict(self):
        c = _make_candidate()
        d = c.to_dict()
        assert d["token_type"] == "numeric"
        assert d["heading_confidence"] == 0.85
        assert d["participates_in_hierarchy"] is True
        assert d["scope"] == "main_contract"

    def test_threshold_constant(self):
        assert HEADING_CONFIDENCE_THRESHOLD == 0.5


class TestScoredToSyntaxAdapter:
    def test_numeric_uid_inferred(self):
        class FakeScored:
            score = 0.9
            accept_reasons = ["toc_match"]
            reject_reasons = []
            metadata = {}

            class raw:
                element_index = 5
                element_id = "el_005"
                raw_text = "3.1 Стороны договора"
                raw_uid = "3.1"
                title = "Стороны договора"
                page = 2
                scope = "main_contract"

        result = scored_to_syntax_candidate(FakeScored())
        assert result.token_type == HierarchyTokenType.NUMERIC
        assert result.heading_confidence == 0.9
        assert result.participates_in_hierarchy is True
        assert "accept:toc_match" in result.confidence_reasons

    def test_low_score_does_not_participate(self):
        class FakeScored:
            score = 0.3
            accept_reasons = []
            reject_reasons = ["garbage_title"]
            metadata = {}

            class raw:
                element_index = 1
                element_id = "el_001"
                raw_text = "1.1 ."
                raw_uid = "1.1"
                title = "."
                page = 1
                scope = "main_contract"

        result = scored_to_syntax_candidate(FakeScored())
        assert result.participates_in_hierarchy is False

    def test_keyword_type_inferred(self):
        class FakeScored:
            score = 0.8
            accept_reasons = []
            reject_reasons = []
            metadata = {}

            class raw:
                element_index = 2
                element_id = "el_002"
                raw_text = "Section 4 Payment terms"
                raw_uid = "4"
                title = "Payment terms"
                page = 3
                scope = "main_contract"

        result = scored_to_syntax_candidate(FakeScored())
        assert result.token_type == HierarchyTokenType.KEYWORD

        