# src/classifiers/stage8/_decision_support.py

"""
Вспомогательные функции для принятия и объяснения решений классификатора.

PR1: build_voting_details, best_pre_l4_signal,
     build_llm_source_text, make_l4_error_details
PR2: apply_voting

UPDATED:
- apply_voting теперь является canonical owner полного details["voting"];
- pre-L4 signal более строго отделяет usable voted signal от weak/conflicted signal;
- details обогащаются полями score/confidence semantics и explainability;
- build_voting_details / apply_voting / best_pre_l4_signal симметрично
  поддерживают type|type_code и voting_score|score;
- backward compatibility по ключам и return contract сохранена.
"""

from __future__ import annotations

from typing import Any

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return []


def _normalize_type_code(value: Any) -> str:
    if value is None:
        return "UNKNOWN"
    result = str(value).strip()
    if not result:
        return "UNKNOWN"
    if result.upper() == "UNKNOWN":
        return "UNKNOWN"
    return result


def _normalize_top2_types(value: Any) -> list[str]:
    result: list[str] = []
    for item in _safe_list(value):
        type_code = _normalize_type_code(item)
        if type_code != "UNKNOWN" and type_code not in result:
            result.append(type_code)
    return result


def _normalize_support_levels(value: Any) -> list[str]:
    levels: list[str] = []
    for item in _safe_list(value):
        level = str(item).strip()
        if level and level not in levels:
            levels.append(level)
    return levels


def _normalize_ranking_entry(item: Any) -> dict | None:
    if not isinstance(item, dict):
        return None

    type_code = _normalize_type_code(item.get("type") or item.get("type_code"))
    if type_code == "UNKNOWN":
        return None

    score = _safe_float(
        item.get("score", item.get("voting_score", 0.0)),
        0.0,
    )
    confidence = _safe_float(item.get("confidence", 0.0), 0.0)
    margin = _safe_float(item.get("margin", 0.0), 0.0)
    support_count = _safe_int(item.get("support_count", 0), 0)
    support_levels = _normalize_support_levels(item.get("support_levels"))

    normalized = dict(item)
    normalized["type"] = type_code
    normalized["score"] = score
    normalized["confidence"] = confidence
    normalized["margin"] = margin
    normalized["support_count"] = support_count
    normalized["support_levels"] = support_levels
    normalized.pop("type_code", None)
    normalized.pop("voting_score", None)

    return normalized


def _normalize_ranking(value: Any) -> list[dict]:
    ranking: list[dict] = []
    for item in _safe_list(value):
        normalized = _normalize_ranking_entry(item)
        if normalized is not None:
            ranking.append(normalized)
    return ranking


def _candidate_from_obj(
    obj: Any,
    *,
    source: str,
    language: str | None,
    jurisdiction: str | None,
) -> tuple[str, float, str | None, str | None, str] | None:
    if obj is None:
        return None

    doctype = _normalize_type_code(getattr(obj, "doctype", None))
    if doctype == "UNKNOWN":
        return None

    confidence = _safe_float(getattr(obj, "confidence", 0.0), 0.0)
    if confidence <= 0.0:
        return None

    return (
        doctype,
        confidence,
        getattr(obj, "language", language),
        getattr(obj, "jurisdiction", jurisdiction),
        source,
    )


def _get_voted_type(voted: dict | None) -> str:
    if not isinstance(voted, dict):
        return "UNKNOWN"
    return _normalize_type_code(voted.get("type") or voted.get("type_code"))


def _get_voted_score(voted: dict | None) -> float:
    if not isinstance(voted, dict):
        return 0.0
    return _safe_float(voted.get("voting_score", voted.get("score", 0.0)), 0.0)


