# src/services/structure/_models/_analysis.py

"""
Phase 9 — Quality Evaluation: data contracts.

Определяет immutable типы данных для postbuild-анализа:
- StructureQualityReport   — главный output Phase 9
- SegmentAnalysisArtifacts — sidecar артефакты на сегмент
- FileStructureAnalysisResult — bundle для downstream (Phase 10)

Архитектурные принципы:
- типы immutable после создания;
- Phase 9 НЕ останавливает pipeline при плохой структуре —
  она рекомендует режим chunking;
- rewrite_ratio может быть None если текущий runtime contract
  не предоставляет эту метрику;
- fallback_fragment_ratio: отдельная метрика для обнаружения
  technical fallback node trees;
- все поля сериализуемы через to_dict() для audit/telemetry.

Зависимости:
- SemanticCohesionGraph из Phase 8
- FileStructureResult из pipeline
- НЕ зависит от _quality_metrics.py напрямую
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from services.structure.cohesion._types import SemanticCohesionGraph
    from services.structure._models._result import FileStructureResult


# ─── Chunking Mode ────────────────────────────────────────────────────────────

class RecommendedChunkingMode(str, Enum):
    """
    Рекомендованный режим chunking от Phase 9 для Phase 10.

    STRUCTURE_FIRST:
        Дерево надёжно. Chunk Planner использует section boundaries
        как основной сигнал. Citation-safe поведение максимальное.

    HYBRID:
        Дерево пригодно, но есть шум. Chunk Planner комбинирует
        структурные и layout сигналы. Более широкий overlap.

    LAYOUT_FALLBACK:
        Дерево ненадёжно. Chunk Planner игнорирует структуру
        как основной сигнал и использует layout/text heuristics.
        Минимальное semantic enrichment.
    """

    STRUCTURE_FIRST = "structure_first"
    HYBRID = "hybrid"
    LAYOUT_FALLBACK = "layout_fallback"


# ─── Warning Severity ─────────────────────────────────────────────────────────

class WarningSeverity(str, Enum):
    """Уровень серьёзности предупреждения."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# ─── Warning Codes ────────────────────────────────────────────────────────────

class QualityWarningCode(str, Enum):
    """Машиночитаемые коды предупреждений Phase 9."""

    ORPHAN_RATIO_HIGH = "orphan_ratio_high"
    GRAMMAR_VIOLATION_RATIO_HIGH = "grammar_violation_ratio_high"
    RECOVERY_RATIO_LOW = "recovery_ratio_low"
    RETRIEVAL_SAFETY_LOW = "retrieval_safety_low"
    TECHNICAL_FALLBACK_FORCED = "technical_fallback_forced"
    COHESION_AVG_SCORE_LOW = "cohesion_avg_score_low"
    COHESION_HIGH_BOUNDARY_RATIO = "cohesion_high_boundary_ratio"
    CROSSREF_UNRESOLVED_HIGH = "crossref_unresolved_high"
    DEGRADED_TREE = "degraded_tree"
    EMPTY_TREE = "empty_tree"
    REWRITE_RATIO_HIGH = "rewrite_ratio_high"
    FALLBACK_TRIGGERED = "fallback_triggered"
    COHESION_ANALYSIS_FAILED = "cohesion_analysis_failed"
    QUALITY_EVALUATION_FAILED = "quality_evaluation_failed"

    # Fallback fragment detection
    FALLBACK_FRAGMENT_NODES_PRESENT = "fallback_fragment_nodes_present"
    FALLBACK_FRAGMENT_RATIO_HIGH = "fallback_fragment_ratio_high"


# ─── Quality Warning ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class QualityWarning:
    """Одно предупреждение о проблеме в структуре документа."""

    code: QualityWarningCode
    severity: WarningSeverity
    message: str
    metric: str = ""
    value: float | None = None
    threshold: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "severity": self.severity.value,
            "message": self.message,
            "metric": self.metric,
            "value": round(self.value, 4) if self.value is not None else None,
            "threshold": (
                round(self.threshold, 4) if self.threshold is not None else None
            ),
        }


