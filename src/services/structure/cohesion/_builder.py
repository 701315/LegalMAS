# src/services/structure/cohesion/_builder.py

"""
Оркестратор Phase 8 — Semantic Cohesion Analysis.

Строит SemanticCohesionGraph из ClauseTree.

Алгоритм:
1. SIBLING_WINDOW edges    — O(N × window)
2. WITHIN_SECTION edges    — O(N)
3. CROSSREF_NEIGHBOR edges — O(E × neighborhood)

Итого: O(N × window) — не O(N²).

Важно:
- все операции детерминированные;
- нет LLM, нет embeddings;
- нет глобальных попарных сравнений.
"""

from __future__ import annotations

from core.logging import get_logger
from services.structure.models import FrozenHierarchyNode

from ._signals import compute_cohesion_score, extract_signals
from ._traversal import (
    build_document_order_sequence,
    build_parent_index,
    extract_siblings_per_parent,
)
from ._types import (
    CohesionEdge,
    CohesionEdgeKind,
    CohesionStats,
    SemanticCohesionGraph,
)

logger = get_logger(__name__)

# ── Константы политики ───────────────────────────────────────────────────────

_DEFAULT_SLIDING_WINDOW = 5
_DEFAULT_CROSSREF_NEIGHBORHOOD = 2


# ============================================================================
# Edge builders
# ============================================================================

def _build_sibling_window_edges(
    root_nodes: list[FrozenHierarchyNode],
    *,
    crossref_outgoing: dict[str, tuple[str, ...]],
    crossref_incoming: dict[str, tuple[str, ...]],
    sliding_window: int,
) -> list[CohesionEdge]:
    """
    Строит SIBLING_WINDOW edges.

    Для каждой группы siblings берём окно размером sliding_window
    и создаём edges между каждой парой (left, right) в этом окне.

    Complexity: O(N × window).
    """
    edges: list[CohesionEdge] = []
    sibling_groups = extract_siblings_per_parent(root_nodes)

    for group in sibling_groups:
        n = len(group)
        if n < 2:
            continue

        for i in range(n):
            # Смотрим вперёд на window позиций
            for j in range(i + 1, min(i + sliding_window + 1, n)):
                left = group[i]
                right = group[j]
                distance = j - i

                signals = extract_signals(
                    left,
                    right,
                    kind=CohesionEdgeKind.SIBLING_WINDOW,
                    window_distance=distance,
                    crossref_outgoing=crossref_outgoing,
                    crossref_incoming=crossref_incoming,
                )

                score, break_reason = compute_cohesion_score(
                    signals,
                    kind=CohesionEdgeKind.SIBLING_WINDOW,
                )

                edges.append(
                    CohesionEdge(
                        source_uid=left.effective_uid,
                        target_uid=right.effective_uid,
                        kind=CohesionEdgeKind.SIBLING_WINDOW,
                        score=score,
                        signals=signals,
                        break_reason=break_reason,
                    )
                )

    return edges


def _build_within_section_edges(
    root_nodes: list[FrozenHierarchyNode],
    *,
    crossref_outgoing: dict[str, tuple[str, ...]],
    crossref_incoming: dict[str, tuple[str, ...]],
) -> list[CohesionEdge]:
    """
    Строит WITHIN_SECTION edges: parent → each direct child.

    Complexity: O(N) — каждый узел обрабатывается один раз.
    """
    edges: list[CohesionEdge] = []

    from ._traversal import walk_preorder_forest

    for parent in walk_preorder_forest(root_nodes):
        for child in parent.children:
            signals = extract_signals(
                parent,
                child,
                kind=CohesionEdgeKind.WITHIN_SECTION,
                window_distance=1,
                crossref_outgoing=crossref_outgoing,
                crossref_incoming=crossref_incoming,
            )

            score, break_reason = compute_cohesion_score(
                signals,
                kind=CohesionEdgeKind.WITHIN_SECTION,
            )

            edges.append(
                CohesionEdge(
                    source_uid=parent.effective_uid,
                    target_uid=child.effective_uid,
                    kind=CohesionEdgeKind.WITHIN_SECTION,
                    score=score,
                    signals=signals,
                    break_reason=break_reason,
                )
            )

    return edges