def build_voting_details(
    *,
    strategy: str,
    reason: str,
    voted: dict | None = None,
    extra: dict | None = None,
) -> dict:
    """
    Формирует canonical структуру details["voting"].

    Семантика:
    - score: voting score победителя (aggregate score after normalization/caps);
    - confidence: decision confidence итогового voting-решения;
    - margin: отрыв победителя от следующей гипотезы;
    - ranking: ranking hypotheses после голосования;
    - support_*: поддержка по уникальным уровням, а не по count rows.
    """
    payload: dict[str, Any] = {
        "strategy": str(strategy),
        "reason": str(reason),
        "type": "UNKNOWN",
        "score": 0.0,
        "confidence": 0.0,
        "margin": 0.0,
        "support_count": 0,
        "support_levels": [],
        "single_source_cap_applied": False,
        "single_source_cap_used": None,
        "dominant_floor": None,
        "best_level": None,
        "best_component_confidence": None,
        "domain_conflict": False,
        "parent_conflict": False,
        "group_conflict": False,
        "top2_types": [],
        "ranking": [],
        "extra": {
            "score_kind": "voting_score",
            "confidence_kind": "decision_confidence",
            "support_semantics": "unique_levels",
        },
    }

    if voted:
        voted_type = _get_voted_type(voted)
        voted_confidence = _safe_float(voted.get("confidence", 0.0), 0.0)
        voted_score = _get_voted_score(voted)

        if voted_type == "UNKNOWN":
            voted_confidence = 0.0
            voted_score = 0.0

        payload.update(
            {
                "type": voted_type,
                "score": voted_score,
                "confidence": voted_confidence,
                "margin": _safe_float(voted.get("margin"), 0.0),
                "support_count": _safe_int(voted.get("support_count"), 0),
                "support_levels": _normalize_support_levels(voted.get("support_levels")),
                "single_source_cap_applied": bool(voted.get("single_source_cap_applied", False)),
                "single_source_cap_used": (
                    _safe_float(voted.get("single_source_cap_used"), 0.0)
                    if voted.get("single_source_cap_used") is not None
                    else None
                ),
                "dominant_floor": (
                    _safe_float(voted.get("dominant_floor"), 0.0)
                    if voted.get("dominant_floor") is not None
                    else None
                ),
                "best_level": voted.get("best_level"),
                "best_component_confidence": (
                    _safe_float(voted.get("best_component_confidence"), 0.0)
                    if voted.get("best_component_confidence") is not None
                    else None
                ),
                "domain_conflict": bool(voted.get("domain_conflict", False)),
                "parent_conflict": bool(voted.get("parent_conflict", False)),
                "group_conflict": bool(voted.get("group_conflict", False)),
                "top2_types": _normalize_top2_types(voted.get("top2_types")),
                "ranking": _normalize_ranking(voted.get("ranking")),
            }
        )

    if extra:
        top_level_keys = {
            "type",
            "score",
            "confidence",
            "margin",
            "support_count",
            "support_levels",
            "single_source_cap_applied",
            "single_source_cap_used",
            "dominant_floor",
            "best_level",
            "best_component_confidence",
            "domain_conflict",
            "parent_conflict",
            "group_conflict",
            "top2_types",
            "ranking",
        }

        for key in top_level_keys:
            if key not in extra:
                continue

            if key == "type":
                payload[key] = _normalize_type_code(extra[key])
            elif key in {"score", "confidence", "margin"}:
                payload[key] = _safe_float(extra[key], 0.0)
            elif key == "support_count":
                payload[key] = _safe_int(extra[key], 0)
            elif key == "support_levels":
                payload[key] = _normalize_support_levels(extra[key])
            elif key == "top2_types":
                payload[key] = _normalize_top2_types(extra[key])
            elif key == "ranking":
                payload[key] = _normalize_ranking(extra[key])
            elif key in {
                "single_source_cap_applied",
                "domain_conflict",
                "parent_conflict",
                "group_conflict",
            }:
                payload[key] = bool(extra[key])
            elif key in {
                "single_source_cap_used",
                "dominant_floor",
                "best_component_confidence",
            }:
                payload[key] = _safe_float(extra[key], 0.0) if extra[key] is not None else None
            else:
                payload[key] = extra[key]

        merged_extra = dict(payload.get("extra") or {})
        merged_extra.update({k: v for k, v in extra.items() if k not in top_level_keys})
        payload["extra"] = merged_extra

    return payload


