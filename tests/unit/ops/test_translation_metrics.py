# tests/unit/ops/test_translation_metrics.py
"""
Unit tests for translation Prometheus metrics — Sprint 6.5

Verifies:
- All 13 translation and review metrics are registered in dedicated registry
- Counters increment properly with labels
- Histograms observe durations
- Gauges set state values
- generate_latest outputs metrics formatted for Prometheus scrapers
"""

from __future__ import annotations

import pytest
from prometheus_client import generate_latest

from ops.metrics import get_metrics, get_prometheus_registry


def test_translation_metrics_registered_in_dedicated_registry():
    """Verify all 13 translation metrics are accessible on MetricsRegistry."""
    m = get_metrics()
    
    expected_metrics = [
        "translation_requested_total",
        "translation_claimed_total",
        "translation_success_total",
        "translation_failed_total",
        "translation_review_approved_total",
        "translation_review_rejected_total",
        "translation_review_edited_total",
        "translation_review_reset_total",
        "translation_duration_seconds",
        "translation_review_action_duration_seconds",
        "translation_queue_size",
        "translation_review_approved_rate",
        "translation_human_override_rate",
    ]
    
    for metric_name in expected_metrics:
        assert hasattr(m, metric_name), f"Missing metric: {metric_name}"


def test_counters_increment_with_labels():
    """Verify Counter metrics increment without errors."""
    m = get_metrics()

    # Requested counter
    m.translation_requested_total.labels(locale="en").inc(5)
    
    # Claimed counter
    m.translation_claimed_total.labels(locale="de").inc(3)
    
    # Success counter
    m.translation_success_total.labels(locale="fr", provider="ollama", model="llama3.1").inc(2)
    
    # Failed counter
    m.translation_failed_total.labels(locale="es", reason="translation_error").inc()
    
    # Review action counters
    m.translation_review_approved_total.labels(locale="ru").inc()
    m.translation_review_rejected_total.labels(locale="ru").inc()
    m.translation_review_edited_total.labels(locale="ru").inc()
    m.translation_review_reset_total.labels(locale="ru").inc()


def test_histograms_observe_durations():
    """Verify Histogram metrics accept observation values."""
    m = get_metrics()

    m.translation_duration_seconds.labels(locale="en", provider="ollama").observe(1.25)
    m.translation_review_action_duration_seconds.labels(action="approve").observe(0.045)


def test_gauges_set_values():
    """Verify Gauge metrics can be set."""
    m = get_metrics()

    m.translation_queue_size.set(42)
    m.translation_review_approved_rate.set(0.95)
    m.translation_human_override_rate.set(0.08)


def test_prometheus_output_contains_translation_metrics():
    """Verify output of generate_latest contains translation metric names."""
    registry = get_prometheus_registry()
    output = generate_latest(registry).decode("utf-8")

    assert "mas_dd_translation_requested_total" in output
    assert "mas_dd_translation_success_total" in output
    assert "mas_dd_translation_duration_seconds" in output
    assert "mas_dd_translation_queue_size" in output
