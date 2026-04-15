# src/services/structure/heading_builder.py

from __future__ import annotations
import re

from collections import Counter
from typing import Any

from core.config import settings
from core.logging import get_logger
from services.structure.heading_llm_refiner import (
    ScoredHeadingCandidate,
    refine_ambiguous_candidates,
)
from services.structure.heading_patterns import normalize_spaces, parse_raw_heading
from services.structure.heading_scoring import (
    CandidateStatus,
    score_heading_candidate,
)
from services.structure.hierarchy_builder import HeadingCandidate, level_from_uid


logger = get_logger(__name__)


# _is_plausible_heading_title УДАЛЕНА — её логика полностью покрыта
# score_heading_candidate через is_garbage_heading_title / is_bad_heading_title / has_letters.
# Оставлять два фильтра с разными правилами опасно: кандидат мог отклоняться
# здесь по слабому критерию, не доходя до scorer'а с правильной причиной.


def _status_to_decision(status: CandidateStatus | str | None) -> str:
    """
    Приводит статус deterministic scorer к строковому decision-формату:
    - "accepted"
    - "rejected"
    - "ambiguous"
    """
    if status == CandidateStatus.ACCEPTED:
        return "accepted"
    if status == CandidateStatus.REJECTED:
        return "rejected"
    if status == CandidateStatus.AMBIGUOUS:
        return "ambiguous"

    if isinstance(status, str):
        value = status.strip().lower()
        if value in {"accepted", "rejected", "ambiguous"}:
            return value

    status_name = getattr(status, "name", None)
    if isinstance(status_name, str):
        value = status_name.strip().lower()
        if value in {"accepted", "rejected", "ambiguous"}:
            return value

    return "rejected"


_NUMERIC_UID_RE = re.compile(r"^\d+(?:\.\d+)*$")


def _is_strict_numeric_uid(uid: str) -> bool:
    return bool(_NUMERIC_UID_RE.fullmatch(uid.strip()))


def _select_best_candidates_by_uid(
    candidates: list[ScoredHeadingCandidate],
    *,
    document_id: str,
) -> list[ScoredHeadingCandidate]:
    """
    Для каждого uid оставляем одного лучшего кандидата.

    Приоритет выбора:
    1. Статус: accepted > ambiguous > rejected
       (не берём rejected, если есть хоть один accepted/ambiguous для того же uid)
    2. Score (чем выше — тем лучше)
    3. При равном score — больше букв в title
    4. При равном числе букв — длиннее title
    """
    best_by_uid: dict[str, ScoredHeadingCandidate] = {}

    # Вес статуса: accepted — самый желанный
    _status_weight = {"accepted": 2, "ambiguous": 1, "rejected": 0}

    for cand in candidates:
        uid = normalize_spaces(str(getattr(cand, "uid", "") or ""))
        if not uid:
            continue

        existing = best_by_uid.get(uid)
        if existing is None:
            best_by_uid[uid] = cand
            continue

        cand_weight = _status_weight.get(cand.decision, 0)
        exist_weight = _status_weight.get(existing.decision, 0)

        better = existing

        if cand_weight > exist_weight:
            # accepted всегда выигрывает у rejected
            better = cand
        elif cand_weight == exist_weight:
            if cand.score > existing.score:
                better = cand
            elif cand.score == existing.score:
                cand_t = normalize_spaces(cand.title or "")
                exist_t = normalize_spaces(existing.title or "")
                cand_letters = sum(ch.isalpha() for ch in cand_t)
                exist_letters = sum(ch.isalpha() for ch in exist_t)
                if cand_letters > exist_letters:
                    better = cand
                elif cand_letters == exist_letters and len(cand_t) > len(exist_t):
                    better = cand

        loser = cand if better is existing else existing
        logger.debug(
            "STRUCTURE heading_candidate_duplicate_uid_skipped",
            extra={
                "document_id": document_id,
                "uid": uid,
                "page": getattr(loser, "page", None),
                "elem_i": getattr(loser, "elem_i", None),
            },
        )

        best_by_uid[uid] = better

    return list(best_by_uid.values())


