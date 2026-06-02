# src/services/structure/_segmenter/confidence.py

"""
Маппинг числового score уверенности на строковый label.
"""

from __future__ import annotations

from services.structure.models import (
    SEGMENT_CONFIDENCE_HIGH,
    SEGMENT_CONFIDENCE_LOW,
    SEGMENT_CONFIDENCE_MEDIUM,
)


def confidence_label(score: float) -> str:
    """Возвращает строковый label уверенности по числовому score."""
    if score >= 0.80:
        return SEGMENT_CONFIDENCE_HIGH
    if score >= 0.60:
        return SEGMENT_CONFIDENCE_MEDIUM
    return SEGMENT_CONFIDENCE_LOW

