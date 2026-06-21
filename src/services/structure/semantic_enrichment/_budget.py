# src/services/structure/semantic_enrichment/_budget.py

"""
Semantic Enrichment Runtime Budget Helpers.

Deterministic helpers for computing time budgets and deadlines
for the semantic enrichment formal pipeline stage.

Design principles:
- No LLM dependencies; purely computational.
- All functions are deterministic given their inputs.
- Budget logic is isolated here to keep worker/orchestration code clean.
- Uses time.monotonic() for elapsed/deadline calculations (not wall-clock).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.config import Settings


def build_document_enrichment_deadline(
    *,
    started_monotonic: float,
    settings: "Settings",
) -> float:
    """
    Compute monotonic deadline for enriching all segments of a document.

    Priority:
    1. Explicit SEMANTIC_ENRICHMENT_DOCUMENT_BUDGET_SECONDS if > 0.
    2. Derived from worker soft limit minus cleanup margin.

    Returns:
        Monotonic timestamp (time.monotonic()) at which enrichment
        must stop to preserve cleanup margin.
    """
    doc_budget = settings.SEMANTIC_ENRICHMENT_DOCUMENT_BUDGET_SECONDS
    if doc_budget > 0:
        return started_monotonic + float(doc_budget)

    soft_limit = settings.SEMANTIC_ENRICHMENT_WORKER_SOFT_TIME_LIMIT_SECONDS
    margin = settings.SEMANTIC_ENRICHMENT_CLEANUP_MARGIN_SECONDS
    usable = max(float(soft_limit - margin), 0.0)
    return started_monotonic + usable


def remaining_enrichment_budget_seconds(
    *,
    deadline_monotonic: float,
    now_monotonic: float | None = None,
) -> float:
    """
    Compute remaining seconds until the document enrichment deadline.

    Returns:
        Remaining seconds, clamped to 0.0 if deadline already passed.
    """
    now = now_monotonic if now_monotonic is not None else time.monotonic()
    return max(deadline_monotonic - now, 0.0)


def resolve_segment_enrichment_timeout(
    *,
    deadline_monotonic: float,
    settings: "Settings",
    now_monotonic: float | None = None,
) -> float:
    """
    Compute per-segment enrichment timeout in seconds.

    Returns the minimum of:
    - SEMANTIC_ENRICHMENT_SEGMENT_TIMEOUT_SECONDS (configured cap)
    - remaining document budget

    Returns 0.0 if document budget is already exhausted.
    """
    remaining = remaining_enrichment_budget_seconds(
        deadline_monotonic=deadline_monotonic,
        now_monotonic=now_monotonic,
    )
    segment_cap = float(settings.SEMANTIC_ENRICHMENT_SEGMENT_TIMEOUT_SECONDS)
    return min(segment_cap, remaining)


def is_enrichment_budget_exhausted(
    *,
    deadline_monotonic: float,
    now_monotonic: float | None = None,
) -> bool:
    """
    Return True if the document enrichment deadline has passed.
    """
    now = now_monotonic if now_monotonic is not None else time.monotonic()
    return now >= deadline_monotonic


def resolve_per_unit_enrichment_timeout(
    *,
    settings: "Settings",
    eligible_unit_count: int,
    segment_timeout_seconds: float,
) -> float:
    """
    Compute per-unit timeout for semantic enrichment LLM calls.

    Prevents a single hanging LLM call from consuming the entire segment budget.
    This is a hardware-agnostic safety ceiling: on a fast GPU machine the actual
    LLM call finishes well within this limit; on a slow CPU machine it prevents
    the segment from being fully blocked by one problematic unit.

    Strategy (in priority order):
    1. Explicit SEMANTIC_ENRICHMENT_PER_UNIT_TIMEOUT_SECONDS if > 0.
    2. Derived: segment_timeout_seconds / max(eligible_unit_count, 1).
    3. Always at least SEMANTIC_ENRICHMENT_PER_UNIT_MIN_TIMEOUT_SECONDS.

    Args:
        settings: application settings instance.
        eligible_unit_count: number of units eligible for LLM enrichment
            in this segment (pre-computed by enricher before loop).
        segment_timeout_seconds: the effective timeout budget for this segment
            (already capped to remaining document budget by caller).

    Returns:
        Per-unit timeout in seconds, always >= SEMANTIC_ENRICHMENT_PER_UNIT_MIN_TIMEOUT_SECONDS.
    """
    per_unit_min = float(
        getattr(settings, "SEMANTIC_ENRICHMENT_PER_UNIT_MIN_TIMEOUT_SECONDS", 30)
    )
    per_unit_explicit = float(
        getattr(settings, "SEMANTIC_ENRICHMENT_PER_UNIT_TIMEOUT_SECONDS", 0)
    )

    # Normalize segment_timeout_seconds: treat invalid/negative as zero.
    try:
        seg_timeout = float(segment_timeout_seconds)
    except (TypeError, ValueError):
        seg_timeout = 0.0
    seg_timeout = max(seg_timeout, 0.0)

    # Compute base timeout from config or derived.
    if per_unit_explicit > 0:
        base = per_unit_explicit
    else:
        count = max(int(eligible_unit_count), 1)
        base = seg_timeout / count if seg_timeout > 0 else per_unit_min

    # Apply floor and ceiling.
    # Floor: per_unit_min ensures each unit gets at least minimal time.
    # Ceiling: per-unit timeout must never exceed the segment budget.
    # When segment budget < per_unit_min, segment budget wins — we cannot
    # give a unit more time than the segment has.
    result = max(base, per_unit_min)

    if seg_timeout > 0:
        result = min(result, seg_timeout)

    return result


    