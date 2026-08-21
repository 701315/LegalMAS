"""Unit tests для Structural Node Builder (Layer 4)."""

import pytest
from services.document_layout.schemas import (
    CanonicalAtom,
    CanonicalAtomSource,
    PageRegion,
    PageRegionType,
)
from services.document_layout.structural_node_builder import (
    StructuralNodeBuilder,
    _merge_bboxes,
)


class TestBboxMerger:
    def test_merge_two_bboxes(self):
        b1 = (10.0, 20.0, 100.0, 40.0)
        b2 = (10.0, 45.0, 120.0, 60.0)
        merged = _merge_bboxes([b1, b2])
        assert merged == (10.0, 20.0, 120.0, 60.0)

    def test_merge_with_none_returns_valid(self):
        b1 = (10.0, 20.0, 100.0, 40.0)
        assert _merge_bboxes([b1, None]) == (10.0, 20.0, 100.0, 40.0)


class TestStructuralNodeBuilder:
    def test_merges_standalone_marker_with_following_text_in_same_region(self):
        marker_atom = CanonicalAtom(
            element_id="atom:001",
            page=1,
            bbox=(50.0, 100.0, 70.0, 120.0),
            source_reading_order=1,
            layout_order=1,
            text="1.1",
            marker="1.1",
            is_marker_only=True,
            label="list_item",
            language="shared",
            source=CanonicalAtomSource(docling_collection="texts"),
        )

        text_atom = CanonicalAtom(
            element_id="atom:002",
            page=1,
            bbox=(75.0, 100.0, 250.0, 120.0),
            source_reading_order=2,
            layout_order=2,
            text="Предмет настоящего Договора",
            label="paragraph",
            language="ru",
            source=CanonicalAtomSource(docling_collection="texts"),
        )

        region = PageRegion(
            region_id="page_1_col_0",
            region_type=PageRegionType.COLUMN,
            page=1,
            bbox=(50.0, 100.0, 250.0, 500.0),
            atom_ids=["atom:001", "atom:002"],
        )

        builder = StructuralNodeBuilder()
        nodes = builder.build_page_nodes([marker_atom, text_atom], [region])

        # Должен создаться 1 объединённый узел, а не 2 оторванных атома!
        assert len(nodes) == 1
        node = nodes[0]
        assert node.marker == "1.1"
        assert node.text == "1.1 Предмет настоящего Договора"
        assert node.source_atom_ids == ["atom:001", "atom:002"]
        assert node.hierarchy_path == ["1", "1"]
        assert node.bbox == (50.0, 100.0, 250.0, 120.0)
