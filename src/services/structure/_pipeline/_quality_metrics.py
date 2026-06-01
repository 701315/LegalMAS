# src/services/structure/pipeline/_quality_metrics.py

"""
Метрики качества структуры и вспомогательные summary-функции.

Содержит:
- расчёт coverage узлов;
- вычисление component-based structure assessment;
- вычисление quality gate decision;
- backward-compatible confidence report;
- сводки по headings;
- сводки по element_type.

Важно:
- assessment и gate policy разделены;
- backward compatibility для текущего pipeline сохранена;
- файл не зависит от hidden FSM policy и не выполняет fallback сам;
- gate_mode является policy-решением поверх assessment, а не частью
  первичного quality смысла.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.config import settings
from services.structure.hierarchy_builder import HeadingCandidate
from services.structure.models import (
    STRUCTURE_CONFIDENCE_FAILED,
    STRUCTURE_CONFIDENCE_HIGH,
    STRUCTURE_CONFIDENCE_LOW,
    STRUCTURE_CONFIDENCE_MEDIUM,
    FrozenHierarchyNode,
)

from ._utils import is_numeric_uid, stable_element_id


QUALITY_GATE_ALLOW_SECTION_CHUNKING = "ALLOW_SECTION_CHUNKING"
QUALITY_GATE_ALLOW_SECTION_CHUNKING_WITH_WARNINGS = "ALLOW_SECTION_CHUNKING_WITH_WARNINGS"
QUALITY_GATE_ALLOW_HYBRID_CHUNKING = "ALLOW_HYBRID_CHUNKING"
QUALITY_GATE_BLOCK_AND_FALLBACK = "BLOCK_AND_FALLBACK"

STRUCTURE_ASSESSMENT_POLICY_VERSION = "v1.2"


class ConfidenceLevel(str, Enum):
    VERY_HIGH = "very_high"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    VERY_LOW = "very_low"


def _clamp01(value: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.0


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    try:
        if value is None:
            return default
        return bool(value)
    except Exception:
        return default


def _safe_str(value: Any, default: str = "") -> str:
    try:
        if value is None:
            return default
        return str(value)
    except Exception:
        return default


def _safe_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _dedupe_reasons(reasons: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for reason in reasons:
        value = _safe_str(reason).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _legacy_confidence_from_level(level: ConfidenceLevel) -> str:
    if level in {ConfidenceLevel.VERY_HIGH, ConfidenceLevel.HIGH}:
        return STRUCTURE_CONFIDENCE_HIGH
    if level == ConfidenceLevel.MEDIUM:
        return STRUCTURE_CONFIDENCE_MEDIUM
    if level == ConfidenceLevel.LOW:
        return STRUCTURE_CONFIDENCE_LOW
    return STRUCTURE_CONFIDENCE_FAILED


def _confidence_level_from_score(
    overall_score: float,
    *,
    headings_count: int,
    structure_degraded: bool,
) -> ConfidenceLevel:
    if headings_count <= 0:
        return ConfidenceLevel.VERY_LOW
    if overall_score >= 0.85 and not structure_degraded:
        return ConfidenceLevel.VERY_HIGH
    if overall_score >= 0.70 and not structure_degraded:
        return ConfidenceLevel.HIGH
    if overall_score >= 0.50:
        return ConfidenceLevel.MEDIUM
    if overall_score >= 0.30:
        return ConfidenceLevel.LOW
    return ConfidenceLevel.VERY_LOW


@dataclass(slots=True)
class EvidenceAssessmentInput:
    """
    Нормализованный вход Phase 2 -> Phase 5.

    Здесь храним только те сигналы, которые реально нужны для оценки структуры.
    """

    present: bool = False
    toc_detected: bool = False
    toc_confidence: float = 0.0
    main_chain_len: int = 0
    appendix_chain_len: int = 0
    crossref_anchor_count: int = 0
    appendix_marker_count: int = 0
    candidate_count: int = 0
    numeric_heading_count: int = 0
    roman_heading_count: int = 0
    alpha_heading_count: int = 0
    max_depth_observed: int = 0
    scope_count: int = 0
    document_quality_signals: dict[str, Any] = field(default_factory=dict)
    avg_accepted_heading_score: float = 0.0  # Phase 13.5

    def __post_init__(self) -> None:
        self.present = _safe_bool(self.present)
        self.toc_detected = _safe_bool(self.toc_detected)
        self.toc_confidence = _clamp01(_safe_float(self.toc_confidence))
        self.main_chain_len = max(0, _safe_int(self.main_chain_len))
        self.appendix_chain_len = max(0, _safe_int(self.appendix_chain_len))
        self.crossref_anchor_count = max(0, _safe_int(self.crossref_anchor_count))
        self.appendix_marker_count = max(0, _safe_int(self.appendix_marker_count))
        self.candidate_count = max(0, _safe_int(self.candidate_count))
        self.numeric_heading_count = max(0, _safe_int(self.numeric_heading_count))
        self.roman_heading_count = max(0, _safe_int(self.roman_heading_count))
        self.alpha_heading_count = max(0, _safe_int(self.alpha_heading_count))
        self.max_depth_observed = max(0, _safe_int(self.max_depth_observed))
        self.scope_count = max(0, _safe_int(self.scope_count))
        self.document_quality_signals = _safe_dict(self.document_quality_signals)
        self.avg_accepted_heading_score = _clamp01(
            _safe_float(self.avg_accepted_heading_score)
        )

@dataclass(slots=True)
class HierarchyAssessmentInput:
    """
    Нормализованный вход deterministic hierarchy части.
    """

    coverage: float = 0.0
    headings_count: int = 0
    numeric_ratio: float = 0.0
    empty_title_count: int = 0
    root_sections_count: int = 0
    appendix_root_count: int = 0
    structure_degraded: bool = False

    def __post_init__(self) -> None:
        self.coverage = _clamp01(_safe_float(self.coverage))
        self.headings_count = max(0, _safe_int(self.headings_count))
        self.numeric_ratio = _clamp01(_safe_float(self.numeric_ratio))
        self.empty_title_count = max(0, _safe_int(self.empty_title_count))
        self.root_sections_count = max(0, _safe_int(self.root_sections_count))
        self.appendix_root_count = max(0, _safe_int(self.appendix_root_count))
        self.structure_degraded = _safe_bool(self.structure_degraded)


@dataclass(slots=True)
class FSMAssessmentInput:
    total_candidates: int = 0
    attached_as_child: int = 0
    attached_as_root: int = 0
    attached_best_effort: int = 0
    attached_deferred_child: int = 0

    skipped_duplicate: int = 0
    skipped_invalid: int = 0
    skipped_semantic_negative: int = 0
    parent_level_rejected: int = 0

    deferred_total: int = 0
    deferred_resolved: int = 0
    deferred_unresolved: int = 0

    root_count: int = 0
    max_depth_reached: int = 0

    def __post_init__(self) -> None:
        self.total_candidates = max(0, _safe_int(self.total_candidates))
        self.attached_as_child = max(0, _safe_int(self.attached_as_child))
        self.attached_as_root = max(0, _safe_int(self.attached_as_root))
        self.attached_best_effort = max(0, _safe_int(self.attached_best_effort))
        self.attached_deferred_child = max(0, _safe_int(self.attached_deferred_child))

        self.skipped_duplicate = max(0, _safe_int(self.skipped_duplicate))
        self.skipped_invalid = max(0, _safe_int(self.skipped_invalid))
        self.skipped_semantic_negative = max(0, _safe_int(self.skipped_semantic_negative))
        self.parent_level_rejected = max(0, _safe_int(self.parent_level_rejected))

        self.deferred_total = max(0, _safe_int(self.deferred_total))
        self.deferred_resolved = max(0, _safe_int(self.deferred_resolved))
        self.deferred_unresolved = max(0, _safe_int(self.deferred_unresolved))

        self.root_count = max(0, _safe_int(self.root_count))
        self.max_depth_reached = max(0, _safe_int(self.max_depth_reached))

    @property
    def total_attached(self) -> int:
        return (
            self.attached_as_child
            + self.attached_as_root
            + self.attached_best_effort
            + self.attached_deferred_child
        )

    @property
    def best_effort_ratio(self) -> float:
        if self.total_attached == 0:
            return 0.0
        return _clamp01(self.attached_best_effort / self.total_attached)

    @property
    def deferred_unresolved_ratio(self) -> float:
        if self.deferred_total == 0:
            return 0.0
        return _clamp01(self.deferred_unresolved / self.deferred_total)

    @property
    def parent_level_rejected_ratio(self) -> float:
        if self.total_candidates == 0:
            return 0.0
        return _clamp01(self.parent_level_rejected / self.total_candidates)


@dataclass(slots=True)
class ResolutionAssessmentInput:
    rewrite_count: int = 0
    rewrite_ratio: float = 0.0
    monotonicity_violations_found: int = 0
    monotonicity_violations_fixed: int = 0

    def __post_init__(self) -> None:
        self.rewrite_count = max(0, _safe_int(self.rewrite_count))
        self.rewrite_ratio = _clamp01(_safe_float(self.rewrite_ratio))
        self.monotonicity_violations_found = max(0, _safe_int(self.monotonicity_violations_found))
        self.monotonicity_violations_fixed = max(0, _safe_int(self.monotonicity_violations_fixed))


@dataclass(slots=True)
class RecoveryAssessmentInput:
    orphans_detected: int = 0
    orphans_recovered: int = 0
    orphans_unresolved: int = 0
    fallback_triggered: bool = False
    fallback_mode: str | None = None

    def __post_init__(self) -> None:
        self.orphans_detected = max(0, _safe_int(self.orphans_detected))
        self.orphans_recovered = max(0, _safe_int(self.orphans_recovered))
        self.orphans_unresolved = max(0, _safe_int(self.orphans_unresolved))
        self.fallback_triggered = _safe_bool(self.fallback_triggered)
        self.fallback_mode = _safe_str(self.fallback_mode) or None


@dataclass(slots=True)
class CrossRefAssessmentInput:
    """
    Нормализованный вход cross-reference части.
    """

    references_count: int = 0
    resolved_count: int | None = None
    unresolved_count: int | None = None
    ambiguous_count: int | None = None
    appendix_scoped_resolved_count: int | None = None
    appendix_scope_miss_count: int | None = None
    toc_like_reference_skipped_count: int | None = None

    def __post_init__(self) -> None:
        self.references_count = max(0, _safe_int(self.references_count))
        self.resolved_count = None if self.resolved_count is None else max(0, _safe_int(self.resolved_count))
        self.unresolved_count = None if self.unresolved_count is None else max(0, _safe_int(self.unresolved_count))
        self.ambiguous_count = None if self.ambiguous_count is None else max(0, _safe_int(self.ambiguous_count))
        self.appendix_scoped_resolved_count = (
            None if self.appendix_scoped_resolved_count is None
            else max(0, _safe_int(self.appendix_scoped_resolved_count))
        )
        self.appendix_scope_miss_count = (
            None if self.appendix_scope_miss_count is None
            else max(0, _safe_int(self.appendix_scope_miss_count))
        )
        self.toc_like_reference_skipped_count = (
            None if self.toc_like_reference_skipped_count is None
            else max(0, _safe_int(self.toc_like_reference_skipped_count))
        )


@dataclass(slots=True)
class HeadingQualityScore:
    score: float
    avg_heading_confidence: float
    low_confidence_ratio: float
    toc_validated: bool

    def __post_init__(self) -> None:
        self.score = _clamp01(_safe_float(self.score))
        self.avg_heading_confidence = _clamp01(_safe_float(self.avg_heading_confidence))
        self.low_confidence_ratio = _clamp01(_safe_float(self.low_confidence_ratio))
        self.toc_validated = _safe_bool(self.toc_validated)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "avg_heading_confidence": round(self.avg_heading_confidence, 4),
            "low_confidence_ratio": round(self.low_confidence_ratio, 4),
            "toc_validated": self.toc_validated,
        }


@dataclass(slots=True)
class GrammarConsistencyScore:
    score: float
    violation_ratio: float
    scope_integrity: float

    def __post_init__(self) -> None:
        self.score = _clamp01(_safe_float(self.score))
        self.violation_ratio = _clamp01(_safe_float(self.violation_ratio))
        self.scope_integrity = _clamp01(_safe_float(self.scope_integrity))

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "violation_ratio": round(self.violation_ratio, 4),
            "scope_integrity": round(self.scope_integrity, 4),
        }


@dataclass(slots=True)
class RecoveryImpactScore:
    score: float
    orphan_ratio: float
    recovery_success_rate: float
    fallback_ratio: float

    def __post_init__(self) -> None:
        self.score = _clamp01(_safe_float(self.score))
        self.orphan_ratio = _clamp01(_safe_float(self.orphan_ratio))
        self.recovery_success_rate = _clamp01(_safe_float(self.recovery_success_rate))
        self.fallback_ratio = _clamp01(_safe_float(self.fallback_ratio))

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "orphan_ratio": round(self.orphan_ratio, 4),
            "recovery_success_rate": round(self.recovery_success_rate, 4),
            "fallback_ratio": round(self.fallback_ratio, 4),
        }


@dataclass(slots=True)
class NumberingStabilityScore:
    score: float
    rewrite_ratio: float
    illegal_jumps_ratio: float

    def __post_init__(self) -> None:
        self.score = _clamp01(_safe_float(self.score))
        self.rewrite_ratio = _clamp01(_safe_float(self.rewrite_ratio))
        self.illegal_jumps_ratio = _clamp01(_safe_float(self.illegal_jumps_ratio))

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "rewrite_ratio": round(self.rewrite_ratio, 4),
            "illegal_jumps_ratio": round(self.illegal_jumps_ratio, 4),
        }


@dataclass(slots=True)
class CrossRefResolutionScore:
    score: float
    resolution_rate: float
    appendix_resolution_rate: float

    def __post_init__(self) -> None:
        self.score = _clamp01(_safe_float(self.score))
        self.resolution_rate = _clamp01(_safe_float(self.resolution_rate))
        self.appendix_resolution_rate = _clamp01(_safe_float(self.appendix_resolution_rate))

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "resolution_rate": round(self.resolution_rate, 4),
            "appendix_resolution_rate": round(self.appendix_resolution_rate, 4),
        }


@dataclass(slots=True)
class StructureAssessment:
    """
    Итоговая оценка качества структуры.
    """

    heading_quality: HeadingQualityScore
    grammar_consistency: GrammarConsistencyScore
    recovery_impact: RecoveryImpactScore
    numbering_stability: NumberingStabilityScore
    crossref_quality: CrossRefResolutionScore
    aggregate_score: float
    confidence_level: ConfidenceLevel
    confidence: str
    retrieval_safe: bool
    degraded: bool
    reasons: list[str] = field(default_factory=list)
    policy_version: str = STRUCTURE_ASSESSMENT_POLICY_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.heading_quality, HeadingQualityScore):
            raise ValueError("StructureAssessment.heading_quality must be HeadingQualityScore")
        if not isinstance(self.grammar_consistency, GrammarConsistencyScore):
            raise ValueError("StructureAssessment.grammar_consistency must be GrammarConsistencyScore")
        if not isinstance(self.recovery_impact, RecoveryImpactScore):
            raise ValueError("StructureAssessment.recovery_impact must be RecoveryImpactScore")
        if not isinstance(self.numbering_stability, NumberingStabilityScore):
            raise ValueError("StructureAssessment.numbering_stability must be NumberingStabilityScore")
        if not isinstance(self.crossref_quality, CrossRefResolutionScore):
            raise ValueError("StructureAssessment.crossref_quality must be CrossRefResolutionScore")
        if not isinstance(self.confidence_level, ConfidenceLevel):
            raise ValueError("StructureAssessment.confidence_level must be ConfidenceLevel")

        self.aggregate_score = _clamp01(_safe_float(self.aggregate_score))
        self.confidence = _safe_str(self.confidence, default=STRUCTURE_CONFIDENCE_FAILED)
        self.retrieval_safe = _safe_bool(self.retrieval_safe)
        self.degraded = _safe_bool(self.degraded)
        self.reasons = _dedupe_reasons(list(self.reasons or []))
        self.policy_version = _safe_str(
            self.policy_version,
            default=STRUCTURE_ASSESSMENT_POLICY_VERSION,
        ) or STRUCTURE_ASSESSMENT_POLICY_VERSION

    @property
    def overall_score(self) -> float:
        return self.aggregate_score

    @property
    def heading_confidence(self) -> float:
        return self.heading_quality.score

    @property
    def tree_consistency_confidence(self) -> float:
        return self.grammar_consistency.score

    @property
    def appendix_confidence(self) -> float:
        return self.numbering_stability.score

    @property
    def crossref_anchor_confidence(self) -> float:
        return self.crossref_quality.score

    @property
    def layout_quality_confidence(self) -> float:
        return self.recovery_impact.score

    def to_dict(self) -> dict[str, Any]:
        return {
            "confidence_level": self.confidence_level.value,
            "confidence": self.confidence,
            "degraded": self.degraded,
            "retrieval_safe": self.retrieval_safe,
            "aggregate_score": round(self.aggregate_score, 4),
            "overall_score": round(self.aggregate_score, 4),
            "heading_quality": self.heading_quality.to_dict(),
            "grammar_consistency": self.grammar_consistency.to_dict(),
            "recovery_impact": self.recovery_impact.to_dict(),
            "numbering_stability": self.numbering_stability.to_dict(),
            "crossref_quality": self.crossref_quality.to_dict(),
            "heading_confidence": round(self.heading_confidence, 4),
            "tree_consistency_confidence": round(self.tree_consistency_confidence, 4),
            "appendix_confidence": round(self.appendix_confidence, 4),
            "crossref_anchor_confidence": round(self.crossref_anchor_confidence, 4),
            "layout_quality_confidence": round(self.layout_quality_confidence, 4),
            "reasons": list(self.reasons),
            "policy_version": self.policy_version,
        }


@dataclass(slots=True)
class StructureGateDecision:
    """
    Policy-решение поверх уже рассчитанного assessment.
    """

    gate_mode: str
    section_chunking_allowed: bool
    technical_fallback_only: bool
    semantic_tree_preserved_despite_low_confidence: bool
    final_mode: str
    reasons: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.gate_mode = _safe_str(self.gate_mode, default=QUALITY_GATE_BLOCK_AND_FALLBACK)
        self.section_chunking_allowed = _safe_bool(self.section_chunking_allowed)
        self.technical_fallback_only = _safe_bool(self.technical_fallback_only)
        self.semantic_tree_preserved_despite_low_confidence = _safe_bool(
            self.semantic_tree_preserved_despite_low_confidence
        )
        self.final_mode = _safe_str(self.final_mode, default="technical_fallback") or "technical_fallback"
        self.reasons = _dedupe_reasons(list(self.reasons or []))

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_mode": self.gate_mode,
            "section_chunking_allowed": self.section_chunking_allowed,
            "technical_fallback_only": self.technical_fallback_only,
            "semantic_tree_preserved_despite_low_confidence": self.semantic_tree_preserved_despite_low_confidence,
            "final_mode": self.final_mode,
            "reasons": list(self.reasons),
        }


@dataclass(slots=True)
class StructureConfidenceReport:
    """
    Backward-compatible обёртка для текущего pipeline.
    """

    confidence: str
    degraded: bool
    overall_score: float
    heading_confidence: float
    tree_consistency_confidence: float
    appendix_confidence: float
    crossref_anchor_confidence: float
    layout_quality_confidence: float
    reasons: list[str] = field(default_factory=list)
    gate_mode: str = QUALITY_GATE_BLOCK_AND_FALLBACK
    retrieval_safe: bool = False
    section_chunking_allowed: bool = False
    technical_fallback_only: bool = True
    semantic_tree_preserved_despite_low_confidence: bool = False
    final_mode: str = "technical_fallback"
    policy_version: str = STRUCTURE_ASSESSMENT_POLICY_VERSION

    def __post_init__(self) -> None:
        self.confidence = _safe_str(self.confidence, default=STRUCTURE_CONFIDENCE_FAILED)
        self.degraded = _safe_bool(self.degraded)
        self.overall_score = _clamp01(_safe_float(self.overall_score))
        self.heading_confidence = _clamp01(_safe_float(self.heading_confidence))
        self.tree_consistency_confidence = _clamp01(_safe_float(self.tree_consistency_confidence))
        self.appendix_confidence = _clamp01(_safe_float(self.appendix_confidence))
        self.crossref_anchor_confidence = _clamp01(_safe_float(self.crossref_anchor_confidence))
        self.layout_quality_confidence = _clamp01(_safe_float(self.layout_quality_confidence))
        self.reasons = _dedupe_reasons(list(self.reasons or []))
        self.gate_mode = _safe_str(self.gate_mode, default=QUALITY_GATE_BLOCK_AND_FALLBACK)
        self.retrieval_safe = _safe_bool(self.retrieval_safe)
        self.section_chunking_allowed = _safe_bool(self.section_chunking_allowed)
        self.technical_fallback_only = _safe_bool(self.technical_fallback_only)
        self.semantic_tree_preserved_despite_low_confidence = _safe_bool(
            self.semantic_tree_preserved_despite_low_confidence
        )
        self.final_mode = _safe_str(self.final_mode, default="technical_fallback") or "technical_fallback"
        self.policy_version = _safe_str(
            self.policy_version,
            default=STRUCTURE_ASSESSMENT_POLICY_VERSION,
        ) or STRUCTURE_ASSESSMENT_POLICY_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "confidence": self.confidence,
            "degraded": self.degraded,
            "retrieval_safe": self.retrieval_safe,
            "overall_score": round(self.overall_score, 4),
            "heading_confidence": round(self.heading_confidence, 4),
            "tree_consistency_confidence": round(self.tree_consistency_confidence, 4),
            "appendix_confidence": round(self.appendix_confidence, 4),
            "crossref_anchor_confidence": round(self.crossref_anchor_confidence, 4),
            "layout_quality_confidence": round(self.layout_quality_confidence, 4),
            "reasons": list(self.reasons),
            "gate_mode": self.gate_mode,
            "section_chunking_allowed": self.section_chunking_allowed,
            "technical_fallback_only": self.technical_fallback_only,
            "semantic_tree_preserved_despite_low_confidence": self.semantic_tree_preserved_despite_low_confidence,
            "final_mode": self.final_mode,
            "policy_version": self.policy_version,
        }


def calculate_node_coverage(
    *,
    nodes: dict[str, FrozenHierarchyNode] | dict[str, Any],
    elements: list[dict],
) -> float:
    """
    Доля body-элементов, покрытых own_element_ids.
    """
    if not elements or not nodes:
        return 0.0

    all_ids: set[str] = set()
    covered_ids: set[str] = set()

    for idx, el in enumerate(elements):
        stable_id = stable_element_id(el, idx)
        if stable_id:
            all_ids.add(stable_id)

    for node in nodes.values():
        own_ids = getattr(node, "own_element_ids", None) or ()
        try:
            covered_ids.update(own_ids)
        except Exception:
            continue

    if not all_ids:
        return 0.0

    return len(all_ids & covered_ids) / len(all_ids)


def summarize_headings(headings: list[HeadingCandidate]) -> dict[str, Any]:
    """
    Лёгкая quality summary по принятым headings.
    """
    total = len(headings)
    if not total:
        return {
            "total": 0,
            "numeric_count": 0,
            "numeric_ratio": 0.0,
            "empty_title_count": 0,
            "scope_distribution": {},
        }

    numeric_count = 0
    empty_title_count = 0
    scope_distribution: dict[str, int] = {}

    for heading in headings:
        raw_uid = _safe_str(
            getattr(heading, "raw_uid", None) or getattr(heading, "uid", None) or ""
        ).strip()
        title = _safe_str(getattr(heading, "title", "")).strip()
        scope = _safe_str(getattr(heading, "scope", None), default="unknown").strip() or "unknown"

        scope_distribution[scope] = scope_distribution.get(scope, 0) + 1

        if is_numeric_uid(raw_uid):
            numeric_count += 1
        if not title:
            empty_title_count += 1

    return {
        "total": total,
        "numeric_count": numeric_count,
        "numeric_ratio": numeric_count / total,
        "empty_title_count": empty_title_count,
        "scope_distribution": scope_distribution,
    }


def summarize_element_types(elements: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Сводка по element_type.
    """
    counts: dict[str, int] = {}

    for el in elements:
        element_type = _safe_str(el.get("element_type"), default="unknown").strip() or "unknown"
        counts[element_type] = counts.get(element_type, 0) + 1

    total = len(elements)
    toc_total = (
        counts.get("toc_header", 0)
        + counts.get("toc_line", 0)
        + counts.get("possible_toc", 0)
        + counts.get("toc_false_positive", 0)
    )

    return {
        "total": total,
        "counts": counts,
        "heading_candidates": counts.get("heading_candidate", 0),
        "body_text": counts.get("body_text", 0),
        "list_items": counts.get("list_item", 0),
        "toc_header": counts.get("toc_header", 0),
        "toc_line": counts.get("toc_line", 0),
        "possible_toc": counts.get("possible_toc", 0),
        "toc_false_positive": counts.get("toc_false_positive", 0),
        "toc_total": toc_total,
        "signature_blocks": counts.get("signature_block", 0),
        "requisites_blocks": counts.get("requisites_block", 0),
        "page_artifacts": counts.get("page_artifact", 0),
        "unknown_layout": counts.get("unknown_layout", 0),
    }


