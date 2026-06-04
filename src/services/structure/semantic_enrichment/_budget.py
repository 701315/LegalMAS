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


    