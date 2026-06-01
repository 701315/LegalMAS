# tests/services/structure/test_artifacts.py

from __future__ import annotations

import pytest

from services.structure._models._artifacts import (
    CanonicalArtifactRefs,
    CanonicalArtifactRegistry,
    SegmentArtifactRefs,
)


def test_segment_artifact_refs_requires_non_empty_segment_id() -> None:
    with pytest.raises(ValueError, match="segment_id must not be empty"):
        SegmentArtifactRefs(segment_id="")


def test_segment_artifact_refs_flags_reflect_presence_of_refs() -> None:
    seg = SegmentArtifactRefs(
        segment_id="seg-1",
        segment_clause_tree_ref="s3://bucket/segment_1.json",
        segment_chunks_ref="s3://bucket/chunks_1.json",
    )

    assert seg.has_tree is True
    assert seg.has_chunks is True


def test_segment_artifact_refs_flags_are_false_when_refs_missing() -> None:
    seg = SegmentArtifactRefs(segment_id="seg-1")

    assert seg.has_tree is False
    assert seg.has_chunks is False


def test_segment_artifact_refs_to_dict_is_deterministic() -> None:
    seg = SegmentArtifactRefs(
        segment_id="seg-1",
        segment_clause_tree_ref="s3://bucket/segment_1.json",
        segment_chunks_ref="s3://bucket/chunks_1.json",
    )

    assert seg.to_dict() == {
        "segment_id": "seg-1",
        "segment_clause_tree_ref": "s3://bucket/segment_1.json",
        "segment_chunks_ref": "s3://bucket/chunks_1.json",
        "legal_units_ref": None,
        "legal_units_enrichment_ref": None,
        "has_tree": True,
        "has_chunks": True,
        "has_legal_units": False,
        "has_enrichment": False,
    }


def test_canonical_artifact_refs_requires_non_empty_document_id() -> None:
    with pytest.raises(ValueError, match="document_id must not be empty"):
        CanonicalArtifactRefs(document_id="")


def test_canonical_artifact_refs_rejects_duplicate_segment_ids() -> None:
    seg1 = SegmentArtifactRefs(segment_id="seg-1")
    seg2 = SegmentArtifactRefs(segment_id="seg-1")

    with pytest.raises(ValueError, match="duplicate segment_id='seg-1'"):
        CanonicalArtifactRefs(
            document_id="doc-1",
            segment_refs=(seg1, seg2),
        )


def test_canonical_artifact_refs_empty_segments_are_not_ready() -> None:
    refs = CanonicalArtifactRefs(
        document_id="doc-1",
        clause_tree_ref="s3://bucket/clause_tree.json",
        file_graph_ref="s3://bucket/file_graph.json",
        chunks_manifest_v2_ref="s3://bucket/chunks_manifest_v2.json",
        segment_refs=(),
    )

    assert refs.segment_count == 0
    assert refs.all_segments_have_trees is False
    assert refs.all_segments_have_chunks is False
    assert refs.structure_ready is False
    assert refs.retrieval_ready is False
    assert refs.is_complete_for_current_phase is False


def test_canonical_artifact_refs_structure_ready_when_all_structure_refs_exist() -> None:
    seg1 = SegmentArtifactRefs(
        segment_id="seg-1",
        segment_clause_tree_ref="s3://bucket/segment_1.json",
    )
    seg2 = SegmentArtifactRefs(
        segment_id="seg-2",
        segment_clause_tree_ref="s3://bucket/segment_2.json",
    )

    refs = CanonicalArtifactRefs(
        document_id="doc-1",
        clause_tree_ref="s3://bucket/clause_tree.json",
        file_graph_ref="s3://bucket/file_graph.json",
        segment_refs=(seg1, seg2),
    )

    assert refs.has_primary_tree is True
    assert refs.has_file_graph is True
    assert refs.all_segments_have_trees is True
    assert refs.structure_ready is True
    assert refs.retrieval_ready is False
    assert refs.is_complete_for_current_phase is False