def collect_scored_heading_candidates(
    elements: list[dict[str, Any]],
    *,
    document_id: str,
) -> list[ScoredHeadingCandidate]:
    """
    Извлекает raw heading-кандидаты из layout-элементов, прогоняет их через
    deterministic scorer и возвращает список ScoredHeadingCandidate.

    Важно: возвращаем ВСЕ решения scorer'а (accepted / ambiguous / rejected).
    Фильтрация по статусу — только в build_heading_candidates.
    Это даёт полную картину в логах и корректную работу _select_best_candidates_by_uid.
    """
    scored_candidates: list[ScoredHeadingCandidate] = []
    reject_stats: Counter[str] = Counter()

    for elem_i, element in enumerate(elements):
        raw_text = normalize_spaces(str(element.get("text") or ""))
        if not raw_text:
            continue

        logger.debug(
            "STRUCTURE parse_raw_heading",
            extra={"text_sample": raw_text[:160]},
        )

        parsed = parse_raw_heading(raw_text)
        if parsed is None:
            # строка не распознана как заголовок регулярным парсером — пропускаем
            continue

        parsed_uid, parsed_title = parsed
        parsed_uid = normalize_spaces(str(parsed_uid or ""))
        parsed_title = normalize_spaces(str(parsed_title or ""))

        logger.debug(
            "STRUCTURE parse_raw_heading_result",
            extra={
                "document_id": document_id,
                "elem_i": elem_i,
                "raw_text_sample": raw_text[:160],
                "parsed_uid": parsed_uid,
                "parsed_title": parsed_title,
            },
        )

        if not parsed_uid:
            # uid обязателен для построения дерева
            continue

        # Для чисто нумерованных uid (1, 1.2, 3.1.4) считаем uid/title каноническими
        freeze_structural_fields = _is_strict_numeric_uid(parsed_uid)

        page = int(element.get("page") or 0)

        # Единственная точка оценки кандидата — scorer.
        # Он сам проверяет наличие букв, мусорные title, plausibility uid и т.д.
        score_result = score_heading_candidate(
            uid=parsed_uid,
            title=parsed_title,
            raw_text=raw_text,
        )

        decision = _status_to_decision(getattr(score_result, "status", None))
        reason = str(getattr(score_result, "primary_reason", "") or "")
        score = float(getattr(score_result, "score", 0.0) or 0.0)

        metadata = {
            "accept_reasons": list(getattr(score_result, "accept_reasons", []) or []),
            "reject_reasons": list(getattr(score_result, "reject_reasons", []) or []),
            "parsed_uid": parsed_uid,
            "parsed_title": parsed_title,
            "freeze_structural_fields": freeze_structural_fields,
        }

        candidate = ScoredHeadingCandidate(
            elem_i=elem_i,
            page=page,
            raw_text=raw_text,
            uid=parsed_uid,
            title=parsed_title,
            decision=decision,
            reason=reason,
            score=score,
            decision_source="rules",
            metadata=metadata,
        )
        scored_candidates.append(candidate)

        log_extra = {
            "document_id": document_id,
            "elem_i": elem_i,
            "uid": parsed_uid,
            "title": parsed_title,
            "reason": reason or decision,
            "raw_text_sample": raw_text[:160],
            "page": page,
        }

        if decision == "accepted":
            logger.debug("STRUCTURE heading_candidate_accepted", extra=log_extra)
        elif decision == "ambiguous":
            logger.debug("STRUCTURE heading_candidate_ambiguous", extra=log_extra)
        else:
            reject_stats[reason or "unknown"] += 1
            logger.debug("STRUCTURE heading_candidate_rejected", extra=log_extra)

    if reject_stats:
        logger.debug(
            "STRUCTURE heading_candidate_reject_stats",
            extra={
                "document_id": document_id,
                "reject_stats": dict(reject_stats),
            },
        )

    # Выбираем лучшего кандидата для каждого uid из всех решений scorer'а.
    # accepted побеждает ambiguous, ambiguous побеждает rejected.
    scored_candidates = _select_best_candidates_by_uid(
        scored_candidates,
        document_id=document_id,
    )

    return scored_candidates


