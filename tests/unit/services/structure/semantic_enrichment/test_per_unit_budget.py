"""
Tests for per-unit enrichment timeout budget computation.

Covers:
- explicit config path
- derived path (segment_timeout / eligible_count)
- minimum floor enforcement
- segment timeout cap (per-unit never exceeds segment)
- edge cases: zero units, zero segment timeout
"""

from unittest.mock import MagicMock

from services.structure.semantic_enrichment._budget import (
    resolve_per_unit_enrichment_timeout,
)


def _make_settings(
    *,
    per_unit_timeout: int = 0,
    per_unit_min: int = 30,
) -> MagicMock:
    s = MagicMock()
    s.SEMANTIC_ENRICHMENT_PER_UNIT_TIMEOUT_SECONDS = per_unit_timeout
    s.SEMANTIC_ENRICHMENT_PER_UNIT_MIN_TIMEOUT_SECONDS = per_unit_min
    return s


class TestExplicitConfig:
    def test_explicit_timeout_used_when_positive(self) -> None:
        s = _make_settings(per_unit_timeout=180, per_unit_min=30)
        result = resolve_per_unit_enrichment_timeout(
            settings=s,
            eligible_unit_count=10,
            segment_timeout_seconds=900.0,
        )
        assert result == 180.0

    def test_explicit_timeout_capped_by_segment_timeout(self) -> None:
        s = _make_settings(per_unit_timeout=500, per_unit_min=30)
        result = resolve_per_unit_enrichment_timeout(
            settings=s,
            eligible_unit_count=10,
            segment_timeout_seconds=200.0,
        )
        assert result == 200.0

    def test_explicit_timeout_respects_min_floor(self) -> None:
        s = _make_settings(per_unit_timeout=10, per_unit_min=30)
        result = resolve_per_unit_enrichment_timeout(
            settings=s,
            eligible_unit_count=10,
            segment_timeout_seconds=900.0,
        )
        assert result == 30.0


class TestDerivedFromSegmentBudget:
    def test_derived_evenly_splits_segment_budget(self) -> None:
        s = _make_settings(per_unit_timeout=0, per_unit_min=30)
        result = resolve_per_unit_enrichment_timeout(
            settings=s,
            eligible_unit_count=10,
            segment_timeout_seconds=900.0,
        )
        assert result == 90.0

    def test_derived_respects_min_floor(self) -> None:
        s = _make_settings(per_unit_timeout=0, per_unit_min=30)
        result = resolve_per_unit_enrichment_timeout(
            settings=s,
            eligible_unit_count=100,
            segment_timeout_seconds=900.0,
        )
        assert result == 30.0

    def test_derived_capped_by_segment_timeout(self) -> None:
        s = _make_settings(per_unit_timeout=0, per_unit_min=30)
        result = resolve_per_unit_enrichment_timeout(
            settings=s,
            eligible_unit_count=1,
            segment_timeout_seconds=20.0,
        )
        # segment_timeout=20 < per_unit_min=30 → return segment_timeout
        assert result == 20.0


class TestEdgeCases:
    def test_zero_eligible_units_uses_count_one(self) -> None:
        s = _make_settings(per_unit_timeout=0, per_unit_min=30)
        result = resolve_per_unit_enrichment_timeout(
            settings=s,
            eligible_unit_count=0,
            segment_timeout_seconds=900.0,
        )
        assert result == 900.0

    def test_zero_segment_timeout_returns_min(self) -> None:
        s = _make_settings(per_unit_timeout=0, per_unit_min=30)
        result = resolve_per_unit_enrichment_timeout(
            settings=s,
            eligible_unit_count=10,
            segment_timeout_seconds=0.0,
        )
        assert result == 30.0

    def test_negative_segment_timeout_returns_min(self) -> None:
        s = _make_settings(per_unit_timeout=0, per_unit_min=30)
        result = resolve_per_unit_enrichment_timeout(
            settings=s,
            eligible_unit_count=10,
            segment_timeout_seconds=-100.0,
        )
        assert result == 30.0

    def test_segment_timeout_smaller_than_min_returns_segment_timeout(self) -> None:
        """When segment budget is very tight, per-unit gets the whole segment budget."""
        s = _make_settings(per_unit_timeout=0, per_unit_min=60)
        result = resolve_per_unit_enrichment_timeout(
            settings=s,
            eligible_unit_count=5,
            segment_timeout_seconds=15.0,
        )
        assert result == 15.0


        