def best_pre_l4_signal(
    *,
    voted: dict | None,
    top_l1: dict | None,
    top_l2: Any | None,
    top_l3: Any | None,
    language: str | None,
    jurisdiction: str | None,
    details: dict | None = None,
) -> tuple[str, float, str | None, str | None, str]:
    """
    Возвращает лучший известный сигнал ДО вызова L4.

    Это strongest admissible signal before L4, а не decision rule.

    Источники:
      "VOTED" | "L3" | "L2" | "L1" | "VOTED_FALLBACK" | "NONE"

    Правило:
    - VOTED используется как pre-L4 signal только если он пригоден для adjudication;
    - conflict/contradiction/very-low-quality кейсы не дают VOTED как strong source;
    - дальше идёт fallback к L3/L2/L1;
    - если ничего лучше нет, можно вернуть VOTED_FALLBACK как best known weak belief.
    """
    details = details if isinstance(details, dict) else {}
    voting_details = details.get("voting") if isinstance(details.get("voting"), dict) else {}

    voted_type = _get_voted_type(voted)
    voted_score = _safe_float(
        voting_details.get("score", _get_voted_score(voted)),
        0.0,
    )
    voted_conf = _safe_float(
        voting_details.get("confidence", voted.get("confidence") if voted else 0.0),
        0.0,
    )
    voted_margin = _safe_float(
        details.get("voting_margin", voting_details.get("margin", 0.0)),
        0.0,
    )
    voted_support_count = _safe_int(
        voting_details.get("support_count", voted.get("support_count") if voted else 0),
        0,
    )

    domain_conflict = bool(
        details.get("domain_conflict", voting_details.get("domain_conflict", False))
    )
    contradiction = bool(details.get("contradiction_detected", False))
    input_quality = _safe_float(details.get("input_quality", 1.0), 1.0)

    margin_min: float = settings.CLASSIFICATION_L4_MARGIN_MIN
    accept_threshold: float = settings.CLASSIFICATION_L4_ACCEPT
    review_quality_floor: float = settings.CLASSIFICATION_L4_REVIEW_QUALITY_FLOOR
    tiebreak_delta: float = settings.CLASSIFICATION_L2_L3_TIEBREAK_DELTA

    voted_is_present = voted is not None and voted_type != "UNKNOWN"
    voted_is_structurally_strong = (
        voted_is_present
        and voted_score > 0.0
        and voted_support_count >= 2
        and voted_margin >= margin_min
    )
    voted_is_confident_enough = voted_is_present and voted_conf >= accept_threshold
    voted_is_usable_for_l4 = (
        voted_is_present
        and voted_score > 0.0
        and not contradiction
        and not domain_conflict
        and input_quality >= review_quality_floor
        and (voted_is_structurally_strong or voted_is_confident_enough)
    )

    rejected_voted_reasons = [
        reason
        for reason, active in [
            ("missing_voted", voted is None),
            ("unknown_type", voted is not None and voted_type == "UNKNOWN"),
            ("non_positive_score", voted is not None and voted_score <= 0.0),
            ("contradiction_detected", contradiction),
            ("domain_conflict", domain_conflict),
            ("low_input_quality", input_quality < review_quality_floor),
            ("weak_support", voted is not None and voted_support_count < 2),
            (
                "weak_margin_and_confidence",
                voted is not None
                and not (voted_is_structurally_strong or voted_is_confident_enough),
            ),
        ]
        if active
    ]

    details["pre_l4_signal_decision"] = {
        "voted_present": voted is not None,
        "voted_type": voted_type,
        "voted_score": voted_score,
        "voted_confidence": voted_conf,
        "voted_margin": voted_margin,
        "voted_support_count": voted_support_count,
        "domain_conflict": domain_conflict,
        "contradiction_detected": contradiction,
        "input_quality": input_quality,
        "accept_threshold": accept_threshold,
        "margin_min": margin_min,
        "review_quality_floor": review_quality_floor,
        "voted_is_structurally_strong": voted_is_structurally_strong,
        "voted_is_confident_enough": voted_is_confident_enough,
        "voted_is_usable_for_l4": voted_is_usable_for_l4,
        "rejected_voted_reasons": rejected_voted_reasons,
    }

    if voted_is_usable_for_l4:
        details["pre_l4_signal_decision"]["selected_source"] = "VOTED"
        details["pre_l4_signal_decision"]["selected_quality"] = "strong"
        return (
            voted_type,
            voted_conf,
            voted.get("language", language) if voted else language,
            voted.get("jurisdiction", jurisdiction) if voted else jurisdiction,
            "VOTED",
        )

    l3_candidate = _candidate_from_obj(
        top_l3,
        source="L3",
        language=language,
        jurisdiction=jurisdiction,
    )
    l2_candidate = _candidate_from_obj(
        top_l2,
        source="L2",
        language=language,
        jurisdiction=jurisdiction,
    )

    if l3_candidate and l2_candidate:
        if l3_candidate[1] >= l2_candidate[1] + tiebreak_delta:
            details["pre_l4_signal_decision"]["selected_source"] = "L3"
            details["pre_l4_signal_decision"]["selected_quality"] = "fallback_candidate"
            return l3_candidate
        if l2_candidate[1] >= l3_candidate[1] + tiebreak_delta:
            details["pre_l4_signal_decision"]["selected_source"] = "L2"
            details["pre_l4_signal_decision"]["selected_quality"] = "fallback_candidate"
            return l2_candidate
        if l3_candidate[1] >= l2_candidate[1]:
            details["pre_l4_signal_decision"]["selected_source"] = "L3"
            details["pre_l4_signal_decision"]["selected_quality"] = "fallback_candidate"
            return l3_candidate
        details["pre_l4_signal_decision"]["selected_source"] = "L2"
        details["pre_l4_signal_decision"]["selected_quality"] = "fallback_candidate"
        return l2_candidate

    if l3_candidate:
        details["pre_l4_signal_decision"]["selected_source"] = "L3"
        details["pre_l4_signal_decision"]["selected_quality"] = "fallback_candidate"
        return l3_candidate

    if l2_candidate:
        details["pre_l4_signal_decision"]["selected_source"] = "L2"
        details["pre_l4_signal_decision"]["selected_quality"] = "fallback_candidate"
        return l2_candidate

    if top_l1 is not None and _normalize_type_code(top_l1.get("type_code")) != "UNKNOWN":
        details["pre_l4_signal_decision"]["selected_source"] = "L1"
        details["pre_l4_signal_decision"]["selected_quality"] = "weak"
        return (
            _normalize_type_code(top_l1.get("type_code")),
            _safe_float(top_l1.get("confidence", 0.0), 0.0),
            language,
            jurisdiction,
            "L1",
        )

    if voted is not None and voted_type != "UNKNOWN":
        details["pre_l4_signal_decision"]["selected_source"] = "VOTED_FALLBACK"
        details["pre_l4_signal_decision"]["selected_quality"] = "weak_belief"
        return (
            voted_type,
            voted_conf,
            voted.get("language", language),
            voted.get("jurisdiction", jurisdiction),
            "VOTED_FALLBACK",
        )

    details["pre_l4_signal_decision"]["selected_source"] = "NONE"
    details["pre_l4_signal_decision"]["selected_quality"] = "none"
    return "UNKNOWN", 0.0, language, jurisdiction, "NONE"


