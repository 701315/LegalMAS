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
from services.structure.hierarchy_builder import HeadingCandidate

logger = get_logger(__name__)

_DEFAULT_SCOPE = "main_contract"
_NUMERIC_UID_RE = re.compile(r"^\d+(?:\.\d+)*$")
_MAX_HEADING_RAW_TEXT_LEN = 2000


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


def _is_strict_numeric_uid(uid: str) -> bool:
    return bool(_NUMERIC_UID_RE.fullmatch((uid or "").strip()))


def _normalize_scope(value: Any) -> str:
    """
    Нормализация scope для heading-кандидатов.

    Backward-compatible поведение:
    - если scope ещё не прокинут в layout / candidate, используем main_contract;
    - пустые/битые значения тоже сводим к main_contract.
    """
    if value is None:
        return _DEFAULT_SCOPE
    scope = normalize_spaces(str(value or ""))
    return scope or _DEFAULT_SCOPE


def _candidate_scope(candidate: Any) -> str:
    """
    Безопасно достать scope из объекта-кандидата.
    """
    return _normalize_scope(getattr(candidate, "scope", None))


def _element_scope(element: dict[str, Any]) -> str:
    """
    Источник scope на этапе разбора layout.

    Приоритет:
    1. element["scope"]
    2. element["metadata"]["scope"]
    3. main_contract
    """
    scope = element.get("scope")
    if scope is not None:
        return _normalize_scope(scope)

    metadata = element.get("metadata")
    if isinstance(metadata, dict):
        scope = metadata.get("scope")
        if scope is not None:
            return _normalize_scope(scope)

    return _DEFAULT_SCOPE


def _uid_depth(uid: str) -> int:
    """
    Глубина numeric uid:
    - "1" -> 1
    - "1.2" -> 2
    - "1.2.3" -> 3

    Для не-numeric uid возвращаем 1.
    """
    u = normalize_spaces(uid)
    if not _is_strict_numeric_uid(u):
        return 1
    return u.count(".") + 1


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _normalize_reject_reason(value: Any) -> str:
    reason = normalize_spaces(str(value or ""))
    return reason or "unknown"


def _scope_aware_effective_uid(scope: str, raw_uid: str) -> str:
    """
    Эффективный uid для хранения/диагностики.

    Важно:
    - в main_contract оставляем raw_uid как есть, чтобы не ломать legacy-код;
    - в appendix_* и других non-default scope добавляем scope-префикс.
    """
    scope = _normalize_scope(scope)
    raw_uid = normalize_spaces(raw_uid)

    if not raw_uid:
        return raw_uid

    if scope == _DEFAULT_SCOPE:
        return raw_uid

    return f"{scope}::{raw_uid}"


def _make_scored_heading_candidate(
    *,
    elem_i: int,
    page: int,
    raw_text: str,
    uid: str,
    title: str,
    decision: str,
    reason: str,
    score: float,
    decision_source: str,
    metadata: dict[str, Any],
    scope: str,
) -> ScoredHeadingCandidate:
    """
    Пытаемся создать ScoredHeadingCandidate с новым полем scope.
    Если dataclass/модель ещё не обновлена, мягко откатываемся на старый контракт.
    """
    try:
        return ScoredHeadingCandidate(
            elem_i=elem_i,
            page=page,
            raw_text=raw_text,
            uid=uid,
            title=title,
            decision=decision,
            reason=reason,
            score=score,
            decision_source=decision_source,
            metadata=metadata,
            scope=scope,
        )
    except TypeError:
        candidate = ScoredHeadingCandidate(
            elem_i=elem_i,
            page=page,
            raw_text=raw_text,
            uid=uid,
            title=title,
            decision=decision,
            reason=reason,
            score=score,
            decision_source=decision_source,
            metadata=metadata,
        )
        try:
            setattr(candidate, "scope", scope)
        except Exception:
            pass
        return candidate


