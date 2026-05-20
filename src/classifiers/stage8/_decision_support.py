# src/classifiers/stage8/_decision_support.py
"""
Вспомогательные функции для принятия и объяснения решений классификатора.

PR1: build_voting_details, best_pre_l4_signal,
     build_llm_source_text, make_l4_error_details
PR2: apply_voting
"""
from __future__ import annotations

from typing import Any, Optional

from core.config import settings          # PR2: добавлен импорт
from core.logging import get_logger       # PR2: добавлен импорт

logger = get_logger(__name__)             # PR2: добавлен logger


# ══════════════════════════════════════════════════════════════════════════════
# build_voting_details  (PR1 — без изменений)
# ══════════════════════════════════════════════════════════════════════════════

def build_voting_details(
    *,
    strategy: str,
    reason: str,
    voted: dict | None = None,
    extra: dict | None = None,
) -> dict:
    """
    Формирует структуру details["voting"].

    Параметры:
      strategy — строковый идентификатор стратегии
                 (напр. "L2_STRONG_WINS", "WEIGHTED_VOTING", "NO_VOTED_RESULT")
      reason   — человекочитаемое объяснение выбора
      voted    — raw payload от WeightedVoter (опционально)
      extra    — дополнительные поля; ключи из top_level_keys перезапишут
                 поля voted, остальные попадут во вложенный "extra"

    Возвращает dict с фиксированной схемой — все ключи всегда присутствуют,
    что позволяет безопасно делать details["voting"].get("score") без KeyError.

    Схема результата:
      {
        "strategy":                  str,
        "reason":                    str,
        "type":                      str | None,
        "score":                     float | None,
        "confidence":                float | None,
        "margin":                    float | None,
        "support_count":             int | None,
        "support_levels":            list[str],
        "single_source_cap_applied": bool,
        "ranking":                   list,
        "extra":                     dict,
      }
    """
    payload: dict[str, Any] = {
        "strategy": strategy,
        "reason": reason,
        "type": None,
        "score": None,
        "confidence": None,
        "margin": None,
        "support_count": None,
        "support_levels": [],
        "single_source_cap_applied": False,
        "ranking": [],
        "extra": {},
    }

    if voted:
        payload.update(
            {
                "type": voted.get("type"),
                "score": voted.get("voting_score"),
                "confidence": voted.get("confidence"),
                "margin": voted.get("margin"),
                "support_count": voted.get("support_count"),
                "support_levels": list(voted.get("support_levels") or []),
                "single_source_cap_applied": bool(
                    voted.get("single_source_cap_applied", False)
                ),
                "ranking": list(voted.get("ranking") or []),
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
            "ranking",
        }

        for key in top_level_keys:
            if key in extra:
                payload[key] = extra[key]

        payload["extra"] = {
            k: v
            for k, v in extra.items()
            if k not in top_level_keys
        }

    return payload


# ══════════════════════════════════════════════════════════════════════════════
# best_pre_l4_signal  (PR1 — без изменений)
# ══════════════════════════════════════════════════════════════════════════════

def best_pre_l4_signal(
    *,
    voted: dict | None,
    top_l1: dict | None,
    top_l2: Any | None,
    top_l3: Any | None,
    language: str | None,
    jurisdiction: str | None,
) -> tuple[str, float, str | None, str | None, str]:
    """
    Возвращает лучший известный сигнал ДО вызова L4.

    Используется для:
      - routing: стоит ли запускать L4;
      - fallback: что вернуть, если L4 не запустился или ничего не дал;
      - logging: что было "лучшим кандидатом" в pre_l4_best_signal.

    Важно:
      Это НЕ decision rule и НЕ ранний return.
      Это честная оценка strongest-known signal без изменения flow.
      Вызывающий код сам решает, что делать с результатом.

    Приоритет выбора:
      1. voted result        (если voter вернул что-то)
      2. top_l2              (если L2 дал результат != UNKNOWN)
      3. top_l3              (если L3 дал результат != UNKNOWN)
      4. top_l1              (если L1 дал результат)
      5. UNKNOWN             (нет ни одного сигнала)

    Возвращает:
      (final_type, final_conf, language, jurisdiction, source)

      source — строка: "VOTED" | "L2" | "L3" | "L1" | "NONE"
    """
    if voted is not None:
        return (
            str(voted.get("type") or "UNKNOWN"),
            float(voted.get("confidence", 0.0)),
            voted.get("language", language),
            voted.get("jurisdiction", jurisdiction),
            "VOTED",
        )

    if top_l2 is not None and getattr(top_l2, "doctype", "UNKNOWN") != "UNKNOWN":
        return (
            str(top_l2.doctype),
            float(top_l2.confidence),
            language,
            jurisdiction,
            "L2",
        )

    if top_l3 is not None and getattr(top_l3, "doctype", "UNKNOWN") != "UNKNOWN":
        return (
            str(top_l3.doctype),
            float(top_l3.confidence),
            getattr(top_l3, "language", language),
            getattr(top_l3, "jurisdiction", jurisdiction),
            "L3",
        )

    if top_l1 is not None and top_l1.get("type_code"):
        return (
            str(top_l1["type_code"]),
            float(top_l1.get("confidence", 0.0)),
            language,
            jurisdiction,
            "L1",
        )

    return "UNKNOWN", 0.0, language, jurisdiction, "NONE"


# ══════════════════════════════════════════════════════════════════════════════
# build_llm_source_text  (PR1 — без изменений)
# ══════════════════════════════════════════════════════════════════════════════

def build_llm_source_text(
    header_text: Optional[str],
    snippet_text: Optional[str],
) -> str:
    """
    Собирает текст для передачи в LLM из header и snippet.

    Правила:
      - пустые строки игнорируются;
      - части соединяются двойным переносом строки;
      - результат всегда strip()-нут;
      - если обе части пусты — возвращает пустую строку.
    """
    parts: list[str] = []
    if header_text:
        parts.append(header_text.strip())
    if snippet_text:
        parts.append(snippet_text.strip())
    return "\n\n".join(p for p in parts if p).strip()


# ══════════════════════════════════════════════════════════════════════════════
# make_l4_error_details  (PR1 — без изменений)
# ══════════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════════
# apply_voting  (PR2 — новое)
# ══════════════════════════════════════════════════════════════════════════════

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

    Важные инварианты (нельзя нарушать):
      - voting определяет итоговый type и confidence;
      - L1 может выступать только как supporting signal для explainability;
      - L1 никогда не меняет final_type и не повышает final_conf post-hoc;
      - details изменяется in-place И возвращается — вызывающий код
        должен использовать возвращённый details, а не рассчитывать только
        на мутацию.

    Параметры:
      doc_id       — идентификатор документа или сегмента (для логов)
      voted        — raw payload от WeightedVoter или None
      top_l1       — dict с ключами type_code/confidence или None
      top_l3       — объект с атрибутами doctype/confidence или None
      language     — текущий язык (может обновиться из voted)
      jurisdiction — текущая юрисдикция (может обновиться из voted)
      details      — текущий dict деталей (изменяется in-place)

    Возвращает:
      (final_type, final_conf, language, jurisdiction, details)

    Что пишет в details:
      details["voting"]        — структура из build_voting_details(...)
      details["voting_raw"]    — raw payload от voter (или None)
      details["voting_margin"] — float margin (или 0.0)
      details["voting_ranking"]— top-3 ranking (только если settings разрешает)
      details["l1_support"]    — если L1 совпадает с final_type (explainability)
    """
    final_type = "UNKNOWN"
    final_conf = 0.0

    if voted is not None:
        details["voting"] = build_voting_details(
            strategy="WEIGHTED_VOTING",
            reason="weighted voter selected best candidate",
            voted=voted,
        )
        details["voting_raw"] = voted

        final_type = str(voted.get("type") or "UNKNOWN")
        final_conf = float(voted.get("confidence", 0.0))
        language = voted.get("language", language)
        jurisdiction = voted.get("jurisdiction", jurisdiction)

        margin = float(voted.get("margin", 0.0))
        ranking = voted.get("ranking", [])
        details["voting_margin"] = margin

        if settings.CLASSIFICATION_TRACE_INCLUDE_RANKING:
            details["voting_ranking"] = ranking[:3]

        logger.debug(
            "Hybrid voting result applied",
            extra={
                "doc_id": doc_id,
                "final_type": final_type,
                "final_conf": final_conf,
                "margin": margin,
                "top3": ranking[:3],
            },
        )

    else:
        details["voting"] = build_voting_details(
            strategy="NO_VOTED_RESULT",
            reason="voter returned None",
            voted=None,
        )
        details["voting_raw"] = None
        details["voting_margin"] = 0.0

    # L1 используется только как supporting evidence для explainability.
    # Он не меняет итоговый type и не повышает confidence после voting.
    if (
        voted is not None
        and top_l1
        and final_type != "UNKNOWN"
        and top_l1.get("type_code") == final_type
    ):
        l1_conf = float(top_l1.get("confidence", 0.0))
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

    return final_type, final_conf, language, jurisdiction, details
    

