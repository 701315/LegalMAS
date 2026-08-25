# src/services/document_layout/reading_order_reconstructor.py

"""
Reading Order Reconstructor Module (Layer 2).

Отвечает за естественную геометрическую реконструкцию порядка чтения атомов:
- Группировка регионов страницы в вертикальные полосы (Bands);
- Поколоночный обход многоколоночных полос (слева направо, сверху вниз);
- Сортировка атомов внутри колонок по (y0, x0);
- Обновление layout_order и привязка region_id к атомам.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.logging import get_logger
from services.document_layout.schemas import (
    CanonicalAtom,
    CanonicalPage,
    PageRegion,
    PageRegionType,
)

logger = get_logger(__name__)


@dataclass(slots=True)
class _RegionBand:
    min_y: float
    max_y: float
    regions: list[PageRegion] = field(default_factory=list)


class ReadingOrderReconstructor:
    """
    Сервис геометрической реконструкции порядка чтения атомов на странице.
    """

    def reconstruct_page_reading_order(
        self,
        page: CanonicalPage,
        regions: list[PageRegion],
    ) -> list[CanonicalAtom]:
        """
        Упорядочивает атомы страницы в естественном порядке чтения.
        """
        atoms_by_id = {atom.element_id: atom for atom in page.atoms}
        if not atoms_by_id or not regions:
            return page.atoms

        logger.info(
            "Reconstructing reading order for page",
            page_number=page.page_number,
            regions_count=len(regions),
            atoms_count=len(page.atoms),
        )

        bands: list[_RegionBand] = []
        sorted_regions = sorted(regions, key=lambda r: (r.bbox[1], r.bbox[0]))

        for region in sorted_regions:
            r_y0, r_y1 = region.bbox[1], region.bbox[3]

            if region.region_type == PageRegionType.COLUMN:
                matched_band = None
                for band in bands:
                    overlap_y0 = max(band.min_y, r_y0)
                    overlap_y1 = min(band.max_y, r_y1)
                    if (overlap_y1 - overlap_y0) > 20.0:
                        matched_band = band
                        break

                if matched_band:
                    matched_band.regions.append(region)
                    matched_band.min_y = min(matched_band.min_y, r_y0)
                    matched_band.max_y = max(matched_band.max_y, r_y1)
                else:
                    bands.append(_RegionBand(min_y=r_y0, max_y=r_y1, regions=[region]))
            else:
                bands.append(_RegionBand(min_y=r_y0, max_y=r_y1, regions=[region]))

        bands.sort(key=lambda b: b.min_y)

        ordered_atoms: list[CanonicalAtom] = []
        global_order = 0

        for band in bands:
            band_regions = sorted(band.regions, key=lambda r: r.bbox[0])

            for region in band_regions:
                region_atoms = [
                    atoms_by_id[aid]
                    for aid in region.atom_ids
                    if aid in atoms_by_id
                ]

                region_atoms.sort(
                    key=lambda a: (
                        a.bbox[1] if a.bbox else 0.0,
                        a.bbox[0] if a.bbox else 0.0,
                    )
                )

                for atom in region_atoms:
                    updated_atom = atom.model_copy(
                        update={
                            "layout_order": global_order,
                            "parent_ref": region.region_id,
                        }
                    )
                    ordered_atoms.append(updated_atom)
                    global_order += 1

        ordered_ids = {a.element_id for a in ordered_atoms}
        unassigned_atoms = [a for a in page.atoms if a.element_id not in ordered_ids]

        if unassigned_atoms:
            unassigned_atoms.sort(
                key=lambda a: (
                    a.bbox[1] if a.bbox else 0.0,
                    a.bbox[0] if a.bbox else 0.0,
                )
            )
            for atom in unassigned_atoms:
                updated_atom = atom.model_copy(update={"layout_order": global_order})
                ordered_atoms.append(updated_atom)
                global_order += 1

        logger.info(
            "Reading order reconstruction completed",
            page_number=page.page_number,
            ordered_atoms_count=len(ordered_atoms),
        )

        return ordered_atoms