def filter_heading_sequence(
    candidates: list[HeadingCandidate],
    *,
    document_id: str,
) -> list[HeadingCandidate]:
    """
    Финальная очистка accepted heading candidates перед hierarchy assembly.

    Правила:
    - пустой uid → пропускаем;
    - uid с невалидной структурой → пропускаем;
    - дублирующий uid → оставляем только первое появление;
    - порядок документа сохраняется.
    """
    if not candidates:
        logger.debug(
            "STRUCTURE heading_candidates_filtered",
            extra={
                "document_id": document_id,
                "raw_candidates": 0,
                "filtered_candidates": 0,
            },
        )
        return []

    filtered: list[HeadingCandidate] = []
    seen_uids: set[str] = set()

    for candidate in candidates:
        uid = normalize_spaces(str(candidate.uid or ""))
        if not uid:
            continue

        try:
            level_from_uid(uid)
        except Exception:
            logger.debug(
                "STRUCTURE heading_candidate_invalid_uid_skipped",
                extra={
                    "document_id": document_id,
                    "uid": uid,
                    "page": getattr(candidate, "page", None),
                    "elem_i": getattr(candidate, "elem_i", None),
                },
            )
            continue

        if uid in seen_uids:
            logger.debug(
                "STRUCTURE heading_candidate_duplicate_uid_skipped",
                extra={
                    "document_id": document_id,
                    "uid": uid,
                    "page": getattr(candidate, "page", None),
                    "elem_i": getattr(candidate, "elem_i", None),
                },
            )
            continue

        seen_uids.add(uid)
        filtered.append(candidate)

    logger.debug(
        "STRUCTURE heading_candidates_filtered",
        extra={
            "document_id": document_id,
            "raw_candidates": len(candidates),
            "filtered_candidates": len(filtered),
        },
    )
    return filtered


def build_heading_candidates(
    elements: list[dict[str, Any]],
    *,
    document_id: str,
) -> list[HeadingCandidate]:
    """
    Полный heading-building flow:
    1. parse + deterministic scoring (все решения, включая rejected);
    2. optional LLM refinement для ambiguous;
    3. фильтрация: берём только accepted;
    4. финальная очистка дубликатов.
    """
    scored_candidates = collect_scored_heading_candidates(
        elements,
        document_id=document_id,
    )

    if not scored_candidates:
        logger.debug(
            "STRUCTURE heading_candidates_filtered",
            extra={
                "document_id": document_id,
                "raw_candidates": 0,
                "filtered_candidates": 0,
            },
        )
        return []

    enable_llm_refiner = bool(
        getattr(settings, "STRUCTURE_ENABLE_HEADING_LLM_REFINER", False)
    )

    if enable_llm_refiner:
        try:
            scored_candidates = refine_ambiguous_candidates(
                scored_candidates=scored_candidates,
                elements=elements,
                document_id=document_id,
            )
        except Exception:
            logger.exception(
                "STRUCTURE heading_llm_refiner_failed",
                extra={"document_id": document_id},
            )

    accepted_candidates: list[HeadingCandidate] = []

    for scored in scored_candidates:
        # Берём только accepted — единственная точка фильтрации по статусу
        if getattr(scored, "decision", None) != "accepted":
            continue

        uid = normalize_spaces(str(getattr(scored, "uid", "") or ""))
        title = normalize_spaces(str(getattr(scored, "title", "") or ""))

        if not uid:
            continue

        accepted_candidates.append(
            HeadingCandidate(
                elem_i=int(getattr(scored, "elem_i")),
                uid=uid,
                title=title,
                page=int(getattr(scored, "page")),
            )
        )

    return filter_heading_sequence(
        accepted_candidates,
        document_id=document_id,
    )

