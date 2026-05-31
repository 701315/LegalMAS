# src/services/structure/semantic_enrichment/_validator.py

"""
Безопасный парсер LLM response для semantic enrichment.

Этот модуль превращает сырую строку от LLM в типизированный
LLMEnrichmentProposal. Он спроектирован для максимальной устойчивости
к некорректным ответам модели.

Что обрабатывается:
- Валидный JSON → полный proposal.
- JSON обёрнутый в markdown code fences (```json ... ```) → очистка и парсинг.
- Невалидные enum values → парсятся как None, сохраняются в diagnostics.
- Topics как строка вместо массива → разбиваются по запятым/точкам с запятой.
- Evidence quotes как строка → оборачивается в список.
- Confidence вне [0, 1] → clamped.
- Reasoning обрезается до max_reasoning_chars.
- Полностью невалидный JSON → возвращает None (caller обрабатывает как FAILED).

Принципы:
- Никогда не бросает исключений — всегда возвращает proposal или None.
- Partial parse лучше чем полный reject: если unit_type невалиден
  но topics валидны, proposal содержит topics.
- Все невалидные поля документируются в proposal.diagnostics["invalid_fields"].
"""

from __future__ import annotations

import json
import re
from typing import Any

from services.structure.legal_unit_models import ClauseFunction, LegalUnitType
from services.structure.semantic_enrichment._types import LLMEnrichmentProposal


def _strip_code_fences(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _parse_unit_type(value: Any) -> tuple[LegalUnitType | None, str | None]:
    raw = _normalize_text(value).lower()
    if not raw or raw in {"null", "none", "unknown"}:
        return None, None

    try:
        return LegalUnitType(raw), None
    except Exception:
        return None, raw


def _parse_clause_function(value: Any) -> tuple[ClauseFunction | None, str | None]:
    raw = _normalize_text(value).lower()
    if not raw or raw in {"null", "none", "unknown"}:
        return None, None

    try:
        return ClauseFunction(raw), None
    except Exception:
        return None, raw


def _parse_string_list(value: Any) -> list[str]:
    """
    Парсит поле, которое может быть:
    - list[str]
    - str
    - None
    """
    if value is None:
        return []

    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            text = _normalize_text(item)
            if text:
                result.append(text)
        return result

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        return [part.strip() for part in re.split(r"[,\n;]+", text) if part.strip()]

    return []


def _parse_evidence_quotes(value: Any, *, max_quotes: int = 5) -> list[str]:
    """
    Парсит evidence_quotes — список коротких цитат из текста clause.
    """
    raw_list = _parse_string_list(value)

    result: list[str] = []
    for quote in raw_list:
        cleaned = quote.strip().strip("\"'")
        if cleaned and len(cleaned) >= 3:
            result.append(cleaned[:300])

    return result[:max_quotes]


def parse_llm_enrichment_response(
    raw: str,
    *,
    max_reasoning_chars: int = 600,
) -> LLMEnrichmentProposal | None:
    """
    Безопасно парсит raw LLM JSON в LLMEnrichmentProposal.

    Возвращает:
    - proposal, даже если часть полей невалидна;
    - None только если JSON совсем не удалось распарсить.
    """
    cleaned = _strip_code_fences(raw)
    if not cleaned:
        return None

    try:
        data = json.loads(cleaned)
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    invalid_fields: dict[str, Any] = {}

    unit_type, invalid_unit_type = _parse_unit_type(data.get("suggested_unit_type"))
    if invalid_unit_type:
        invalid_fields["suggested_unit_type"] = invalid_unit_type

    clause_function, invalid_clause_function = _parse_clause_function(
        data.get("suggested_clause_function")
    )
    if invalid_clause_function:
        invalid_fields["suggested_clause_function"] = invalid_clause_function

    topics = _parse_string_list(data.get("suggested_topics"))
    evidence_quotes = _parse_evidence_quotes(data.get("evidence_quotes"))
    confidence = max(0.0, min(1.0, _safe_float(data.get("confidence"), 0.0)))
    reasoning = _normalize_text(data.get("reasoning"))[:max_reasoning_chars]

    diagnostics: dict[str, Any] = {}
    if invalid_fields:
        diagnostics["invalid_fields"] = invalid_fields

    return LLMEnrichmentProposal(
        suggested_unit_type=unit_type,
        suggested_clause_function=clause_function,
        suggested_topics=topics,
        confidence=round(confidence, 3),
        reasoning=reasoning,
        evidence_quotes=evidence_quotes,
        diagnostics=diagnostics,
    )