def _extract_evidence_metrics(structure_evidence: Any | None) -> EvidenceAssessmentInput:
    if structure_evidence is None:
        return EvidenceAssessmentInput()

    try:
        global_signals = getattr(structure_evidence, "global_signals", None)
        stats = getattr(structure_evidence, "stats", None)
        scope_boundaries = getattr(structure_evidence, "scope_boundaries", None) or []

        # Phase 13.5:
        # canonical StructureEvidenceBundle хранит кандидатов в heading_candidates.
        # Оставляем fallback на legacy candidates для backward compatibility.
        candidates = (
            getattr(structure_evidence, "heading_candidates", None)
            or getattr(structure_evidence, "candidates", None)
            or []
        )

        accepted_scores: list[float] = []
        for candidate in candidates:
            try:
                if _safe_bool(getattr(candidate, "is_toc_entry", False)):
                    continue

                features = _safe_dict(getattr(candidate, "features", {}) or {})
                decision = _safe_str(features.get("decision")).strip().lower()

                # Если decision присутствует — учитываем только accepted.
                # Если decision отсутствует (legacy shape), берём score как fallback.
                if decision and decision != "accepted":
                    continue

                accepted_scores.append(
                    _clamp01(_safe_float(getattr(candidate, "score", 0.0)))
                )
            except Exception:
                continue

        avg_accepted_heading_score = (
            round(sum(accepted_scores) / len(accepted_scores), 4)
            if accepted_scores
            else 0.0
        )

        return EvidenceAssessmentInput(
            present=True,
            toc_detected=_safe_bool(getattr(global_signals, "toc_detected", False)),
            toc_confidence=_safe_float(
                getattr(global_signals, "toc_confidence", 0.0),
                default=0.0,
            ),
            main_chain_len=max(
                0,
                _safe_int(getattr(global_signals, "main_section_chain_length", 0)),
            ),
            appendix_chain_len=max(
                0,
                _safe_int(getattr(global_signals, "appendix_chain_length", 0)),
            ),
            crossref_anchor_count=max(
                0,
                _safe_int(getattr(global_signals, "crossref_anchor_count", 0)),
            ),
            appendix_marker_count=len(getattr(structure_evidence, "appendix_markers", []) or []),
            candidate_count=max(
                0,
                _safe_int(getattr(stats, "candidate_count", 0) or len(candidates)),
            ),
            numeric_heading_count=max(
                0,
                _safe_int(getattr(stats, "numeric_heading_count", 0)),
            ),
            roman_heading_count=max(
                0,
                _safe_int(getattr(stats, "roman_heading_count", 0)),
            ),
            alpha_heading_count=max(
                0,
                _safe_int(getattr(stats, "alpha_heading_count", 0)),
            ),
            max_depth_observed=max(
                0,
                _safe_int(getattr(stats, "max_depth_observed", 0)),
            ),
            scope_count=max(
                0,
                _safe_int(getattr(stats, "scope_count", 0) or len(scope_boundaries)),
            ),
            document_quality_signals=_safe_dict(
                getattr(global_signals, "document_quality_signals", {}) or {}
            ),
            avg_accepted_heading_score=avg_accepted_heading_score,
        )

    except Exception:
        return EvidenceAssessmentInput(present=True)


