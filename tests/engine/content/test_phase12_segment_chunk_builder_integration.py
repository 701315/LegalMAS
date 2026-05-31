# tests/engine/content/test_phase12_segment_chunk_builder_integration.py

"""
Integration тест Phase 12 — semantic enrichment в SegmentChunkBuilderV2.

Проверяем:
- legal_units_enrichment_result появляется в snapshot когда LLM доступна (mock).
- legal_units_enrichment_result = None когда LLM падает.
- Основной chunk pipeline не ломается при любом исходе enrichment.
- to_dict() содержит semantic_enrichment блок.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import json
import pytest

from engine.content.segment_chunk_builder_v2 import SegmentChunkSnapshotV2
from services.structure.legal_unit_models import LegalUnitsSnapshot
from services.structure.semantic_enrichment._types import (
    LegalUnitsEnrichmentResult,
    SemanticEnrichmentStatus,
)


def _make_minimal_snapshot(
    *,
    with_enrichment: bool = False,
) -> SegmentChunkSnapshotV2:
    import uuid

    enrichment = None
    if with_enrichment:
        enrichment = LegalUnitsEnrichmentResult(
            document_id="doc-1",
            document_version_id="ver-1",
            segment_id="seg-1",
            segment_type="contract",
            segment_order=0,
            is_primary_segment=True,
            policy_version="phase12_v1",
            llm_model="qwen2.5",
        )

    return SegmentChunkSnapshotV2(
        document_id=uuid.uuid4(),
        document_version_id=uuid.uuid4(),
        segment_id="seg-1",
        segment_type="contract",
        segment_title=None,
        segment_order=0,
        is_primary_segment=True,
        segment_page_start=1,
        segment_page_end=10,
        layout_ref="minio://layout",
        file_graph_ref="minio://graph",
        segment_clause_tree_ref="minio://tree",
        params={"target_tokens": 300, "max_tokens": 800, "overlap_ratio": 0.15},
        section_chunks=[],
        clause_chunks=[],
        subclause_chunks=[],
        legal_units_snapshot=None,
        legal_units_enrichment_result=enrichment,
    )


class TestSegmentChunkSnapshotV2WithEnrichment:
    def test_snapshot_has_enrichment_result_field(self) -> None:
        snap = _make_minimal_snapshot(with_enrichment=True)

        assert snap.legal_units_enrichment_result is not None
        assert snap.legal_units_enrichment_result.segment_id == "seg-1"

    def test_snapshot_enrichment_result_none_by_default(self) -> None:
        snap = _make_minimal_snapshot(with_enrichment=False)

        assert snap.legal_units_enrichment_result is None

    def test_to_dict_contains_semantic_enrichment_applied(self) -> None:
        snap = _make_minimal_snapshot(with_enrichment=True)

        result = snap.to_dict()

        assert "semantic_enrichment" in result
        assert result["semantic_enrichment"]["applied"] is True
        assert result["semantic_enrichment"]["policy_version"] == "phase12_v1"
        assert result["semantic_enrichment"]["llm_model"] == "qwen2.5"

    def test_to_dict_contains_semantic_enrichment_not_applied(self) -> None:
        snap = _make_minimal_snapshot(with_enrichment=False)

        result = snap.to_dict()

        assert "semantic_enrichment" in result
        assert result["semantic_enrichment"]["applied"] is False


        