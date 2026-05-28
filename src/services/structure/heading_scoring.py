# src/services/structure/heading_scoring.py

"""
Scoring / decision слой для heading detection.
Публичный фасад.
"""

from __future__ import annotations

from ._heading_scoring._core import score_heading_candidate
from ._heading_scoring._legacy import (
    validate_heading_candidate,
    validate_heading_candidate_with_reason,
)
from ._heading_scoring._types import CandidateStatus, HeadingScoreResult
from ._heading_scoring._utils import level_from_uid

__all__ = [
    "CandidateStatus",
    "HeadingScoreResult",
    "score_heading_candidate",
    "validate_heading_candidate",
    "validate_heading_candidate_with_reason",
    "level_from_uid",
]
