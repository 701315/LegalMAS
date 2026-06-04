"""
Tests for E1: skip_already_classified_units in enrichment eligibility.

Validates that units fully classified by deterministic rules
are skipped from LLM enrichment to save budget.
"""

from __future__ import annotations

from services.structure.legal_unit_models import (
    CitabilityMetrics,
    ClauseFunction,
    LegalUnit,
    LegalUnitType,
)
from services.structure.semantic_enrichment._policy import (
    _is_deterministic_source,
    is_unit_eligible_for_enrichment,
)
from services.structure.semantic_enrichment._types import SemanticEnrichmentPolicy


def _make_unit(
    *,
    unit_type: LegalUnitType = LegalUnitType.UNKNOWN,
    clause_function: ClauseFunction = ClauseFunction.UNKNOWN,
    unit_type_source: str = "",
    text: str = "Some legal clause text that is long enough for eligibility check.",
    is_heading_only: bool = False,
    is_technical_fallback: bool = False,
) -> LegalUnit:
    """Helper to build a minimal LegalUnit for testing."""
    diagnostics: dict = {}
    if unit_type_source:
        diagnostics["unit_type_source"] = unit_type_source

    return LegalUnit(
        unit_id="test-unit-001",
        raw_uid="1.1",
        scope="main",
        title="Test Clause",
        level=1,
        unit_type=unit_type,
        clause_function=clause_function,
        segment_id="segment-001",
        segment_type="contract",
        page_start=1,
        page_end=1,
        own_text=text,
        subtree_text=text,
        topic_tags=[],
        diagnostics=diagnostics,
        citability=CitabilityMetrics(
            has_own_text=bool(text),
            has_subtree_text=bool(text),
            is_heading_only=is_heading_only,
            is_technical_fallback=is_technical_fallback,
        ),
    )


# ── _is_deterministic_source ──────────────────────────────────────────────


class TestIsDeterministicSource:
    def test_title_pattern(self):
        unit = _make_unit(unit_type_source="title_pattern")
        assert _is_deterministic_source(unit) is True

    def test_keyword_match(self):
        unit = _make_unit(unit_type_source="keyword_match")
        assert _is_deterministic_source(unit) is True

    def test_rule_based(self):
        unit = _make_unit(unit_type_source="rule_based")
        assert _is_deterministic_source(unit) is True

    def test_default_mapping(self):
        unit = _make_unit(unit_type_source="default_mapping")
        assert _is_deterministic_source(unit) is True

    def test_llm_source_not_deterministic(self):
        unit = _make_unit(unit_type_source="llm_enrichment")
        assert _is_deterministic_source(unit) is False

    def test_empty_source_not_deterministic(self):
        unit = _make_unit(unit_type_source="")
        assert _is_deterministic_source(unit) is False

    def test_missing_diagnostics(self):
        unit = _make_unit()
        unit.diagnostics = None
        assert _is_deterministic_source(unit) is False

    def test_no_diagnostics_attr(self):
        unit = _make_unit()
        delattr(unit, "diagnostics")
        assert _is_deterministic_source(unit) is False


# ── is_unit_eligible_for_enrichment — skip already classified ─────────────


class TestSkipAlreadyClassified:
    def _policy(self, *, skip: bool = True) -> SemanticEnrichmentPolicy:
        return SemanticEnrichmentPolicy(skip_already_classified_units=skip)

    def test_fully_classified_rule_based_skipped(self):
        """Known type + known function + deterministic source → skip."""
        unit = _make_unit(
            unit_type=LegalUnitType.OBLIGATION,
            clause_function=ClauseFunction.OBLIGATIONS,
            unit_type_source="title_pattern",
        )
        eligible, reason = is_unit_eligible_for_enrichment(unit, policy=self._policy())
        assert eligible is False
        assert reason == "already_classified_by_rules"

    def test_type_unknown_not_skipped(self):
        """UNKNOWN type → should NOT be skipped."""
        unit = _make_unit(
            unit_type=LegalUnitType.UNKNOWN,
            clause_function=ClauseFunction.OBLIGATIONS,
            unit_type_source="title_pattern",
        )
        eligible, reason = is_unit_eligible_for_enrichment(unit, policy=self._policy())
        assert eligible is True
        assert reason is None

    def test_function_unknown_not_skipped(self):
        """Known type but UNKNOWN function → should NOT be skipped."""
        unit = _make_unit(
            unit_type=LegalUnitType.OBLIGATION,
            clause_function=ClauseFunction.UNKNOWN,
            unit_type_source="title_pattern",
        )
        eligible, reason = is_unit_eligible_for_enrichment(unit, policy=self._policy())
        assert eligible is True
        assert reason is None

    def test_non_deterministic_source_not_skipped(self):
        """LLM/non-rule source → should NOT be skipped."""
        unit = _make_unit(
            unit_type=LegalUnitType.OBLIGATION,
            clause_function=ClauseFunction.OBLIGATIONS,
            unit_type_source="llm_enrichment",
        )
        eligible, reason = is_unit_eligible_for_enrichment(unit, policy=self._policy())
        assert eligible is True
        assert reason is None

    def test_skip_disabled_by_policy(self):
        """When skip flag is disabled → unit stays eligible."""
        unit = _make_unit(
            unit_type=LegalUnitType.OBLIGATION,
            clause_function=ClauseFunction.OBLIGATIONS,
            unit_type_source="title_pattern",
        )
        eligible, reason = is_unit_eligible_for_enrichment(
            unit,
            policy=self._policy(skip=False),
        )
        assert eligible is True
        assert reason is None

    def test_all_deterministic_sources_trigger_skip(self):
        """Each deterministic source should trigger skip."""
        for source in ("title_pattern", "keyword_match", "rule_based", "default_mapping"):
            unit = _make_unit(
                unit_type=LegalUnitType.WARRANTY,
                clause_function=ClauseFunction.REPRESENTATIONS,
                unit_type_source=source,
            )
            eligible, reason = is_unit_eligible_for_enrichment(
                unit,
                policy=self._policy(),
            )
            assert eligible is False, f"Expected skip for source={source}"
            assert reason == "already_classified_by_rules"

    def test_technical_fallback_still_skipped_first(self):
        """technical_fallback guard should still win first."""
        unit = _make_unit(
            unit_type=LegalUnitType.OBLIGATION,
            clause_function=ClauseFunction.OBLIGATIONS,
            unit_type_source="title_pattern",
            is_technical_fallback=True,
        )
        eligible, reason = is_unit_eligible_for_enrichment(unit, policy=self._policy())
        assert eligible is False
        assert reason == "technical_fallback"

    def test_heading_only_still_skipped_first(self):
        """heading_only guard should still win first."""
        unit = _make_unit(
            unit_type=LegalUnitType.OBLIGATION,
            clause_function=ClauseFunction.OBLIGATIONS,
            unit_type_source="title_pattern",
            is_heading_only=True,
        )
        eligible, reason = is_unit_eligible_for_enrichment(unit, policy=self._policy())
        assert eligible is False
        assert reason == "heading_only"

    def test_text_too_short_still_skipped_first(self):
        """Short text guard should still win first."""
        unit = _make_unit(
            unit_type=LegalUnitType.OBLIGATION,
            clause_function=ClauseFunction.OBLIGATIONS,
            unit_type_source="title_pattern",
            text="short",
        )
        eligible, reason = is_unit_eligible_for_enrichment(unit, policy=self._policy())
        assert eligible is False
        assert reason == "text_too_short"

        

