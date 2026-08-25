# src/services/document_layout/structural_node_builder.py

"""
Structural Node Builder Module (Layer 4).

Отвечает за построение составных структурных узлов (StructuralNodeCandidate):
- Группировка оторванных маркеров с их текстом внутри одного региона;
- Вычисление цепочки родительской иерархии (hierarchy_path, например ['1', '1.1']);
- Объединение bounding box входящих атомов;
- Запрет ранней генерации marker-only заглушек до параллельного выравнивания.
"""

from __future__ import annotations

from typing import Any

from core.logging import get_logger
from services.document_layout.schemas import (
    CanonicalAtom,
    PageRegion,
    StructuralNodeCandidate,
    ElementStyle,
)

logger = get_logger(__name__)


def _merge_bboxes(
    bboxes: list[tuple[float, float, float, float] | None],
) -> tuple[float, float, float, float] | None:
    """
    Объединяет список Bounding Boxes в один общий охватывающий Bounding Box.
    """
    valid_boxes = [b for b in bboxes if b is not None]
    if not valid_boxes:
        return None

    min_x0 = min(b[0] for b in valid_boxes)
    min_y0 = min(b[1] for b in valid_boxes)
    max_x1 = max(b[2] for b in valid_boxes)
    max_y1 = max(b[3] for b in valid_boxes)

    return (round(min_x0, 2), round(min_y0, 2), round(max_x1, 2), round(max_y1, 2))


class StructuralNodeBuilder:
    """
    Сервис построения составных структурных узлов документа.
    """

    def build_page_nodes(
        self,
        atoms: list[CanonicalAtom],
        regions: list[PageRegion],
    ) -> list[StructuralNodeCandidate]:
        """
        Формирует список StructuralNodeCandidate из упорядоченных атомов страницы.
        """
        if not atoms:
            return []

        # Карта привязки атома к region_id
        atom_region_map: dict[str, str] = {}
        for region in regions:
            for aid in region.atom_ids:
                atom_region_map[aid] = region.region_id

        nodes: list[StructuralNodeCandidate] = []
        hierarchy_stack: list[str] = []

        i = 0
        node_counter = 0

        while i < len(atoms):
            curr_atom = atoms[i]
            region_id = atom_region_map.get(curr_atom.element_id)

            # Отслеживаем иерархию нумерации
            if curr_atom.marker:
                m = curr_atom.marker
                # Если маркер вида "1.", "2.", "1.1" -> обновляем hierarchy_stack
                if m.count(".") == 0 or m.endswith("."):
                    hierarchy_stack = [m.rstrip(".")]
                elif m.count(".") >= 1:
                    parts = m.split(".")
                    hierarchy_stack = parts[: len(parts)]

            current_hierarchy = list(hierarchy_stack)

            # Проверяем возможность объединения маркера с следующим текстом внутри того же региона
            if (
                curr_atom.is_marker_only
                and i + 1 < len(atoms)
                and atom_region_map.get(atoms[i + 1].element_id) == region_id
                and not atoms[i + 1].is_marker_only
            ):
                next_atom = atoms[i + 1]
                merged_text = f"{curr_atom.text} {next_atom.text}".strip()
                if not merged_text and curr_atom.marker:
                    merged_text = next_atom.text

                combined_bbox = _merge_bboxes([curr_atom.bbox, next_atom.bbox])

                merged_metadata = dict(getattr(curr_atom, "metadata", {}) or {})
                merged_metadata.update(dict(getattr(next_atom, "metadata", {}) or {}))

                node = StructuralNodeCandidate(
                    node_id=f"node:{curr_atom.page}:{node_counter:04d}",
                    marker=curr_atom.marker or next_atom.marker,
                    bbox=combined_bbox,
                    page=curr_atom.page,
                    region_id=region_id,
                    hierarchy_path=current_hierarchy,
                    source_atom_ids=[curr_atom.element_id, next_atom.element_id],
                    language=next_atom.language,
                    text=merged_text,
                    confidence=min(curr_atom.language_confidence, next_atom.language_confidence),
                    label=next_atom.label,
                    metadata=merged_metadata,
                )
                nodes.append(node)
                node_counter += 1
                i += 2  # Пропускаем два объединённых атома
                continue

            # Обычный автономный узел
            # Наследуем визуальные признаки от первого атома узла
            first_atom_style = curr_atom.style
            single_metadata = dict(getattr(curr_atom, "metadata", {}) or {})

            node = StructuralNodeCandidate(
                node_id=f"node:{curr_atom.page}:{node_counter:04d}",
                marker=curr_atom.marker,
                bbox=curr_atom.bbox,
                page=curr_atom.page,
                region_id=region_id,
                hierarchy_path=current_hierarchy,
                source_atom_ids=[curr_atom.element_id],
                language=curr_atom.language,
                text=curr_atom.text,
                confidence=curr_atom.language_confidence,
                label=curr_atom.label,
                font_size=first_atom_style.font_size if first_atom_style else None,
                bold=first_atom_style.bold if first_atom_style else False,
                style=first_atom_style,
                metadata=single_metadata,
            )
            nodes.append(node)
            node_counter += 1
            i += 1

        logger.info(
            "Structural nodes construction completed",
            page=atoms[0].page if atoms else 1,
            nodes_count=len(nodes),
        )

        return nodes
