# src/core/semantic_enrichment_degradation.py

"""
Pure-logic helpers for semantic enrichment degradation analysis.

Задача:
- вычислить степень деградации (severity) при terminal outcome DEGRADED;
- сформировать список machine-readable reason codes;
- собрать финальный degradation payload для result_details / stage_trace.

Этот модуль не зависит от ORM/Celery/settings.
Пригоден для unit-тестов без тяжёлых импортов.

Reason codes (стабильные, машиночитаемые):
- segment_timeout       — один или несколько сегментов превысили timeout
- segment_failure       — ошибка при LLM enrichment или загрузке baseline
- budget_exhausted      — бюджет документа исчерпан
- persist_mismatch      — sidecar записан в S3, но не привязан в БД
- primary_missing_enrichment — primary-сегмент не получил enrichment

Согласованность с проектным стилем:
- degraded_reason строится через ";" по аналогии с layout_language_filter.py
  и quick_pdf_layout.py.
"""

from __future__ import annotations

from typing import Any

from core.constants import (
    SemanticEnrichmentDegradationSeverity,
    SemanticEnrichmentStageOutcome,
)

# ── Severity thresholds ───────────────────────────────────────────────────────

_MINOR_THRESHOLD = 0.8     # ≥ 80% enriched → MINOR
_PARTIAL_THRESHOLD = 0.2   # ≥ 20% enriched → PARTIAL; < 20% → CRITICAL


def _compute_enrichment_ratio(
    segments_enriched: int,
    segments_with_legal_units_ref: int,
) -> float:
    """
    Вычислить долю успешно обогащённых сегментов.

    Возвращает 0.0, если нет кандидат-сегментов.
    """
    if segments_with_legal_units_ref <= 0:
        return 0.0
    return segments_enriched / segments_with_legal_units_ref


def _compute_severity(enrichment_ratio: float) -> SemanticEnrichmentDegradationSeverity:
    """
    Определить степень деградации по доле enriched сегментов.

    Пороги:
    - MINOR    → ratio >= 0.8
    - PARTIAL  → 0.2 <= ratio < 0.8
    - CRITICAL → ratio < 0.2
    """
    if enrichment_ratio >= _MINOR_THRESHOLD:
        return SemanticEnrichmentDegradationSeverity.MINOR
    if enrichment_ratio >= _PARTIAL_THRESHOLD:
        return SemanticEnrichmentDegradationSeverity.PARTIAL
    return SemanticEnrichmentDegradationSeverity.CRITICAL


def _collect_degradation_reasons(
    *,
    segments_timed_out: int,
    segments_failed: int,
    segments_skipped_budget: int,
    persist_mismatch_count: int,
    primary_missing_count: int,
) -> list[str]:
    """
    Собрать список machine-readable reason codes деградации.

    Порядок: от наиболее критичного к наименее критичному.
    """
    reasons: list[str] = []

    if primary_missing_count > 0:
        reasons.append("primary_missing_enrichment")

    if persist_mismatch_count > 0:
        reasons.append("persist_mismatch")

    if segments_timed_out > 0:
        reasons.append("segment_timeout")

    if segments_failed > 0:
        reasons.append("segment_failure")

    if segments_skipped_budget > 0:
        reasons.append("budget_exhausted")

    return reasons


def derive_semantic_enrichment_degradation(
    *,
    outcome: SemanticEnrichmentStageOutcome,
    segments_enriched: int,
    segments_with_legal_units_ref: int,
    segments_timed_out: int,
    segments_failed: int,
    segments_skipped_budget: int,
    persist_mismatch_count: int,
    primary_missing_count: int,
) -> dict[str, Any]:
    """
    Вычислить полный degradation payload для result_details.

    Возвращает dict, который включается в:
    - result_payload (возврат из worker)
    - output_summary (stage_trace)
    - decision_details (stage_trace)

    При outcome != DEGRADED:
    - degraded = False
    - degradation_severity = None
    - degradation_reasons = []
    - degraded_reason = None

    При outcome == DEGRADED:
    - degraded = True
    - degradation_severity: "minor" | "partial" | "critical"
    - degradation_reasons: list[str] (machine-readable reason codes)
    - degraded_reason: str (joined by ";") или None
    """
    enrichment_ratio = _compute_enrichment_ratio(
        segments_enriched=segments_enriched,
        segments_with_legal_units_ref=segments_with_legal_units_ref,
    )

    if outcome != SemanticEnrichmentStageOutcome.DEGRADED:
        return {
            "degraded": False,
            "degradation_severity": None,
            "enrichment_ratio": round(enrichment_ratio, 4),
            "degraded_segments": (
                segments_timed_out + segments_failed + segments_skipped_budget
            ),
            "degradation_reasons": [],
            "degraded_reason": None,
            "persist_mismatch_count": persist_mismatch_count,
            "primary_missing_count": primary_missing_count,
        }

    severity = _compute_severity(enrichment_ratio)
    reasons = _collect_degradation_reasons(
        segments_timed_out=segments_timed_out,
        segments_failed=segments_failed,
        segments_skipped_budget=segments_skipped_budget,
        persist_mismatch_count=persist_mismatch_count,
        primary_missing_count=primary_missing_count,
    )

    return {
        "degraded": True,
        "degradation_severity": severity.value,
        "enrichment_ratio": round(enrichment_ratio, 4),
        "degraded_segments": (
            segments_timed_out + segments_failed + segments_skipped_budget
        ),
        "degradation_reasons": reasons,
        "degraded_reason": ";".join(reasons) if reasons else None,
        "persist_mismatch_count": persist_mismatch_count,
        "primary_missing_count": primary_missing_count,
    }



