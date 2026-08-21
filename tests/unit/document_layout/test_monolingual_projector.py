"""Unit tests для Monolingual Projector (Phase 4 / Layer 8 v3)."""

import pytest
from services.document_layout.monolingual_projector import MonolingualProjector
from services.document_layout.parallel_alignment import ParallelAligner
from services.document_layout.schemas import StructuralNodeCandidate


class TestMonolingualProjector:
    def test_target_language_nodes_projected(self):
        node_ru = StructuralNodeCandidate(
            node_id="node:1:0001",
            marker="1.",
            bbox=(10.0, 10.0, 100.0, 20.0),
            page=1,
            region_id="col_0",
            hierarchy_path=["1"],
            source_atom_ids=["atom:001"],
            language="ru",
            text="1. Текст на русском языке",
        )
        node_en = StructuralNodeCandidate(
            node_id="node:1:0002",
            marker="1.",
            bbox=(200.0, 10.0, 300.0, 20.0),
            page=1,
            region_id="col_1",
            hierarchy_path=["1"],
            source_atom_ids=["atom:002"],
            language="en",
            text="1. English text",
        )

        aligner = ParallelAligner()
        alignment_res = aligner.align_nodes([node_ru, node_en], target_language="ru")

        projector = MonolingualProjector()
        result = projector.project_nodes(
            [node_ru, node_en],
            target_language="ru",
            alignment_result=alignment_res,
        )

        # Благодаря выравниванию (alignment) английский узел с маркером '1.' не создаёт дубликат пустышки!
        assert result.projected_atom_count == 1
        assert result.elements[0].text == "1. Текст на русском языке"
        assert result.elements[0].language == "ru"

    def test_shared_nodes_included(self):
        node_shared = StructuralNodeCandidate(
            node_id="node:1:0003",
            marker=None,
            bbox=(10.0, 10.0, 50.0, 20.0),
            page=1,
            region_id="col_0",
            hierarchy_path=[],
            source_atom_ids=["atom:003"],
            language="shared",
            text="100 000 USD",
        )

        projector = MonolingualProjector()
        result_ru = projector.project_nodes([node_shared], target_language="ru")
        assert result_ru.projected_atom_count == 1
        assert result_ru.elements[0].text == "100 000 USD"
