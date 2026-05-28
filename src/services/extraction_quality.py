# src/services/extraction_quality.py

"""
Extraction quality policy.

Задача:
- отделить бизнес-решение о качестве extraction от worker orchestration;
- классифицировать результат extract как:
  - ok         -> пайплайн продолжается;
  - quarantine -> результат сомнительный, нужна ручная проверка;
  - failed     -> extraction по сути непригоден для дальнейшей обработки.

Почему это важно:
- avg_ocr_confidence в hybrid-документах отражает только OCR-страницы,
  а не весь документ;
- низкое OCR-качество на небольшой доле страниц не должно всегда
  блокировать весь документ;
- policy должна быть тестируемой отдельно от Celery/MinIO/DB.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from services.pdf_extractor import ExtractionResult

QualityOutcome = Literal["ok", "quarantine", "failed"]


@dataclass(frozen=True)
class ExtractionQualityPolicy:
    ocr_quarantine_threshold: float
    hybrid_min_ocr_rate_for_quarantine: float
    policy_version: str = "v1"


@dataclass(frozen=True)
class ExtractionQualityDecision:
    outcome: QualityOutcome
    reason: str | None
    message: str
    details: dict[str, object]


def evaluate_extraction_quality(
    extraction: ExtractionResult,
    *,
    policy: ExtractionQualityPolicy,
) -> ExtractionQualityDecision:
    """
    Production-grade quality policy for ExtractionResult.

    Правила:
    1. Жёсткий провал:
       - есть ошибки и нет элементов;
       - нет элементов вообще.
    2. Чистый OCR:
       - если avg_ocr_confidence ниже порога -> quarantine.
    3. Hybrid:
       - учитываем не только avg_ocr_confidence, но и долю OCR-страниц (ocr_rate);
       - quarantine только если OCR занимает существенную часть документа
         и confidence реально низкий;
       - если OCR-страниц мало, документ пропускаем дальше.
    4. Unknown strategy:
       - не считаем это нормальным состоянием;
       - отправляем в quarantine как нарушение контракта extractor -> policy.
    """

    page_count = int(extraction.page_count or 0)
    elements = extraction.elements or []
    errors = extraction.errors or []
    page_strategies = extraction.page_strategies or {}

    element_count = len(elements)
    error_count = len(errors)

    raw_strategy = extraction.strategy or "text"
    strategy = str(raw_strategy).lower()

    raw_avg_conf = extraction.avg_ocr_confidence
    avg_conf: float | None = None
    if raw_avg_conf is not None:
        try:
            avg_conf = float(raw_avg_conf)
        except (TypeError, ValueError):
            avg_conf = None

    if avg_conf is not None and not (0.0 <= avg_conf <= 1.0):
        avg_conf = None

    ocr_page_count = sum(1 for s in page_strategies.values() if s == "ocr")
    empty_page_count = sum(1 for s in page_strategies.values() if s == "empty")

    ocr_rate = (ocr_page_count / page_count) if page_count > 0 else 0.0
    empty_rate = (empty_page_count / page_count) if page_count > 0 else 0.0

    base_details = _build_base_details(
        strategy=strategy,
        page_count=page_count,
        element_count=element_count,
        error_count=error_count,
        ocr_page_count=ocr_page_count,
        empty_page_count=empty_page_count,
        ocr_rate=ocr_rate,
        empty_rate=empty_rate,
        avg_conf=avg_conf,
        confidence_available=avg_conf is not None,
        policy=policy,
    )

    if errors and element_count == 0:
        return ExtractionQualityDecision(
            outcome="failed",
            reason="extraction_failed",
            message=f"PDF extraction failed: {'; '.join(map(str, errors))}",
            details={
                **base_details,
                "errors": [str(e) for e in errors],
            },
        )

    if element_count == 0:
        return ExtractionQualityDecision(
            outcome="failed",
            reason="no_text_extracted",
            message="No text extracted from PDF — 0 elements",
            details=base_details,
        )

    if strategy == "text":
        return ExtractionQualityDecision(
            outcome="ok",
            reason=None,
            message="Extraction quality is acceptable",
            details={
                **base_details,
                "policy_mode": "text_passthrough",
            },
        )

    if strategy == "ocr":
        if avg_conf is None:
            return ExtractionQualityDecision(
                outcome="quarantine",
                reason="ocr_confidence_unavailable",
                message="OCR document has no valid OCR confidence metric",
                details={
                    **base_details,
                    "policy_mode": "ocr_strict",
                },
            )

        if avg_conf < policy.ocr_quarantine_threshold:
            return ExtractionQualityDecision(
                outcome="quarantine",
                reason="ocr_low_confidence",
                message=(
                    f"OCR confidence too low: "
                    f"{avg_conf:.2f} < threshold "
                    f"{policy.ocr_quarantine_threshold:.2f}"
                ),
                details={
                    **base_details,
                    "policy_mode": "ocr_strict",
                },
            )

        return ExtractionQualityDecision(
            outcome="ok",
            reason=None,
            message="Extraction quality is acceptable",
            details={
                **base_details,
                "policy_mode": "ocr_strict",
            },
        )

    if strategy == "hybrid":
        if ocr_rate < policy.hybrid_min_ocr_rate_for_quarantine:
            return ExtractionQualityDecision(
                outcome="ok",
                reason=None,
                message="Hybrid extraction quality is acceptable",
                details={
                    **base_details,
                    "policy_mode": "hybrid_low_ocr_rate_pass",
                },
            )

        if avg_conf is None:
            return ExtractionQualityDecision(
                outcome="quarantine",
                reason="ocr_confidence_unavailable",
                message=(
                    "Hybrid document has substantial OCR coverage but no valid "
                    "OCR confidence metric"
                ),
                details={
                    **base_details,
                    "policy_mode": "hybrid_contextual",
                },
            )

        if avg_conf < policy.ocr_quarantine_threshold:
            return ExtractionQualityDecision(
                outcome="quarantine",
                reason="ocr_low_confidence",
                message=(
                    f"Hybrid OCR confidence too low: "
                    f"{avg_conf:.2f} < threshold "
                    f"{policy.ocr_quarantine_threshold:.2f} "
                    f"(ocr_rate={ocr_rate:.2f})"
                ),
                details={
                    **base_details,
                    "policy_mode": "hybrid_contextual",
                },
            )

        return ExtractionQualityDecision(
            outcome="ok",
            reason=None,
            message="Hybrid extraction quality is acceptable",
            details={
                **base_details,
                "policy_mode": "hybrid_contextual",
            },
        )

    return ExtractionQualityDecision(
        outcome="quarantine",
        reason="unknown_extraction_strategy",
        message=f"Unknown extraction strategy: {strategy}",
        details={
            **base_details,
            "policy_mode": "unknown_strategy",
            "raw_strategy": raw_strategy,
        },
    )


def _build_base_details(
    *,
    strategy: str,
    page_count: int,
    element_count: int,
    error_count: int,
    ocr_page_count: int,
    empty_page_count: int,
    ocr_rate: float,
    empty_rate: float,
    avg_conf: float | None,
    confidence_available: bool,
    policy: ExtractionQualityPolicy,
) -> dict[str, object]:
    return {
        "policy_version": policy.policy_version,
        "strategy": strategy,
        "page_count": page_count,
        "element_count": element_count,
        "error_count": error_count,
        "ocr_page_count": ocr_page_count,
        "empty_page_count": empty_page_count,
        "ocr_rate": round(ocr_rate, 3),
        "empty_rate": round(empty_rate, 3),
        "avg_ocr_confidence": round(avg_conf, 3) if avg_conf is not None else None,
        "ocr_confidence_available": confidence_available,
        "ocr_quarantine_threshold": round(policy.ocr_quarantine_threshold, 3),
        "hybrid_min_ocr_rate_for_quarantine": round(policy.hybrid_min_ocr_rate_for_quarantine, 3),
    }
