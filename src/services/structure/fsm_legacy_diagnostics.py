# src/services/structure/fsm_legacy_diagnostics.py

"""
Legacy FSM diagnostics compatibility helpers.

ВАЖНО:
- этот модуль не является authoritative source of truth для quality policy;
- он существует как временный adapter, пока Phase 5 confidence layer
  не станет единственной точкой вычисления structure confidence / chunking readiness;
- входом служит только FSMBuildSummary из deterministic FSM runtime.
"""

from __future__ import annotations

from typing import Any

from services.structure._models._fsm_summary import FSMBuildSummary


def _has_valid_roots(summary: FSMBuildSummary) -> bool:
    return summary.root_count > 0 and summary.total_attached > 0


def _is_recoverable_numeric_backbone(summary: FSMBuildSummary) -> bool:
    """
    Transitional heuristic.

    Здесь мы больше НЕ читаем raw root nodes из runtime FSM.
    Оцениваем backbone только по summary counters.

    Это intentionally weaker heuristic, но она не нарушает
    архитектурную границу между Phase 3 и Phase 5.
    """
    return (
        _has_valid_roots(summary)
        and summary.attached_as_root >= 3
        and (summary.attached_as_child + summary.attached_deferred_child) >= 1
    )


def _structure_confidence_from_summary(
    summary: FSMBuildSummary,
    *,
    has_valid_roots: bool,
    recoverable_numeric_backbone: bool,
    deferred_resolution_good: bool,
    best_effort_ratio: float,
) -> str:
    if not has_valid_roots:
        return "LOW"

    if best_effort_ratio < 0.25 and deferred_resolution_good:
        return "HIGH"

    if best_effort_ratio < 0.45 or recoverable_numeric_backbone:
        return "MEDIUM"

    return "LOW"


def compute_legacy_quality_gates(summary: FSMBuildSummary) -> dict[str, Any]:
    """
    Legacy compatibility adapter.

    НЕ authoritative policy.
    НЕ замена Phase 5 confidence layer.
    НЕ должен вызываться из HierarchyStateMachine.

    Использовать только в transitional runtime, пока downstream
    ещё не переведён на explicit Phase 5 StructuralConfidence.
    """
    has_valid_roots = _has_valid_roots(summary)
    recoverable_numeric_backbone = _is_recoverable_numeric_backbone(summary)

    best_effort_ratio = summary.best_effort_ratio
    deferred_resolution_good = (
        summary.deferred_total == 0
        or summary.deferred_resolved >= summary.deferred_unresolved
    )

    structure_confidence = _structure_confidence_from_summary(
        summary,
        has_valid_roots=has_valid_roots,
        recoverable_numeric_backbone=recoverable_numeric_backbone,
        deferred_resolution_good=deferred_resolution_good,
        best_effort_ratio=best_effort_ratio,
    )

    section_chunking_allowed = (
        has_valid_roots
        and structure_confidence in {"HIGH", "MEDIUM"}
        and summary.root_count > 0
    )

    technical_fallback_only = not section_chunking_allowed

    hierarchy_quality = (
        "good"
        if structure_confidence == "HIGH"
        else "partial"
        if structure_confidence == "MEDIUM"
        else "failed"
    )

    return {
        "section_chunking_allowed": section_chunking_allowed,
        "technical_fallback_only": technical_fallback_only,
        "structure_confidence": structure_confidence,
        "recoverable_hierarchy_used": (
            summary.attached_best_effort > 0
            or recoverable_numeric_backbone
            or summary.deferred_resolved > 0
        ),
        "recoverable_numeric_backbone": recoverable_numeric_backbone,
        "deferred_resolution_good": deferred_resolution_good,
        "total_fallback_blocked": summary.total_skipped,
        "hierarchy_quality": hierarchy_quality,
        "best_effort_ratio": round(best_effort_ratio, 4),
        "deferred_total": summary.deferred_total,
        "deferred_resolved": summary.deferred_resolved,
        "deferred_unresolved": summary.deferred_unresolved,
        "root_count": summary.root_count,
        "total_attached": summary.total_attached,
        "total_skipped": summary.total_skipped,
        "max_depth_reached": summary.max_depth_reached,
    }


