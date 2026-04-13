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

def _is_plausible_heading_title(title: str) -> bool:
    t = normalize_spaces(title or "")
    if not t:
        return False
    if len(t) < 3:
        return False
    letters = sum(ch.isalpha() for ch in t)
    if letters == 0:
        return False
    # доля букв хотя бы 40%
    if letters / len(t) < 0.4:
        return False
    return True

def _status_to_decision(status: CandidateStatus | str | None) -> str:
    """
    Приводит статус deterministic scorer к строковому decision-формату:
    - accepted
    - rejected
    - ambiguous
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
    Для каждого uid выбираем лучший кандидат:
    - сначала по score;
    - при равном score — по длине title (короче лучше).
    """
    best_by_uid: dict[str, ScoredHeadingCandidate] = {}

    for cand in candidates:
        uid = normalize_spaces(str(getattr(cand, "uid", "") or ""))
        if not uid:
            continue

        existing = best_by_uid.get(uid)
        if existing is None:
            best_by_uid[uid] = cand
            continue

        better = existing
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

        # залогируем того, кто проиграл выбор
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
            # строка не похожа на заголовок
            continue

        # ожидаем кортеж (uid, title) из heading_patterns
        parsed_uid, parsed_title = parsed

        parsed_uid = normalize_spaces(str(parsed_uid or ""))
        parsed_title = normalize_spaces(str(parsed_title or ""))

        # логируем именно результат парсера, до всякого скоринга
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
            # без uid структура бессмысленна
            continue

        # новый блок – отсекаем явный мусор вроде ",", "-", "."
        if not _is_plausible_heading_title(parsed_title):
            reject_stats["badheadingtitle"] += 1
            logger.debug(
                "STRUCTURE heading_candidate_rejected",
                extra={
                    "document_id": document_id,
                    "elem_i": elem_i,
                    "uid": parsed_uid,
                    "title": parsed_title,
                    "reason": "badheadingtitle",
                    "raw_text_sample": raw_text[:160],
                    "page": int(element.get("page") or 0),
                },
            )
            continue

        # Фикс: для чисто нумерованных uid считаем uid/title каноническими
        freeze_structural_fields = _is_strict_numeric_uid(parsed_uid)

        page = int(element.get("page") or 0)

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

        # ВАЖНО: uid/title берём ТОЛЬКО из парсера
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

    # На этом этапе уже выберем лучших кандидатов по uid,
    # чтобы дальше дерево строилось из максимально "человеческих" шапок.
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

    Текущие правила:
    - пустой uid отбрасываем;
    - uid с невалидной структурой отбрасываем;
    - duplicate uid оставляем только в первом появлении;
    - исходный порядок документа сохраняем.
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
    1. parse + deterministic scoring,
    2. optional LLM refinement for ambiguous items,
    3. projection accepted -> HeadingCandidate,
    4. duplicate/noise filtering.
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

