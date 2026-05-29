# src/services/structure/_models/_confidence.py

"""
Phase 5 — Structural Confidence contracts.

Оценивает reliability hierarchy ПОСЛЕ:
    FSM → Resolution → Recovery → freeze()

Содержит:
- ConfidenceInput    — входные сигналы для расчёта
- StructuralConfidence — итоговая оценка (основной контракт Phase 5)
- DegradedModeConfig — параметры degraded mode

ВАЖНО по плану v5.2:
- retrieval_safe=True если confidence >= RETRIEVAL_SAFE_THRESHOLD (0.7)
- Если retrieval_safe=False — pipeline НЕ останавливается,
  включается degraded mode (layout fallback chunking,
  conservative overlaps, minimal semantic enrichment).
- local_confidence   — quality heading/grammar/recovery/numbering
- context_reliability — отдельный score для noisy/OCR-heavy зон
- Downstream (Chunk Planner Phase 10) читает retrieval_safe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Threshold фиксирован по плану v5.2
RETRIEVAL_SAFE_THRESHOLD: float = 0.7


@dataclass(slots=True)
class ConfidenceInput:
    """
    Входные сигналы для расчёта StructuralConfidence.

    Собирается после FSM + Resolution + Recovery.
    Передаётся в StructuralConfidence.from_inputs().

    heading_quality:        средний heading_confidence по принятым headings
    grammar_consistency:    доля headings без grammar violations
    recovery_confidence:    средний confidence по RecoveryReport decisions
    numbering_stability:    доля numeric/stable headings от общего числа
    ocr_noise_ratio:        доля элементов с OCR artifacts (0.0 если чистый PDF)
    rewrite_ratio:          из ResolutionAuditLog.rewrite_ratio
    orphan_ratio:           из RecoveryReport.orphan_ratio
    total_headings:         общее число принятых headings
    """

    heading_quality: float
    grammar_consistency: float
    recovery_confidence: float
    numbering_stability: float
    ocr_noise_ratio: float = 0.0
    rewrite_ratio: float = 0.0
    orphan_ratio: float = 0.0
    total_headings: int = 0

    def __post_init__(self) -> None:
        for fname, val in [
            ("heading_quality", self.heading_quality),
            ("grammar_consistency", self.grammar_consistency),
            ("recovery_confidence", self.recovery_confidence),
            ("numbering_stability", self.numbering_stability),
            ("ocr_noise_ratio", self.ocr_noise_ratio),
            ("rewrite_ratio", self.rewrite_ratio),
            ("orphan_ratio", self.orphan_ratio),
        ]:
            if not (0.0 <= val <= 1.0):
                raise ValueError(f"{fname} must be in [0.0, 1.0], got {val}")
        if self.total_headings < 0:
            raise ValueError(
                f"total_headings must be >= 0, got {self.total_headings}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "heading_quality": self.heading_quality,
            "grammar_consistency": self.grammar_consistency,
            "recovery_confidence": self.recovery_confidence,
            "numbering_stability": self.numbering_stability,
            "ocr_noise_ratio": self.ocr_noise_ratio,
            "rewrite_ratio": self.rewrite_ratio,
            "orphan_ratio": self.orphan_ratio,
            "total_headings": self.total_headings,
        }


@dataclass(slots=True)
class DegradedModeConfig:
    """
    Параметры degraded mode — активируется когда retrieval_safe=False.

    По плану v5.2:
    - layout fallback chunking
    - conservative overlaps
    - minimal semantic enrichment

    use_layout_fallback:     использовать Mode C chunking (Phase 10)
    conservative_overlap:    более широкий overlap между chunks
    skip_semantic_enrichment: пропустить LLM enrichment (Phase 12)
    reason:                  почему активирован degraded mode
    """

    use_layout_fallback: bool = True
    conservative_overlap: bool = True
    skip_semantic_enrichment: bool = True
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "use_layout_fallback": self.use_layout_fallback,
            "conservative_overlap": self.conservative_overlap,
            "skip_semantic_enrichment": self.skip_semantic_enrichment,
            "reason": self.reason,
        }


@dataclass(slots=True)
class StructuralConfidence:
    """
    Итоговая оценка reliability hierarchy — основной контракт Phase 5.

    local_confidence:    качество structure в пределах документа
                         [heading_quality, grammar, recovery, numbering]
    context_reliability: отдельный score для noisy/OCR-heavy зон
                         снижается при высоком ocr_noise_ratio
    retrieval_safe:      True если local_confidence >= 0.7
                         downstream Chunk Planner (Phase 10) читает это поле
    degraded_mode:       конфигурация fallback если retrieval_safe=False
                         None если retrieval_safe=True
    inputs:              исходные сигналы (для audit/telemetry)
    """

    local_confidence: float
    context_reliability: float
    retrieval_safe: bool
    degraded_mode: DegradedModeConfig | None
    inputs: ConfidenceInput

    def __post_init__(self) -> None:
        if not (0.0 <= self.local_confidence <= 1.0):
            raise ValueError(
                f"local_confidence must be in [0.0, 1.0], got {self.local_confidence}"
            )
        if not (0.0 <= self.context_reliability <= 1.0):
            raise ValueError(
                f"context_reliability must be in [0.0, 1.0], "
                f"got {self.context_reliability}"
            )
        # Инвариант: retrieval_safe соответствует threshold
        expected = self.local_confidence >= RETRIEVAL_SAFE_THRESHOLD
        if self.retrieval_safe != expected:
            raise ValueError(
                f"retrieval_safe={self.retrieval_safe} inconsistent with "
                f"local_confidence={self.local_confidence} "
                f"(threshold={RETRIEVAL_SAFE_THRESHOLD})"
            )
        # Инвариант: degraded_mode присутствует только когда не retrieval_safe
        if self.retrieval_safe and self.degraded_mode is not None:
            raise ValueError(
                "degraded_mode must be None when retrieval_safe=True"
            )
        if not self.retrieval_safe and self.degraded_mode is None:
            raise ValueError(
                "degraded_mode must not be None when retrieval_safe=False"
            )

    @classmethod
    def from_inputs(cls, inputs: ConfidenceInput) -> "StructuralConfidence":
        """
        Детерминированный расчёт из ConfidenceInput.

        local_confidence — взвешенное среднее четырёх сигналов:
            heading_quality      × 0.35
            grammar_consistency  × 0.30
            numbering_stability  × 0.20
            recovery_confidence  × 0.15

        Штрафы (аддитивные, применяются последовательно):
            orphan_ratio > 0.1   → −0.10
            rewrite_ratio > 0.1  → −0.05
            total_headings < 3   → −0.20

        context_reliability:
            base = local_confidence
            ocr_noise_ratio > 0.3 → ×0.85
            ocr_noise_ratio > 0.6 → ×0.70 (вместо ×0.85)
        """
        raw = (
            inputs.heading_quality * 0.35
            + inputs.grammar_consistency * 0.30
            + inputs.numbering_stability * 0.20
            + inputs.recovery_confidence * 0.15
        )

        # Штрафы
        if inputs.orphan_ratio > 0.1:
            raw -= 0.10
        if inputs.rewrite_ratio > 0.1:
            raw -= 0.05
        if inputs.total_headings < 3:
            raw -= 0.20

        local_confidence = round(max(0.0, min(1.0, raw)), 4)

        # context_reliability
        ctx = local_confidence
        if inputs.ocr_noise_ratio > 0.6:
            ctx *= 0.70
        elif inputs.ocr_noise_ratio > 0.3:
            ctx *= 0.85
        context_reliability = round(max(0.0, min(1.0, ctx)), 4)

        retrieval_safe = local_confidence >= RETRIEVAL_SAFE_THRESHOLD

        degraded_mode: DegradedModeConfig | None = None
        if not retrieval_safe:
            reasons: list[str] = []
            if local_confidence < RETRIEVAL_SAFE_THRESHOLD:
                reasons.append(
                    f"local_confidence={local_confidence} < {RETRIEVAL_SAFE_THRESHOLD}"
                )
            if inputs.total_headings < 3:
                reasons.append(f"total_headings={inputs.total_headings} < 3")
            degraded_mode = DegradedModeConfig(
                reason="; ".join(reasons) if reasons else "low confidence"
            )

        return cls(
            local_confidence=local_confidence,
            context_reliability=context_reliability,
            retrieval_safe=retrieval_safe,
            degraded_mode=degraded_mode,
            inputs=inputs,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_confidence": self.local_confidence,
            "context_reliability": self.context_reliability,
            "retrieval_safe": self.retrieval_safe,
            "degraded_mode": (
                self.degraded_mode.to_dict() if self.degraded_mode else None
            ),
            "inputs": self.inputs.to_dict(),
        }
    
    