# ─── Metric Thresholds ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class QualityThresholds:
    """
    Пороговые значения для Phase 9 метрик.
    Дефолты соответствуют плану v5.2.
    """

    orphan_ratio_warning: float = 0.10
    grammar_violation_ratio_warning: float = 0.15
    rewrite_ratio_warning: float = 0.10
    recovery_ratio_low: float = 0.70
    retrieval_safety_threshold: float = 0.70

    crossref_unresolved_ratio_warning: float = 0.30

    cohesion_avg_score_low: float = 0.45
    cohesion_boundary_ratio_high: float = 0.40

    mode_a_min_score: float = 0.75
    mode_b_min_score: float = 0.55

    # Fallback fragment thresholds
    fallback_fragment_ratio_warning: float = 0.50
    fallback_fragment_ratio_critical: float = 0.90

    def __post_init__(self) -> None:
        float_fields = [
            ("orphan_ratio_warning", self.orphan_ratio_warning),
            ("grammar_violation_ratio_warning", self.grammar_violation_ratio_warning),
            ("rewrite_ratio_warning", self.rewrite_ratio_warning),
            ("recovery_ratio_low", self.recovery_ratio_low),
            ("retrieval_safety_threshold", self.retrieval_safety_threshold),
            ("crossref_unresolved_ratio_warning", self.crossref_unresolved_ratio_warning),
            ("cohesion_avg_score_low", self.cohesion_avg_score_low),
            ("cohesion_boundary_ratio_high", self.cohesion_boundary_ratio_high),
            ("mode_a_min_score", self.mode_a_min_score),
            ("mode_b_min_score", self.mode_b_min_score),
            ("fallback_fragment_ratio_warning", self.fallback_fragment_ratio_warning),
            ("fallback_fragment_ratio_critical", self.fallback_fragment_ratio_critical),
        ]
        for name, value in float_fields:
            if not isinstance(value, (int, float)):
                raise ValueError(
                    f"QualityThresholds.{name} must be numeric, "
                    f"got {type(value).__name__}"
                )
            if not (0.0 <= float(value) <= 1.0):
                raise ValueError(
                    f"QualityThresholds.{name} must be in [0.0, 1.0], "
                    f"got {value}"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "orphan_ratio_warning": self.orphan_ratio_warning,
            "grammar_violation_ratio_warning": self.grammar_violation_ratio_warning,
            "rewrite_ratio_warning": self.rewrite_ratio_warning,
            "recovery_ratio_low": self.recovery_ratio_low,
            "retrieval_safety_threshold": self.retrieval_safety_threshold,
            "crossref_unresolved_ratio_warning": self.crossref_unresolved_ratio_warning,
            "cohesion_avg_score_low": self.cohesion_avg_score_low,
            "cohesion_boundary_ratio_high": self.cohesion_boundary_ratio_high,
            "mode_a_min_score": self.mode_a_min_score,
            "mode_b_min_score": self.mode_b_min_score,
            "fallback_fragment_ratio_warning": self.fallback_fragment_ratio_warning,
            "fallback_fragment_ratio_critical": self.fallback_fragment_ratio_critical,
        }


