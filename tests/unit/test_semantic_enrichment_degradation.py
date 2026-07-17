"""
Pure-logic tests for semantic enrichment degradation analysis.

Не тянет ORM/Celery импорты.
Проверяет:
- вычисление enrichment_ratio,
- severity thresholds (minor / partial / critical),
- сбор machine-readable reason codes,
- degraded_reason (joined by ";"),
- поведение при outcome != DEGRADED.
"""

from __future__ import annotations

from core.constants import SemanticEnrichmentStageOutcome
from core.semantic_enrichment_degradation import (
    derive_semantic_enrichment_degradation,
)


def _derive(
    *,
    outcome: SemanticEnrichmentStageOutcome = SemanticEnrichmentStageOutcome.DEGRADED,
    segments_enriched: int = 0,
    segments_with_legal_units_ref: int = 10,
    segments_timed_out: int = 0,
    segments_failed: int = 0,
    segments_skipped_budget: int = 0,
    persist_mismatch_count: int = 0,
    primary_missing_count: int = 0,
) -> dict:
    return derive_semantic_enrichment_degradation(
        outcome=outcome,
        segments_enriched=segments_enriched,
        segments_with_legal_units_ref=segments_with_legal_units_ref,
        segments_timed_out=segments_timed_out,
        segments_failed=segments_failed,
        segments_skipped_budget=segments_skipped_budget,
        persist_mismatch_count=persist_mismatch_count,
        primary_missing_count=primary_missing_count,
    )


class TestEnrichmentRatio:
    def test_ratio_full_enrichment(self):
        result = _derive(segments_enriched=10, segments_with_legal_units_ref=10)
        assert result["enrichment_ratio"] == 1.0

    def test_ratio_zero_enrichment(self):
        result = _derive(segments_enriched=0, segments_with_legal_units_ref=10)
        assert result["enrichment_ratio"] == 0.0

    def test_ratio_partial_enrichment(self):
        result = _derive(segments_enriched=5, segments_with_legal_units_ref=10)
        assert result["enrichment_ratio"] == 0.5

    def test_ratio_no_candidates_returns_zero(self):
        result = _derive(segments_enriched=0, segments_with_legal_units_ref=0)
        assert result["enrichment_ratio"] == 0.0

    def test_ratio_rounded_to_4_decimals(self):
        result = _derive(segments_enriched=1, segments_with_legal_units_ref=3)
        assert result["enrichment_ratio"] == round(1 / 3, 4)


class TestDegradationSeverity:
    def test_severity_minor_at_exact_threshold(self):
        result = _derive(segments_enriched=8, segments_with_legal_units_ref=10)
        assert result["degradation_severity"] == "minor"

    def test_severity_minor_above_threshold(self):
        result = _derive(segments_enriched=9, segments_with_legal_units_ref=10)
        assert result["degradation_severity"] == "minor"

    def test_severity_partial_at_lower_boundary(self):
        result = _derive(segments_enriched=2, segments_with_legal_units_ref=10)
        assert result["degradation_severity"] == "partial"

    def test_severity_partial_in_middle(self):
        result = _derive(segments_enriched=5, segments_with_legal_units_ref=10)
        assert result["degradation_severity"] == "partial"

    def test_severity_partial_just_below_minor(self):
        result = _derive(segments_enriched=7, segments_with_legal_units_ref=10)
        assert result["degradation_severity"] == "partial"

    def test_severity_critical_at_zero(self):
        result = _derive(segments_enriched=0, segments_with_legal_units_ref=10)
        assert result["degradation_severity"] == "critical"

    def test_severity_critical_below_partial_threshold(self):
        result = _derive(segments_enriched=1, segments_with_legal_units_ref=10)
        assert result["degradation_severity"] == "critical"


