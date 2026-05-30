# src/services/structure/_models/_quality_evaluation.py

"""
Phase 9 — Quality Evaluation: evaluator.

Единственная точка входа: evaluate_structure_quality().

Читает данные из:
- ClauseTree.structure_diagnostics  (Phase 3-7 artifacts)
- ClauseTree.nodes_index            (tree-level truth)
- ClauseTree.cross_reference_graph  (Phase 7)
- SemanticCohesionGraph             (Phase 8, опционально)

Возвращает StructureQualityReport для Phase 10 (Chunk Planner).

Архитектурные принципы:
- детерминированный: same input → same output;
- НЕ модифицирует ClauseTree или любые входные артефакты;
- НЕ пересчитывает то что уже посчитала Phase 5 —
  использует Phase 5 overall_score как базу;
- НЕ зависит от chunk manifests как источника truth;
- graceful degradation: отсутствие Phase 8 данных не ломает evaluator;
- rewrite_ratio = None если runtime contract не предоставляет данные;
- fallback_fragment_ratio: tree-level детекция technical fallback nodes
  которые могут выглядеть структурно но являются surrogate fragments.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.logging import get_logger
from services.structure._models._analysis import (
    CohesionMetrics,
    QualityThresholds,
    QualityWarning,
    QualityWarningCode,
    RecommendedChunkingMode,
    StructureMetrics,
    StructureQualityReport,
    WarningSeverity,
)

if TYPE_CHECKING:
    from services.structure.cohesion._types import SemanticCohesionGraph
    from services.structure._models._tree import ClauseTree

logger = get_logger(__name__)


# ─── Safe Accessors ───────────────────────────────────────────────────────────

def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return max(0, int(value))
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


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return _clamp01(numerator / denominator)


# ─── Fallback Fragment Detection ──────────────────────────────────────────────

_FALLBACK_TITLE_PREFIX = "[TECHNICAL FALLBACK]"

def _is_fallback_fragment_node(node: Any) -> bool:
    """
    Определяет является ли узел technical fallback fragment.

    Использует только tree-level сигналы из FrozenHierarchyNode.
    НЕ зависит от chunk manifests или downstream артефактов.

    Приоритет проверок:
    1. title prefix — самый надёжный сигнал
    2. node_origin — прямой machine-readable маркер
    3. content_mode — structural type маркер
    4. citability — качественный маркер
    5. diagnostics dict — legacy/transitional маркеры
    """
    try:
        title = _safe_str(getattr(node, "title", ""))
        if title.startswith(_FALLBACK_TITLE_PREFIX):
            return True

        node_origin = _safe_str(getattr(node, "node_origin", ""))
        if node_origin == "technical_fallback":
            return True

        content_mode = _safe_str(getattr(node, "content_mode", ""))
        if content_mode == "technical_fragment":
            return True

        citability = _safe_str(getattr(node, "citability", ""))
        if citability == "technical":
            return True

        diagnostics = _safe_dict(getattr(node, "diagnostics", None))
        if _safe_str(diagnostics.get("fallback_reason")) == "technical_fallback":
            return True
        if _safe_str(diagnostics.get("source_mode")) == "pipeline_fallback":
            return True
        if _safe_bool(diagnostics.get("degraded_chunk")):
            return True
        if _safe_bool(diagnostics.get("is_technical_fallback")):
            return True
        if _safe_str(diagnostics.get("fallback_mode")) == "technical_fallback":
            return True

    except Exception:
        return False

    return False


def _compute_fallback_fragment_metrics(
    nodes_index: dict[str, Any],
    total_nodes: int,
) -> tuple[int, float]:
    """
    Вычисляет fallback_fragment_nodes и fallback_fragment_ratio.

    Возвращает: (fallback_fragment_nodes, fallback_fragment_ratio)
    """
    if not nodes_index:
        return 0, 0.0

    fallback_count = sum(
        1 for node in nodes_index.values()
        if _is_fallback_fragment_node(node)
    )
    ratio = _safe_ratio(fallback_count, total_nodes)
    return fallback_count, ratio


# ─── Fallback StructureMetrics ────────────────────────────────────────────────

def _fallback_structure_metrics() -> StructureMetrics:
    """Безопасный fallback если extraction failed."""
    return StructureMetrics(
        total_nodes=0,
        root_nodes_count=0,
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
        quality_gate_mode="unknown",
        crossref_references_count=0,
        crossref_unresolved_count=0,
        crossref_unresolved_ratio=0.0,
        fallback_fragment_nodes=0,
        fallback_fragment_ratio=0.0,
    )


# ─── Data Extraction ──────────────────────────────────────────────────────────

def _extract_structure_metrics(tree: "ClauseTree") -> StructureMetrics:
    """
    Извлекает нормализованные метрики из ClauseTree.

    Источники данных (в порядке приоритета):
    1. tree.nodes_index, tree.root        — размер и состав дерева
    2. tree.degraded                      — Phase 5 degraded flag
    3. tree.cross_reference_graph.stats   — Phase 7 crossref stats
    4. diagnostics["hierarchy_builder"]   — FSM, recovery, resolution
    5. diagnostics["structure_confidence"]— Phase 5 scores
    6. diagnostics["quality_gates"]       — gate decision

    ВАЖНО: НЕ читает chunk manifests как источник truth.
    """
    diagnostics = _safe_dict(getattr(tree, "structure_diagnostics", None))
    hierarchy_builder = _safe_dict(diagnostics.get("hierarchy_builder"))
    structure_confidence = _safe_dict(diagnostics.get("structure_confidence"))
    quality_gates = _safe_dict(diagnostics.get("quality_gates"))
    quality_gate_assessment = _safe_dict(quality_gates.get("assessment"))

    # ── Tree size ─────────────────────────────────────────────────────────
    nodes_index = getattr(tree, "nodes_index", None) or {}
    total_nodes = len(nodes_index)
    root_nodes = getattr(tree, "root", None) or []
    root_nodes_count = len(root_nodes)

    # ── Fallback fragment detection (tree-level truth) ────────────────────
    fallback_fragment_nodes, fallback_fragment_ratio = (
        _compute_fallback_fragment_metrics(nodes_index, total_nodes)
    )

    # ── Recovery ──────────────────────────────────────────────────────────
    recovery_audit = _safe_dict(hierarchy_builder.get("recovery_audit"))
    orphans_detected = _safe_int(recovery_audit.get("orphans_detected"))
    orphans_recovered = _safe_int(recovery_audit.get("orphans_recovered"))
    orphans_unresolved = _safe_int(recovery_audit.get("orphans_unresolved"))
    fallback_triggered = _safe_bool(recovery_audit.get("fallback_triggered"))

    orphan_ratio = _safe_ratio(orphans_unresolved, total_nodes)
    recovery_ratio = (
        1.0
        if orphans_detected == 0
        else _safe_ratio(orphans_recovered, orphans_detected)
    )

    # ── FSM / Grammar ─────────────────────────────────────────────────────
    fsm_summary = _safe_dict(hierarchy_builder.get("fsm_summary"))
    total_candidates = _safe_int(fsm_summary.get("total_candidates"))
    total_attached = _safe_int(fsm_summary.get("total_attached"))
    attached_best_effort = _safe_int(fsm_summary.get("attached_best_effort"))
    parent_level_rejected = _safe_int(
        fsm_summary.get("parent_level_rejected")
    )
    deferred_total = _safe_int(fsm_summary.get("deferred_total"))
    deferred_unresolved = _safe_int(fsm_summary.get("deferred_unresolved"))

    best_effort_ratio = _safe_ratio(attached_best_effort, total_attached)
    parent_reject_ratio = _safe_ratio(
        parent_level_rejected, total_candidates
    )
    deferred_unresolved_ratio = _safe_ratio(
        deferred_unresolved, deferred_total
    )
    grammar_violation_ratio = _clamp01(
        max(
            best_effort_ratio,
            parent_reject_ratio,
            deferred_unresolved_ratio,
        )
    )

    # ── Resolution ────────────────────────────────────────────────────────
    resolution_audit = _safe_dict(hierarchy_builder.get("resolution_audit"))
    rewrite_ratio: float | None = None
    raw_rr = resolution_audit.get("rewrite_ratio")
    if raw_rr is not None:
        try:
            parsed = float(raw_rr)
            if 0.0 <= parsed <= 1.0:
                rewrite_ratio = parsed
        except Exception:
            rewrite_ratio = None

    # ── Phase 5 confidence ────────────────────────────────────────────────
    overall_score = _safe_float(
        structure_confidence.get(
            "overall_score",
            quality_gate_assessment.get("overall_score", 0.0),
        ),
        default=0.0,
    )
    retrieval_safe_phase5 = _safe_bool(
        structure_confidence.get(
            "retrieval_safe",
            quality_gate_assessment.get("retrieval_safe", False),
        ),
        default=False,
    )
    degraded = _safe_bool(
        structure_confidence.get(
            "degraded",
            getattr(tree, "degraded", True),
        ),
        default=True,
    )

    # ── Quality gate ──────────────────────────────────────────────────────
    technical_fallback_only = _safe_bool(
        quality_gates.get("technical_fallback_only"),
        default=False,
    )
    final_mode = _safe_str(
        quality_gates.get("final_mode"),
        default="unknown",
    )
    quality_gate_mode = _safe_str(
        quality_gates.get("quality_gate_mode"),
        default="unknown",
    )

    # ── Crossref ──────────────────────────────────────────────────────────
    crossref_graph = getattr(tree, "cross_reference_graph", None)
    crossref_stats = getattr(crossref_graph, "stats", None)
    crossref_references_count = _safe_int(
        getattr(crossref_stats, "references_count", 0)
    )
    crossref_unresolved_count = _safe_int(
        getattr(crossref_stats, "unresolved_count", 0)
    )
    crossref_unresolved_ratio = _safe_ratio(
        crossref_unresolved_count,
        crossref_references_count,
    )

    return StructureMetrics(
        total_nodes=total_nodes,
        root_nodes_count=root_nodes_count,
        orphans_detected=orphans_detected,
        orphans_recovered=orphans_recovered,
        orphans_unresolved=orphans_unresolved,
        orphan_ratio=orphan_ratio,
        recovery_ratio=recovery_ratio,
        fallback_triggered=fallback_triggered,
        total_candidates=total_candidates,
        attached_best_effort=attached_best_effort,
        parent_level_rejected=parent_level_rejected,
        deferred_unresolved=deferred_unresolved,
        grammar_violation_ratio=grammar_violation_ratio,
        rewrite_ratio=rewrite_ratio,
        overall_score=overall_score,
        retrieval_safe_phase5=retrieval_safe_phase5,
        degraded=degraded,
        technical_fallback_only=technical_fallback_only,
        final_mode=final_mode,
        quality_gate_mode=quality_gate_mode,
        crossref_references_count=crossref_references_count,
        crossref_unresolved_count=crossref_unresolved_count,
        crossref_unresolved_ratio=crossref_unresolved_ratio,
        fallback_fragment_nodes=fallback_fragment_nodes,
        fallback_fragment_ratio=fallback_fragment_ratio,
    )


def _extract_cohesion_metrics(
    cohesion_graph: "SemanticCohesionGraph | None",
) -> CohesionMetrics:
    """
    Извлекает метрики из SemanticCohesionGraph.

    Если cohesion_graph отсутствует или пуст — возвращает
    CohesionMetrics.unavailable() без штрафов.
    """
    if cohesion_graph is None:
        return CohesionMetrics.unavailable()

    stats = getattr(cohesion_graph, "stats", None)
    if stats is None:
        return CohesionMetrics.unavailable()

    total_edges = _safe_int(getattr(stats, "total_edges", 0))
    if total_edges == 0:
        return CohesionMetrics.unavailable()

    avg_score = _clamp01(_safe_float(getattr(stats, "avg_score", 1.0)))
    strong_boundaries_count = _safe_int(
        getattr(stats, "strong_boundaries_count", 0)
    )
    cohesive_pairs_count = _safe_int(
        getattr(stats, "cohesive_pairs_count", 0)
    )
    boundary_ratio = _safe_ratio(strong_boundaries_count, total_edges)

    return CohesionMetrics(
        available=True,
        total_edges=total_edges,
        avg_score=avg_score,
        strong_boundaries_count=strong_boundaries_count,
        cohesive_pairs_count=cohesive_pairs_count,
        boundary_ratio=boundary_ratio,
    )


# ─── Warning Generation ───────────────────────────────────────────────────────

def _generate_warnings(
    metrics: StructureMetrics,
    cohesion: CohesionMetrics,
    thresholds: QualityThresholds,
) -> list[QualityWarning]:
    """
    Генерирует список QualityWarning.

    Порядок проверок фиксирован (deterministic).
    Severity: value > threshold × 2.0 → CRITICAL, иначе → WARNING.
    """
    warnings: list[QualityWarning] = []

    def _severity(value: float, threshold: float) -> WarningSeverity:
        if value > threshold * 2.0:
            return WarningSeverity.CRITICAL
        return WarningSeverity.WARNING

    # 1. Empty tree
    if metrics.total_nodes == 0:
        warnings.append(QualityWarning(
            code=QualityWarningCode.EMPTY_TREE,
            severity=WarningSeverity.CRITICAL,
            message=(
                "No nodes in hierarchy tree — "
                "structure parsing produced empty result"
            ),
            metric="total_nodes",
            value=0.0,
            threshold=1.0,
        ))
        return warnings

    # 2. Degraded tree
    if metrics.degraded:
        warnings.append(QualityWarning(
            code=QualityWarningCode.DEGRADED_TREE,
            severity=WarningSeverity.WARNING,
            message="Structure tree marked as degraded by Phase 5",
            metric="degraded",
        ))

    # 3. Technical fallback forced
    if metrics.technical_fallback_only:
        warnings.append(QualityWarning(
            code=QualityWarningCode.TECHNICAL_FALLBACK_FORCED,
            severity=WarningSeverity.CRITICAL,
            message=(
                f"Quality gate forced technical fallback: "
                f"gate={metrics.quality_gate_mode}, "
                f"mode={metrics.final_mode}"
            ),
            metric="technical_fallback_only",
        ))

    # 4. Fallback fragment nodes present
    if metrics.fallback_fragment_nodes > 0:
        warnings.append(QualityWarning(
            code=QualityWarningCode.FALLBACK_FRAGMENT_NODES_PRESENT,
            severity=WarningSeverity.WARNING,
            message=(
                f"Detected {metrics.fallback_fragment_nodes} "
                f"technical fallback fragment nodes "
                f"out of {metrics.total_nodes} total"
            ),
            metric="fallback_fragment_nodes",
            value=float(metrics.fallback_fragment_nodes),
            threshold=1.0,
        ))

    # 5. Fallback fragment ratio high
    if metrics.fallback_fragment_ratio >= thresholds.fallback_fragment_ratio_warning:
        severity = (
            WarningSeverity.CRITICAL
            if metrics.fallback_fragment_ratio
            >= thresholds.fallback_fragment_ratio_critical
            else WarningSeverity.WARNING
        )
        warnings.append(QualityWarning(
            code=QualityWarningCode.FALLBACK_FRAGMENT_RATIO_HIGH,
            severity=severity,
            message=(
                f"fallback_fragment_ratio="
                f"{metrics.fallback_fragment_ratio:.3f} indicates "
                f"technical fallback structure dominates the tree. "
                f"Not a real legal hierarchy."
            ),
            metric="fallback_fragment_ratio",
            value=metrics.fallback_fragment_ratio,
            threshold=thresholds.fallback_fragment_ratio_warning,
        ))

    # 6. Orphan ratio
    if metrics.orphan_ratio > thresholds.orphan_ratio_warning:
        warnings.append(QualityWarning(
            code=QualityWarningCode.ORPHAN_RATIO_HIGH,
            severity=_severity(
                metrics.orphan_ratio,
                thresholds.orphan_ratio_warning,
            ),
            message=(
                f"orphan_ratio={metrics.orphan_ratio:.3f} exceeds "
                f"threshold={thresholds.orphan_ratio_warning:.3f}. "
                f"{metrics.orphans_unresolved} unrecovered orphans "
                f"out of {metrics.total_nodes} nodes"
            ),
            metric="orphan_ratio",
            value=metrics.orphan_ratio,
            threshold=thresholds.orphan_ratio_warning,
        ))

    # 7. Grammar violation ratio
    if (
        metrics.grammar_violation_ratio
        > thresholds.grammar_violation_ratio_warning
    ):
        warnings.append(QualityWarning(
            code=QualityWarningCode.GRAMMAR_VIOLATION_RATIO_HIGH,
            severity=_severity(
                metrics.grammar_violation_ratio,
                thresholds.grammar_violation_ratio_warning,
            ),
            message=(
                f"grammar_violation_ratio="
                f"{metrics.grammar_violation_ratio:.3f} exceeds "
                f"threshold="
                f"{thresholds.grammar_violation_ratio_warning:.3f}"
            ),
            metric="grammar_violation_ratio",
            value=metrics.grammar_violation_ratio,
            threshold=thresholds.grammar_violation_ratio_warning,
        ))

    # 8. Rewrite ratio
    if (
        metrics.rewrite_ratio is not None
        and metrics.rewrite_ratio > thresholds.rewrite_ratio_warning
    ):
        warnings.append(QualityWarning(
            code=QualityWarningCode.REWRITE_RATIO_HIGH,
            severity=_severity(
                metrics.rewrite_ratio,
                thresholds.rewrite_ratio_warning,
            ),
            message=(
                f"rewrite_ratio={metrics.rewrite_ratio:.3f} exceeds "
                f"threshold={thresholds.rewrite_ratio_warning:.3f}"
            ),
            metric="rewrite_ratio",
            value=metrics.rewrite_ratio,
            threshold=thresholds.rewrite_ratio_warning,
        ))

    # 9. Recovery ratio low
    if (
        metrics.orphans_detected > 0
        and metrics.recovery_ratio < thresholds.recovery_ratio_low
    ):
        warnings.append(QualityWarning(
            code=QualityWarningCode.RECOVERY_RATIO_LOW,
            severity=WarningSeverity.WARNING,
            message=(
                f"recovery_ratio={metrics.recovery_ratio:.3f} below "
                f"threshold={thresholds.recovery_ratio_low:.3f}. "
                f"Only {metrics.orphans_recovered} of "
                f"{metrics.orphans_detected} orphans recovered"
            ),
            metric="recovery_ratio",
            value=metrics.recovery_ratio,
            threshold=thresholds.recovery_ratio_low,
        ))

    # 10. Fallback triggered
    if metrics.fallback_triggered:
        warnings.append(QualityWarning(
            code=QualityWarningCode.FALLBACK_TRIGGERED,
            severity=WarningSeverity.WARNING,
            message="Recovery engine triggered fallback mode",
            metric="fallback_triggered",
        ))

    # 11. Crossref unresolved
    if (
        metrics.crossref_references_count > 0
        and metrics.crossref_unresolved_ratio
        > thresholds.crossref_unresolved_ratio_warning
    ):
        warnings.append(QualityWarning(
            code=QualityWarningCode.CROSSREF_UNRESOLVED_HIGH,
            severity=WarningSeverity.WARNING,
            message=(
                f"crossref_unresolved_ratio="
                f"{metrics.crossref_unresolved_ratio:.3f} exceeds "
                f"threshold="
                f"{thresholds.crossref_unresolved_ratio_warning:.3f}. "
                f"{metrics.crossref_unresolved_count} unresolved "
                f"out of {metrics.crossref_references_count}"
            ),
            metric="crossref_unresolved_ratio",
            value=metrics.crossref_unresolved_ratio,
            threshold=thresholds.crossref_unresolved_ratio_warning,
        ))

    # 12. Cohesion avg score low
    if (
        cohesion.available
        and cohesion.avg_score < thresholds.cohesion_avg_score_low
    ):
        warnings.append(QualityWarning(
            code=QualityWarningCode.COHESION_AVG_SCORE_LOW,
            severity=WarningSeverity.WARNING,
            message=(
                f"cohesion avg_score={cohesion.avg_score:.3f} below "
                f"threshold={thresholds.cohesion_avg_score_low:.3f}"
            ),
            metric="cohesion_avg_score",
            value=cohesion.avg_score,
            threshold=thresholds.cohesion_avg_score_low,
        ))

    # 13. Cohesion high boundary ratio
    if (
        cohesion.available
        and cohesion.boundary_ratio
        > thresholds.cohesion_boundary_ratio_high
    ):
        warnings.append(QualityWarning(
            code=QualityWarningCode.COHESION_HIGH_BOUNDARY_RATIO,
            severity=WarningSeverity.WARNING,
            message=(
                f"cohesion boundary_ratio="
                f"{cohesion.boundary_ratio:.3f} exceeds "
                f"threshold="
                f"{thresholds.cohesion_boundary_ratio_high:.3f}"
            ),
            metric="cohesion_boundary_ratio",
            value=cohesion.boundary_ratio,
            threshold=thresholds.cohesion_boundary_ratio_high,
        ))

    return warnings


# ─── Retrieval Safety Score ───────────────────────────────────────────────────

def _calculate_retrieval_safety_score(
    metrics: StructureMetrics,
    cohesion: CohesionMetrics,
    warnings: list[QualityWarning],
    thresholds: QualityThresholds,
) -> float:
    """
    Рассчитывает retrieval_safety_score для Phase 10.

    Стратегия v1:
    - берём overall_score из Phase 5 как базу;
    - применяем penalties за fallback fragments;
    - применяем penalties за structural problems;
    - применяем cohesion penalties если Phase 8 доступна;
    - применяем penalty за critical warnings;
    - НЕ пересчитываем Phase 5 с нуля.

    Penalty breakdown:
    - technical_fallback_only    → −0.35
    - fallback_fragment_ratio    → −ratio × 0.35 (cap 0.35)
    - orphan_ratio > threshold   → −ratio × 0.25
    - grammar_violation > thresh → −ratio × 0.20
    - cohesion avg_score low     → −deficit × 0.15
    - cohesion boundary_ratio hi → −excess × 0.10
    - critical warnings          → −0.15 per warning (cap 0.30)
    """
    base = metrics.overall_score

    # Технический fallback — жёсткий penalty
    if metrics.technical_fallback_only:
        base -= 0.35

    # Fallback fragment penalty — tree-level truth
    if metrics.fallback_fragment_ratio > 0.0:
        base -= min(metrics.fallback_fragment_ratio * 0.35, 0.35)

    # Orphan penalty
    if metrics.orphan_ratio > thresholds.orphan_ratio_warning:
        base -= metrics.orphan_ratio * 0.25

    # Grammar violation penalty
    if (
        metrics.grammar_violation_ratio
        > thresholds.grammar_violation_ratio_warning
    ):
        base -= metrics.grammar_violation_ratio * 0.20

    # Cohesion penalties (только если Phase 8 доступна)
    if cohesion.available:
        if cohesion.avg_score < thresholds.cohesion_avg_score_low:
            deficit = thresholds.cohesion_avg_score_low - cohesion.avg_score
            base -= deficit * 0.15

        if (
            cohesion.boundary_ratio
            > thresholds.cohesion_boundary_ratio_high
        ):
            excess = (
                cohesion.boundary_ratio
                - thresholds.cohesion_boundary_ratio_high
            )
            base -= excess * 0.10

    # Critical warnings penalty (cap = 0.30)
    critical_count = sum(
        1 for w in warnings if w.severity == WarningSeverity.CRITICAL
    )
    if critical_count > 0:
        base -= min(critical_count * 0.15, 0.30)

    return round(_clamp01(base), 4)


# ─── Chunking Mode Selection ──────────────────────────────────────────────────

def _select_chunking_mode(
    score: float,
    metrics: StructureMetrics,
    thresholds: QualityThresholds,
) -> RecommendedChunkingMode:
    """
    Детерминированный выбор chunking mode для Phase 10.

    Правила (в порядке приоритета):
    1. technical_fallback_only      → LAYOUT_FALLBACK
    2. total_nodes == 0             → LAYOUT_FALLBACK
    3. fallback_fragment_ratio >= critical threshold → LAYOUT_FALLBACK
    4. score >= mode_a_min          → STRUCTURE_FIRST
    5. score >= mode_b_min          → HYBRID
    6. иначе                        → LAYOUT_FALLBACK
    """
    if metrics.technical_fallback_only:
        return RecommendedChunkingMode.LAYOUT_FALLBACK

    if metrics.total_nodes == 0:
        return RecommendedChunkingMode.LAYOUT_FALLBACK

    if metrics.fallback_fragment_ratio >= thresholds.fallback_fragment_ratio_critical:
        return RecommendedChunkingMode.LAYOUT_FALLBACK

    if score >= thresholds.mode_a_min_score:
        return RecommendedChunkingMode.STRUCTURE_FIRST

    if score >= thresholds.mode_b_min_score:
        return RecommendedChunkingMode.HYBRID

    return RecommendedChunkingMode.LAYOUT_FALLBACK


# ─── Main Evaluator ───────────────────────────────────────────────────────────

def evaluate_structure_quality(
    tree: "ClauseTree",
    *,
    cohesion_graph: "SemanticCohesionGraph | None" = None,
    thresholds: QualityThresholds | None = None,
) -> StructureQualityReport:
    """
    Phase 9 — главная точка входа.

    Принимает:
    - tree: ClauseTree (Phase 1-7 финальный артефакт)
    - cohesion_graph: SemanticCohesionGraph (Phase 8, опционально)
    - thresholds: кастомные пороги (None → дефолты)

    Возвращает:
    - StructureQualityReport для Phase 10

    Гарантии:
    - детерминированный: same input → same output;
    - не бросает исключений при неполных данных;
    - не зависит от chunk manifests как источника truth.
    """
    effective_thresholds = thresholds or QualityThresholds()

    document_id = _safe_str(
        getattr(tree, "document_id", None),
        default="unknown",
    )
    segment_id = getattr(tree, "segment_id", None)
    if segment_id is not None:
        segment_id = _safe_str(segment_id) or None

    logger.debug(
        "STRUCTURE phase9_quality_evaluation_started",
        extra={
            "document_id": document_id,
            "segment_id": segment_id,
        },
    )

    # 1. Извлечение структурных метрик (включая fallback detection)
    try:
        structure_metrics = _extract_structure_metrics(tree)
    except Exception:
        logger.exception(
            "STRUCTURE phase9_structure_metrics_extraction_failed",
            extra={
                "document_id": document_id,
                "segment_id": segment_id,
            },
        )
        structure_metrics = _fallback_structure_metrics()

    # 2. Извлечение cohesion метрик
    try:
        cohesion_metrics = _extract_cohesion_metrics(cohesion_graph)
    except Exception:
        logger.exception(
            "STRUCTURE phase9_cohesion_metrics_extraction_failed",
            extra={
                "document_id": document_id,
                "segment_id": segment_id,
            },
        )
        cohesion_metrics = CohesionMetrics.unavailable()

    # 3. Генерация warnings
    try:
        warnings = _generate_warnings(
            structure_metrics,
            cohesion_metrics,
            effective_thresholds,
        )
    except Exception:
        logger.exception(
            "STRUCTURE phase9_warning_generation_failed",
            extra={
                "document_id": document_id,
                "segment_id": segment_id,
            },
        )
        warnings = []

    # 4. Retrieval safety score
    try:
        retrieval_safety_score = _calculate_retrieval_safety_score(
            structure_metrics,
            cohesion_metrics,
            warnings,
            effective_thresholds,
        )
    except Exception:
        logger.exception(
            "STRUCTURE phase9_safety_score_calculation_failed",
            extra={
                "document_id": document_id,
                "segment_id": segment_id,
            },
        )
        retrieval_safety_score = 0.0

    # 5. Retrieval safety flag + warning
    retrieval_safe = (
        retrieval_safety_score
        >= effective_thresholds.retrieval_safety_threshold
    )
    if not retrieval_safe:
        warnings.append(QualityWarning(
            code=QualityWarningCode.RETRIEVAL_SAFETY_LOW,
            severity=WarningSeverity.CRITICAL,
            message=(
                f"retrieval_safety_score={retrieval_safety_score:.3f} "
                f"below threshold="
                f"{effective_thresholds.retrieval_safety_threshold:.3f}"
            ),
            metric="retrieval_safety_score",
            value=retrieval_safety_score,
            threshold=effective_thresholds.retrieval_safety_threshold,
        ))

    # 6. Chunking mode
    chunking_mode = _select_chunking_mode(
        retrieval_safety_score,
        structure_metrics,
        effective_thresholds,
    )

    logger.info(
        "STRUCTURE phase9_quality_evaluation_complete",
        extra={
            "document_id": document_id,
            "segment_id": segment_id,
            "retrieval_safety_score": retrieval_safety_score,
            "retrieval_safe": retrieval_safe,
            "recommended_chunking_mode": chunking_mode.value,
            "orphan_ratio": structure_metrics.orphan_ratio,
            "grammar_violation_ratio": (
                structure_metrics.grammar_violation_ratio
            ),
            "rewrite_ratio": structure_metrics.rewrite_ratio,
            "recovery_ratio": structure_metrics.recovery_ratio,
            "fallback_fragment_nodes": structure_metrics.fallback_fragment_nodes,
            "fallback_fragment_ratio": structure_metrics.fallback_fragment_ratio,
            "cohesion_available": cohesion_metrics.available,
            "cohesion_avg_score": (
                cohesion_metrics.avg_score
                if cohesion_metrics.available
                else None
            ),
            "warnings_count": len(warnings),
            "critical_warnings_count": sum(
                1
                for w in warnings
                if w.severity == WarningSeverity.CRITICAL
            ),
        },
    )

    return StructureQualityReport(
        document_id=document_id,
        segment_id=segment_id,
        orphan_ratio=structure_metrics.orphan_ratio,
        grammar_violation_ratio=structure_metrics.grammar_violation_ratio,
        rewrite_ratio=structure_metrics.rewrite_ratio,
        recovery_ratio=structure_metrics.recovery_ratio,
        retrieval_safety_score=retrieval_safety_score,
        retrieval_safe=retrieval_safe,
        recommended_chunking_mode=chunking_mode,
        warnings=tuple(warnings),
        structure_metrics=structure_metrics,
        cohesion_metrics=cohesion_metrics,
        thresholds=effective_thresholds,
    )

