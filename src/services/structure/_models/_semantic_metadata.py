# src/services/structure/_models/_semantic_metadata.py

"""
SemanticNodeMetadata — DTO для semantic, quality и recovery полей.

Содержит всё, что НЕ является частью structural identity узла:
  semantic_node_type  — классификация типа (semantic concern)
  parse_confidence    — оценка качества парсинга (quality concern)
  citability_hint     — retrieval hint (retrieval concern)
  recovery_info       — информация о best-effort recovery (recovery concern)

Жизненный цикл:
  Создаётся downstream от FrozenHierarchyNode (Phase 5+, Phase 12).
  Не участвует в structural_hash.
  Не передаётся в FSM.
  Привязывается к узлу через effective_uid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ._constants import VALID_SEMANTIC_ELEMENT_TYPES
from ._normalization import (
    _norm_bool,
    _norm_opt_str,
    _norm_str,
    _normalize_probability,
)

_VALID_CITABILITY_HINTS: frozenset[str] = frozenset({"high", "medium", "low"})


@dataclass
class RecoveryInfo:
    """
    Информация о best-effort recovery для одного узла.

    Создаётся Recovery Engine (Phase 4).
    Используется в ResolutionAuditLog и retrieval diagnostics.
    """

    recovered: bool
    strategy: str | None = None        # "numbering_inference" | "grammar_compat" | "layout" | "embeddings"
    confidence: float | None = None    # [0.0, 1.0]
    fallback_reason: str | None = None

    def __post_init__(self) -> None:
        self.recovered = _norm_bool(self.recovered)
        self.strategy = _norm_opt_str(self.strategy)
        self.fallback_reason = _norm_opt_str(self.fallback_reason)
        if self.confidence is not None:
            self.confidence = _normalize_probability(self.confidence, "RecoveryInfo.confidence")

    def to_dict(self) -> dict[str, Any]:
        return {
            "recovered": self.recovered,
            "strategy": self.strategy,
            "confidence": self.confidence,
            "fallback_reason": self.fallback_reason,
        }


@dataclass
class SemanticNodeMetadata:
    """
    Semantic, quality и recovery metadata для одного структурного узла.

    Все поля опциональны — отсутствие SemanticNodeMetadata не делает
    структурный узел невалидным.
    """

    effective_uid: str

    semantic_node_type: str | None = None
    parse_confidence: float | None = None
    citability_hint: str | None = None
    recovery_info: RecoveryInfo | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.effective_uid = _norm_str(self.effective_uid)
        if not self.effective_uid:
            raise ValueError("SemanticNodeMetadata.effective_uid must be non-empty")

        if self.semantic_node_type is not None:
            normalized = _norm_str(self.semantic_node_type).lower()
            if normalized not in VALID_SEMANTIC_ELEMENT_TYPES:
                raise ValueError(
                    f"SemanticNodeMetadata.semantic_node_type={self.semantic_node_type!r} "
                    f"is not valid. Expected one of {sorted(VALID_SEMANTIC_ELEMENT_TYPES)} or None"
                )
            self.semantic_node_type = normalized

        if self.parse_confidence is not None:
            self.parse_confidence = _normalize_probability(
                self.parse_confidence,
                "SemanticNodeMetadata.parse_confidence",
            )

        if self.citability_hint is not None:
            normalized_ch = _norm_str(self.citability_hint).lower()
            if normalized_ch not in _VALID_CITABILITY_HINTS:
                raise ValueError(
                    f"SemanticNodeMetadata.citability_hint={self.citability_hint!r} is not valid. "
                    f"Expected one of {sorted(_VALID_CITABILITY_HINTS)} or None"
                )
            self.citability_hint = normalized_ch

        if self.recovery_info is not None and not isinstance(self.recovery_info, RecoveryInfo):
            raise ValueError("SemanticNodeMetadata.recovery_info must be RecoveryInfo or None")

        if self.extra is None:
            self.extra = {}
        elif not isinstance(self.extra, dict):
            raise ValueError("SemanticNodeMetadata.extra must be a dict")

    def to_dict(self) -> dict[str, Any]:
        return {
            "effective_uid": self.effective_uid,
            "semantic_node_type": self.semantic_node_type,
            "parse_confidence": self.parse_confidence,
            "citability_hint": self.citability_hint,
            "recovery_info": self.recovery_info.to_dict() if self.recovery_info else None,
            "extra": dict(self.extra),
        }
    
    