# ─── Raw Metrics ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class StructureMetrics:
    """
    Нормализованные структурные метрики документа.

    Извлекаются из ClauseTree.structure_diagnostics evaluator'ом.
    Все ratio в [0.0, 1.0].
    rewrite_ratio может быть None если runtime contract не предоставляет данные.

    fallback_fragment_nodes:
        Количество узлов, являющихся technical fallback fragments.
        Определяется по tree-level сигналам:
        - title.startswith("[TECHNICAL FALLBACK]")
        - node_origin == "technical_fallback"
        - content_mode == "technical_fragment"
        - citability == "technical"
        - diagnostics.fallback_reason / source_mode / degraded_chunk

    fallback_fragment_ratio:
        fallback_fragment_nodes / total_nodes
        Высокое значение (>= 0.5) означает, что структура фактически
        является техническим fallback, даже если выглядит структурной.
    """

    total_nodes: int
    root_nodes_count: int

    orphans_detected: int
    orphans_recovered: int
    orphans_unresolved: int
    orphan_ratio: float
    recovery_ratio: float
    fallback_triggered: bool

    total_candidates: int
    attached_best_effort: int
    parent_level_rejected: int
    deferred_unresolved: int
    grammar_violation_ratio: float

    rewrite_ratio: float | None

    overall_score: float
    retrieval_safe_phase5: bool
    degraded: bool
    technical_fallback_only: bool
    final_mode: str
    quality_gate_mode: str

    crossref_references_count: int
    crossref_unresolved_count: int
    crossref_unresolved_ratio: float

    # Fallback fragment detection
    fallback_fragment_nodes: int
    fallback_fragment_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_nodes": self.total_nodes,
            "root_nodes_count": self.root_nodes_count,
            "orphans_detected": self.orphans_detected,
            "orphans_recovered": self.orphans_recovered,
            "orphans_unresolved": self.orphans_unresolved,
            "orphan_ratio": round(self.orphan_ratio, 4),
            "recovery_ratio": round(self.recovery_ratio, 4),
            "fallback_triggered": self.fallback_triggered,
            "total_candidates": self.total_candidates,
            "attached_best_effort": self.attached_best_effort,
            "parent_level_rejected": self.parent_level_rejected,
            "deferred_unresolved": self.deferred_unresolved,
            "grammar_violation_ratio": round(self.grammar_violation_ratio, 4),
            "rewrite_ratio": (
                round(self.rewrite_ratio, 4)
                if self.rewrite_ratio is not None
                else None
            ),
            "overall_score": round(self.overall_score, 4),
            "retrieval_safe_phase5": self.retrieval_safe_phase5,
            "degraded": self.degraded,
            "technical_fallback_only": self.technical_fallback_only,
            "final_mode": self.final_mode,
            "quality_gate_mode": self.quality_gate_mode,
            "crossref_references_count": self.crossref_references_count,
            "crossref_unresolved_count": self.crossref_unresolved_count,
            "crossref_unresolved_ratio": round(self.crossref_unresolved_ratio, 4),
            "fallback_fragment_nodes": self.fallback_fragment_nodes,
            "fallback_fragment_ratio": round(self.fallback_fragment_ratio, 4),
        }


@dataclass(frozen=True)
class CohesionMetrics:
    """
    Метрики из SemanticCohesionGraph (Phase 8).

    available=False если Phase 8 не была запущена или вернула пустой граф.
    При available=False cohesion не штрафует документ.
    """

    available: bool
    total_edges: int
    avg_score: float
    strong_boundaries_count: int
    cohesive_pairs_count: int
    boundary_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "total_edges": self.total_edges,
            "avg_score": round(self.avg_score, 4),
            "strong_boundaries_count": self.strong_boundaries_count,
            "cohesive_pairs_count": self.cohesive_pairs_count,
            "boundary_ratio": round(self.boundary_ratio, 4),
        }

    @classmethod
    def unavailable(cls) -> "CohesionMetrics":
        """Нейтральные метрики когда Phase 8 недоступна."""
        return cls(
            available=False,
            total_edges=0,
            avg_score=1.0,
            strong_boundaries_count=0,
            cohesive_pairs_count=0,
            boundary_ratio=0.0,
        )