def _build_hierarchy_input(
    *,
    coverage: float,
    headings_count: int,
    numeric_ratio: float,
    empty_title_count: int,
    structure_degraded: bool,
    root_sections_count: int,
    appendix_root_count: int,
) -> HierarchyAssessmentInput:
    return HierarchyAssessmentInput(
        coverage=coverage,
        headings_count=headings_count,
        numeric_ratio=numeric_ratio,
        empty_title_count=empty_title_count,
        structure_degraded=structure_degraded,
        root_sections_count=root_sections_count,
        appendix_root_count=appendix_root_count,
    )


def _build_crossref_input(
    *,
    cross_references_count: int,
) -> CrossRefAssessmentInput:
    return CrossRefAssessmentInput(
        references_count=cross_references_count,
    )


def _extract_fsm_input(fsm_summary: Any | None) -> FSMAssessmentInput:
    if fsm_summary is None:
        return FSMAssessmentInput()

    return FSMAssessmentInput(
        total_candidates=_safe_int(getattr(fsm_summary, "total_candidates", 0)),
        attached_as_child=_safe_int(getattr(fsm_summary, "attached_as_child", 0)),
        attached_as_root=_safe_int(getattr(fsm_summary, "attached_as_root", 0)),
        attached_best_effort=_safe_int(getattr(fsm_summary, "attached_best_effort", 0)),
        attached_deferred_child=_safe_int(getattr(fsm_summary, "attached_deferred_child", 0)),
        skipped_duplicate=_safe_int(getattr(fsm_summary, "skipped_duplicate", 0)),
        skipped_invalid=_safe_int(getattr(fsm_summary, "skipped_invalid", 0)),
        skipped_semantic_negative=_safe_int(getattr(fsm_summary, "skipped_semantic_negative", 0)),
        parent_level_rejected=_safe_int(getattr(fsm_summary, "parent_level_rejected", 0)),
        deferred_total=_safe_int(getattr(fsm_summary, "deferred_total", 0)),
        deferred_resolved=_safe_int(getattr(fsm_summary, "deferred_resolved", 0)),
        deferred_unresolved=_safe_int(getattr(fsm_summary, "deferred_unresolved", 0)),
        root_count=_safe_int(getattr(fsm_summary, "root_count", 0)),
        max_depth_reached=_safe_int(getattr(fsm_summary, "max_depth_reached", 0)),
    )