def build_llm_source_text(
    header_text: str | None,
    body_text: str | None,
) -> str:
    """
    Собирает текст для передачи в LLM из header и body.

    Правила:
      - пустые строки игнорируются;
      - части соединяются двойным переносом строки;
      - результат всегда strip()-нут;
      - если обе части пусты — возвращает пустую строку.
    """
    parts: list[str] = []
    if header_text:
        parts.append(header_text.strip())
    if body_text:
        parts.append(body_text.strip())
    return "\n\n".join(p for p in parts if p).strip()


def make_l4_error_details(e: Exception) -> dict:
    """
    Формирует payload details["L4"] при неожиданной ошибке вызова LLM.

    Гарантирует, что все ключи всегда присутствуют — это позволяет
    вызывающему коду не проверять, что именно упало.
    """
    return {
        "type": "UNKNOWN",
        "confidence": 0.0,
        "method": "llm_error",
        "reasoning": "",
        "parse_success": False,
        "error_kind": "unexpected_exception",
        "raw": {
            "provider": None,
            "model": None,
            "tokens_used": None,
            "parse_success": False,
            "error_type": "unexpected_exception",
            "error_message": str(e),
            "response_text": None,
            "parsed_json": None,
            "llm_attempts": 0,
        },
    }


def apply_voting(
    *,
    doc_id: str,
    voted: dict | None,
    top_l1: dict | None,
    top_l3: Any | None,
    language: str | None,
    jurisdiction: str | None,
    details: dict,
) -> tuple[str, float, str | None, str | None, dict]:
    """
    Применяет результат голосования и обновляет details.

    Возвращает: (final_type, final_conf, language, jurisdiction, details)
      - final_type  — тип-победитель голосования (или "UNKNOWN");
      - final_conf  — decision confidence голосования (voting_score + margin_bonus);
                      это НЕ raw confidence отдельного кандидата.

    Поля details после вызова:

    Canonical (используются downstream-кодом и тестами как контракт):
      details["voting"]                  — полный canonical объект voting-решения
                                           (build_voting_details). Содержит:
                                           type, score, confidence, margin,
                                           support_count, support_levels,
                                           ranking (enriched), domain_conflict, ...
      details["voting_ranking"]          — top-3 в минимальном формате:
                                           [{"type": str, "score": float}, ...]
                                           Только эти два поля, ничего лишнего.
      details["voting_raw"]              — сырой dict из WeightedVoter.vote().
      details["voting_margin"]           — float, margin между #1 и #2.
      details["voting_score"]            — float, voting_score победителя.
      details["voting_support_count"]    — int, число уникальных уровней.
      details["voting_support_levels"]   — list[str], какие уровни поддержали.
      details["domain_conflict"]         — bool.
      details["parent_conflict"]         — bool.
      details["group_conflict"]          — bool.
      details["top2_types"]              — list[str], top-2 типа из голосования.

    Debug/trace (только при CLASSIFICATION_TRACE_INCLUDE_RANKING=True):
      details["voting_ranking_enriched"] — top-3 с полным payload voter'а:
                                           raw_score, normalized_score,
                                           agreement_bonus, dominant_floor,
                                           level_contributions, и т.д.
                                           НЕ является контрактом, может меняться.

    Опциональные (если применимо):
      details["l1_support"]              — если L1 согласен с результатом voting.
      details["top_l3_snapshot"]         — снапшот top_l3 для explainability.
    """

    final_type = "UNKNOWN"
    final_conf = 0.0

    existing_voting = details.get("voting") if isinstance(details.get("voting"), dict) else {}

    if voted is not None:
        ranking = _normalize_ranking(voted.get("ranking"))
        margin = _safe_float(voted.get("margin", 0.0), 0.0)
        voting_score = _get_voted_score(voted)
        final_type = _get_voted_type(voted)
        final_conf = _safe_float(voted.get("confidence", 0.0), 0.0)

        if final_type == "UNKNOWN":
            final_conf = 0.0
            voting_score = 0.0
            margin = 0.0

        language = voted.get("language", language)
        jurisdiction = voted.get("jurisdiction", jurisdiction)

        details["voting"] = build_voting_details(
            strategy="WEIGHTED_VOTING",
            reason="weighted voter selected best candidate",
            voted=voted,
            extra=existing_voting,
        )
        details["voting_raw"] = voted
        details["voting_margin"] = margin
        details["voting_score"] = voting_score
        details["domain_conflict"] = bool(details["voting"].get("domain_conflict", False))
        details["parent_conflict"] = bool(details["voting"].get("parent_conflict", False))
        details["group_conflict"] = bool(details["voting"].get("group_conflict", False))
        details["top2_types"] = _normalize_top2_types(details["voting"].get("top2_types"))
        details["voting_support_count"] = _safe_int(
            details["voting"].get("support_count", 0),
            0,
        )
        details["voting_support_levels"] = _normalize_support_levels(
            details["voting"].get("support_levels")
        )

        if settings.CLASSIFICATION_TRACE_INCLUDE_RANKING:
            # voting_ranking — canonical формат: только type и score.
            # Используется downstream-кодом и тестами как минимальный контракт.
            # Не содержит debug-полей voter'а (raw_score, level_contributions, и т.д.).
            details["voting_ranking"] = [
                {"type": entry["type"], "score": entry["score"]} for entry in ranking[:3]
            ]
            # voting_ranking_enriched — полный debug payload из voter'а.
            # Содержит все поля: raw_score, normalized_score, agreement_bonus,
            # dominant_floor, level_contributions, support_count, и т.д.
            # Используется только для трейсинга и аналитики, не является контрактом.
            details["voting_ranking_enriched"] = ranking[:3]

        logger.debug(
            "Hybrid voting result applied",
            extra={
                "doc_id": doc_id,
                "final_type": final_type,
                "final_conf": final_conf,
                "voting_score": voting_score,
                "margin": margin,
                "support_count": details["voting_support_count"],
                "support_levels": details["voting_support_levels"],
                "domain_conflict": details["domain_conflict"],
                "top2": details["top2_types"],
                "top3": ranking[:3],
            },
        )

    else:
        details["voting"] = build_voting_details(
            strategy="NO_VOTED_RESULT",
            reason="voter returned None",
            voted=None,
            extra=existing_voting,
        )
        details["voting_raw"] = None
        details["voting_margin"] = 0.0
        details["voting_score"] = 0.0
        details["domain_conflict"] = False
        details["parent_conflict"] = False
        details["group_conflict"] = False
        details["top2_types"] = []
        details["voting_support_count"] = 0
        details["voting_support_levels"] = []

    if (
        voted is not None
        and top_l1
        and final_type != "UNKNOWN"
        and _normalize_type_code(top_l1.get("type_code")) == final_type
    ):
        l1_conf = _safe_float(top_l1.get("confidence", 0.0), 0.0)
        details["l1_support"] = {
            "strategy": "L1_SUPPORTS_FINAL_TYPE",
            "reason": "filename signal agrees with voted type",
            "final_type": final_type,
            "final_confidence": final_conf,
            "l1_confidence": l1_conf,
            "applied_as": "explainability_only",
        }

        logger.debug(
            "Hybrid voting supported by aligned L1",
            extra={
                "doc_id": doc_id,
                "final_type": final_type,
                "final_confidence": final_conf,
                "l1_confidence": l1_conf,
            },
        )

    if top_l3 is not None and getattr(top_l3, "doctype", None):
        details["top_l3_snapshot"] = {
            "type": _normalize_type_code(getattr(top_l3, "doctype", None)),
            "confidence": _safe_float(getattr(top_l3, "confidence", 0.0), 0.0),
            "language": getattr(top_l3, "language", language),
            "jurisdiction": getattr(top_l3, "jurisdiction", jurisdiction),
        }

    return final_type, final_conf, language, jurisdiction, details
