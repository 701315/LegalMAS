# src/services/structure/coherence/_types.py

"""
Phase 13.7 — Cross-Segment Coherence types.

CoherenceLink: связь между last heading сегмента N и orphan root сегмента N+1.
Не мутирует деревья — sidecar артефакт поверх FileStructureResult.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CoherenceLink:
    """
    Семантическая связь на границе двух смежных сегментов.

    source_*: последний deep heading в сегменте N
    target_*: orphan root в сегменте N+1
    confidence: 1.0 при level_delta=1 и page_distance=0, снижается линейно
    """

    source_segment_id: str
    target_segment_id: str
    source_node_uid: str
    target_node_uid: str
    source_level: int
    target_level: int
    page_distance: int
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_segment_id": self.source_segment_id,
            "target_segment_id": self.target_segment_id,
            "source_node_uid": self.source_node_uid,
            "target_node_uid": self.target_node_uid,
            "source_level": self.source_level,
            "target_level": self.target_level,
            "page_distance": self.page_distance,
            "confidence": self.confidence,
        }


@dataclass
class CrossSegmentCoherenceResult:
    """
    Итог coherence pass по всем смежным парам сегментов документа.
    Failure-isolated — если resolver упал, pipeline получает пустой результат.
    """

    links: list[CoherenceLink] = field(default_factory=list)
    segments_analyzed: int = 0
    links_found: int = 0
    resolver_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "segments_analyzed": self.segments_analyzed,
            "links_found": self.links_found,
            "resolver_error": self.resolver_error,
            "links": [link.to_dict() for link in self.links],
        }
    

