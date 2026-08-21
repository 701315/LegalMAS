"""
Page Region Segmenter Module (Layer 1).

Отвечает за геометрическое разделение страницы на логические регионы:
- COLUMN (высокие текстовые колонки, height >= 25% от высоты страницы);
- FULL_WIDTH (заголовки, полноширинные параграфы);
- GRID_BLOCK (короткие титульные блоки сторон, блоки подписей).

Применяет height-gating:
- Исключает короткие блоки из колоночной резки, предохраняя их
  от скремблирования порядка чтения.
- Универсален на 100%: не зависит от языка, скрипта или типа документа.
"""

from __future__ import annotations

from typing import Any

from core.logging import get_logger
from services.document_layout.config import layout_config
from services.document_layout.schemas import (
    CanonicalAtom,
    CanonicalPage,
    PageRegion,
    PageRegionType,
)

logger = get_logger(__name__)


def _find_x_columns(
    atoms: list[CanonicalAtom],
    page_width: float,
) -> list[tuple[float, float]]:
    """
    Находит X-интервалы вертикальных колонок на основе пространственного разделения.
    Возвращает список кортежей [(x0_col0, x1_col0), (x0_col1, x1_col1), ...].
    """
    if not atoms:
        return []

    gutter_min_px = page_width * layout_config.column_gutter_min_ratio

    # Собираем все X-интервалы атомов
    x_spans: list[tuple[float, float]] = []
    for atom in atoms:
        if atom.bbox:
            x0, _, x1, _ = atom.bbox
            if x1 > x0:
                x_spans.append((x0, x1))

    if not x_spans:
        return []

    # Сортируем по x0
    x_spans.sort(key=lambda s: s[0])

    # Объединяем перекрывающиеся или близкие X-интервалы
    merged_columns: list[list[float]] = []
    for x0, x1 in x_spans:
        if not merged_columns:
            merged_columns.append([x0, x1])
        else:
            last_col = merged_columns[-1]
            if x0 <= (last_col[1] + gutter_min_px):
                last_col[1] = max(last_col[1], x1)
            else:
                merged_columns.append([x0, x1])

    return [(round(col[0], 2), round(col[1], 2)) for col in merged_columns]


class PageRegionSegmenter:
    """
    Сервис геометрической сегментации страницы на регионы.
    """

    def segment_page(
        self,
        page: CanonicalPage,
    ) -> list[PageRegion]:
        """
        Сегментирует атомы одной страницы на логические регионы.
        """
        atoms = page.atoms
        page_num = page.page_number
        page_width = page.width
        page_height = page.height

        if not atoms:
            return []

        valid_atoms = [a for a in atoms if a.bbox is not None]
        null_bbox_atoms = [a for a in atoms if a.bbox is None]

        if not valid_atoms:
            return [
                PageRegion(
                    region_id=f"page_{page_num}_region_fullwidth_0",
                    region_type=PageRegionType.FULL_WIDTH,
                    page=page_num,
                    bbox=(0.0, 0.0, page_width, page_height),
                    column_index=None,
                    atom_ids=[a.element_id for a in atoms],
                )
            ]

        # УНИВЕРСАЛЬНОЕ РЕШЕНИЕ:
        # Считаем порог колонки от физической высоты страницы, а не от контента!
        height_threshold_px = page_height * layout_config.column_min_height_ratio

        full_width_atoms: list[CanonicalAtom] = []
        column_candidate_atoms: list[CanonicalAtom] = []

        # Разделение по ширине
        for atom in valid_atoms:
            bbox = atom.bbox
            if not bbox:
                continue
            atom_width = bbox[2] - bbox[0]
            if (atom_width / max(page_width, 1.0)) >= 0.65 or atom.label in ("title", "section_header"):
                full_width_atoms.append(atom)
            else:
                column_candidate_atoms.append(atom)

        column_atoms_filtered: list[CanonicalAtom] = []
        grid_block_atoms: list[CanonicalAtom] = []

        # Height-gating (фильтр по высоте)
        if column_candidate_atoms:
            col_min_y = min(a.bbox[1] for a in column_candidate_atoms if a.bbox)
            col_max_y = max(a.bbox[3] for a in column_candidate_atoms if a.bbox)
            col_height = col_max_y - col_min_y

            if col_height >= height_threshold_px:
                column_atoms_filtered = column_candidate_atoms
            else:
                grid_block_atoms = column_candidate_atoms

        x_columns = _find_x_columns(column_atoms_filtered, page_width)

        regions: list[PageRegion] = []
        region_counter = 0

        if full_width_atoms:
            fw_min_y = min(a.bbox[1] for a in full_width_atoms if a.bbox)
            fw_max_y = max(a.bbox[3] for a in full_width_atoms if a.bbox)
            regions.append(
                PageRegion(
                    region_id=f"page_{page_num}_fw_{region_counter}",
                    region_type=PageRegionType.FULL_WIDTH,
                    page=page_num,
                    bbox=(0.0, fw_min_y, page_width, fw_max_y),
                    column_index=None,
                    atom_ids=[a.element_id for a in full_width_atoms],
                )
            )
            region_counter += 1

        if len(x_columns) >= 2:
            for col_idx, (x0_col, x1_col) in enumerate(x_columns):
                col_atoms = [
                    a for a in column_atoms_filtered
                    if a.bbox and (x0_col - 5.0) <= a.bbox[0] <= (x1_col + 5.0)
                ]
                if col_atoms:
                    c_min_y = min(a.bbox[1] for a in col_atoms if a.bbox)
                    c_max_y = max(a.bbox[3] for a in col_atoms if a.bbox)
                    regions.append(
                        PageRegion(
                            region_id=f"page_{page_num}_col_{col_idx}",
                            region_type=PageRegionType.COLUMN,
                            page=page_num,
                            bbox=(x0_col, c_min_y, x1_col, c_max_y),
                            column_index=col_idx,
                            atom_ids=[a.element_id for a in col_atoms],
                        )
                    )
        elif column_atoms_filtered:
            c_min_y = min(a.bbox[1] for a in column_atoms_filtered if a.bbox)
            c_max_y = max(a.bbox[3] for a in column_atoms_filtered if a.bbox)
            regions.append(
                PageRegion(
                    region_id=f"page_{page_num}_col_0",
                    region_type=PageRegionType.COLUMN,
                    page=page_num,
                    bbox=(0.0, c_min_y, page_width, c_max_y),
                    column_index=0,
                    atom_ids=[a.element_id for a in column_atoms_filtered],
                )
            )

        if grid_block_atoms:
            gb_min_y = min(a.bbox[1] for a in grid_block_atoms if a.bbox)
            gb_max_y = max(a.bbox[3] for a in grid_block_atoms if a.bbox)
            regions.append(
                PageRegion(
                    region_id=f"page_{page_num}_grid_{region_counter}",
                    region_type=PageRegionType.GRID_BLOCK,
                    page=page_num,
                    bbox=(0.0, gb_min_y, page_width, gb_max_y),
                    column_index=None,
                    atom_ids=[a.element_id for a in grid_block_atoms],
                )
            )

        if null_bbox_atoms and regions:
            regions[0].atom_ids.extend([a.element_id for a in null_bbox_atoms])

        logger.info(
            "Page region segmentation completed",
            page_number=page_num,
            regions_count=len(regions),
            region_types=[r.region_type.value for r in regions],
        )

        return regions
