from __future__ import annotations

import json

import pytest

from services.structure.crossrefs import build_cross_reference_graph

pytestmark = [pytest.mark.integration, pytest.mark.phase7, pytest.mark.regression]


def test_phase7_regression_counts_are_stable(
    sample_multiscope_tree,
    sample_phase7_elements,
    sample_element_to_uid,
    stable_element_id_resolver,
):
    graph = build_cross_reference_graph(
        elements=sample_phase7_elements,
        element_to_effective_uid=sample_element_to_uid,
        nodes=sample_multiscope_tree,
        document_id="doc-phase7-regression",
        stable_element_id_resolver=stable_element_id_resolver,
    )

    stats = graph.stats.to_dict()

    assert stats == {
        "references_count": 5,
        "unique_sources_count": 4,
        "unique_targets_count": 5,
        "unresolved_count": 1,
        "ambiguous_count": 0,
        "invalid_source_mapping_count": 0,
        "malformed_stable_element_id_count": 0,
        "duplicate_reference_count": 0,
        "skipped_self_reference_count": 0,
        "index_node_skipped_count": 0,
        "duplicate_effective_uid_count": 0,
        "duplicate_scoped_raw_uid_count": 0,
    }


def test_phase7_regression_serialized_json_shape(
    sample_multiscope_tree,
    sample_phase7_elements,
    sample_element_to_uid,
    stable_element_id_resolver,
):
    graph = build_cross_reference_graph(
        elements=sample_phase7_elements,
        element_to_effective_uid=sample_element_to_uid,
        nodes=sample_multiscope_tree,
        document_id="doc-phase7-json",
        stable_element_id_resolver=stable_element_id_resolver,
    )

    rendered = json.dumps(graph.to_dict(), ensure_ascii=False, sort_keys=True, indent=2)

    assert '"document_id": "doc-phase7-json"' in rendered
    assert '"references_count": 5' in rendered
    assert '"unresolved_count": 1' in rendered
    assert '"outgoing_index"' in rendered
    assert '"incoming_index"' in rendered
    assert '"schema_version": "1.0"' in rendered


    