# tests/unit/engine/enrichment/test_per_unit_timeout_adaptive.py
"""
Tests for resolve_per_unit_enrichment_timeout adaptive behavior.

Invariant: when PER_UNIT_TIMEOUT_SECONDS=0 (adaptive mode),
timeout must be derived from segment_timeout / eligible_unit_count,
with floor at PER_UNIT_MIN_TIMEOUT_SECONDS.

Why this matters:
  With fixed 180s per unit and 47 eligible units in 900s segment,
  only ~5 units are processed (900 / 180 = 5).
  Adaptive gives each unit ~30s (floor), processing ~30 units instead.
"""

import pytest
from unittest.mock import MagicMock

from services.structure.semantic_enrichment._budget import (
    resolve_per_unit_enrichment_timeout,
)


def _make_settings(
    *,
    per_unit_explicit: int = 0,
    per_unit_min: int = 30,
) -> MagicMock:
    s = MagicMock()
    s.SEMANTIC_ENRICHMENT_PER_UNIT_TIMEOUT_SECONDS = per_unit_explicit
    s.SEMANTIC_ENRICHMENT_PER_UNIT_MIN_TIMEOUT_SECONDS = per_unit_min
    return s


class TestResolvePerUnitTimeout:

    def test_explicit_zero_uses_derived_path(self):
        """When PER_UNIT_TIMEOUT=0, timeout derived from segment_timeout / count."""
        settings = _make_settings(per_unit_explicit=0, per_unit_min=30)
        result = resolve_per_unit_enrichment_timeout(
            settings=settings,
            eligible_unit_count=10,
            segment_timeout_seconds=300.0,
        )
        # derived = 300 / 10 = 30, floor = 30 → result = 30
        assert result == pytest.approx(30.0)

    def test_explicit_positive_uses_explicit(self):
        """When PER_UNIT_TIMEOUT > 0, explicit value is used."""
        settings = _make_settings(per_unit_explicit=180, per_unit_min=30)
        result = resolve_per_unit_enrichment_timeout(
            settings=settings,
            eligible_unit_count=47,
            segment_timeout_seconds=900.0,
        )
        assert result == pytest.approx(180.0)

    def test_adaptive_respects_min_floor(self):
        """Derived timeout never goes below per_unit_min_timeout."""
        settings = _make_settings(per_unit_explicit=0, per_unit_min=30)
        result = resolve_per_unit_enrichment_timeout(
            settings=settings,
            eligible_unit_count=100,
            segment_timeout_seconds=900.0,
        )
        # derived = 900 / 100 = 9 < floor 30 → result = 30
        assert result == pytest.approx(30.0)

    def test_adaptive_does_not_exceed_segment_timeout(self):
        """Per-unit timeout never exceeds segment_timeout."""
        settings = _make_settings(per_unit_explicit=0, per_unit_min=30)
        result = resolve_per_unit_enrichment_timeout(
            settings=settings,
            eligible_unit_count=1,
            segment_timeout_seconds=20.0,
        )
        # derived = 20, floor pushes to 30, but segment cap = 20
        assert result == pytest.approx(20.0)

    def test_realistic_cpu_only_scenario(self):
        """
        47 eligible units, 900s segment timeout.
        Adaptive result must be much less than old fixed 180s.
        """
        settings = _make_settings(per_unit_explicit=0, per_unit_min=30)
        result = resolve_per_unit_enrichment_timeout(
            settings=settings,
            eligible_unit_count=47,
            segment_timeout_seconds=900.0,
        )
        # derived = 900/47 ≈ 19.1, floor = 30
        assert result == pytest.approx(30.0)
        assert result < 180.0, (
            f"Adaptive timeout ({result}s) must be less than fixed 180s "
            "otherwise segment budget is starved on CPU-only inference"
        )

    def test_zero_eligible_units_no_division_error(self):
        """eligible_unit_count=0 must not divide by zero."""
        settings = _make_settings(per_unit_explicit=0, per_unit_min=30)
        result = resolve_per_unit_enrichment_timeout(
            settings=settings,
            eligible_unit_count=0,
            segment_timeout_seconds=300.0,
        )
        assert result > 0

    def test_zero_segment_timeout_returns_min(self):
        """segment_timeout=0 returns per_unit_min (safe floor)."""
        settings = _make_settings(per_unit_explicit=0, per_unit_min=30)
        result = resolve_per_unit_enrichment_timeout(
            settings=settings,
            eligible_unit_count=10,
            segment_timeout_seconds=0.0,
        )
        assert result == pytest.approx(30.0)

    def test_negative_segment_timeout_treated_as_zero(self):
        """Negative segment_timeout is invalid — treated as zero."""
        settings = _make_settings(per_unit_explicit=0, per_unit_min=30)
        result = resolve_per_unit_enrichment_timeout(
            settings=settings,
            eligible_unit_count=10,
            segment_timeout_seconds=-100.0,
        )
        assert result == pytest.approx(30.0)
