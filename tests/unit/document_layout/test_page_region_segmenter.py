"""Unit tests для Page Region Segmenter (Layer 1)."""

import pytest
from services.document_layout.page_region_segmenter import PageRegionSegmenter
from services.document_layout.schemas import (
    CanonicalAtom,
    CanonicalAtomSource,
    CanonicalPage,
    PageRegionType,
)


class TestPageRegionSegmenter:
    def test_single_column_page_creates_single_region(self):
        atom1 = CanonicalAtom(
            element_id="atom:001",
            page=1,
            bbox=(50.0, 50.0, 500.0, 200.0),
            source_reading_order=1,
            layout_order=1,
            text="Заголовок документа",
            label="title",
            source=CanonicalAtomSource(docling_collection="texts"),
        )
        atom2 = CanonicalAtom(
            element_id="atom:002",
            page=1,
            bbox=(50.0, 220.0, 500.0, 700.0),
            source_reading_order=2,
            layout_order=2,
            text="Полноширинный абзац текста на всю страницу.",
            label="paragraph",
            source=CanonicalAtomSource(docling_collection="texts"),
        )

        page = CanonicalPage(page_number=1, width=600.0, height=800.0, atoms=[atom1, atom2])
        segmenter = PageRegionSegmenter()
        regions = segmenter.segment_page(page)

        assert len(regions) >= 1
        assert "atom:001" in regions[0].atom_ids
        assert "atom:002" in regions[0].atom_ids or "atom:002" in regions[1].atom_ids

    def test_two_columns_with_height_gating(self):
        """Проверяет детекцию 2 высоких колонок (высота >= 25% высоты контента)."""
        # Полноширинный заголовок
        atom_header = CanonicalAtom(
            element_id="atom:header",
            page=1,
            bbox=(50.0, 50.0, 550.0, 80.0),
            source_reading_order=0,
            layout_order=0,
            text="ДОГОВОР КУПЛИ-ПРОДАЖИ / AGREEMENT",
            label="title",
            source=CanonicalAtomSource(docling_collection="texts"),
        )

        # Левая колонка (EN): Y в диапазоне 100-600 (высота 500px >= 25% от 800px)
        atom_left = CanonicalAtom(
            element_id="atom:left_col",
            page=1,
            bbox=(50.0, 100.0, 270.0, 600.0),
            source_reading_order=1,
            layout_order=1,
            text="English text in left column",
            label="paragraph",
            source=CanonicalAtomSource(docling_collection="texts"),
        )

        # Правая колонка (RU): Y в диапазоне 100-600
        atom_right = CanonicalAtom(
            element_id="atom:right_col",
            page=1,
            bbox=(300.0, 100.0, 520.0, 600.0),
            source_reading_order=2,
            layout_order=2,
            text="Русский текст в правой колонке",
            label="paragraph",
            source=CanonicalAtomSource(docling_collection="texts"),
        )

        page = CanonicalPage(
            page_number=1,
            width=600.0,
            height=800.0,
            atoms=[atom_header, atom_left, atom_right],
        )

        segmenter = PageRegionSegmenter()
        regions = segmenter.segment_page(page)

        # Должно быть создано 3 региона: 1 FULL_WIDTH + 2 COLUMN
        region_types = [r.region_type for r in regions]
        assert PageRegionType.FULL_WIDTH in region_types
        assert PageRegionType.COLUMN in region_types

        column_regions = [r for r in regions if r.region_type == PageRegionType.COLUMN]
        assert len(column_regions) == 2
        assert column_regions[0].column_index == 0
        assert column_regions[1].column_index == 1

    def test_short_grid_block_excluded_from_columns(self):
        """Проверяет height-gating: короткий блок (< 25% высоты) определяется как GRID_BLOCK."""
        atom_short = CanonicalAtom(
            element_id="atom:short_grid",
            page=1,
            bbox=(50.0, 50.0, 200.0, 80.0),  # высота 30px (< 25% от 800px)
            source_reading_order=1,
            layout_order=1,
            text="Короткий титул сторон",
            label="paragraph",
            source=CanonicalAtomSource(docling_collection="texts"),
        )

        page = CanonicalPage(page_number=1, width=600.0, height=800.0, atoms=[atom_short])
        segmenter = PageRegionSegmenter()
        regions = segmenter.segment_page(page)

        assert len(regions) == 1
        assert regions[0].region_type == PageRegionType.GRID_BLOCK