# ─── Main Quality Report ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class StructureQualityReport:
    """
    Главный output Phase 9 — Quality Evaluation.

    Используется Phase 10 (Chunk Planner) для выбора chunking strategy.

    ВАЖНО:
    - этот report НЕ останавливает pipeline;
    - он рекомендует режим через recommended_chunking_mode;
    - rewrite_ratio может быть None (честно, без фальсификации);
    - fallback_fragment_ratio детектирует technical fallback деревья,
      которые могут выглядеть структурно, но не являются настоящей
      legal hierarchy.
    """

    document_id: str
    segment_id: str | None

    orphan_ratio: float
    grammar_violation_ratio: float
    rewrite_ratio: float | None
    recovery_ratio: float

    retrieval_safety_score: float
    retrieval_safe: bool

    recommended_chunking_mode: RecommendedChunkingMode
    warnings: tuple[QualityWarning, ...]

    structure_metrics: StructureMetrics
    cohesion_metrics: CohesionMetrics
    thresholds: QualityThresholds

    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if not self.document_id:
            raise ValueError(
                "StructureQualityReport.document_id must not be empty"
            )

        for name, value in [
            ("orphan_ratio", self.orphan_ratio),
            ("grammar_violation_ratio", self.grammar_violation_ratio),
            ("recovery_ratio", self.recovery_ratio),
            ("retrieval_safety_score", self.retrieval_safety_score),
        ]:
            if not (0.0 <= value <= 1.0):
                raise ValueError(
                    f"StructureQualityReport.{name} must be in "
                    f"[0.0, 1.0], got {value}"
                )

        if self.rewrite_ratio is not None:
            if not (0.0 <= self.rewrite_ratio <= 1.0):
                raise ValueError(
                    f"StructureQualityReport.rewrite_ratio must be in "
                    f"[0.0, 1.0] or None, got {self.rewrite_ratio}"
                )

        expected_safe = (
            self.retrieval_safety_score
            >= self.thresholds.retrieval_safety_threshold
        )
        if self.retrieval_safe != expected_safe:
            raise ValueError(
                f"StructureQualityReport.retrieval_safe={self.retrieval_safe} "
                f"inconsistent with retrieval_safety_score="
                f"{self.retrieval_safety_score} and threshold="
                f"{self.thresholds.retrieval_safety_threshold}"
            )

    @property
    def has_critical_warnings(self) -> bool:
        return any(
            w.severity == WarningSeverity.CRITICAL for w in self.warnings
        )

    @property
    def has_warnings(self) -> bool:
        return any(
            w.severity in {WarningSeverity.WARNING, WarningSeverity.CRITICAL}
            for w in self.warnings
        )

    @property
    def warning_codes(self) -> frozenset[str]:
        return frozenset(w.code.value for w in self.warnings)

    @property
    def is_full_fallback(self) -> bool:
        """
        True если всё дерево состоит из technical fallback fragments.
        Convenience accessor для Phase 10.
        """
        return self.structure_metrics.fallback_fragment_ratio >= 0.90

    def warnings_by_severity(
        self, severity: WarningSeverity,
    ) -> list[QualityWarning]:
        return [w for w in self.warnings if w.severity == severity]

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "segment_id": self.segment_id,
            "schema_version": self.schema_version,
            "orphan_ratio": round(self.orphan_ratio, 4),
            "grammar_violation_ratio": round(
                self.grammar_violation_ratio, 4
            ),
            "rewrite_ratio": (
                round(self.rewrite_ratio, 4)
                if self.rewrite_ratio is not None
                else None
            ),
            "recovery_ratio": round(self.recovery_ratio, 4),
            "retrieval_safety_score": round(
                self.retrieval_safety_score, 4
            ),
            "retrieval_safe": self.retrieval_safe,
            "recommended_chunking_mode": (
                self.recommended_chunking_mode.value
            ),
            "is_full_fallback": self.is_full_fallback,
            "has_critical_warnings": self.has_critical_warnings,
            "has_warnings": self.has_warnings,
            "warning_codes": sorted(self.warning_codes),
            "warnings": [w.to_dict() for w in self.warnings],
            "structure_metrics": self.structure_metrics.to_dict(),
            "cohesion_metrics": self.cohesion_metrics.to_dict(),
            "thresholds": self.thresholds.to_dict(),
        }


# ─── Sidecar Artifacts ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SegmentAnalysisArtifacts:
    """Postbuild sidecar-артефакты для одного сегмента."""

    segment_id: str | None
    cohesion_graph: "SemanticCohesionGraph | None"
    quality_report: StructureQualityReport | None

    @property
    def has_cohesion(self) -> bool:
        return self.cohesion_graph is not None

    @property
    def has_quality_report(self) -> bool:
        return self.quality_report is not None

    @property
    def recommended_chunking_mode(self) -> RecommendedChunkingMode:
        if self.quality_report is None:
            return RecommendedChunkingMode.LAYOUT_FALLBACK
        return self.quality_report.recommended_chunking_mode

    @property
    def retrieval_safe(self) -> bool:
        if self.quality_report is None:
            return False
        return self.quality_report.retrieval_safe

    @property
    def is_full_fallback(self) -> bool:
        if self.quality_report is None:
            return True
        return self.quality_report.is_full_fallback

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "has_cohesion": self.has_cohesion,
            "has_quality_report": self.has_quality_report,
            "recommended_chunking_mode": (
                self.recommended_chunking_mode.value
            ),
            "retrieval_safe": self.retrieval_safe,
            "is_full_fallback": self.is_full_fallback,
            "quality_report": (
                self.quality_report.to_dict()
                if self.quality_report is not None
                else None
            ),
            "cohesion_stats": (
                self.cohesion_graph.stats.to_dict()
                if self.cohesion_graph is not None
                else None
            ),
        }