class TestDegradationReasons:
    def test_timeout_reason_added(self):
        result = _derive(segments_timed_out=2)
        assert "segment_timeout" in result["degradation_reasons"]

    def test_failure_reason_added(self):
        result = _derive(segments_failed=1)
        assert "segment_failure" in result["degradation_reasons"]

    def test_budget_exhausted_reason_added(self):
        result = _derive(segments_skipped_budget=3)
        assert "budget_exhausted" in result["degradation_reasons"]

    def test_persist_mismatch_reason_added(self):
        result = _derive(persist_mismatch_count=2)
        assert "persist_mismatch" in result["degradation_reasons"]

    def test_primary_missing_reason_added(self):
        result = _derive(primary_missing_count=1)
        assert "primary_missing_enrichment" in result["degradation_reasons"]

    def test_multiple_reasons_all_present(self):
        result = _derive(
            segments_timed_out=2,
            segments_failed=1,
            segments_skipped_budget=1,
            persist_mismatch_count=1,
            primary_missing_count=1,
        )
        reasons = result["degradation_reasons"]
        assert "segment_timeout" in reasons
        assert "segment_failure" in reasons
        assert "budget_exhausted" in reasons
        assert "persist_mismatch" in reasons
        assert "primary_missing_enrichment" in reasons

    def test_primary_missing_comes_first_in_reasons(self):
        result = _derive(
            segments_timed_out=1,
            primary_missing_count=1,
        )
        assert result["degradation_reasons"][0] == "primary_missing_enrichment"

    def test_no_reasons_when_no_issues(self):
        result = _derive(
            segments_enriched=8,
            segments_with_legal_units_ref=10,
            segments_failed=2,
        )
        assert len(result["degradation_reasons"]) > 0

    def test_empty_reasons_only_when_degraded_is_false(self):
        result = _derive(
            outcome=SemanticEnrichmentStageOutcome.COMPLETED,
            segments_enriched=10,
            segments_with_legal_units_ref=10,
        )
        assert result["degradation_reasons"] == []


class TestDegradedReason:
    def test_degraded_reason_joined_by_semicolon(self):
        result = _derive(
            segments_timed_out=1,
            segments_failed=1,
        )
        parts = result["degraded_reason"].split(";")
        assert len(parts) == 2
        assert "segment_timeout" in parts
        assert "segment_failure" in parts

    def test_degraded_reason_single_cause(self):
        result = _derive(segments_failed=1)
        assert result["degraded_reason"] == "segment_failure"

    def test_degraded_reason_none_when_not_degraded(self):
        result = _derive(
            outcome=SemanticEnrichmentStageOutcome.COMPLETED,
            segments_enriched=10,
            segments_with_legal_units_ref=10,
        )
        assert result["degraded_reason"] is None


class TestNonDegradedOutcomes:
    def test_completed_outcome_has_no_degradation(self):
        result = _derive(
            outcome=SemanticEnrichmentStageOutcome.COMPLETED,
            segments_enriched=10,
            segments_with_legal_units_ref=10,
        )
        assert result["degraded"] is False
        assert result["degradation_severity"] is None
        assert result["degradation_reasons"] == []
        assert result["degraded_reason"] is None

    def test_skipped_outcome_has_no_degradation(self):
        result = _derive(
            outcome=SemanticEnrichmentStageOutcome.SKIPPED,
            segments_enriched=0,
            segments_with_legal_units_ref=0,
        )
        assert result["degraded"] is False
        assert result["degradation_severity"] is None

    def test_timed_out_outcome_has_no_degradation(self):
        result = _derive(
            outcome=SemanticEnrichmentStageOutcome.TIMED_OUT,
            segments_enriched=0,
            segments_with_legal_units_ref=5,
            segments_timed_out=5,
        )
        assert result["degraded"] is False
        assert result["degradation_severity"] is None

    def test_unavailable_outcome_has_no_degradation(self):
        result = _derive(
            outcome=SemanticEnrichmentStageOutcome.UNAVAILABLE,
            segments_enriched=0,
            segments_with_legal_units_ref=0,
        )
        assert result["degraded"] is False
        assert result["degradation_severity"] is None


class TestDegradedFlag:
    def test_degraded_flag_true_for_degraded_outcome(self):
        result = _derive(
            outcome=SemanticEnrichmentStageOutcome.DEGRADED,
            segments_enriched=5,
            segments_with_legal_units_ref=10,
            segments_failed=5,
        )
        assert result["degraded"] is True

    def test_degraded_flag_false_for_completed(self):
        result = _derive(
            outcome=SemanticEnrichmentStageOutcome.COMPLETED,
            segments_enriched=10,
            segments_with_legal_units_ref=10,
        )
        assert result["degraded"] is False


class TestDegradedSegmentsCount:
    def test_degraded_segments_sum_of_all_non_enriched(self):
        result = _derive(
            segments_timed_out=2,
            segments_failed=3,
            segments_skipped_budget=1,
        )
        assert result["degraded_segments"] == 6

    def test_degraded_segments_zero_when_all_enriched(self):
        result = _derive(
            outcome=SemanticEnrichmentStageOutcome.COMPLETED,
            segments_enriched=10,
            segments_with_legal_units_ref=10,
        )
        assert result["degraded_segments"] == 0


        