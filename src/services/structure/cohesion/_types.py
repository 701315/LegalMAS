# src/services/structure/cohesion/_types.py

"""
Типы данных Phase 8 — Semantic Cohesion Analysis.

Контракт:
- все типы immutable (frozen=True где возможно);
- CohesionEdge — единица анализа;
- SemanticCohesionGraph — финальный артефакт фазы;
- score: float [0.0, 1.0] — для downstream threshold policy.

Важно:
- Phase 8 не использует LLM;
- все сигналы — структурные, детерминированные;
- complexity O(N × window), не O(N²).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CohesionEdgeKind(str, Enum):
    """
    Тип связи между двумя узлами.

    SIBLING_WINDOW:
        Соседние узлы одного родителя в пределах sliding_window.
        Основной источник cohesion сигнала.

    WITHIN_SECTION:
        Связь parent → direct child.
        Фиксирует structural containment как cohesion.

    CROSSREF_NEIGHBOR:
        Узлы связанные через CrossReferenceGraph.
        Только если оба узла в пределах cross_ref_neighborhood.
    """

    SIBLING_WINDOW = "sibling_window"
    WITHIN_SECTION = "within_section"
    CROSSREF_NEIGHBOR = "crossref_neighbor"


class CohesionBreakReason(str, Enum):
    """
    Причина низкого cohesion score на edge.

    Используется для:
    - объяснимости решений Phase 10 (Chunk Planner);
    - audit и telemetry;
    - diagnostics.
    """

    SCOPE_CHANGE = "scope_change"
    LEVEL_JUMP = "level_jump"
    NUMBERING_GAP = "numbering_gap"
    NO_CROSSREF_LINK = "no_crossref_link"
    APPENDIX_BOUNDARY = "appendix_boundary"
    NONE = "none"


@dataclass(frozen=True)
class CohesionSignals:
    """
    Структурные сигналы для вычисления cohesion score.

    Все поля — детерминированные, из структурных артефактов Phases 2-7.
    Никакого LLM, никаких embeddings.

    Поля:
    - same_scope: узлы в одном scope
    - level_delta: разница в уровнях (0 = siblings, 1 = parent-child)
    - numbering_continuous: uid нумерация непрерывна между узлами
    - has_crossref: есть прямая cross-reference между узлами
    - window_distance: расстояние в sliding window (1 = adjacent)
    - both_have_own_text: оба узла имеют own_text (не skeleton)
    - is_appendix_boundary: один из узлов — appendix root
    """

    same_scope: bool = True
    level_delta: int = 0
    numbering_continuous: bool = False
    has_crossref: bool = False
    window_distance: int = 1
    both_have_own_text: bool = True
    is_appendix_boundary: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "same_scope": self.same_scope,
            "level_delta": self.level_delta,
            "numbering_continuous": self.numbering_continuous,
            "has_crossref": self.has_crossref,
            "window_distance": self.window_distance,
            "both_have_own_text": self.both_have_own_text,
            "is_appendix_boundary": self.is_appendix_boundary,
        }


@dataclass(frozen=True)
class CohesionEdge:
    """
    Единица cohesion анализа — связь между двумя узлами.

    source_uid / target_uid:
        effective_uid узлов из FrozenHierarchyNode.

    kind:
        Тип связи — определяет как интерпретировать score.

    score:
        float [0.0, 1.0]
        0.0 = нет cohesion (strong boundary для Chunk Planner)
        1.0 = высокая cohesion (не резать здесь)

    signals:
        Структурные сигналы из которых вычислен score.
        Нужны для explainability и audit.

    break_reason:
        Причина если score низкий.
        NONE если score >= threshold.
    """

    source_uid: str
    target_uid: str
    kind: CohesionEdgeKind
    score: float
    signals: CohesionSignals
    break_reason: CohesionBreakReason = CohesionBreakReason.NONE

    def __post_init__(self) -> None:
        if not self.source_uid:
            raise ValueError("CohesionEdge.source_uid must be non-empty")
        if not self.target_uid:
            raise ValueError("CohesionEdge.target_uid must be non-empty")
        if self.source_uid == self.target_uid:
            raise ValueError("CohesionEdge: source_uid and target_uid must differ")
        if not isinstance(self.kind, CohesionEdgeKind):
            raise ValueError("CohesionEdge.kind must be CohesionEdgeKind")
        if not isinstance(self.signals, CohesionSignals):
            raise ValueError("CohesionEdge.signals must be CohesionSignals")
        if not isinstance(self.break_reason, CohesionBreakReason):
            raise ValueError("CohesionEdge.break_reason must be CohesionBreakReason")

        # Clamp score в [0.0, 1.0]
        object.__setattr__(
            self, "score", max(0.0, min(1.0, float(self.score)))
        )

    @property
    def is_strong_boundary(self) -> bool:
        """
        True если score указывает на сильную границу между узлами.
        Phase 10 использует это для chunk boundary detection.
        Threshold 0.35 — консервативный, не режем без явных сигналов.
        """
        return self.score < 0.35

    @property
    def is_cohesive(self) -> bool:
        """Convenience: высокая cohesion между узлами."""
        return self.score >= 0.65

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_uid": self.source_uid,
            "target_uid": self.target_uid,
            "kind": self.kind.value,
            "score": round(self.score, 4),
            "break_reason": self.break_reason.value,
            "signals": self.signals.to_dict(),
            "is_strong_boundary": self.is_strong_boundary,
            "is_cohesive": self.is_cohesive,
        }


@dataclass(frozen=True)
class CohesionStats:
    """
    Сводная статистика по SemanticCohesionGraph.

    Используется для:
    - Phase 9 Quality Evaluation;
    - diagnostics и telemetry;
    - audit.
    """

    total_edges: int = 0
    sibling_window_edges: int = 0
    within_section_edges: int = 0
    crossref_neighbor_edges: int = 0
    strong_boundaries_count: int = 0
    cohesive_pairs_count: int = 0
    avg_score: float = 0.0
    min_score: float = 1.0
    max_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_edges": self.total_edges,
            "sibling_window_edges": self.sibling_window_edges,
            "within_section_edges": self.within_section_edges,
            "crossref_neighbor_edges": self.crossref_neighbor_edges,
            "strong_boundaries_count": self.strong_boundaries_count,
            "cohesive_pairs_count": self.cohesive_pairs_count,
            "avg_score": round(self.avg_score, 4),
            "min_score": round(self.min_score, 4),
            "max_score": round(self.max_score, 4),
        }


@dataclass(frozen=True)
class SemanticCohesionGraph:
    """
    Финальный артефакт Phase 8.

    Содержит locality-bounded cohesion edges между узлами дерева.
    Используется Phase 10 (Chunk Planner) для boundary detection.

    Гарантии:
    - все edge score в [0.0, 1.0];
    - нет глобальных O(N²) edges;
    - все edges locality-bounded (window, section, crossref neighborhood);
    - deterministic: один и тот же ClauseTree → один и тот же граф.

    Поля:
    - document_id: для correlation с ClauseTree
    - local_edges: все cohesion edges
    - stats: сводная статистика
    - schema_version: для versioning downstream
    """

    document_id: str
    local_edges: tuple[CohesionEdge, ...]
    stats: CohesionStats
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if not self.document_id:
            raise ValueError("SemanticCohesionGraph.document_id must be non-empty")
        if not isinstance(self.local_edges, tuple):
            raise ValueError("SemanticCohesionGraph.local_edges must be tuple")
        if not isinstance(self.stats, CohesionStats):
            raise ValueError("SemanticCohesionGraph.stats must be CohesionStats")

    def edges_for_node(self, effective_uid: str) -> list[CohesionEdge]:
        """
        Все edges где узел является source или target.

        O(E) — приемлемо так как вызывается per-node в Phase 10,
        а E = O(N × window) — не O(N²).
        """
        return [
            edge for edge in self.local_edges
            if edge.source_uid == effective_uid
            or edge.target_uid == effective_uid
        ]

    def strong_boundaries(self) -> list[CohesionEdge]:
        """
        Все edges которые являются strong boundaries.
        Phase 10 использует для chunk split decisions.
        """
        return [edge for edge in self.local_edges if edge.is_strong_boundary]

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "schema_version": self.schema_version,
            "stats": self.stats.to_dict(),
            "local_edges": [edge.to_dict() for edge in self.local_edges],
        }


__all__ = [
    "CohesionBreakReason",
    "CohesionEdge",
    "CohesionEdgeKind",
    "CohesionSignals",
    "CohesionStats",
    "SemanticCohesionGraph",
]


