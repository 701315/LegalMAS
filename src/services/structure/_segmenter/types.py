# src/services/structure/_segmenter/types.py

"""
Dataclass-модели boundary layer сегментации.

Содержит:
- ``BoundarySignal``  — один сигнал в пользу границы сегмента;
- ``BoundaryCandidate`` — кандидат на начало нового сегмента.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BoundarySignal:
    """Один сигнал в пользу границы сегмента."""

    name: str
    weight: float
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BoundaryCandidate:
    """Кандидат на начало нового сегмента."""

    element_index: int
    page: int
    text: str
    segment_type: str
    title: str | None
    confidence_score: float
    confidence_label: str
    signals: tuple[BoundarySignal, ...]
    reasons: tuple[str, ...]
    is_mid_page: bool

