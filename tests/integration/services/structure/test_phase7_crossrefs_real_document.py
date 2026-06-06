from __future__ import annotations

import pytest

from services.structure.crossrefs import build_cross_reference_graph
from services.structure.models import CrossReferenceGraph


pytestmark = [
    pytest.mark.integration,
    pytest.mark.phase7,
    pytest.mark.regression,
]


def _stable_element_id_resolver(el: dict, idx: int) -> str:
    value = el.get("id")
    assert value is not None, f"Element at idx={idx} has no 'id'"
    return str(value).strip()


def test_phase7_spa_real_document_smoke(
    spa_document_id: str,
    spa_elements: list[dict],
    spa_element_to_uid: dict[str, str],
    spa_nodes_index,
):
    graph = build_cross_reference_graph(
        elements=spa_elements,
        element_to_effective_uid=spa_element_to_uid,
        nodes=spa_nodes_index,
        document_id=spa_document_id,
        stable_element_id_resolver=_stable_element_id_resolver,
    )

    assert isinstance(graph, CrossReferenceGraph)
    assert graph.document_id == spa_document_id

    assert graph.stats.references_count >= 0
    assert graph.stats.unresolved_count >= 0
    assert graph.stats.ambiguous_count >= 0

    for uid in graph.outgoing_index.keys():
        assert uid in spa_nodes_index

    for uid in graph.incoming_index.keys():
        assert uid in spa_nodes_index

    data = graph.to_dict()
    assert data["document_id"] == spa_document_id
    assert "stats" in data


def test_phase7_spa_real_document_baseline_counts(
    spa_document_id: str,
    spa_elements: list[dict],
    spa_element_to_uid: dict[str, str],
    spa_nodes_index,
):
    graph = build_cross_reference_graph(
        elements=spa_elements,
        element_to_effective_uid=spa_element_to_uid,
        nodes=spa_nodes_index,
        document_id=spa_document_id,
        stable_element_id_resolver=_stable_element_id_resolver,
    )

    assert graph.document_id == spa_document_id

    assert graph.stats.references_count == 0
    assert graph.stats.unresolved_count == 0
    assert graph.stats.ambiguous_count == 0
    assert graph.stats.unique_sources_count == 0
    assert graph.stats.unique_targets_count == 0


def test_phase7_spa_real_document_fixture_sanity(
    spa_document_id: str,
    spa_elements: list[dict],
    spa_nodes_index,
    spa_leaf_uids: list[str],
    spa_element_to_uid: dict[str, str],
):
    assert spa_document_id == "7e90117a-8b16-49f5-b81c-1d2c26b9732c"
    assert len(spa_elements) == 457

    assert len(spa_nodes_index) >= 6
    assert len(spa_leaf_uids) >= 6

    expected_leafs = {
        "main_contract:1",
        "main_contract:2",
        "main_contract:3",
        "main_contract:4",
        "main_contract:5",
        "main_contract:6",
    }
    assert expected_leafs.issubset(set(spa_leaf_uids))

    mapped_element_ids = {str(k).strip() for k in spa_element_to_uid.keys()}
    layout_element_ids = {
        str(el["id"]).strip()
        for el in spa_elements
        if el.get("id") is not None
    }

    assert mapped_element_ids
    assert mapped_element_ids.issubset(layout_element_ids)


    