def test_canonical_artifact_refs_retrieval_ready_when_all_chunk_refs_exist() -> None:
    seg1 = SegmentArtifactRefs(
        segment_id="seg-1",
        segment_clause_tree_ref="s3://bucket/segment_1.json",
        segment_chunks_ref="s3://bucket/chunks_1.json",
    )
    seg2 = SegmentArtifactRefs(
        segment_id="seg-2",
        segment_clause_tree_ref="s3://bucket/segment_2.json",
        segment_chunks_ref="s3://bucket/chunks_2.json",
    )

    refs = CanonicalArtifactRefs(
        document_id="doc-1",
        clause_tree_ref="s3://bucket/clause_tree.json",
        file_graph_ref="s3://bucket/file_graph.json",
        chunks_manifest_v2_ref="s3://bucket/chunks_manifest_v2.json",
        segment_refs=(seg1, seg2),
    )

    assert refs.all_segments_have_trees is True
    assert refs.all_segments_have_chunks is True
    assert refs.structure_ready is True
    assert refs.retrieval_ready is True
    assert refs.is_complete_for_current_phase is True


def test_canonical_artifact_refs_retrieval_not_ready_when_manifest_missing() -> None:
    seg = SegmentArtifactRefs(
        segment_id="seg-1",
        segment_clause_tree_ref="s3://bucket/segment_1.json",
        segment_chunks_ref="s3://bucket/chunks_1.json",
    )

    refs = CanonicalArtifactRefs(
        document_id="doc-1",
        clause_tree_ref="s3://bucket/clause_tree.json",
        file_graph_ref="s3://bucket/file_graph.json",
        segment_refs=(seg,),
    )

    assert refs.structure_ready is True
    assert refs.has_chunk_manifest is False
    assert refs.retrieval_ready is False


def test_canonical_artifact_refs_retrieval_not_ready_when_some_segment_chunks_missing() -> None:
    seg1 = SegmentArtifactRefs(
        segment_id="seg-1",
        segment_clause_tree_ref="s3://bucket/segment_1.json",
        segment_chunks_ref="s3://bucket/chunks_1.json",
    )
    seg2 = SegmentArtifactRefs(
        segment_id="seg-2",
        segment_clause_tree_ref="s3://bucket/segment_2.json",
        segment_chunks_ref=None,
    )

    refs = CanonicalArtifactRefs(
        document_id="doc-1",
        clause_tree_ref="s3://bucket/clause_tree.json",
        file_graph_ref="s3://bucket/file_graph.json",
        chunks_manifest_v2_ref="s3://bucket/chunks_manifest_v2.json",
        segment_refs=(seg1, seg2),
    )

    assert refs.structure_ready is True
    assert refs.all_segments_have_chunks is False
    assert refs.retrieval_ready is False


def test_canonical_artifact_refs_future_artifact_flags_default_to_false() -> None:
    refs = CanonicalArtifactRefs(document_id="doc-1")

    assert refs.has_cross_ref_graph is False
    assert refs.has_confidence_map is False


def test_canonical_artifact_refs_future_artifact_flags_become_true_when_set() -> None:
    refs = CanonicalArtifactRefs(
        document_id="doc-1",
        cross_ref_graph_ref="s3://bucket/cross_ref_graph.json",
        confidence_map_ref="s3://bucket/confidence_map.json",
    )

    assert refs.has_cross_ref_graph is True
    assert refs.has_confidence_map is True


