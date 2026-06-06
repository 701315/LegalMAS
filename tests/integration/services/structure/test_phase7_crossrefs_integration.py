from __future__ import annotations

import pytest

from services.structure.crossrefs import build_cross_reference_graph
from services.structure.models import (
    ClauseTree,
    CrossReferenceGraph,
    STRUCTURE_CONFIDENCE_HIGH,
)

pytestmark = [pytest.mark.integration, pytest.mark.phase7]


def test_phase7_pipeline_builds_graph_from_frozen_tree_fixture(
    sample_multiscope_tree,
    sample_phase7_elements,
    sample_element_to_uid,
    stable_element_id_resolver,
):
    graph = build_cross_reference_graph(
        elements=sample_phase7_elements,
        element_to_effective_uid=sample_element_to_uid,
        nodes=sample_multiscope_tree,
        document_id="doc-phase7-int-1",
        stable_element_id_resolver=stable_element_id_resolver,
    )

    assert isinstance(graph, CrossReferenceGraph)
    assert graph.document_id == "doc-phase7-int-1"
    assert graph.stats.references_count == 5
    assert graph.stats.unique_sources_count == 4
    assert graph.stats.unique_targets_count == 4
    assert graph.stats.unresolved_count == 1
    assert graph.stats.ambiguous_count == 0

    actual_pairs = {(r.source_effective_uid, r.target_effective_uid) for r in graph.references}
    expected_pairs = {
        ("main_contract:1.1", "main_contract:2"),
        ("main_contract:1.1", "appendix_a:3"),
        ("main_contract:1.2", "main_contract:2.1"),
        ("appendix_a:3", "main_contract:2"),
        ("main_contract:2.1", "main_contract:1.1"),
    }
    assert actual_pairs == expected_pairs


def test_phase7_multiscope_resolution_prefers_same_scope(
    sample_multiscope_tree,
    stable_element_id_resolver,
):
    elements = [{"id": "e-scope", "text": "Clause 2"}]
    element_to_effective_uid = {"e-scope": "main_contract:1.1"}

    graph = build_cross_reference_graph(
        elements=elements,
        element_to_effective_uid=element_to_effective_uid,
        nodes=sample_multiscope_tree,
        document_id="doc-phase7-int-2",
        stable_element_id_resolver=stable_element_id_resolver,
    )

    assert len(graph.references) == 1
    ref = graph.references[0]
    assert ref.source_effective_uid == "main_contract:1.1"
    assert ref.target_effective_uid == "main_contract:2"
    assert ref.resolution_mode == "same_scope_raw_uid"


def test_phase7_clause_tree_integration_roundtrip(
    sample_multiscope_tree,
    sample_multiscope_root,
    sample_phase7_elements,
    sample_element_to_uid,
    stable_element_id_resolver,
):
    graph = build_cross_reference_graph(
        elements=sample_phase7_elements,
        element_to_effective_uid=sample_element_to_uid,
        nodes=sample_multiscope_tree,
        document_id="doc-phase7-int-tree",
        stable_element_id_resolver=stable_element_id_resolver,
    )

    tree = ClauseTree(
        document_id="doc-phase7-int-tree",
        root=sample_multiscope_root,
        cross_reference_graph=graph,
        structure_confidence=STRUCTURE_CONFIDENCE_HIGH,
        nodes_index=sample_multiscope_tree,
        scope_name=None,
        segment_page_range=(1, 3),
        segment_order=0,
        is_primary_segment=True,
    )

    data = tree.to_dict()

    assert data["document_id"] == "doc-phase7-int-tree"
    assert data["cross_reference_graph"]["document_id"] == "doc-phase7-int-tree"
    assert data["cross_reference_graph"]["stats"]["references_count"] == 5
    assert isinstance(data["root"], list)
    assert len(data["root"]) == 3
    assert data["schema_version"] == "4.0"


def test_phase7_serialized_graph_is_deterministic(
    sample_multiscope_tree,
    sample_phase7_elements,
    sample_element_to_uid,
    stable_element_id_resolver,
):
    graph_1 = build_cross_reference_graph(
        elements=sample_phase7_elements,
        element_to_effective_uid=sample_element_to_uid,
        nodes=sample_multiscope_tree,
        document_id="doc-phase7-deterministic",
        stable_element_id_resolver=stable_element_id_resolver,
    )
    graph_2 = build_cross_reference_graph(
        elements=sample_phase7_elements,
        element_to_effective_uid=sample_element_to_uid,
        nodes=sample_multiscope_tree,
        document_id="doc-phase7-deterministic",
        stable_element_id_resolver=stable_element_id_resolver,
    )

    assert graph_1.to_dict() == graph_2.to_dict()


    