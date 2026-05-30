# src/services/structure/cohesion/cohesion.py

"""
Публичный фасад Phase 8 — Semantic Cohesion Analysis.

Единственная точка входа для downstream (Phase 9, Phase 10).
Скрывает внутреннюю структуру cohesion пакета.
"""

from __future__ import annotations

from services.structure.models import ClauseTree

from ._builder import build_semantic_cohesion_graph
from ._types import (
    CohesionBreakReason,
    CohesionEdge,
    CohesionEdgeKind,
    CohesionSignals,
    CohesionStats,
    SemanticCohesionGraph,
)


def analyze_cohesion(
    clause_tree: ClauseTree,
    *,
    sliding_window: int = 5,
    crossref_neighborhood: int = 2,
) -> SemanticCohesionGraph:
    """
    Canonical Phase 8 entry point.

    Принимает ClauseTree — финальный артефакт Phases 1-7.
    Возвращает SemanticCohesionGraph для Phase 9 и Phase 10.

    Параметры:
    - sliding_window: размер окна для sibling анализа (default=5)
    - crossref_neighborhood: максимальная дистанция для crossref edges (default=2)

    Complexity: O(N × window) где N = узлы в дереве.
    """
    return build_semantic_cohesion_graph(
        document_id=clause_tree.document_id,
        root_nodes=clause_tree.root,
        nodes_index=clause_tree.nodes_index,
        crossref_outgoing=dict(clause_tree.cross_reference_graph.outgoing_index),
        crossref_incoming=dict(clause_tree.cross_reference_graph.incoming_index),
        sliding_window=sliding_window,
        crossref_neighborhood=crossref_neighborhood,
    )


__all__ = [
    # Entry point
    "analyze_cohesion",
    # Result types
    "SemanticCohesionGraph",
    "CohesionEdge",
    "CohesionEdgeKind",
    "CohesionSignals",
    "CohesionStats",
    "CohesionBreakReason",
]