def _extract_resolution_input(resolution_audit: Any | None) -> ResolutionAssessmentInput:
    if resolution_audit is None:
        return ResolutionAssessmentInput()
    return ResolutionAssessmentInput(
        rewrite_count=_safe_int(
            getattr(resolution_audit, "rewrite_count", None)
            if hasattr(resolution_audit, "rewrite_count")
            else len(getattr(resolution_audit, "rewrites", []) or [])
        ),
        rewrite_ratio=_safe_float(getattr(resolution_audit, "rewrite_ratio", 0.0), default=0.0),
        monotonicity_violations_found=_safe_int(
            getattr(resolution_audit, "monotonicity_violations_found", 0)
        ),
        monotonicity_violations_fixed=_safe_int(
            getattr(resolution_audit, "monotonicity_violations_fixed", 0)
        ),
    )


def _extract_recovery_input(recovery_audit: Any | None) -> RecoveryAssessmentInput:
    if recovery_audit is None:
        return RecoveryAssessmentInput()
    return RecoveryAssessmentInput(
        orphans_detected=_safe_int(getattr(recovery_audit, "orphans_detected", 0)),
        orphans_recovered=_safe_int(getattr(recovery_audit, "orphans_recovered", 0)),
        orphans_unresolved=_safe_int(getattr(recovery_audit, "orphans_unresolved", 0)),
        fallback_triggered=_safe_bool(
            getattr(recovery_audit, "fallback_triggered", False)
            or _safe_int(getattr(recovery_audit, "fallback_triggered_count", 0)) > 0
        ),
        fallback_mode=_safe_str(getattr(recovery_audit, "fallback_mode", None)) or None,
    )