def _make_heading_candidate(
    *,
    elem_i: int,
    uid: str,
    title: str,
    page: int,
    scope: str,
    raw_uid: str | None = None,
    effective_uid: str | None = None,
) -> HeadingCandidate:
    """
    Пытаемся создать HeadingCandidate с новыми полями scope/raw_uid/effective_uid.
    Если dataclass/модель ещё не обновлена, мягко откатываемся на старый контракт.
    """
    try:
        return HeadingCandidate(
            elem_i=elem_i,
            uid=uid,
            title=title,
            page=page,
            scope=scope,
            raw_uid=raw_uid or uid,
            effective_uid=effective_uid or uid,
        )
    except TypeError:
        try:
            candidate = HeadingCandidate(
                elem_i=elem_i,
                uid=uid,
                title=title,
                page=page,
                scope=scope,
            )
        except TypeError:
            candidate = HeadingCandidate(
                elem_i=elem_i,
                uid=uid,
                title=title,
                page=page,
            )

        for attr_name, attr_value in (
            ("scope", scope),
            ("raw_uid", raw_uid or uid),
            ("effective_uid", effective_uid or uid),
        ):
            try:
                setattr(candidate, attr_name, attr_value)
            except Exception:
                pass

        return candidate


def _candidate_raw_uid(candidate: Any) -> str:
    return normalize_spaces(str(getattr(candidate, "raw_uid", None) or getattr(candidate, "uid", "") or ""))


def _candidate_effective_uid(candidate: Any) -> str:
    explicit = normalize_spaces(str(getattr(candidate, "effective_uid", "") or ""))
    if explicit:
        return explicit

    scope = _candidate_scope(candidate)
    raw_uid = _candidate_raw_uid(candidate)
    return _scope_aware_effective_uid(scope, raw_uid)


def _candidate_decision(candidate: Any) -> str:
    return normalize_spaces(str(getattr(candidate, "decision", "") or "")).lower()


def _candidate_reason(candidate: Any) -> str:
    return _normalize_reject_reason(getattr(candidate, "reason", None))


