# src/services/structure/heading_builder.py

"""
Построение списка heading candidates из layout-элементов документа.

Роль модуля:
- получает layout elements уже после segmenter + element_classifier;
- проверяет обязательный scope-aware контракт;
- извлекает heading candidates;
- выполняет deterministic scoring;
- умеет использовать TOC match index как дополнительный scoring signal;
- делает scope-aware deduplication;
- возвращает accepted HeadingCandidate для hierarchy builder.

Главный принцип:
heading_builder больше не "угадывает" scope и не исправляет upstream.
Если сегментация/metadata не были проставлены — это ошибка входа.

TOC integration policy:
- toc_match_index является опциональным входом;
- отсутствие TOC signal не считается ошибкой;
- exact/fuzzy TOC match усиливает хорошие кандидаты;
- stale или noisy TOC не должен сам по себе производить accepted candidate.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import replace
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
from services.structure.toc_match_utils import toc_match_payload
from services.structure.hierarchy_builder import HeadingCandidate
from services.structure.models import DEFAULT_SCOPE, make_effective_uid

logger = get_logger(__name__)

_NUMERIC_UID_RE = re.compile(r"^\d+(?:\.\d+)*$")
_MAX_HEADING_RAW_TEXT_LEN = 2000

_REQUIRED_ELEMENT_FIELDS = (
    "scope",
    "segment_id",
    "segment_type",
    "segment_order",
    "element_type",
)

_EXCLUDED_ELEMENT_TYPES = {
    "body_text",
    "table_content",
    "requisites_block",
    "signature_block",
    "toc_content",
    "page_artifact",
    "unknown_layout",
}

_ALLOWED_ELEMENT_TYPES = {
    "heading_candidate",
    "list_item",
}


def _status_to_decision(status: CandidateStatus | str | None) -> str:
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
    if value is None:
        return DEFAULT_SCOPE
    scope = normalize_spaces(str(value or ""))
    return scope or DEFAULT_SCOPE


def _candidate_scope(candidate: Any) -> str:
    return _normalize_scope(getattr(candidate, "scope", None))


def _element_scope(element: dict[str, Any]) -> str:
    scope = element.get("scope")
    if scope is not None:
        return _normalize_scope(scope)

    metadata = element.get("metadata")
    if isinstance(metadata, dict):
        scope = metadata.get("scope")
        if scope is not None:
            return _normalize_scope(scope)

    raise ValueError("Element is missing required field 'scope'")


def _uid_depth(uid: str) -> int:
    u = normalize_spaces(uid)
    if not _is_strict_numeric_uid(u):
        return 1
    return u.count(".") + 1


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _normalize_reject_reason(value: Any) -> str:
    reason = normalize_spaces(str(value or ""))
    return reason or "unknown"


def _scope_aware_effective_uid(scope: str, raw_uid: str) -> str:
    scope = _normalize_scope(scope)
    raw_uid = normalize_spaces(raw_uid)

    if not raw_uid:
        return raw_uid

    return make_effective_uid(scope, raw_uid)


def _candidate_raw_uid(candidate: Any) -> str:
    metadata = getattr(candidate, "metadata", None)
    if isinstance(metadata, dict):
        raw_uid = normalize_spaces(str(metadata.get("raw_uid") or ""))
        if raw_uid:
            return raw_uid

    return normalize_spaces(
        str(getattr(candidate, "uid", "") or "")
    )


def _candidate_effective_uid(candidate: Any) -> str:
    metadata = getattr(candidate, "metadata", None)
    if isinstance(metadata, dict):
        explicit = normalize_spaces(str(metadata.get("effective_uid") or ""))
        if explicit:
            return explicit

    scope = _candidate_scope(candidate)
    raw_uid = _candidate_raw_uid(candidate)
    return _scope_aware_effective_uid(scope, raw_uid)


def _candidate_decision(candidate: Any) -> str:
    return normalize_spaces(str(getattr(candidate, "decision", "") or "")).lower()


def _candidate_reason(candidate: Any) -> str:
    return _normalize_reject_reason(getattr(candidate, "reason", None))


def _require_element_structure_contract(
    *,
    element: dict[str, Any],
    elem_i: int,
    document_id: str,
) -> None:
    missing_fields = [field for field in _REQUIRED_ELEMENT_FIELDS if element.get(field) is None]

    if missing_fields:
        logger.error(
            "STRUCTURE heading_builder_element_contract_violation",
            extra={
                "document_id": document_id,
                "elem_i": elem_i,
                "missing_fields": missing_fields,
                "page": element.get("page"),
                "text_sample": normalize_spaces(str(element.get("text") or ""))[:160],
            },
        )
        raise ValueError(
            f"Heading builder requires scope/segment metadata before execution. "
            f"Missing fields for element #{elem_i}: {missing_fields}"
        )


def _is_candidate_element_type_allowed(element_type: str) -> bool:
    """
    Более строгая политика:
    - явно разрешаем heading_candidate и list_item;
    - явно запрещённые типы режем;
    - неизвестные типы НЕ пускаем, чтобы не ловить ложные headings.
    """
    normalized = normalize_spaces(element_type).lower()
    if not normalized:
        return False
    if normalized in _EXCLUDED_ELEMENT_TYPES:
        return False
    return normalized in _ALLOWED_ELEMENT_TYPES


def _candidate_priority_tuple(candidate: ScoredHeadingCandidate) -> tuple:
    """
    Deterministic ranking для conflict resolution внутри одного scope/raw_uid.

    Policy ladder:
    1. decision quality: accepted > ambiguous > rejected
    2. TOC match quality: exact > fuzzy > no_match
    3. local score
    4. не-list_item
    5. глубина uid
    6. информативность title
    7. earlier position

    Важно:
    - TOC match должен влиять на resolution конфликтов сильнее, чем локальный score;
    - stale / no_match TOC не даёт приоритета;
    - ranking остаётся deterministic и explainable.
    """
    decision = _candidate_decision(candidate)
    status_weight = {"accepted": 2, "ambiguous": 1, "rejected": 0}.get(decision, 0)

    metadata = getattr(candidate, "metadata", {}) or {}

    toc_match_type = normalize_spaces(str(metadata.get("toc_match_type") or "")).lower()
    toc_match_score = _safe_float(metadata.get("toc_match_score"), 0.0)

    if toc_match_type == "exact" and toc_match_score > 0.0:
        toc_priority = 3
    elif toc_match_type == "fuzzy" and toc_match_score > 0.0:
        toc_priority = 2
    else:
        toc_priority = 0

    score = float(getattr(candidate, "score", 0.0) or 0.0)

    element_type = normalize_spaces(str(metadata.get("element_type") or "")).lower()
    non_list_bonus = 1 if element_type != "list_item" else 0

    raw_uid = _candidate_raw_uid(candidate)
    uid_depth = _uid_depth(raw_uid)

    title = normalize_spaces(getattr(candidate, "title", "") or "")
    letters = sum(ch.isalpha() for ch in title)
    title_len = len(title)

    elem_i = _safe_int(getattr(candidate, "elem_i", 10**9), 10**9)

    return (
        status_weight,
        toc_priority,
        score,
        non_list_bonus,
        uid_depth,
        letters,
        title_len,
        -elem_i,
    )


def _select_best_candidates_by_uid(
    candidates: list[ScoredHeadingCandidate],
    *,
    document_id: str,
) -> list[ScoredHeadingCandidate]:
    best_by_key: dict[tuple[str, str], ScoredHeadingCandidate] = {}

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

        cand_rank = _candidate_priority_tuple(cand)
        existing_rank = _candidate_priority_tuple(existing)

        better = cand if cand_rank > existing_rank else existing
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


def _build_context_windows(
    elements: list[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    """
    Готовит локальный context для scorer:
    prev_heading_uid / next_heading_uid в пределах одного scope.
    """
    parsed_candidates_by_scope: dict[str, list[tuple[int, str]]] = defaultdict(list)

    for elem_i, element in enumerate(elements):
        try:
            scope = _element_scope(element)
        except Exception:
            continue

        raw_text = normalize_spaces(str(element.get("text") or ""))
        if not raw_text:
            continue

        parsed = parse_raw_heading(raw_text)
        if parsed is None:
            continue

        raw_uid, _ = parsed
        raw_uid = normalize_spaces(str(raw_uid or ""))
        if not raw_uid:
            continue

        parsed_candidates_by_scope[scope].append((elem_i, raw_uid))

    context_map: dict[int, dict[str, Any]] = {}

    for scope, items in parsed_candidates_by_scope.items():
        items.sort(key=lambda x: x[0])
        for pos, (elem_i, raw_uid) in enumerate(items):
            prev_uid = items[pos - 1][1] if pos > 0 else None
            next_uid = items[pos + 1][1] if pos + 1 < len(items) else None
            context_map[elem_i] = {
                "scope": scope,
                "prev_heading_uid": prev_uid,
                "next_heading_uid": next_uid,
            }

    return context_map


def _patched_scored_candidate(
    candidate: ScoredHeadingCandidate,
    *,
    metadata_updates: dict[str, Any] | None = None,
    decision: str | None = None,
    reason: str | None = None,
    score: float | None = None,
    decision_source: str | None = None,
) -> ScoredHeadingCandidate:
    """
    Безопасная альтернатива setattr(): обновляем dataclass через replace.
    """
    new_metadata = dict(getattr(candidate, "metadata", {}) or {})
    if metadata_updates:
        new_metadata.update(metadata_updates)

    updates: dict[str, Any] = {"metadata": new_metadata}
    if decision is not None:
        updates["decision"] = decision
    if reason is not None:
        updates["reason"] = reason
    if score is not None:
        updates["score"] = score
    if decision_source is not None:
        updates["decision_source"] = decision_source

    return replace(candidate, **updates)


def collect_scored_heading_candidates(
    elements: list[dict[str, Any]],
    *,
    document_id: str,
    toc_match_index: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> list[ScoredHeadingCandidate]:
    
    """
    Собирает ScoredHeadingCandidate из layout elements.

    Поведение:
    - валидирует обязательный structure contract;
    - парсит heading-like raw text;
    - вычисляет local context для scorer;
    - опционально подмешивает TOC match payload в scoring.

    Важно:
    - toc_match_index является weak/strong evidence, но не заменяет базовые guards;
    - отсутствие toc_match_index должно давать полностью корректное поведение;
    - все TOC-derived поля сохраняются в candidate metadata для diagnostics.
    """

    scored_candidates: list[ScoredHeadingCandidate] = []
    reject_stats: Counter[str] = Counter()
    context_map = _build_context_windows(elements)

    for elem_i, element in enumerate(elements):
        _require_element_structure_contract(
            element=element,
            elem_i=elem_i,
            document_id=document_id,
        )

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
        segment_id = normalize_spaces(str(element.get("segment_id") or ""))
        segment_type = normalize_spaces(str(element.get("segment_type") or ""))
        segment_order = _safe_int(element.get("segment_order"), -1)
        element_type = normalize_spaces(str(element.get("element_type") or ""))

        if not _is_candidate_element_type_allowed(element_type):
            logger.debug(
                "STRUCTURE non_heading_element_skipped",
                extra={
                    "document_id": document_id,
                    "elem_i": elem_i,
                    "scope": scope,
                    "segment_id": segment_id,
                    "element_type": element_type,
                    "page": element.get("page"),
                },
            )
            continue

        logger.debug(
            "STRUCTURE parse_raw_heading",
            extra={
                "document_id": document_id,
                "elem_i": elem_i,
                "scope": scope,
                "segment_id": segment_id,
                "segment_type": segment_type,
                "segment_order": segment_order,
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
                "segment_id": segment_id,
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

        page_offset = element.get("page_offset")
        formatting = element.get("formatting")
        ocr_confidence = element.get("ocr_confidence")

        local_context = context_map.get(elem_i, {})
        prev_heading_uid = local_context.get("prev_heading_uid")
        next_heading_uid = local_context.get("next_heading_uid")
        toc_match = toc_match_payload(
            raw_uid=parsed_raw_uid,
            title=parsed_title,
            toc_match_index=toc_match_index,
        )

        score_result = score_heading_candidate(
            uid=parsed_raw_uid,
            title=parsed_title,
            raw_text=raw_text,
            toc_match=toc_match,
        )

        decision = _status_to_decision(getattr(score_result, "status", None))
        reason = _normalize_reject_reason(getattr(score_result, "primary_reason", None))
        score = float(getattr(score_result, "score", 0.0) or 0.0)

        if element_type == "list_item" and decision == "accepted":
            if not _is_strict_numeric_uid(parsed_raw_uid):
                decision = "rejected"
                reason = "list_item_non_numeric_uid"
            elif _uid_depth(parsed_raw_uid) > 4 and score < 0.85:
                decision = "ambiguous"
                reason = "list_item_deep_uid_requires_stronger_evidence"

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
            "segment_id": segment_id,
            "segment_type": segment_type,
            "segment_order": segment_order,
            "element_type": element_type,
            "uid_depth": _uid_depth(parsed_raw_uid),
            "page": page,
            "page_offset": page_offset,
            "formatting": formatting,
            "ocr_confidence": ocr_confidence,
            "prev_heading_uid": prev_heading_uid,
            "next_heading_uid": next_heading_uid,
            "toc_match": toc_match,
            "toc_match_type": getattr(score_result, "toc_match_type", None),
            "toc_match_score": float(getattr(score_result, "toc_match_score", 0.0) or 0.0),
        }

        if decision == "accepted" and not parsed_title:
            logger.warning(
                "STRUCTURE heading_candidate_empty_title_accepted",
                extra={
                    "document_id": document_id,
                    "elem_i": elem_i,
                    "scope": scope,
                    "segment_id": segment_id,
                    "raw_uid": parsed_raw_uid,
                    "effective_uid": effective_uid,
                    "raw_text_sample": raw_text[:160],
                },
            )

        candidate = ScoredHeadingCandidate(
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

        scored_candidates.append(candidate)

        log_extra = {
            "document_id": document_id,
            "elem_i": elem_i,
            "scope": scope,
            "segment_id": segment_id,
            "segment_type": segment_type,
            "segment_order": segment_order,
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
            "element_type": element_type,
            "prev_heading_uid": prev_heading_uid,
            "next_heading_uid": next_heading_uid,
            "toc_match_type": getattr(score_result, "toc_match_type", None),
            "toc_match_score": float(getattr(score_result, "toc_match_score", 0.0) or 0.0),
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
    toc_match_index: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> list[HeadingCandidate]:
    
    """
    Строит accepted HeadingCandidate для hierarchy builder.

    Поведение:
    - сначала собирает scored candidates из elements;
    - затем опционально пропускает ambiguous случаи через LLM refiner;
    - после этого оставляет только accepted candidates и нормализует их
      для hierarchy builder.

    TOC integration:
    - toc_match_index опционален;
    - при наличии index-а TOC signal участвует в deterministic scoring;
    - LLM refiner работает поверх уже обогащённых metadata.
    """

    scored_candidates = collect_scored_heading_candidates(
        elements,
        document_id=document_id,
        toc_match_index=toc_match_index,
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
            refined = refine_ambiguous_candidates(
                scored_candidates=scored_candidates,
                elements=elements,
                document_id=document_id,
            )

            normalized_refined: list[ScoredHeadingCandidate] = []
            for cand in refined:
                metadata = dict(getattr(cand, "metadata", {}) or {})
                raw_uid = normalize_spaces(str(metadata.get("raw_uid") or getattr(cand, "uid", "") or ""))
                effective_uid = metadata.get("effective_uid") or _scope_aware_effective_uid(
                    _candidate_scope(cand),
                    raw_uid,
                )
                metadata["raw_uid"] = raw_uid
                metadata["effective_uid"] = effective_uid
                metadata["normalized_title"] = normalize_spaces(
                    str(metadata.get("normalized_title") or getattr(cand, "title", "") or "")
                )
                normalized_refined.append(_patched_scored_candidate(cand, metadata_updates=metadata))

            scored_candidates = normalized_refined
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
        metadata = getattr(scored, "metadata", {}) or {}
        title = normalize_spaces(
            str(metadata.get("normalized_title") or getattr(scored, "title", "") or "")
        )
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
            HeadingCandidate(
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