def _extract_crossref_input(crossref_stats: Any | None) -> CrossRefAssessmentInput:
    if crossref_stats is None:
        return CrossRefAssessmentInput()
    return CrossRefAssessmentInput(
        references_count=_safe_int(getattr(crossref_stats, "references_count", 0)),
        resolved_count=_safe_int(getattr(crossref_stats, "resolved_count", None))
        if hasattr(crossref_stats, "resolved_count") and getattr(crossref_stats, "resolved_count", None) is not None
        else None,
        unresolved_count=_safe_int(getattr(crossref_stats, "unresolved_count", None))
        if hasattr(crossref_stats, "unresolved_count") and getattr(crossref_stats, "unresolved_count", None) is not None
        else None,
        ambiguous_count=_safe_int(getattr(crossref_stats, "ambiguous_count", None))
        if hasattr(crossref_stats, "ambiguous_count") and getattr(crossref_stats, "ambiguous_count", None) is not None
        else None,
        appendix_scoped_resolved_count=_safe_int(
            getattr(crossref_stats, "appendix_scoped_resolved_count", None)
        )
        if hasattr(crossref_stats, "appendix_scoped_resolved_count")
        and getattr(crossref_stats, "appendix_scoped_resolved_count", None) is not None
        else None,
        appendix_scope_miss_count=_safe_int(
            getattr(crossref_stats, "appendix_scope_miss_count", None)
        )
        if hasattr(crossref_stats, "appendix_scope_miss_count")
        and getattr(crossref_stats, "appendix_scope_miss_count", None) is not None
        else None,
        toc_like_reference_skipped_count=_safe_int(
            getattr(crossref_stats, "toc_like_reference_skipped_count", None)
        )
        if hasattr(crossref_stats, "toc_like_reference_skipped_count")
        and getattr(crossref_stats, "toc_like_reference_skipped_count", None) is not None
        else None,
    )


