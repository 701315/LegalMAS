# src/services/structure/_heading_scoring/_legacy.py

"""Поддержка старых бинарных интерфейсов (Legacy API)."""

from __future__ import annotations

from typing import Any

from ._core import score_heading_candidate


def validate_heading_candidate_with_reason(
    uid: str,
    title: str,
    raw_text: str,
    *,
    toc_match: dict[str, Any] | None = None,
    element_type: str | None = None,
    semantic_element_type: str | None = None,
    continuity_signals: dict[str, Any] | None = None,
    prev_heading_uid: str | None = None,
    next_heading_uid: str | None = None,
) -> tuple[bool, str]:
    result = score_heading_candidate(
        uid,
        title,
        raw_text,
        toc_match=toc_match,
        element_type=element_type,
        semantic_element_type=semantic_element_type,
        continuity_signals=continuity_signals,
        prev_heading_uid=prev_heading_uid,
        next_heading_uid=next_heading_uid,
    )
    return result.is_accepted, result.primary_reason


def validate_heading_candidate(
    uid: str,
    title: str,
    raw_text: str,
    *,
    toc_match: dict[str, Any] | None = None,
    element_type: str | None = None,
    semantic_element_type: str | None = None,
    continuity_signals: dict[str, Any] | None = None,
    prev_heading_uid: str | None = None,
    next_heading_uid: str | None = None,
) -> bool:
    ok, _ = validate_heading_candidate_with_reason(
        uid,
        title,
        raw_text,
        toc_match=toc_match,
        element_type=element_type,
        semantic_element_type=semantic_element_type,
        continuity_signals=continuity_signals,
        prev_heading_uid=prev_heading_uid,
        next_heading_uid=next_heading_uid,
    )
    return ok


