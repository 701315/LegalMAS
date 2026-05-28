# src/services/structure/_heading_scoring/_types.py

"""Типы данных и статусы процесса скоринга заголовков."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum

class CandidateStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    AMBIGUOUS = "ambiguous"

@dataclass(slots=True)
class HeadingScoreResult:
    status: CandidateStatus
    score: float
    primary_reason: str
    accept_reasons: list[str] = field(default_factory=list)
    reject_reasons: list[str] = field(default_factory=list)
    toc_match_score: float = 0.0
    toc_match_type: str | None = None
    semantic_element_type: str | None = None
    continuity_bonus: float = 0.0
    legal_negative_signals: list[str] = field(default_factory=list)

    @property
    def is_accepted(self) -> bool:
        return self.status == CandidateStatus.ACCEPTED
    @property
    def is_rejected(self) -> bool:
        return self.status == CandidateStatus.REJECTED
    @property
    def is_ambiguous(self) -> bool:
        return self.status == CandidateStatus.AMBIGUOUS