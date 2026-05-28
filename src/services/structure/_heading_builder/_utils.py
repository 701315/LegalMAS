# src/services/structure/_heading_builder/_utils.py

"""Утилиты нормализации и безопасного извлечения данных."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from services.structure.heading_llm_refiner import ScoredHeadingCandidate
from services.structure.heading_patterns import normalize_spaces
from services.structure.heading_scoring import CandidateStatus
from services.structure.models import DEFAULT_SCOPE, make_effective_uid

_NUMERIC_UID_RE = re.compile(r"^\d+(?:\.\d+)*$")


def _is_strict_numeric_uid(uid: str | None) -> bool:
    """Проверка на строго числовой UID."""
    return bool(_NUMERIC_UID_RE.fullmatch(str(uid or "").strip()))


def _normalize_scope(value: Any) -> str:
    """Нормализация имени scope."""
    if value is None:
        return str(DEFAULT_SCOPE)
    return str(value).strip() or str(DEFAULT_SCOPE)


def _uid_depth(uid: str) -> int:
    """Вычисление глубины вложенности UID."""
    u = normalize_spaces(uid)
    if not _is_strict_numeric_uid(u):
        return 1
    return u.count(".") + 1


def _status_to_decision(status: Any) -> str:
    """Конвертация статуса Scorer-а в строку decision."""
    if status == CandidateStatus.ACCEPTED:
        return "accepted"
    if status == CandidateStatus.REJECTED:
        return "rejected"
    if status == CandidateStatus.AMBIGUOUS:
        return "ambiguous"
    if isinstance(status, str):
        val = status.strip().lower()
        if val in {"accepted", "rejected", "ambiguous"}:
            return val
    return "rejected"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _normalize_reject_reason(value: Any) -> str:
    return str(value).strip() if value else "unknown"


def _scope_aware_effective_uid(scope: str, raw_uid: str) -> str:
    s = _normalize_scope(scope)
    r = normalize_spaces(raw_uid)
    return make_effective_uid(s, r) if r else ""


def _patched_scored_candidate(
    candidate: ScoredHeadingCandidate,
    *,
    metadata_updates: dict[str, Any] | None = None,
    decision: str | None = None,
    reason: str | None = None,
    score: float | None = None,
    decision_source: str | None = None,
) -> ScoredHeadingCandidate:
    """Обновление ScoredHeadingCandidate через replace."""
    new_meta = dict(candidate.metadata or {})
    if metadata_updates:
        new_meta.update(metadata_updates)
    updates: dict[str, Any] = {"metadata": new_meta}
    if decision is not None:
        updates["decision"] = decision
    if reason is not None:
        updates["reason"] = reason
    if score is not None:
        updates["score"] = score
    if decision_source is not None:
        updates["decision_source"] = decision_source
    return replace(candidate, **updates)