def test_canonical_artifact_refs_to_dict_contains_expected_shape() -> None:
    seg = SegmentArtifactRefs(
        segment_id="seg-1",
        segment_clause_tree_ref="s3://bucket/segment_1.json",
        segment_chunks_ref="s3://bucket/chunks_1.json",
    )

    refs = CanonicalArtifactRefs(
        document_id="doc-1",
        clause_tree_ref="s3://bucket/clause_tree.json",
        file_graph_ref="s3://bucket/file_graph.json",
        chunks_manifest_v2_ref="s3://bucket/chunks_manifest_v2.json",
        cross_ref_graph_ref="s3://bucket/cross_ref_graph.json",
        confidence_map_ref="s3://bucket/confidence_map.json",
        segment_refs=(seg,),
    )

    assert refs.to_dict() == {
        "document_id": "doc-1",
        "clause_tree_ref": "s3://bucket/clause_tree.json",
        "file_graph_ref": "s3://bucket/file_graph.json",
        "chunks_manifest_v2_ref": "s3://bucket/chunks_manifest_v2.json",
        "cross_ref_graph_ref": "s3://bucket/cross_ref_graph.json",
        "confidence_map_ref": "s3://bucket/confidence_map.json",
        "segment_count": 1,
        "segments": [
            {
                "segment_id": "seg-1",
                "segment_clause_tree_ref": "s3://bucket/segment_1.json",
                "segment_chunks_ref": "s3://bucket/chunks_1.json",
                "legal_units_ref": None,
                "legal_units_enrichment_ref": None,
                "has_tree": True,
                "has_chunks": True,
                "has_legal_units": False,
                "has_enrichment": False,
            }
        ],
        "structure_ready": True,
        "retrieval_ready": True,
        "is_complete_for_current_phase": True,
    }


def test_canonical_artifact_registry_proxies_refs_flags() -> None:
    seg = SegmentArtifactRefs(
        segment_id="seg-1",
        segment_clause_tree_ref="s3://bucket/segment_1.json",
        segment_chunks_ref="s3://bucket/chunks_1.json",
    )
    refs = CanonicalArtifactRefs(
        document_id="doc-1",
        clause_tree_ref="s3://bucket/clause_tree.json",
        file_graph_ref="s3://bucket/file_graph.json",
        chunks_manifest_v2_ref="s3://bucket/chunks_manifest_v2.json",
        segment_refs=(seg,),
    )

    registry = CanonicalArtifactRegistry(refs=refs)

    assert registry.document_id == "doc-1"
    assert registry.structure_ready is True
    assert registry.retrieval_ready is True


def test_canonical_artifact_registry_attach_and_get_payload() -> None:
    refs = CanonicalArtifactRefs(document_id="doc-1")
    registry = CanonicalArtifactRegistry(refs=refs)

    payload = {"nodes": 10}
    registry.attach_payload("file_graph", payload)

    assert registry.get_payload("file_graph") == {"nodes": 10}
    assert registry.get_payload("missing") is None


def test_canonical_artifact_registry_rejects_empty_payload_key() -> None:
    refs = CanonicalArtifactRefs(document_id="doc-1")
    registry = CanonicalArtifactRegistry(refs=refs)

    with pytest.raises(ValueError, match="payload key must not be empty"):
        registry.attach_payload("", {"x": 1})


def test_canonical_artifact_registry_to_dict_contains_loaded_payload_keys_sorted() -> None:
    refs = CanonicalArtifactRefs(document_id="doc-1")
    registry = CanonicalArtifactRegistry(refs=refs)

    registry.attach_payload("chunks_manifest_v2", {"x": 1})
    registry.attach_payload("file_graph", {"y": 2})

    assert registry.to_dict() == {
        "refs": {
            "document_id": "doc-1",
            "clause_tree_ref": None,
            "file_graph_ref": None,
            "chunks_manifest_v2_ref": None,
            "cross_ref_graph_ref": None,
            "confidence_map_ref": None,
            "segment_count": 0,
            "segments": [],
            "structure_ready": False,
            "retrieval_ready": False,
            "is_complete_for_current_phase": False,
        },
        "loaded_payload_keys": ["chunks_manifest_v2", "file_graph"],
        "structure_ready": False,
        "retrieval_ready": False,
    }

    