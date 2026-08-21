"""
Parallel Alignment Module (Layer 5).

Отвечает за выравнивание параллельных структурных узлов противоположных языков:
- Geometry-first matching (по совпадению marker + hierarchy_path + Y-overlap bbox >= 0.6);
- Monotonic Sequence Matching fallback для последовательных блоков без перекрытия;
- Формирование реестра выровненных узлов (aligned_opposite_node_ids);
- Гарантия отсутствия дублирующих marker-only элементов при наличии целевой пары.
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
    """
    Вычисляет коэффициент относительного вертикального перекрытия Y двух bbox (0.0 - 1.0).
    """
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
    alignment_method: str  # "geometric_y_overlap" | "monotonic_sequence"


@dataclass(slots=True)
class AlignmentResult:
    aligned_pairs: list[AlignedPair] = field(default_factory=list)
    aligned_opposite_node_ids: set[str] = field(default_factory=set)
    unaligned_opposite_node_ids: set[str] = field(default_factory=set)


class ParallelAligner:
    """
    Сервис выравнивания параллельных многоязычных структурных узлов.
    """

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
            "Starting parallel node alignment",
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

        # ─── PASS 1: Geometry-First Alignment (Y-overlap + Marker + Hierarchy) ──
        aligned_opposite_ids: set[str] = set()

        for opp_node in opposite_nodes:
            if not opp_node.marker:
                continue

            best_target_node = None
            best_y_overlap = 0.0

            for t_node in target_nodes:
                if t_node.page != opp_node.page:
                    continue

                if t_node.marker == opp_node.marker:
                    # Проверяем совместимость hierarchy_path (если включено в конфиге)
                    if layout_config.marker_alignment_require_hierarchy_match:
                        if t_node.hierarchy_path != opp_node.hierarchy_path:
                            continue

                    y_overlap = _calculate_y_overlap(opp_node.bbox, t_node.bbox)
                    if y_overlap >= layout_config.marker_alignment_y_overlap_threshold:
                        if y_overlap > best_y_overlap:
                            best_y_overlap = y_overlap
                            best_target_node = t_node

            if best_target_node:
                pair = AlignedPair(
                    target_node_id=best_target_node.node_id,
                    opposite_node_id=opp_node.node_id,
                    marker=opp_node.marker,
                    confidence=round(best_y_overlap, 3),
                    alignment_method="geometric_y_overlap",
                )
                result.aligned_pairs.append(pair)
                aligned_opposite_ids.add(opp_node.node_id)

        # ─── PASS 2: Monotonic Sequence Fallback ──────────────────────────────
        unaligned_opp_nodes = [n for n in opposite_nodes if n.node_id not in aligned_opposite_ids]

        if unaligned_opp_nodes:
            for opp_node in unaligned_opp_nodes:
                if not opp_node.marker:
                    continue

                # Ищем узел целевого языка с таким же маркером и иерархией в пределах документа
                for t_node in target_nodes:
                    if (
                        t_node.marker == opp_node.marker
                        and t_node.hierarchy_path == opp_node.hierarchy_path
                    ):
                        pair = AlignedPair(
                            target_node_id=t_node.node_id,
                            opposite_node_id=opp_node.node_id,
                            marker=opp_node.marker,
                            confidence=0.75,
                            alignment_method="monotonic_sequence",
                        )
                        result.aligned_pairs.append(pair)
                        aligned_opposite_ids.add(opp_node.node_id)
                        break

        result.aligned_opposite_node_ids = aligned_opposite_ids
        result.unaligned_opposite_node_ids = {
            n.node_id for n in opposite_nodes if n.node_id not in aligned_opposite_ids
        }

        logger.info(
            "Parallel node alignment completed",
            total_opposite_nodes=len(opposite_nodes),
            aligned_opposite_nodes=len(result.aligned_opposite_node_ids),
            unaligned_opposite_nodes=len(result.unaligned_opposite_node_ids),
        )

        return result
