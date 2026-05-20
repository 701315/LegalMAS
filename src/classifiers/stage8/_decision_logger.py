# src/classifiers/stage8/_decision_logger.py

"""
Единообразный финальный лог классификационного решения.

Вызывается ровно один раз в каждой ветке classify_document /
classify_segment — непосредственно перед return.

Принципы:
 - Один INFO на одно классификационное решение.
 - Все промежуточные логи (L1/L2/L3/voting) — DEBUG в hybrid_classifier.py.
 - decided_by — типобезопасный StrEnum, не хардкод строк.
 - schema_version — защита от поломки при эволюции формата.
 - trace_id — опциональный, для сквозной корреляции с API / другими воркерами.
   Генерация trace_id в base_task.py — отдельная задача после изучения контракта.
"""
from __future__ import annotations

import time
from enum import StrEnum
from typing import Any

import structlog

from core.config import settings


_logger = structlog.get_logger(__name__)


def _explainability_schema_version() -> str:
    """
    Возвращает версию схемы explainability-лога.

    Делаем это через settings, чтобы версия details и версия INFO-лога
    могли эволюционировать согласованно.
    """
    raw = getattr(settings, "CLASSIFICATION_DECISION_TRACE_SCHEMA_VERSION", 1)
    return f"explainability_v{raw}"


class DecisionStrategy(StrEnum):
    """
    Типобезопасный перечень стратегий классификационного решения.

    Порядок отражает каскад: ранние exits сверху, fallback снизу.
    """
    COPIED = "COPIED"                    # Stage 7: документ — копия мастера
    L2_STRONG_WINS = "L2_STRONG_WINS"    # L2 confidence >= strong threshold, нет решающего L3-конфликта
    L1_L2_AGREE = "L1_L2_AGREE"          # L1 и L2 совпали с confidence >= 0.7
    HYBRID_VOTING = "HYBRID_VOTING"      # Взвешенное голосование L1–L3 дало уверенный результат
    L4_LLM = "L4_LLM"                    # LLM-fallback дал результат
    FALLBACK_LOW = "FALLBACK_LOW"        # Voting слабый, L4 не помог — низкая уверенность
    FALLBACK_UNKNOWN = "FALLBACK_UNKNOWN"  # Не удалось определить тип — UNKNOWN


def log_classification_decision(
    *,
    doc_id: str,
    decided_by: DecisionStrategy,
    final_type: str | None,
    final_confidence: float,
    levels_tried: list[str],
    started_at: float,
    trace_id: str | None = None,
    contradiction: bool = False,
    l4_triggered: bool = False,
    l4_skip_reason: str | None = None,
    requires_manual_review: bool = False,
    confidence_zone: str | None = None,
    unknown_corridor_applied: bool | None = None,
    voting_score: float | None = None,
    single_source_cap_applied: bool | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """
    Единственный INFO-лог, описывающий итог одного классификационного решения.

    Параметры:
        doc_id                   — ID документа или "segment:{id}" для сегментов.
        decided_by               — Стратегия, по которой принято решение.
        final_type               — Итоговый тип документа. None → будет заменён "UNKNOWN".
        final_confidence         — Итоговая уверенность [0.0, 1.0].
        levels_tried             — Список уровней каскада, которые были выполнены.
        started_at               — time.time() из начала classify_document/classify_segment.
        trace_id                 — Опциональный ID для сквозной корреляции.
        contradiction            — Был ли обнаружен конфликт L2 vs L3.
        l4_triggered             — Был ли вызван LLM (L4).
        l4_skip_reason           — Причина, по которой L4 не был вызван (если не вызван).
        requires_manual_review   — Требуется ли ручная проверка.
        confidence_zone          — "confident" | "low" | "unknown".
        unknown_corridor_applied — Был ли final_type принудительно заменён на UNKNOWN.
        voting_score             — "Чистый" score голосования до margin bonus.
        single_source_cap_applied — Был ли применён cap к single-source победителю.
        extra                    — Дополнительные поля, специфичные для стратегии.
    """
    payload: dict[str, Any] = {
        "schema_version": _explainability_schema_version(),
        "decided_by": decided_by.value,
        "final_type": final_type or "UNKNOWN",
        "final_confidence": round(float(final_confidence), 4),
        "levels_tried": levels_tried,
        "duration_ms": round((time.time() - started_at) * 1000),
        "l4_triggered": l4_triggered,
        "contradiction": contradiction,
        "requires_manual_review": requires_manual_review,
    }

    if trace_id is not None:
        payload["trace_id"] = trace_id
    if confidence_zone is not None:
        payload["confidence_zone"] = confidence_zone
    if l4_skip_reason is not None:
        payload["l4_skip_reason"] = l4_skip_reason
    if unknown_corridor_applied is not None:
        payload["unknown_corridor_applied"] = bool(unknown_corridor_applied)
    if voting_score is not None:
        payload["voting_score"] = round(float(voting_score), 4)
    if single_source_cap_applied is not None:
        payload["single_source_cap_applied"] = bool(single_source_cap_applied)

    if extra:
        for k, v in extra.items():
            if k not in payload:
                payload[k] = v

    _logger.info("classification_decision", doc_id=doc_id, **payload)


def describe_l4_skip(
    *,
    l4_enabled: bool,
    llm_available: bool,
    has_source_and_types: bool,
    need_adjudication: bool,
    strong_single: bool,
) -> str:
    """
    Возвращает машиночитаемую причину, почему L4 не был вызван.
    Используется в hybrid_classifier._run_l4 при early return.
    """
    if not l4_enabled:
        return "l4_disabled_by_config"
    if not llm_available:
        return "llm_not_available"
    if not has_source_and_types:
        return "no_source_text_or_allowed_types"
    if not need_adjudication:
        return "confidence_sufficient"
    if strong_single:
        return "strong_single_signal"
    return "unknown_guard"


    