"""Tests for semantic enrichment budget helpers."""

import time
import pytest
from unittest.mock import MagicMock

from services.structure.semantic_enrichment._budget import (
    build_document_enrichment_deadline,
    is_enrichment_budget_exhausted,
    remaining_enrichment_budget_seconds,
    resolve_segment_enrichment_timeout,
)


def _make_settings(
    *,
    document_budget: int = 0,
    worker_soft_limit: int = 1800,
    cleanup_margin: int = 60,
    segment_timeout: int = 180,
) -> MagicMock:
    s = MagicMock()
    s.SEMANTIC_ENRICHMENT_DOCUMENT_BUDGET_SECONDS = document_budget
    s.SEMANTIC_ENRICHMENT_WORKER_SOFT_TIME_LIMIT_SECONDS = worker_soft_limit
    s.SEMANTIC_ENRICHMENT_CLEANUP_MARGIN_SECONDS = cleanup_margin
    s.SEMANTIC_ENRICHMENT_SEGMENT_TIMEOUT_SECONDS = segment_timeout
    return s


def test_explicit_document_budget_used_when_positive() -> None:
    settings = _make_settings(document_budget=600)
    started = 1000.0
    deadline = build_document_enrichment_deadline(
        started_monotonic=started,
        settings=settings,
    )
    assert deadline == pytest.approx(1600.0)


def test_derived_budget_from_soft_limit_when_document_budget_zero() -> None:
    settings = _make_settings(
        document_budget=0,
        worker_soft_limit=1800,
        cleanup_margin=60,
    )
    started = 1000.0
    deadline = build_document_enrichment_deadline(
        started_monotonic=started,
        settings=settings,
    )
    assert deadline == pytest.approx(1000.0 + 1800 - 60)


def test_remaining_budget_positive() -> None:
    deadline = time.monotonic() + 100.0
    remaining = remaining_enrichment_budget_seconds(deadline_monotonic=deadline)
    assert remaining > 90.0
    assert remaining <= 100.0


def test_remaining_budget_returns_zero_when_exhausted() -> None:
    deadline = time.monotonic() - 1.0
    remaining = remaining_enrichment_budget_seconds(deadline_monotonic=deadline)
    assert remaining == 0.0


def test_segment_timeout_is_min_of_cap_and_remaining() -> None:
    settings = _make_settings(segment_timeout=180)
    deadline = time.monotonic() + 50.0
    timeout = resolve_segment_enrichment_timeout(
        deadline_monotonic=deadline,
        settings=settings,
    )
    assert timeout <= 50.0
    assert timeout <= 180.0


def test_segment_timeout_caps_at_segment_limit() -> None:
    settings = _make_settings(segment_timeout=30)
    deadline = time.monotonic() + 500.0
    timeout = resolve_segment_enrichment_timeout(
        deadline_monotonic=deadline,
        settings=settings,
    )
    assert timeout == pytest.approx(30.0)


def test_budget_exhausted_returns_true_when_past_deadline() -> None:
    deadline = time.monotonic() - 1.0
    assert is_enrichment_budget_exhausted(deadline_monotonic=deadline) is True


def test_budget_exhausted_returns_false_when_within_deadline() -> None:
    deadline = time.monotonic() + 100.0
    assert is_enrichment_budget_exhausted(deadline_monotonic=deadline) is False


def test_cleanup_margin_never_produces_negative_usable_budget() -> None:
    settings = _make_settings(
        document_budget=0,
        worker_soft_limit=30,
        cleanup_margin=60,
    )
    started = 1000.0
    deadline = build_document_enrichment_deadline(
        started_monotonic=started,
        settings=settings,
    )
    assert deadline >= started


    