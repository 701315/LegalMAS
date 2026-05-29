# src/services/structure/heading_scoring.py

"""
Публичный фасад для heading scoring pipeline.

Зачем нужен этот файл:
- не заставлять внешний код знать внутреннюю структуру пакета
  `services.structure._heading_scoring.*`;
- держать стабильную import-point для scorer-а, типов и utility helpers;
- обеспечить backward compatibility со старым API validate_*,
  пока pipeline постепенно мигрирует на score_heading_candidate().

Важно:
- canonical scoring API: score_heading_candidate
- legacy compatibility API: validate_heading_candidate,
  validate_heading_candidate_with_reason
- типы результата экспортируются отсюда же, чтобы внешний код
  не ходил во внутренние подмодули напрямую.
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