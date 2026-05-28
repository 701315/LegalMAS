# src/services/structure/_heading_builder/_ranking.py

"""Логика ранжирования и дедупликации кандидатов."""

from __future__ import annotations

from core.logging import get_logger
from services.structure.heading_llm_refiner import ScoredHeadingCandidate
from services.structure.heading_patterns import normalize_spaces

from ._utils import (
    _normalize_reject_reason,
    _normalize_scope,
    _safe_float,
    _safe_int,
    _uid_depth,
)

logger = get_logger(__name__)


def _candidate_priority_tuple(candidate: ScoredHeadingCandidate) -> tuple:
    """Создает кортеж весов для сравнения кандидатов с одинаковым UID."""
    decision = str(candidate.decision or "").strip().lower()
    status_weight = {"accepted": 2, "ambiguous": 1, "rejected": 0}.get(decision, 0)

    meta = candidate.metadata or {}
    t_type = normalize_spaces(str(meta.get("toc_match_type") or "")).lower()
    t_score = _safe_float(meta.get("toc_match_score"))

    toc_priority = (
        3 if t_type == "exact" and t_score > 0 else 2 if t_type == "fuzzy" and t_score > 0 else 0
    )
    score = _safe_float(candidate.score)

    el_type = normalize_spaces(str(meta.get("element_type") or "")).lower()
    non_list_bonus = 1 if el_type != "list_item" else 0

    raw_uid = str(meta.get("raw_uid") or candidate.uid or "")
    title = normalize_spaces(candidate.title or "")
    letters = sum(ch.isalpha() for ch in title)

    return (
        status_weight,
        toc_priority,
        score,
        non_list_bonus,
        _uid_depth(raw_uid),
        letters,
        len(title),
        -_safe_int(candidate.elem_i),
    )


def _select_best_candidates_by_uid(
    candidates: list[ScoredHeadingCandidate], document_id: str
) -> list[ScoredHeadingCandidate]:
    """Выбирает лучшего кандидата для каждой пары (scope, raw_uid)."""
    best_by_key: dict[tuple[str, str], ScoredHeadingCandidate] = {}
    for cand in candidates:
        raw_uid = normalize_spaces(str((cand.metadata or {}).get("raw_uid") or cand.uid or ""))
        if not raw_uid:
            continue
        scope = _normalize_scope(cand.scope)
        key = (scope, raw_uid)

        existing = best_by_key.get(key)
        if existing is None:
            best_by_key[key] = cand
            continue

        if _candidate_priority_tuple(cand) > _candidate_priority_tuple(existing):
            loser = existing
            best_by_key[key] = cand
        else:
            loser = cand

        logger.debug(
            "STRUCTURE heading_candidate_duplicate_uid_skipped",
            extra={
                "document_id": document_id,
                "scope": scope,
                "raw_uid": raw_uid,
                "effective_uid": str((loser.metadata or {}).get("effective_uid") or ""),
                "page": loser.page,
                "elem_i": loser.elem_i,
                "decision": str(loser.decision).lower(),
                "reason": _normalize_reject_reason(loser.reason),
                "duplicate_reason": "duplicate_uid",
            },
        )
    return list(best_by_key.values())