# ─── File Structure Analysis Result ──────────────────────────────────────────

@dataclass(frozen=True)
class FileStructureAnalysisResult:
    """
    Финальный bundle после postbuild-анализа (Phase 8 + Phase 9).

    Содержит:
    - оригинальный FileStructureResult (Phase 1-7)
    - sidecar-артефакты Phase 8/9 по каждому сегменту

    НЕ заменяет FileStructureResult — является его расширением.
    Старый код может продолжать использовать file_structure напрямую.
    """

    file_structure: "FileStructureResult"
    segment_artifacts: tuple[SegmentAnalysisArtifacts, ...]

    def __post_init__(self) -> None:
        if self.file_structure is None:
            raise ValueError(
                "FileStructureAnalysisResult.file_structure must not be None"
            )

    @property
    def primary_artifacts(self) -> SegmentAnalysisArtifacts | None:
        """
        Артефакты primary сегмента.

        Определяется через file_structure.primary_tree.segment_id —
        единственный надёжный способ, гарантированный
        инвариантами FileStructureResult.
        """
        primary_tree = self.file_structure.primary_tree
        primary_segment_id = primary_tree.segment_id

        for artifact in self.segment_artifacts:
            if artifact.segment_id == primary_segment_id:
                return artifact

        if self.segment_artifacts:
            return self.segment_artifacts[0]

        return None

    @property
    def overall_retrieval_safe(self) -> bool:
        """
        True если ВСЕ сегменты retrieval-safe.
        Консервативная политика.
        """
        if not self.segment_artifacts:
            return False
        return all(a.retrieval_safe for a in self.segment_artifacts)

    @property
    def any_critical_warnings(self) -> bool:
        """True если хотя бы один сегмент имеет critical warnings."""
        return any(
            a.quality_report is not None
            and a.quality_report.has_critical_warnings
            for a in self.segment_artifacts
        )

    @property
    def all_segments_full_fallback(self) -> bool:
        """True если ВСЕ сегменты являются full technical fallback."""
        if not self.segment_artifacts:
            return True
        return all(a.is_full_fallback for a in self.segment_artifacts)

    @property
    def recommended_chunking_modes(self) -> dict[str | None, str]:
        """Mapping segment_id → recommended_chunking_mode."""
        return {
            a.segment_id: a.recommended_chunking_mode.value
            for a in self.segment_artifacts
        }

    def artifacts_for_segment(
        self, segment_id: str | None,
    ) -> SegmentAnalysisArtifacts | None:
        """Возвращает артефакты для конкретного сегмента."""
        for artifact in self.segment_artifacts:
            if artifact.segment_id == segment_id:
                return artifact
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.file_structure.primary_tree.document_id,
            "overall_retrieval_safe": self.overall_retrieval_safe,
            "any_critical_warnings": self.any_critical_warnings,
            "all_segments_full_fallback": self.all_segments_full_fallback,
            "segment_count": len(self.segment_artifacts),
            "recommended_chunking_modes": self.recommended_chunking_modes,
            "segment_artifacts": [
                a.to_dict() for a in self.segment_artifacts
            ],
        }


# ─── Public API ───────────────────────────────────────────────────────────────

__all__ = [
    "CohesionMetrics",
    "FileStructureAnalysisResult",
    "QualityThresholds",
    "QualityWarning",
    "QualityWarningCode",
    "RecommendedChunkingMode",
    "SegmentAnalysisArtifacts",
    "StructureMetrics",
    "StructureQualityReport",
    "WarningSeverity",
]


