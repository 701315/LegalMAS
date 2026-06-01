# src/services/structure/coherence/_resolver.py

"""
Phase 13.7 — Cross-Segment Coherence Resolver.

Анализирует смежные пары ClauseTree и строит CoherenceLink артефакты.
Не мутирует деревья.
"""

from __future__ import annotations

from core.logging import get_logger
from services.structure._models._nodes import FrozenHierarchyNode
from services.structure._models._tree import ClauseTree
from services.structure.coherence._types import (
    CoherenceLink,
    CrossSegmentCoherenceResult,
)

logger = get_logger(__name__)

# Дефолтные ограничения окна — настраиваются через параметры resolve()
_DEFAULT_MAX_PAGE_DISTANCE = 5
_DEFAULT_MAX_LEVEL_DELTA = 2


def _get_rightmost_deepest_node(
    nodes: list[FrozenHierarchyNode] | tuple[FrozenHierarchyNode, ...],
) -> FrozenHierarchyNode | None:
    """
    DFS правый обход: возвращает последний node максимальной глубины.

    Это семантически "последний heading" сегмента — тот под которым
    могут продолжаться дочерние разделы в следующем сегменте.
    """
    if not nodes:
        return None
    # Берём последний top-level node и рекурсивно идём вправо-вниз
    last = nodes[-1]
    if last.children:
        deeper = _get_rightmost_deepest_node(last.children)
        if deeper is not None:
            return deeper
    return last


def _get_orphan_roots(
    nodes: list[FrozenHierarchyNode] | tuple[FrozenHierarchyNode, ...],
) -> list[FrozenHierarchyNode]:
    """
    Возвращает top-level nodes дерева у которых
    diagnostics["recovered_via_best_effort"] == True.

    Именно эти nodes являются кандидатами на присоединение
    к last heading предыдущего сегмента.
    """
    return [
        node for node in nodes
        if bool(node.diagnostics.get("recovered_via_best_effort", False))
    ]


def _compute_confidence(
    *,
    level_delta: int,
    page_distance: int,
) -> float:
    """
    Уверенность CoherenceLink.

    1.0 при level_delta=1, page_distance=0.
    Линейно снижается с ростом page_distance.
    При level_delta > 1 — дополнительный штраф 0.1 за каждый лишний уровень.
    Минимум: 0.1.
    """
    base = 1.0
    base -= max(0, level_delta - 1) * 0.10
    base -= page_distance * 0.05
    return round(max(0.10, min(1.0, base)), 3)


class CrossSegmentCoherenceResolver:
    """
    Строит CoherenceLink артефакты между смежными сегментами.

    Алгоритм для каждой пары (tree[N], tree[N+1]):
    1. Найти rightmost deepest node в tree[N] → потенциальный parent.
    2. Найти orphan roots (best_effort_root) в tree[N+1] → кандидаты на child.
    3. Проверить level_delta и page_distance в допустимых пределах.
    4. Создать CoherenceLink для каждой подходящей пары.
    """

    def resolve(
        self,
        segment_trees: list[ClauseTree],
        *,
        max_page_distance: int = _DEFAULT_MAX_PAGE_DISTANCE,
        max_level_delta: int = _DEFAULT_MAX_LEVEL_DELTA,
    ) -> CrossSegmentCoherenceResult:
        """
        Основной entry point. Никогда не бросает — failure-isolated.
        """
        result = CrossSegmentCoherenceResult(
            segments_analyzed=len(segment_trees),
        )

        if len(segment_trees) < 2:
            return result

        try:
            for i in range(len(segment_trees) - 1):
                prev_tree = segment_trees[i]
                next_tree = segment_trees[i + 1]
                links = self._analyze_pair(
                    prev_tree=prev_tree,
                    next_tree=next_tree,
                    max_page_distance=max_page_distance,
                    max_level_delta=max_level_delta,
                )
                result.links.extend(links)

        except Exception as exc:
            logger.warning(
                "STRUCTURE cross_segment_coherence_resolver_failed",
                extra={"error": str(exc)},
            )
            result.resolver_error = str(exc)

        result.links_found = len(result.links)

        if result.links_found > 0:
            logger.info(
                "STRUCTURE cross_segment_coherence_links_found",
                extra={
                    "segments_analyzed": result.segments_analyzed,
                    "links_found": result.links_found,
                },
            )

        return result

    def _analyze_pair(
        self,
        *,
        prev_tree: ClauseTree,
        next_tree: ClauseTree,
        max_page_distance: int,
        max_level_delta: int,
    ) -> list[CoherenceLink]:
        """Анализ одной пары смежных деревьев."""
        links: list[CoherenceLink] = []

        source_node = _get_rightmost_deepest_node(prev_tree.root)
        if source_node is None:
            return links

        orphan_roots = _get_orphan_roots(next_tree.root)
        if not orphan_roots:
            return links

        prev_end_page = prev_tree.segment_page_range[1] if prev_tree.segment_page_range else source_node.end_page

        for orphan in orphan_roots:
            next_start_page = next_tree.segment_page_range[0] if next_tree.segment_page_range else orphan.start_page
            page_distance = abs(next_start_page - prev_end_page)
            level_delta = orphan.level - source_node.level

            # parent должен быть выше по иерархии
            if level_delta <= 0:
                continue
            if level_delta > max_level_delta:
                continue
            if page_distance > max_page_distance:
                continue

            confidence = _compute_confidence(
                level_delta=level_delta,
                page_distance=page_distance,
            )

            links.append(CoherenceLink(
                source_segment_id=str(prev_tree.segment_id or ""),
                target_segment_id=str(next_tree.segment_id or ""),
                source_node_uid=source_node.effective_uid,
                target_node_uid=orphan.effective_uid,
                source_level=source_node.level,
                target_level=orphan.level,
                page_distance=page_distance,
                confidence=confidence,
            ))

        return links
    