def _build_crossref_neighbor_edges(
    nodes_index: dict[str, FrozenHierarchyNode],
    *,
    crossref_outgoing: dict[str, tuple[str, ...]],
    crossref_incoming: dict[str, tuple[str, ...]],
    neighborhood: int,
    document_order_index: dict[str, int],
) -> list[CohesionEdge]:
    """
    Строит CROSSREF_NEIGHBOR edges.

    Для каждой cross-reference (source → target) создаём edge
    только если source и target находятся в пределах neighborhood
    по document order.

    Это предотвращает O(N²) — мы не создаём edges между далёкими узлами
    даже если между ними есть cross-reference.

    Complexity: O(E × neighborhood) где E = edges в crossref graph.
    """
    edges: list[CohesionEdge] = []
    seen_pairs: set[tuple[str, str]] = set()

    for source_uid, targets in crossref_outgoing.items():
        source_node = nodes_index.get(source_uid)
        if source_node is None:
            continue

        source_order = document_order_index.get(source_uid)
        if source_order is None:
            continue

        for target_uid in targets:
            # Deduplicate: не создаём дублирующие edges
            pair = (min(source_uid, target_uid), max(source_uid, target_uid))
            if pair in seen_pairs:
                continue

            target_node = nodes_index.get(target_uid)
            if target_node is None:
                continue

            target_order = document_order_index.get(target_uid)
            if target_order is None:
                continue

            # Locality check: только если в пределах neighborhood
            order_distance = abs(target_order - source_order)
            if order_distance > neighborhood:
                continue

            seen_pairs.add(pair)

            signals = extract_signals(
                source_node,
                target_node,
                kind=CohesionEdgeKind.CROSSREF_NEIGHBOR,
                window_distance=order_distance,
                crossref_outgoing=crossref_outgoing,
                crossref_incoming=crossref_incoming,
            )

            score, break_reason = compute_cohesion_score(
                signals,
                kind=CohesionEdgeKind.CROSSREF_NEIGHBOR,
            )

            edges.append(
                CohesionEdge(
                    source_uid=source_node.effective_uid,
                    target_uid=target_node.effective_uid,
                    kind=CohesionEdgeKind.CROSSREF_NEIGHBOR,
                    score=score,
                    signals=signals,
                    break_reason=break_reason,
                )
            )

    return edges


# ============================================================================
# Stats builder
# ============================================================================

def _build_stats(edges: list[CohesionEdge]) -> CohesionStats:
    """Вычисляет сводную статистику по всем edges. Complexity: O(E)."""
    if not edges:
        return CohesionStats()

    sibling_count = sum(
        1 for e in edges if e.kind == CohesionEdgeKind.SIBLING_WINDOW
    )
    within_count = sum(
        1 for e in edges if e.kind == CohesionEdgeKind.WITHIN_SECTION
    )
    crossref_count = sum(
        1 for e in edges if e.kind == CohesionEdgeKind.CROSSREF_NEIGHBOR
    )
    boundaries = sum(1 for e in edges if e.is_strong_boundary)
    cohesive = sum(1 for e in edges if e.is_cohesive)

    scores = [e.score for e in edges]
    avg_score = sum(scores) / len(scores)
    min_score = min(scores)
    max_score = max(scores)

    return CohesionStats(
        total_edges=len(edges),
        sibling_window_edges=sibling_count,
        within_section_edges=within_count,
        crossref_neighbor_edges=crossref_count,
        strong_boundaries_count=boundaries,
        cohesive_pairs_count=cohesive,
        avg_score=round(avg_score, 4),
        min_score=round(min_score, 4),
        max_score=round(max_score, 4),
    )


# ============================================================================
# Main entry point
# ============================================================================

def build_semantic_cohesion_graph(
    *,
    document_id: str,
    root_nodes: list[FrozenHierarchyNode],
    nodes_index: dict[str, FrozenHierarchyNode],
    crossref_outgoing: dict[str, tuple[str, ...]],
    crossref_incoming: dict[str, tuple[str, ...]],
    sliding_window: int = _DEFAULT_SLIDING_WINDOW,
    crossref_neighborhood: int = _DEFAULT_CROSSREF_NEIGHBORHOOD,
) -> SemanticCohesionGraph:
    """
    Строит SemanticCohesionGraph из компонентов ClauseTree.

    Принимает компоненты напрямую (не ClauseTree целиком) — это позволяет:
    - тестировать каждый компонент независимо;
    - использовать функцию без полного ClauseTree объекта;
    - избежать circular imports.

    Complexity: O(N × window) где N = количество узлов.
    """
    doc_id = str(document_id or "").strip()
    if not doc_id:
        raise ValueError("document_id must be non-empty")

    if not root_nodes:
        logger.info(
            "STRUCTURE cohesion_graph_empty_tree",
            extra={"document_id": doc_id},
        )
        return SemanticCohesionGraph(
            document_id=doc_id,
            local_edges=(),
            stats=CohesionStats(),
        )

    # Строим document order index для crossref neighborhood check
    # O(N)
    document_order: list[FrozenHierarchyNode] = build_document_order_sequence(root_nodes)
    document_order_index: dict[str, int] 


    