def _select_best_candidates_by_uid(
    candidates: list[ScoredHeadingCandidate],
    *,
    document_id: str,
) -> list[ScoredHeadingCandidate]:
    """
    Для каждого (scope, raw_uid) оставляем одного лучшего кандидата.

    Приоритет выбора:
    1. Статус: accepted > ambiguous > rejected
    2. Score (чем выше — тем лучше)
    3. При равном score — больше букв в title
    4. При равном числе букв — длиннее title
    5. При полном равенстве — более раннее появление в документе
    """
    best_by_key: dict[tuple[str, str], ScoredHeadingCandidate] = {}
    status_weight = {"accepted": 2, "ambiguous": 1, "rejected": 0}

    for cand in candidates:
        raw_uid = _candidate_raw_uid(cand)
        if not raw_uid:
            continue

        scope = _candidate_scope(cand)
        key = (scope, raw_uid)

        existing = best_by_key.get(key)
        if existing is None:
            best_by_key[key] = cand
            continue

        cand_weight = status_weight.get(_candidate_decision(cand), 0)
        exist_weight = status_weight.get(_candidate_decision(existing), 0)

        better = existing

        if cand_weight > exist_weight:
            better = cand
        elif cand_weight == exist_weight:
            cand_score = float(getattr(cand, "score", 0.0) or 0.0)
            exist_score = float(getattr(existing, "score", 0.0) or 0.0)

            if cand_score > exist_score:
                better = cand
            elif cand_score == exist_score:
                cand_t = normalize_spaces(getattr(cand, "title", "") or "")
                exist_t = normalize_spaces(getattr(existing, "title", "") or "")
                cand_letters = sum(ch.isalpha() for ch in cand_t)
                exist_letters = sum(ch.isalpha() for ch in exist_t)

                if cand_letters > exist_letters:
                    better = cand
                elif cand_letters == exist_letters and len(cand_t) > len(exist_t):
                    better = cand
                elif cand_letters == exist_letters and len(cand_t) == len(exist_t):
                    cand_elem_i = _safe_int(getattr(cand, "elem_i", 10**9), 10**9)
                    exist_elem_i = _safe_int(getattr(existing, "elem_i", 10**9), 10**9)
                    if cand_elem_i < exist_elem_i:
                        better = cand

        loser = cand if better is existing else existing
        logger.debug(
            "STRUCTURE heading_candidate_duplicate_uid_skipped",
            extra={
                "document_id": document_id,
                "scope": scope,
                "raw_uid": raw_uid,
                "effective_uid": _candidate_effective_uid(loser),
                "page": getattr(loser, "page", None),
                "elem_i": getattr(loser, "elem_i", None),
                "decision": _candidate_decision(loser),
                "reason": _candidate_reason(loser),
                "duplicate_reason": "duplicate_uid",
            },
        )

        best_by_key[key] = better

    return list(best_by_key.values())


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

        if len(raw_text) > _MAX_HEADING_RAW_TEXT_LEN:
            logger.debug(
                "STRUCTURE heading_candidate_line_too_long_skipped",
                extra={
                    "document_id": document_id,
                    "elem_i": elem_i,
                    "page": element.get("page"),
                    "raw_text_len": len(raw_text),
                },
            )
            continue

        scope = _element_scope(element)

        logger.debug(
            "STRUCTURE parse_raw_heading",
            extra={
                "document_id": document_id,
                "elem_i": elem_i,
                "scope": scope,
                "text_sample": raw_text[:160],
            },
        )

        parsed = parse_raw_heading(raw_text)
        if parsed is None:
            continue

        parsed_raw_uid, parsed_title = parsed
        parsed_raw_uid = normalize_spaces(str(parsed_raw_uid or ""))
        parsed_title = normalize_spaces(str(parsed_title or ""))

        logger.debug(
            "STRUCTURE parse_raw_heading_result",
            extra={
                "document_id": document_id,
                "elem_i": elem_i,
                "scope": scope,
                "raw_text_sample": raw_text[:160],
                "parsed_raw_uid": parsed_raw_uid,
                "parsed_title": parsed_title,
            },
        )

        if not parsed_raw_uid:
            continue

        effective_uid = _scope_aware_effective_uid(scope, parsed_raw_uid)
        freeze_structural_fields = _is_strict_numeric_uid(parsed_raw_uid)
        page = _safe_int(element.get("page"), 0)

        score_result = score_heading_candidate(
            uid=parsed_raw_uid,
            title=parsed_title,
            raw_text=raw_text,
        )

        decision = _status_to_decision(getattr(score_result, "status", None))
        reason = _normalize_reject_reason(getattr(score_result, "primary_reason", None))
        score = float(getattr(score_result, "score", 0.0) or 0.0)

        metadata = {
            "accept_reasons": list(getattr(score_result, "accept_reasons", []) or []),
            "reject_reasons": list(getattr(score_result, "reject_reasons", []) or []),
            "parsed_uid": parsed_raw_uid,
            "raw_uid": parsed_raw_uid,
            "effective_uid": effective_uid,
            "parsed_title": parsed_title,
            "normalized_title": parsed_title,
            "freeze_structural_fields": freeze_structural_fields,
            "scope": scope,
        }

        if decision == "accepted" and not parsed_title:
            logger.warning(
                "STRUCTURE heading_candidate_empty_title_accepted",
                extra={
                    "document_id": document_id,
                    "elem_i": elem_i,
                    "scope": scope,
                    "raw_uid": parsed_raw_uid,
                    "effective_uid": effective_uid,
                    "raw_text_sample": raw_text[:160],
                },
            )

        candidate = _make_scored_heading_candidate(
            elem_i=elem_i,
            page=page,
            raw_text=raw_text,
            uid=parsed_raw_uid,
            title=parsed_title,
            decision=decision,
            reason=reason,
            score=score,
            decision_source="rules",
            metadata=metadata,
            scope=scope,
        )

        for attr_name, attr_value in (
            ("raw_uid", parsed_raw_uid),
            ("effective_uid", effective_uid),
            ("normalized_title", parsed_title),
        ):
            try:
                setattr(candidate, attr_name, attr_value)
            except Exception:
                pass

        scored_candidates.append(candidate)

        log_extra = {
            "document_id": document_id,
            "elem_i": elem_i,
            "scope": scope,
            "raw_uid": parsed_raw_uid,
            "effective_uid": effective_uid,
            "uid": parsed_raw_uid,
            "title": parsed_title,
            "reason": reason,
            "decision": decision,
            "raw_text_sample": raw_text[:160],
            "page": page,
            "score": score,
            "decision_source": "rules",
        }

        if decision == "accepted":
            logger.debug("STRUCTURE heading_candidate_accepted", extra=log_extra)
        elif decision == "ambiguous":
            logger.debug("STRUCTURE heading_candidate_ambiguous", extra=log_extra)
        else:
            reject_stats[reason] += 1
            logger.debug("STRUCTURE heading_candidate_rejected", extra=log_extra)

    if reject_stats:
        logger.debug(
            "STRUCTURE heading_candidate_reject_stats",
            extra={
                "document_id": document_id,
                "reject_stats": dict(reject_stats),
            },
        )

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
    - duplicate uid внутри scope → оставляем только первое появление;
    - порядок документа сохраняется.

    ВАЖНО:
    duplicate-проверка здесь идёт на уровне scope-aware final sequence.
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
    seen_keys: set[tuple[str, str]] = set()

    for candidate in candidates:
        raw_uid = _candidate_raw_uid(candidate)
        scope = _candidate_scope(candidate)
        effective_uid = _candidate_effective_uid(candidate)

        if not raw_uid:
            continue

        key = (scope, raw_uid)
        if key in seen_keys:
            logger.debug(
                "STRUCTURE heading_candidate_duplicate_uid_skipped",
                extra={
                    "document_id": document_id,
                    "scope": scope,
                    "raw_uid": raw_uid,
                    "effective_uid": effective_uid,
                    "page": getattr(candidate, "page", None),
                    "elem_i": getattr(candidate, "elem_i", None),
                    "duplicate_reason": "duplicate_uid",
                },
            )
            continue

        seen_keys.add(key)
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
    3. scope-aware dedup scored-candidates по (scope, raw_uid);
    4. фильтрация: берём только accepted;
    5. финальная очистка duplicate uid внутри scope.
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
        if _candidate_decision(scored) != "accepted":
            continue

        raw_uid = _candidate_raw_uid(scored)
        title = normalize_spaces(str(getattr(scored, "normalized_title", None) or getattr(scored, "title", "") or ""))
        scope = _candidate_scope(scored)
        effective_uid = _candidate_effective_uid(scored)

        if not raw_uid:
            continue

        elem_i_raw = getattr(scored, "elem_i", None)
        page_raw = getattr(scored, "page", None)

        try:
            elem_i = int(elem_i_raw)
            page = int(page_raw)
        except Exception:
            logger.warning(
                "STRUCTURE heading_candidate_invalid_position_skipped",
                extra={
                    "document_id": document_id,
                    "scope": scope,
                    "raw_uid": raw_uid,
                    "effective_uid": effective_uid,
                    "raw_elem_i": elem_i_raw,
                    "raw_page": page_raw,
                },
            )
            continue

        accepted_candidates.append(
            _make_heading_candidate(
                elem_i=elem_i,
                uid=raw_uid,
                title=title,
                page=page,
                scope=scope,
                raw_uid=raw_uid,
                effective_uid=effective_uid,
            )
        )

    return filter_heading_sequence(
        accepted_candidates,
        document_id=document_id,
    )


