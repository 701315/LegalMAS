"""Unit tests для Parallel Alignment (Layer 5)."""

import pytest
from services.document_layout.parallel_alignment import ParallelAligner, _calculate_y_overlap
from services.document_layout.schemas import StructuralNodeCandidate


class TestYOverlapCalculation:
    def test_identical_y_boxes_overlap_one(self):
        b1 = (10.0, 100.0, 200.0, 150.0)
        b2 = (250.0, 100.0, 450.0, 150.0)
        assert _calculate_y_overlap(b1, b2) == 1.0

    def test_non_overlapping_y_boxes_overlap_zero(self):
        b1 = (10.0, 100.0, 200.0, 150.0)
        b2 = (10.0, 200.0, 200.0, 250.0)
        assert _calculate_y_overlap(b1, b2) == 0.0


class TestParallelAligner:
    def test_geometric_alignment_matches_parallel_columns(self):
        node_ru = StructuralNodeCandidate(
            node_id="node:1:0001",
            marker="2.2",
            bbox=(300.0, 100.0, 500.0, 150.0),
            page=1,
            region_id="col_1",
            hierarchy_path=["2", "2"],
            source_atom_ids=["atom:001"],
            language="ru",
            text="2.2 Покупатель обязуется...",
        )

        node_en = StructuralNodeCandidate(
            node_id="node:1:0002",
            marker="2.2",
            bbox=(50.0, 100.0, 250.0, 150.0),  # Параллельно по Y
            page=1,
            region_id="col_0",
            hierarchy_path=["2", "2"],
            source_atom_ids=["atom:002"],
            language="en",
            text="2.2 Buyer undertakes...",
        )

        aligner = ParallelAligner()
        res = aligner.align_nodes([node_ru, node_en], target_language="ru")

        assert len(res.aligned_pairs) == 1
        assert res.aligned_pairs[0].opposite_node_id == "node:1:0002"
        assert res.aligned_pairs[0].target_node_id == "node:1:0001"
        assert res.aligned_pairs[0].alignment_method == "geometric_y_overlap"
        assert "node:1:0002" in res.aligned_opposite_node_ids
        assert len(res.unaligned_opposite_node_ids) == 0

    def test_unmatched_opposite_node_marked_as_unaligned(self):
        """Если пункта 3.2 на русском языке нет, английский 3.2 остается unaligned (для сохранения как marker-only)."""
        node_ru = StructuralNodeCandidate(
            node_id="node:1:0001",
            marker="2.2",
            bbox=(300.0, 100.0, 500.0, 150.0),
            page=1,
            region_id="col_1",
            hierarchy_path=["2", "2"],
            source_atom_ids=["atom:001"],
            language="ru",
            text="2.2 Текст пункта",
        )

        node_en_missing = StructuralNodeCandidate(
            node_id="node:1:0003",
            marker="3.2",
            bbox=(50.0, 300.0, 250.0, 350.0),
            page=1,
            region_id="col_0",
            hierarchy_path=["3", "2"],
            source_atom_ids=["atom:003"],
            language="en",
            text="3.2 English only clause",
        )

        aligner = ParallelAligner()
        res = aligner.align_nodes([node_ru, node_en_missing], target_language="ru")

        assert len(res.aligned_pairs) == 0
        assert "node:1:0003" in res.unaligned_opposite_node_ids
