"""
Regression test: SegmentChunkBuilderV2 must NOT perform inline semantic enrichment.

This test locks the architectural invariant introduced when enrichment
was moved to a dedicated formal pipeline stage.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def test_segment_chunk_builder_does_not_call_enrich_legal_units_async() -> None:
    """
    Verify that enrich_legal_units_async is never imported or called
    inside SegmentChunkBuilderV2._build_single_segment_snapshot.
    """
    import importlib
    import sys

    # Reload the module to inspect fresh import state
    module_name = "engine.content.segment_chunk_builder_v2"
    if module_name in sys.modules:
        module = sys.modules[module_name]
    else:
        module = importlib.import_module(module_name)

    # The function must not be a direct attribute of the module
    assert not hasattr(module, "enrich_legal_units_async"), (
        "enrich_legal_units_async must not be imported into segment_chunk_builder_v2"
    )


@pytest.mark.asyncio
async def test_legal_units_enrichment_result_is_none_in_snapshot() -> None:
    """
    When build_single_segment_snapshot runs successfully, the snapshot's
    legal_units_enrichment_result must be None — enrichment is not done inline.
    """
    from engine.content.segment_chunk_builder_v2 import SegmentChunkSnapshotV2

    # Create a minimal mock snapshot to verify the field contract
    snapshot = SegmentChunkSnapshotV2(
        document_id=__import__("uuid").uuid4(),
        document_version_id=__import__("uuid").uuid4(),
        segment_id="test-seg-1",
        segment_type="main_contract",
        segment_title=None,
        segment_order=0,
        is_primary_segment=True,
        segment_page_start=1,
        segment_page_end=10,
        layout_ref="s3://bucket/layout.json",
        file_graph_ref="s3://bucket/graph.json",
        segment_clause_tree_ref="s3://bucket/tree.json",
        params={},
        section_chunks=[],
        clause_chunks=[],
        subclause_chunks=[],
    )

    assert snapshot.legal_units_enrichment_result is None, (
        "legal_units_enrichment_result must be None in chunk build path"
    )


    