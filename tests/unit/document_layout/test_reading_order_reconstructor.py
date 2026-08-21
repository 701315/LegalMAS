"""Unit tests для Reading Order Reconstructor (Layer 2)."""

import pytest
from services.document_layout.reading_order_reconstructor import ReadingOrderReconstructor
from services.document_layout.schemas import (
    CanonicalAtom,
    CanonicalAtomSource,
    CanonicalPage,
    PageRegion,
    PageRegionType,
)


class TestReadingOrderReconstructor:
    def test_reconstructs_two_columns_column_first(self):
        """
        Критический тест:
        В 2-колоночном файле заголовок (FULL_WIDTH) должен идти первым,
        затем ВСЯ левая колонка сверху вниз, затем ВСЯ правая колонка сверху вниз!
        """
        # Заголовок
        atom_header = CanonicalAtom(
            element_id="atom:header",
            page=1,
            bbox=(50.0, 50.0, 550.0, 80.0),
            source_reading_order=0,
            layout_order=0,
            text="ДОГОВОР КУПЛИ-ПРОДАЖИ",
            label="title",
            source=CanonicalAtomSource(docling_collection="texts"),
        )

        # Левая колонка (X: 50-250)
        atom_left_1 = CanonicalAtom(
            element_id="atom:left_1",
            page=1,
            bbox=(50.0, 100.0, 250.0, 150.0),
            source_reading_order=1,
            layout_order=1,
            text="Left paragraph 1",
            label="paragraph",
            source=CanonicalAtomSource(docling_collection="texts"),
        )
        atom_left_2 = CanonicalAtom(
            element_id="atom:left_2",
            page=1,
            bbox=(50.0, 160.0, 250.0, 210.0),
            source_reading_order=3,  # B Docling шёл горизонтально
            layout_order=3,
            text="Left paragraph 2",
            label="paragraph",
            source=CanonicalAtomSource(docling_collection="texts"),
        )

        # Правая колонка (X: 300-500)
        atom_right_1 = CanonicalAtom(
            element_id="atom:right_1",
            page=1,
            bbox=(300.0, 100.0, 500.0, 150.0),
            source_reading_order=2,  # B Docling шёл между left_1 и left_2!
            layout_order=2,
            text="Right paragraph 1",
            label="paragraph",
            source=CanonicalAtomSource(docling_collection="texts"),
        )

        page = CanonicalPage(
            page_number=1,
            width=600.0,
            height=800.0,
            atoms=[atom_header, atom_left_1, atom_right_1, atom_left_2],
        )

        regions = [
            PageRegion(
                region_id="page_1_fw_0",
                region_type=PageRegionType.FULL_WIDTH,
                page=1,
                bbox=(50.0, 50.0, 550.0, 80.0),
                atom_ids=["atom:header"],
            ),
            PageRegion(
                region_id="page_1_col_0",
                region_type=PageRegionType.COLUMN,
                page=1,
                bbox=(50.0, 100.0, 250.0, 600.0),
                column_index=0,
                atom_ids=["atom:left_1", "atom:left_2"],
            ),
            PageRegion(
                region_id="page_1_col_1",
                region_type=PageRegionType.COLUMN,
                page=1,
                bbox=(300.0, 100.0, 500.0, 600.0),
                column_index=1,
                atom_ids=["atom:right_1"],
            ),
        ]

        reconstructor = ReadingOrderReconstructor()
        ordered_atoms = reconstructor.reconstruct_page_reading_order(page, regions)

        ordered_ids = [a.element_id for a in ordered_atoms]

        # Порядок должен стать: header -> left_1 -> left_2 -> right_1
        assert ordered_ids == ["atom:header", "atom:left_1", "atom:left_2", "atom:right_1"]
        assert ordered_atoms[1].layout_order == 1
        assert ordered_atoms[2].layout_order == 2
        assert ordered_atoms[3].layout_order == 3
