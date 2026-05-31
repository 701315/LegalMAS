# src/services/structure/_pipeline/_postbuild_analysis.py

"""
Postbuild orchestration for Phase 8 + Phase 9.

Работает поверх уже построенного FileStructureResult:
- Phase 8: строит SemanticCohesionGraph для каждого ClauseTree
- Phase 9: строит StructureQualityReport для каждого ClauseTree

Архитектурные принципы:
- не влезает в _core_builder.py;
- не меняет существующий FileStructureResult;
- не ломает старый API;
- graceful degradation: если Phase 8 падает — Phase 9 продолжает
  без cohesion penalties;
- если Phase 9 падает — возвращает безопасный fallback report.

Phase 13.1 — Telemetry:
- analyze_segment_tree() принимает опциональный collector;
- если collector передан — emit QualityEvaluatedEvent после Phase 9;
- failure-isolated: ошибка emit не ломает pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.logging import get_logger
from services.structure._models._analysis import (
    CohesionMetrics,
    FileStructureAnalysisResult,
    QualityThresholds,
    QualityWarning,
    QualityWarningCode,
    RecommendedChunkingMode,
    SegmentAnalysisArtifacts,
    StructureMetrics,
    StructureQualityReport,
    WarningSeverity,
)
from services.structure._pipeline._quality_evaluation import (
    evaluate_structure_quality,
)
from services.structure.cohesion.cohesion import analyze_cohesion

if TYPE_CHECKING:
    from services.structure.cohesion._types import SemanticCohesionGraph
    from services.structure._models._tree import ClauseTree
    from services.structure._models._result import FileStructureResult
    from services.telemetry._collector import TelemetryCollector

logger = get_logger(__name__)


def _safe_str(value: Any, default: str = "") -> str:
    try:
        if value is None:
            return default
        return str(value)
    except Exception:
        return default


def _build_fallback_quality_report(
    tree: "ClauseTree",
    *,
    thresholds: QualityThresholds,
) -> StructureQualityReport:
    """
    Безопасный fallback report если Phase 9 evaluation упала.
    """
    document_id = _safe_str(
        getattr(tree, "document_id", None), default="unknown"
    )
    segment_id = getattr(tree, "segment_id", None)
    if segment_id is not None:
        segment_id = _safe_str(segment_id) or None

    nodes_index = getattr(tree, "nodes_index", None) or {}
    root_nodes = getattr(tree, "root", None) or []

    warning = QualityWarning(
        code=QualityWarningCode.QUALITY_EVALUATION_FAILED,
        severity=WarningSeverity.CRITICAL,
        message=(
            "Phase 9 quality evaluation failed unexpectedly; "
            "forcing layout fallback chunking"
        ),
        metric="quality_evaluation",
    )

    safety_warning = QualityWarning(
        code=QualityWarningCode.RETRIEVAL_SAFETY_LOW,
        severity=WarningSeverity.CRITICAL,
        message=(
            f"retrieval_safety_score=0.000 below "
            f"threshold={thresholds.retrieval_safety_threshold:.3f}"
        ),
        metric="retrieval_safety_score",
        value=0.0,
        threshold=thresholds.retrieval_safety_threshold,
    )

    structure_metrics = StructureMetrics(
        total_nodes=len(nodes_index),
        root_nodes_count=len(root_nodes),
        orphans_detected=0,
        orphans_recovered=0,
        orphans_unresolved=0,
        orphan_ratio=0.0,
        recovery_ratio=1.0,
        fallback_triggered=False,
        total_candidates=0,
        attached_best_effort=0,
        parent_level_rejected=0,
        deferred_unresolved=0,
        grammar_violation_ratio=0.0,
        rewrite_ratio=None,
        overall_score=0.0,
        retrieval_safe_phase5=False,
        degraded=True,
        technical_fallback_only=True,
        final_mode="technical_fallback",
        quality_gate_mode="phase9_fallback",
        crossref_references_count=0,
        crossref_unresolved_count=0,
        crossref_unresolved_ratio=0.0,
        fallback_fragment_nodes=0,
        fallback_fragment_ratio=0.0,
    )

    return StructureQualityReport(
        document_id=document_id,
        segment_id=segment_id,
        orphan_ratio=0.0,
        grammar_violation_ratio=0.0,
        rewrite_ratio=None,
        recovery_ratio=1.0,
        retrieval_safety_score=0.0,
        retrieval_safe=False,
        recommended_chunking_mode=RecommendedChunkingMode.LAYOUT_FALLBACK,
        warnings=(warning, safety_warning),
        structure_metrics=structure_metrics,
        cohesion_metrics=CohesionMetrics.unavailable(),
        thresholds=thresholds,
    )


def _make_report_with_extra_warning(
    report: StructureQualityReport,
    warning: QualityWarning,
) -> StructureQualityReport:
    """
    Возвращает НОВЫЙ immutable report с дополнительным warning.
    """
    return StructureQualityReport(
        document_id=report.document_id,
        segment_id=report.segment_id,
        orphan_ratio=report.orphan_ratio,
        grammar_violation_ratio=report.grammar_violation_ratio,
        rewrite_ratio=report.rewrite_ratio,
        recovery_ratio=report.recovery_ratio,
        retrieval_safety_score=report.retrieval_safety_score,
        retrieval_safe=report.retrieval_safe,
        recommended_chunking_mode=report.recommended_chunking_mode,
        warnings=report.warnings + (warning,),
        structure_metrics=report.structure_metrics,
        cohesion_metrics=report.cohesion_metrics,
        thresholds=report.thresholds,
        schema_version=report.schema_version,
    )


def _emit_quality_telemetry(
    collector: "TelemetryCollector",
    quality_report: StructureQualityReport,
    document_id: str,
    segment_id: str | None,
) -> None:
    """
    Phase 13.1: emit QualityEvaluatedEvent в collector.

    Failure-isolated: любая ошибка логируется и игнорируется.
    Вынесено в отдельную функцию для чистоты analyze_segment_tree().
    """
    try:
        from services.telemetry._events import QualityEvaluatedEvent

        collector.emit(QualityEvaluatedEvent(
            document_id=document_id,
            segment_id=segment_id,
            retrieval_safety_score=quality_report.retrieval_safety_score,
            retrieval_safe=quality_report.retrieval_safe,
            recommended_chunking_mode=(
                quality_report.recommended_chunking_mode.value
            ),
            warnings_count=len(quality_report.warnings),
            critical_warnings_count=sum(
                1 for w in quality_report.warnings
                if w.severity == WarningSeverity.CRITICAL
            ),
            cohesion_available=quality_report.cohesion_metrics.available,
            cohesion_avg_score=(
                quality_report.cohesion_metrics.avg_score
                if quality_report.cohesion_metrics.available else None
            ),
            fallback_fragment_ratio=(
                quality_report.structure_metrics.fallback_fragment_ratio
            ),
        ))
    except Exception as exc:
        logger.warning(
            "TELEMETRY postbuild_emit_quality_failed",
            document_id=document_id,
            segment_id=segment_id,
            error=str(exc),
        )


def analyze_segment_tree(
    tree: "ClauseTree",
    *,
    thresholds: QualityThresholds | None = None,
    sliding_window: int = 5,
    crossref_neighborhood: int = 2,
    collector: "TelemetryCollector | None" = None,
) -> SegmentAnalysisArtifacts:
    """
    Анализирует один ClauseTree:
    - Phase 8 → SemanticCohesionGraph
    - Phase 9 → StructureQualityReport

    Phase 13.1:
    - если передан collector → emit QualityEvaluatedEvent после Phase 9.
    """
    effective_thresholds = thresholds or QualityThresholds()

    document_id = _safe_str(
        getattr(tree, "document_id", None), default="unknown"
    )
    segment_id = getattr(tree, "segment_id", None)
    if segment_id is not None:
        segment_id = _safe_str(segment_id) or None

    logger.debug(
        "STRUCTURE postbuild_segment_analysis_started",
        extra={
            "document_id": document_id,
            "segment_id": segment_id,
        },
    )

    # ── Phase 8: Cohesion ─────────────────────────────────────────────────
    cohesion_graph: SemanticCohesionGraph | None = None
    cohesion_failed = False

    try:
        root_nodes = getattr(tree, "root", None) or []
        nodes_index = getattr(tree, "nodes_index", None) or {}

        if root_nodes and nodes_index:
            cohesion_graph = analyze_cohesion(
                tree,
                sliding_window=sliding_window,
                crossref_neighborhood=crossref_neighborhood,
            )
        else:
            logger.debug(
                "STRUCTURE postbuild_cohesion_skipped_empty_tree",
                extra={
                    "document_id": document_id,
                    "segment_id": segment_id,
                },
            )
    except Exception:
        cohesion_failed = True
        logger.exception(
            "STRUCTURE postbuild_cohesion_analysis_failed",
            extra={
                "document_id": document_id,
                "segment_id": segment_id,
            },
        )

    # ── Phase 9: Quality Evaluation ───────────────────────────────────────
    try:
        quality_report = evaluate_structure_quality(
            tree,
            cohesion_graph=cohesion_graph,
            thresholds=effective_thresholds,
        )
    except Exception:
        logger.exception(
            "STRUCTURE postbuild_quality_evaluation_failed",
            extra={
                "document_id": document_id,
                "segment_id": segment_id,
            },
        )
        quality_report = _build_fallback_quality_report(
            tree,
            thresholds=effective_thresholds,
        )

    # Если cohesion упала — добавляем warning в report
    if cohesion_failed:
        quality_report = _make_report_with_extra_warning(
            quality_report,
            QualityWarning(
                code=QualityWarningCode.COHESION_ANALYSIS_FAILED,
                severity=WarningSeverity.WARNING,
                message=(
                    "Phase 8 cohesion analysis failed; "
                    "quality evaluation continued "
                    "without cohesion penalties"
                ),
                metric="cohesion_analysis",
            ),
        )

    # ── Phase 13.1: Telemetry ─────────────────────────────────────────────
    if collector is not None:
        _emit_quality_telemetry(
            collector=collector,
            quality_report=quality_report,
            document_id=document_id,
            segment_id=segment_id,
        )

    logger.info(
        "STRUCTURE postbuild_segment_analysis_complete",
        extra={
            "document_id": document_id,
            "segment_id": segment_id,
            "has_cohesion": cohesion_graph is not None,
            "retrieval_safe": quality_report.retrieval_safe,
            "recommended_chunking_mode": (
                quality_report.recommended_chunking_mode.value
            ),
            "warnings_count": len(quality_report.warnings),
        },
    )

    return SegmentAnalysisArtifacts(
        segment_id=segment_id,
        cohesion_graph=cohesion_graph,
        quality_report=quality_report,
    )


def analyze_file_structure(
    file_structure: "FileStructureResult",
    *,
    thresholds: QualityThresholds | None = None,
    sliding_window: int = 5,
    crossref_neighborhood: int = 2,
    collector: "TelemetryCollector | None" = None,
) -> FileStructureAnalysisResult:
    """
    Анализирует FileStructureResult целиком по всем segment trees.

    Для каждого segment tree запускает Phase 8 + Phase 9.
    Если segment_trees пусто — анализирует primary_tree.

    Phase 13.1:
    - если передан collector → передаётся в каждый analyze_segment_tree().
    """
    if file_structure is None:
        raise ValueError("file_structure must not be None")

    segment_trees = list(
        getattr(file_structure, "segment_trees", None) or []
    )
    if not segment_trees:
        primary_tree = getattr(file_structure, "primary_tree", None)
        if primary_tree is not None:
            segment_trees = [primary_tree]

    artifacts: list[SegmentAnalysisArtifacts] = []
    for tree in segment_trees:
        artifacts.append(
            analyze_segment_tree(
                tree,
                thresholds=thresholds,
                sliding_window=sliding_window,
                crossref_neighborhood=crossref_neighborhood,
                collector=collector,
            )
        )

    return FileStructureAnalysisResult(
        file_structure=file_structure,
        segment_artifacts=tuple(artifacts),
    )




