# src/services/document_layout/parallel_alignment.py

"""
Parallel Alignment Module (Layer 5 v3.2 Final).

Двухфакторный метод выравнивания параллельных структурных узлов:
1. Geometric Hypothesis (Y-Overlap): для параллельных колонок и таблиц.
   Маркеры переносятся даже при отсутствии на одной из сторон.
2. Monotonic Hypothesis: для последовательного перевода (интерливинга).

Полностью универсален: не зависит от языка, типа документов или конкретных слов.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.logging import get_logger
from services.document_layout.config import layout_config
from services.document_layout.schemas import StructuralNodeCandidate

logger = get_logger(__name__)


def _calculate_y_overlap(
    bbox1: tuple[float, float, float, float] | None,
    bbox2: tuple[float, float, float, float] | None,
) -> float:
    if not bbox1 or not bbox2:
        return 0.0

    _, y0_1, _, y1_1 = bbox1
    _, y0_2, _, y1_2 = bbox2

    overlap_y0 = max(y0_1, y0_2)
    overlap_y1 = min(y1_1, y1_2)
    overlap_h = max(0.0, overlap_y1 - overlap_y0)

    if overlap_h <= 0.0:
        return 0.0

    h1 = max(0.1, y1_1 - y0_1)
    h2 = max(0.1, y1_2 - y0_2)

    return overlap_h / min(h1, h2)


@dataclass(slots=True)
class AlignedPair:
    target_node_id: str
    opposite_node_id: str
    marker: str | None
    confidence: float
    alignment_method: str


@dataclass(slots=True)
class AlignmentResult:
    aligned_pairs: list[AlignedPair] = field(default_factory=list)
    aligned_opposite_node_ids: set[str] = field(default_factory=set)
    unaligned_opposite_node_ids: set[str] = field(default_factory=set)


class ParallelAligner:
    def align_nodes(
        self,
        nodes: list[StructuralNodeCandidate],
        target_language: str,
    ) -> AlignmentResult:
        target_lang = target_language.lower().strip()
        result = AlignmentResult()

        if not nodes:
            return result

        logger.info(
            "Starting parallel node alignment (Dual-Hypothesis v3.2)",
            target_language=target_lang,
            total_nodes=len(nodes),
        )

        target_nodes: list[StructuralNodeCandidate] = []
        opposite_nodes: list[StructuralNodeCandidate] = []

        for node in nodes:
            if node.language in (target_lang, "shared", "mixed"):
                target_nodes.append(node)
            else:
                opposite_nodes.append(node)

        if not opposite_nodes or not target_nodes:
            result.unaligned_opposite_node_ids = {n.node_id for n in opposite_nodes}
            return result

        aligned_opposite_ids: set[str] = set()
        aligned_target_ids: set[str] = set()

        # ─── HYPOTHESIS 1A: Exact marker match + Y-overlap ────────────────
        for opp_node in opposite_nodes:
            if not opp_node.marker:
                continue

            best_target = None
            best_overlap = 0.0

            for t_node in target_nodes:
                if t_node.page != opp_node.page or t_node.node_id in aligned_target_ids:
                    continue
                if t_node.marker == opp_node.marker:
                    y_overlap = _calculate_y_overlap(opp_node.bbox, t_node.bbox)
                    if y_overlap >= layout_config.marker_alignment_y_overlap_threshold:
                        if y_overlap > best_overlap:
                            best_overlap = y_overlap
                            best_target = t_node

            if best_target:
                result.aligned_pairs.append(AlignedPair(
                    target_node_id=best_target.node_id,
                    opposite_node_id=opp_node.node_id,
                    marker=opp_node.marker,
                    confidence=round(best_overlap, 3),
                    alignment_method="geometric_exact_marker",
                ))
                aligned_opposite_ids.add(opp_node.node_id)
                aligned_target_ids.add(best_target.node_id)

        # ─── HYPOTHESIS 1B: Y-overlap WITHOUT marker match ────────────────
        # Перенос маркеров с одной колонки на другую при их отсутствии
        for opp_node in opposite_nodes:
            if opp_node.node_id in aligned_opposite_ids:
                continue

            best_target = None
            best_overlap = 0.0

            for t_node in target_nodes:
                if t_node.page != opp_node.page or t_node.node_id in aligned_target_ids:
                    continue
                y_overlap = _calculate_y_overlap(opp_node.bbox, t_node.bbox)
                if y_overlap >= layout_config.marker_alignment_y_overlap_threshold:
                    if y_overlap > best_overlap:
                        best_overlap = y_overlap
                        best_target = t_node

            if best_target:
                effective_marker = opp_node.marker or best_target.marker
                result.aligned_pairs.append(AlignedPair(
                    target_node_id=best_target.node_id,
                    opposite_node_id=opp_node.node_id,
                    marker=effective_marker,
                    confidence=round(best_overlap, 3) * 0.9,
                    alignment_method="geometric_marker_propagation",
                ))
                aligned_opposite_ids.add(opp_node.node_id)
                aligned_target_ids.add(best_target.node_id)

        # ─── HYPOTHESIS 2: Monotonic sequence (shifted/sequential) ────────
        pages_in_doc = sorted(list({n.page for n in nodes}))

        for page_no in pages_in_doc:
            page_opp = [
                n for n in opposite_nodes
                if n.page == page_no and n.node_id not in aligned_opposite_ids
            ]
            page_target = [
                n for n in target_nodes
                if n.page == page_no and n.node_id not in aligned_target_ids
            ]

            if not page_opp or not page_target:
                continue

            # Monotonic matching by marker
            opp_with_markers = [n for n in page_opp if n.marker]
            t_with_markers = [n for n in page_target if n.marker]

            if opp_with_markers and len(opp_with_markers) == len(t_with_markers):
                for opp_m, t_m in zip(opp_with_markers, t_with_markers):
                    if opp_m.marker == t_m.marker:
                        result.aligned_pairs.append(AlignedPair(
                            target_node_id=t_m.node_id,
                            opposite_node_id=opp_m.node_id,
                            marker=opp_m.marker,
                            confidence=0.80,
                            alignment_method="monotonic_marker_match",
                        ))
                        aligned_opposite_ids.add(opp_m.node_id)
                        aligned_target_ids.add(t_m.node_id)

            # Sequential 1-to-1 matching for remaining
            remaining_opp = [n for n in page_opp if n.node_id not in aligned_opposite_ids]
            remaining_target = [n for n in page_target if n.node_id not in aligned_target_ids]

            if len(remaining_opp) == len(remaining_target):
                for opp_n, t_n in zip(remaining_opp, remaining_target):
                    effective_marker = opp_n.marker or t_n.marker
                    result.aligned_pairs.append(AlignedPair(
                        target_node_id=t_n.node_id,
                        opposite_node_id=opp_n.node_id,
                        marker=effective_marker,
                        confidence=0.70,
                        alignment_method="monotonic_sequence_order",
                    ))
                    aligned_opposite_ids.add(opp_n.node_id)
                    aligned_target_ids.add(t_n.node_id)

        result.aligned_opposite_node_ids = aligned_opposite_ids
        result.unaligned_opposite_node_ids = {
            n.node_id for n in opposite_nodes if n.node_id not in aligned_opposite_ids
        }

        logger.info(
            "Parallel node alignment completed",
            total_opposite=len(opposite_nodes),
            aligned=len(result.aligned_opposite_node_ids),
            unaligned=len(result.unaligned_opposite_node_ids),
        )

        return result