def _calculate_heading_quality_score(
    hierarchy: HierarchyAssessmentInput,
    evidence: EvidenceAssessmentInput,
    reasons: list[str],
) -> HeadingQualityScore:
    headings_count = hierarchy.headings_count
    numeric_ratio = hierarchy.numeric_ratio
    empty_title_count = hierarchy.empty_title_count

    if headings_count <= 0:
        reasons.append("no_headings_materialized")
        return HeadingQualityScore(
            score=0.0,
            avg_heading_confidence=0.0,
            low_confidence_ratio=1.0,
            toc_validated=False,
        )

    structural_score = 0.35
    if headings_count >= 3:
        structural_score += 0.15
    if headings_count >= 8:
        structural_score += 0.15
    if numeric_ratio >= 0.30:
        structural_score += 0.15
    if numeric_ratio >= 0.60:
        structural_score += 0.10

    if empty_title_count == 0:
        structural_score += 0.10
    elif empty_title_count >= max(2, headings_count // 2):
        reasons.append("too_many_empty_heading_titles")
        structural_score -= 0.20

    toc_validated = evidence.toc_detected and evidence.toc_confidence >= 0.50
    if toc_validated:
        structural_score += 0.05

    low_confidence_ratio = 1.0 if headings_count == 0 else min(
        1.0,
        empty_title_count / max(1, headings_count),
    )

    structural_confidence = min(
        1.0,
        0.40
        + 0.30 * numeric_ratio
        + 0.20 * (1.0 - low_confidence_ratio)
        + 0.10 * (1.0 if toc_validated else 0.0),
    )

    # Phase 13.5:
    # blending structural heuristic with real accepted heading scores
    # extracted from StructureEvidenceBundle.heading_candidates.
    real_scores_component = _clamp01(
        _safe_float(getattr(evidence, "avg_accepted_heading_score", 0.0))
    )

    if real_scores_component > 0.0:
        score = _clamp01(0.75 * structural_score + 0.25 * real_scores_component)
        avg_heading_confidence = _clamp01(
            0.60 * structural_confidence + 0.40 * real_scores_component
        )
    else:
        score = _clamp01(structural_score)
        avg_heading_confidence = _clamp01(structural_confidence)

    return HeadingQualityScore(
        score=score,
        avg_heading_confidence=avg_heading_confidence,
        low_confidence_ratio=_clamp01(low_confidence_ratio),
        toc_validated=toc_validated,
    )


def _calculate_grammar_consistency_score(
    hierarchy: HierarchyAssessmentInput,
    fsm: FSMAssessmentInput,
    resolution: ResolutionAssessmentInput,
    reasons: list[str],
) -> GrammarConsistencyScore:
    base_score = hierarchy.coverage

    if hierarchy.root_sections_count >= 3:
        base_score += 0.10
    if hierarchy.root_sections_count >= 8:
        base_score += 0.10

    if hierarchy.structure_degraded:
        base_score -= 0.25
        reasons.append("hierarchy_builder_marked_structure_degraded")

    min_coverage = _safe_float(
        getattr(settings, "STRUCTURE_MIN_CLAUSE_COVERAGE", 0.55),
        default=0.55,
    )
    if hierarchy.coverage < min_coverage:
        reasons.append("low_node_coverage")

    best_effort_ratio = fsm.best_effort_ratio
    deferred_unresolved_ratio = fsm.deferred_unresolved_ratio
    parent_level_rejected_ratio = fsm.parent_level_rejected_ratio

    violation_ratio = _clamp01(
        max(
            best_effort_ratio,
            deferred_unresolved_ratio,
            parent_level_rejected_ratio,
            resolution.rewrite_ratio,
        )
    )
    scope_integrity = _clamp01(1.0 - violation_ratio)

    if best_effort_ratio > 0.10:
        reasons.append("high_best_effort_attach_ratio")
    if deferred_unresolved_ratio > 0.0:
        reasons.append("unresolved_deferred_numeric_nodes")
    if parent_level_rejected_ratio > 0.05:
        reasons.append("parent_level_rejections_detected")
    if resolution.rewrite_ratio > 0.10:
        reasons.append("high_resolution_rewrite_ratio")

    score = base_score
    score -= 0.20 * best_effort_ratio
    score -= 0.20 * deferred_unresolved_ratio
    score -= 0.15 * parent_level_rejected_ratio
    score -= 0.25 * resolution.rewrite_ratio
    score = _clamp01(score)

    return GrammarConsistencyScore(
        score=score,
        violation_ratio=violation_ratio,
        scope_integrity=scope_integrity,
    )


def _calculate_recovery_impact_score(
    hierarchy: HierarchyAssessmentInput,
    recovery: RecoveryAssessmentInput,
    layout_degraded: bool,
    evidence: EvidenceAssessmentInput,
    reasons: list[str],
) -> RecoveryImpactScore:
    orphan_ratio = (
        min(1.0, recovery.orphans_detected / max(1, hierarchy.headings_count))
        if hierarchy.headings_count > 0 else 0.0
    )
    recovery_success_rate = (
        _clamp01(recovery.orphans_recovered / max(1, recovery.orphans_detected))
        if recovery.orphans_detected > 0 else 1.0
    )
    fallback_ratio = 1.0 if recovery.fallback_triggered else 0.0

    if recovery.orphans_detected > 0 and recovery_success_rate < 0.50:
        reasons.append("low_recovery_success_rate")
    if recovery.fallback_triggered:
        reasons.append("recovery_triggered_fallback_mode")
    if layout_degraded:
        reasons.append("layout_degraded")

    score = 0.85
    extraction_quality = evidence.document_quality_signals.get("extraction_quality_score")
    if extraction_quality is not None:
        score = _clamp01(_safe_float(extraction_quality, default=0.85))

    score -= 0.25 * orphan_ratio
    score -= 0.20 * fallback_ratio
    score = _clamp01(score)

    return RecoveryImpactScore(
        score=score,
        orphan_ratio=orphan_ratio,
        recovery_success_rate=recovery_success_rate,
        fallback_ratio=fallback_ratio,
    )


def _calculate_numbering_stability_score(
    hierarchy: HierarchyAssessmentInput,
    evidence: EvidenceAssessmentInput,
    fsm: FSMAssessmentInput,
    resolution: ResolutionAssessmentInput,
    reasons: list[str],
) -> NumberingStabilityScore:
    best_effort_ratio = fsm.best_effort_ratio
    deferred_unresolved_ratio = fsm.deferred_unresolved_ratio
    parent_level_rejected_ratio = fsm.parent_level_rejected_ratio
    rewrite_ratio = resolution.rewrite_ratio

    score = 0.40
    if evidence.appendix_chain_len >= 3:
        score += 0.15
    if hierarchy.appendix_root_count >= 1:
        score += 0.10
    if (
        evidence.appendix_marker_count >= hierarchy.appendix_root_count
        and evidence.appendix_marker_count > 0
    ):
        score += 0.05
    if evidence.max_depth_observed >= 2:
        score += 0.10
    if evidence.scope_count >= 2:
        score += 0.10

    score -= 0.20 * rewrite_ratio
    score -= 0.20 * parent_level_rejected_ratio
    score -= 0.15 * deferred_unresolved_ratio
    score -= 0.10 * best_effort_ratio

    if rewrite_ratio > 0.10:
        reasons.append("numbering_rewrite_ratio_above_warning")
    if parent_level_rejected_ratio > 0.05:
        reasons.append("numbering_parent_level_rejections_above_warning")
    if deferred_unresolved_ratio > 0.0:
        reasons.append("numbering_unresolved_deferred_nodes_detected")

    return NumberingStabilityScore(
        score=_clamp01(score),
        rewrite_ratio=rewrite_ratio,
        illegal_jumps_ratio=_clamp01(
            max(parent_level_rejected_ratio, deferred_unresolved_ratio)
        ),
    )


def _calculate_crossref_resolution_score(
    evidence: EvidenceAssessmentInput,
    crossrefs: CrossRefAssessmentInput,
    reasons: list[str],
) -> CrossRefResolutionScore:
    score = 0.0
    resolution_rate = 0.0
    appendix_resolution_rate = 0.0

    if evidence.crossref_anchor_count > 0:
        score = 0.35
        if evidence.crossref_anchor_count >= 3:
            score += 0.10
        if crossrefs.references_count > 0:
            score += 0.15
        else:
            reasons.append("crossref_anchors_detected_but_not_resolved")
    elif crossrefs.references_count > 0:
        score = 0.40

    if crossrefs.resolved_count is not None and crossrefs.references_count > 0:
        resolution_rate = _clamp01(crossrefs.resolved_count / max(1, crossrefs.references_count))
        score += 0.25 * resolution_rate
        if resolution_rate < 0.50:
            reasons.append("low_crossref_resolution_rate")

    appendix_total = 0
    if crossrefs.appendix_scoped_resolved_count is not None:
        appendix_total += crossrefs.appendix_scoped_resolved_count
    if crossrefs.appendix_scope_miss_count is not None:
        appendix_total += crossrefs.appendix_scope_miss_count
    if appendix_total > 0 and crossrefs.appendix_scoped_resolved_count is not None:
        appendix_resolution_rate = _clamp01(
            crossrefs.appendix_scoped_resolved_count / max(1, appendix_total)
        )
        score += 0.15 * appendix_resolution_rate
        if appendix_resolution_rate < 0.50:
            reasons.append("low_appendix_crossref_resolution_rate")

    if crossrefs.appendix_scope_miss_count is not None and crossrefs.appendix_scope_miss_count > 0:
        reasons.append("appendix_scope_reference_misses_detected")
        score -= min(0.15, 0.03 * crossrefs.appendix_scope_miss_count)

    if (
        crossrefs.toc_like_reference_skipped_count is not None
        and crossrefs.toc_like_reference_skipped_count > 0
    ):
        reasons.append("toc_like_references_skipped")

    return CrossRefResolutionScore(
        score=_clamp01(score),
        resolution_rate=resolution_rate,
        appendix_resolution_rate=appendix_resolution_rate,
    )


def build_structure_assessment(
    *,
    evidence: Any | None = None,
    fsm_summary: Any | None = None,
    resolution_audit: Any | None = None,
    recovery_audit: Any | None = None,
    crossref_stats: Any | None = None,
    coverage: float = 0.0,
    headings_count: int = 0,
    numeric_ratio: float = 1.0,
    empty_title_count: int = 0,
    structure_degraded: bool = False,
    root_sections_count: int = 0,
    appendix_root_count: int = 0,
    layout_degraded: bool = False,
) -> StructureAssessment:
    reasons: list[str] = []

    evidence_input = (
        evidence if isinstance(evidence, EvidenceAssessmentInput) else _extract_evidence_metrics(evidence)
    )
    hierarchy_input = HierarchyAssessmentInput(
        coverage=coverage,
        headings_count=headings_count,
        numeric_ratio=numeric_ratio,
        empty_title_count=empty_title_count,
        structure_degraded=structure_degraded,
        root_sections_count=root_sections_count,
        appendix_root_count=appendix_root_count,
    )
    fsm_input = _extract_fsm_input(fsm_summary)
    resolution_input = _extract_resolution_input(resolution_audit)
    recovery_input = _extract_recovery_input(recovery_audit)
    crossref_input = (
        crossref_stats if isinstance(crossref_stats, CrossRefAssessmentInput)
        else _extract_crossref_input(crossref_stats)
    )

    heading_quality = _calculate_heading_quality_score(hierarchy_input, evidence_input, reasons)
    grammar_consistency = _calculate_grammar_consistency_score(
        hierarchy_input, fsm_input, resolution_input, reasons
    )
    recovery_impact = _calculate_recovery_impact_score(
        hierarchy_input, recovery_input, layout_degraded, evidence_input, reasons
    )
    numbering_stability = _calculate_numbering_stability_score(
        hierarchy_input, evidence_input, fsm_input, resolution_input, reasons
    )
    crossref_quality = _calculate_crossref_resolution_score(
        evidence_input, crossref_input, reasons
    )

    if evidence_input.toc_detected and evidence_input.main_chain_len >= 5:
        reasons.append("strong_toc_and_main_chain_detected")
    elif evidence_input.toc_detected:
        reasons.append("toc_detected")

    if evidence_input.appendix_chain_len >= 3:
        reasons.append("appendix_chain_detected")

    if hierarchy_input.root_sections_count == 0 and evidence_input.main_chain_len >= 5:
        reasons.append("main_chain_detected_but_root_sections_not_materialized")

    if hierarchy_input.headings_count > 0 and hierarchy_input.structure_degraded:
        reasons.append("tree_incomplete_but_document_has_structure_signals")

    aggregate_score = (
        heading_quality.score * 0.25
        + grammar_consistency.score * 0.25
        + recovery_impact.score * 0.20
        + numbering_stability.score * 0.15
        + crossref_quality.score * 0.15
    )
    aggregate_score = _clamp01(aggregate_score)

    confidence_level = _confidence_level_from_score(
        aggregate_score,
        headings_count=hierarchy_input.headings_count,
        structure_degraded=hierarchy_input.structure_degraded,
    )
    confidence = _legacy_confidence_from_level(confidence_level)
    degraded = confidence_level in {ConfidenceLevel.LOW, ConfidenceLevel.VERY_LOW}
    retrieval_safe = confidence_level in {
        ConfidenceLevel.VERY_HIGH,
        ConfidenceLevel.HIGH,
        ConfidenceLevel.MEDIUM,
    }

    if confidence_level in {ConfidenceLevel.LOW, ConfidenceLevel.VERY_LOW} and not reasons:
        reasons.append("low_confidence_without_specific_explanation")

    return StructureAssessment(
        heading_quality=heading_quality,
        grammar_consistency=grammar_consistency,
        recovery_impact=recovery_impact,
        numbering_stability=numbering_stability,
        crossref_quality=crossref_quality,
        aggregate_score=aggregate_score,
        confidence_level=confidence_level,
        confidence=confidence,
        retrieval_safe=retrieval_safe,
        degraded=degraded,
        reasons=_dedupe_reasons(reasons),
        policy_version=STRUCTURE_ASSESSMENT_POLICY_VERSION,
    )


def build_structure_gate_decision(
    *,
    assessment: StructureAssessment,
    allow_semantic_tree_with_warnings: bool = True,
    hierarchy: HierarchyAssessmentInput | None = None,
    evidence: EvidenceAssessmentInput | None = None,
    crossrefs: CrossRefAssessmentInput | None = None,
) -> StructureGateDecision:
    reasons: list[str] = list(assessment.reasons)

    hierarchy = hierarchy or HierarchyAssessmentInput()
    evidence = evidence or EvidenceAssessmentInput()
    crossrefs = crossrefs or CrossRefAssessmentInput()

    strong_backbone = bool(
        evidence.toc_detected
        or evidence.main_chain_len >= 5
        or evidence.appendix_chain_len >= 3
        or hierarchy.root_sections_count >= 3
    )
    references_support_structure = crossrefs.references_count > 0

    if assessment.confidence_level in {ConfidenceLevel.VERY_HIGH, ConfidenceLevel.HIGH}:
        gate_mode = QUALITY_GATE_ALLOW_SECTION_CHUNKING
        section_chunking_allowed = True
        technical_fallback_only = False
        semantic_tree_preserved_despite_low_confidence = False
        final_mode = "semantic_tree"

    elif assessment.confidence_level == ConfidenceLevel.MEDIUM:
        gate_mode = (
            QUALITY_GATE_ALLOW_SECTION_CHUNKING_WITH_WARNINGS
            if strong_backbone
            else QUALITY_GATE_ALLOW_HYBRID_CHUNKING
        )
        section_chunking_allowed = True
        technical_fallback_only = False
        semantic_tree_preserved_despite_low_confidence = False
        final_mode = (
            "hybrid_chunking"
            if gate_mode == QUALITY_GATE_ALLOW_HYBRID_CHUNKING
            else "semantic_tree"
        )

    elif assessment.confidence_level == ConfidenceLevel.LOW:
        if allow_semantic_tree_with_warnings and (strong_backbone or references_support_structure):
            gate_mode = QUALITY_GATE_ALLOW_SECTION_CHUNKING_WITH_WARNINGS
            section_chunking_allowed = True
            technical_fallback_only = False
            semantic_tree_preserved_despite_low_confidence = True
            final_mode = "semantic_preserved_with_warnings"
            reasons.append("low_confidence_but_strong_structure_backbone_present")
        elif hierarchy.headings_count >= 3:
            gate_mode = QUALITY_GATE_ALLOW_HYBRID_CHUNKING
            section_chunking_allowed = True
            technical_fallback_only = False
            semantic_tree_preserved_despite_low_confidence = False
            final_mode = "hybrid_chunking"
            reasons.append("low_confidence_hybrid_chunking_allowed")
        else:
            gate_mode = QUALITY_GATE_BLOCK_AND_FALLBACK
            section_chunking_allowed = False
            technical_fallback_only = True
            semantic_tree_preserved_despite_low_confidence = False
            final_mode = "technical_fallback"
            reasons.append("low_confidence_without_recoverable_backbone")

    else:
        gate_mode = QUALITY_GATE_BLOCK_AND_FALLBACK
        section_chunking_allowed = False
        technical_fallback_only = True
        semantic_tree_preserved_despite_low_confidence = False
        final_mode = "technical_fallback"
        reasons.append("structure_confidence_failed")

    return StructureGateDecision(
        gate_mode=gate_mode,
        section_chunking_allowed=section_chunking_allowed,
        technical_fallback_only=technical_fallback_only,
        semantic_tree_preserved_despite_low_confidence=semantic_tree_preserved_despite_low_confidence,
        final_mode=final_mode,
        reasons=_dedupe_reasons(reasons),
    )


def compute_structure_assessment(
    *,
    hierarchy: HierarchyAssessmentInput,
    evidence: EvidenceAssessmentInput,
    crossrefs: CrossRefAssessmentInput,
    fsm_summary: Any | None = None,
    resolution_audit: Any | None = None,
    recovery_audit: Any | None = None,
    layout_degraded: bool = False,
) -> StructureAssessment:
    """
    Backward-compatible transitional wrapper.
    """
    return build_structure_assessment(
        evidence=evidence,
        fsm_summary=fsm_summary,
        resolution_audit=resolution_audit,
        recovery_audit=recovery_audit,
        crossref_stats=crossrefs,
        coverage=hierarchy.coverage,
        headings_count=hierarchy.headings_count,
        numeric_ratio=hierarchy.numeric_ratio,
        empty_title_count=hierarchy.empty_title_count,
        structure_degraded=hierarchy.structure_degraded,
        root_sections_count=hierarchy.root_sections_count,
        appendix_root_count=hierarchy.appendix_root_count,
        layout_degraded=layout_degraded,
    )


def decide_structure_gate(
    *,
    assessment: StructureAssessment,
    hierarchy: HierarchyAssessmentInput,
    evidence: EvidenceAssessmentInput,
    crossrefs: CrossRefAssessmentInput,
) -> StructureGateDecision:
    """
    Backward-compatible transitional wrapper.
    """
    return build_structure_gate_decision(
        assessment=assessment,
        allow_semantic_tree_with_warnings=True,
        hierarchy=hierarchy,
        evidence=evidence,
        crossrefs=crossrefs,
    )


def build_structure_confidence_report(
    *,
    coverage: float,
    headings_count: int = 0,
    numeric_ratio: float = 1.0,
    empty_title_count: int = 0,
    structure_degraded: bool = False,
    layout_degraded: bool = False,
    structure_evidence: Any | None = None,
    root_sections_count: int = 0,
    appendix_root_count: int = 0,
    cross_references_count: int = 0,
    fsm_summary: Any | None = None,
    resolution_audit: Any | None = None,
    recovery_audit: Any | None = None,
) -> StructureConfidenceReport:
    """
    Backward-compatible входная точка для текущего pipeline.
    """
    evidence_input = _extract_evidence_metrics(structure_evidence)

    hierarchy_input = _build_hierarchy_input(
        coverage=coverage,
        headings_count=headings_count,
        numeric_ratio=numeric_ratio,
        empty_title_count=empty_title_count,
        structure_degraded=structure_degraded,
        root_sections_count=root_sections_count,
        appendix_root_count=appendix_root_count,
    )

    crossref_input = _build_crossref_input(
        cross_references_count=cross_references_count,
    )

    assessment = compute_structure_assessment(
        hierarchy=hierarchy_input,
        evidence=evidence_input,
        crossrefs=crossref_input,
        fsm_summary=fsm_summary,
        resolution_audit=resolution_audit,
        recovery_audit=recovery_audit,
        layout_degraded=layout_degraded,
    )

    gate_decision = decide_structure_gate(
        assessment=assessment,
        hierarchy=hierarchy_input,
        evidence=evidence_input,
        crossrefs=crossref_input,
    )

    return StructureConfidenceReport(
        confidence=assessment.confidence,
        degraded=assessment.degraded,
        retrieval_safe=assessment.retrieval_safe,
        overall_score=assessment.aggregate_score,
        heading_confidence=assessment.heading_confidence,
        tree_consistency_confidence=assessment.tree_consistency_confidence,
        appendix_confidence=assessment.appendix_confidence,
        crossref_anchor_confidence=assessment.crossref_anchor_confidence,
        layout_quality_confidence=assessment.layout_quality_confidence,
        reasons=_dedupe_reasons(assessment.reasons),
        gate_mode=gate_decision.gate_mode,
        section_chunking_allowed=gate_decision.section_chunking_allowed,
        technical_fallback_only=gate_decision.technical_fallback_only,
        semantic_tree_preserved_despite_low_confidence=(
            gate_decision.semantic_tree_preserved_despite_low_confidence
        ),
        final_mode=gate_decision.final_mode,
        policy_version=assessment.policy_version,
    )

def confidence_and_mode(
    coverage: float,
    *,
    layout_degraded: bool = False,
    headings_count: int = 0,
    numeric_ratio: float = 1.0,
    empty_title_count: int = 0,
    structure_degraded: bool = False,
    structure_evidence: Any | None = None,
    root_sections_count: int = 0,
    appendix_root_count: int = 0,
    cross_references_count: int = 0,
) -> tuple[str, bool]:
    """
    Backward-compatible wrapper.

    Возвращает:
    - structural_confidence
    - degraded_flag
    """
    report = build_structure_confidence_report(
        coverage=coverage,
        headings_count=headings_count,
        numeric_ratio=numeric_ratio,
        empty_title_count=empty_title_count,
        structure_degraded=structure_degraded,
        layout_degraded=layout_degraded,
        structure_evidence=structure_evidence,
        root_sections_count=root_sections_count,
        appendix_root_count=appendix_root_count,
        cross_references_count=cross_references_count,
    )
    return report.confidence, report.degraded


