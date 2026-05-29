import pytest

from services.structure.crossrefs import build_cross_reference_graph
from services.structure.models import (
    CrossReferenceGraph,
    FrozenHierarchyNode,
    ClauseTree,
    STRUCTURE_CONFIDENCE_HIGH,
)


def _stable_element_id_resolver(el: dict, idx: int) -> str:
    return str(el["id"])


def _node(
    *,
    scope: str,
    raw_uid: str,
    title: str | None = None,
    own_text: str | None = None,
    children: tuple[FrozenHierarchyNode, ...] = (),
    node_kind: str = "leaf",
    start_page: int = 1,
    end_page: int = 1,
) -> FrozenHierarchyNode:
    effective_uid = f"{scope}:{raw_uid}"
    return FrozenHierarchyNode(
        effective_uid=effective_uid,
        raw_uid=raw_uid,
        scope=scope,
        title=title or raw_uid,
        level=len(raw_uid.split(".")),
        node_kind=node_kind,
        structural_hash=f"h_{scope}_{raw_uid.replace('.', '_')}",
        own_element_ids=(f"el_{scope}_{raw_uid}",),
        subtree_element_ids=(f"el_{scope}_{raw_uid}",),
        own_text=own_text,
        subtree_text=own_text,
        start_page=start_page,
        end_page=end_page,
        children=children,
        range_end_reason=None,
        diagnostics={},
    )


def test_phase7_same_scope_and_unique_global_resolution():
    nodes = {
        "main_contract:1": _node(scope="main_contract", raw_uid="1"),
        "main_contract:2": _node(scope="main_contract", raw_uid="2"),
        "appendix_a:3": _node(scope="appendix_a", raw_uid="3"),
        "main_contract:4": _node(scope="main_contract", raw_uid="4"),
    }

    elements = [
        {"id": "e1", "text": "см. п. 2 и Clause 3"},
        {"id": "e2", "text": "Sec. 4"},
    ]
    element_to_effective_uid = {
        "e1": "main_contract:1",
        "e2": "appendix_a:3",
    }

    graph = build_cross_reference_graph(
        elements=elements,
        element_to_effective_uid=element_to_effective_uid,
        nodes=nodes,
        document_id="doc-1",
        stable_element_id_resolver=_stable_element_id_resolver,
    )

    assert isinstance(graph, CrossReferenceGraph)
    assert graph.document_id == "doc-1"
    assert len(graph.references) == 3

    triples = {
        (r.source_effective_uid, r.target_effective_uid, r.reference_text, r.resolution_mode)
        for r in graph.references
    }
    assert ("main_contract:1", "main_contract:2", "см. п. 2", "same_scope_raw_uid") in triples
    assert ("main_contract:1", "appendix_a:3", "Clause 3", "global_unique_raw_uid_fallback") in triples
    assert ("appendix_a:3", "main_contract:4", "Sec. 4", "global_unique_raw_uid_fallback") in triples

    assert graph.outgoing_index["main_contract:1"] == ("main_contract:2", "appendix_a:3")
    assert graph.incoming_index["main_contract:4"] == ("appendix_a:3",)
    assert graph.stats.references_count == 3
    assert graph.stats.unique_sources_count == 2
    assert graph.stats.unique_targets_count == 3
    assert graph.stats.unresolved_count == 0
    assert graph.stats.ambiguous_count == 0


def test_phase7_ambiguous_and_unresolved_are_counted_but_not_emitted():
    nodes = {
        "main_contract:1": _node(scope="main_contract", raw_uid="1"),
        "appendix_a:2": _node(scope="appendix_a", raw_uid="2"),
        "appendix_b:2": _node(scope="appendix_b", raw_uid="2"),
    }

    elements = [
        {"id": "e1", "text": "Clause 2 and Clause 9"},
    ]
    element_to_effective_uid = {
        "e1": "main_contract:1",
    }

    graph = build_cross_reference_graph(
        elements=elements,
        element_to_effective_uid=element_to_effective_uid,
        nodes=nodes,
        document_id="doc-amb",
        stable_element_id_resolver=_stable_element_id_resolver,
    )

    assert len(graph.references) == 0
    assert graph.stats.references_count == 0
    assert graph.stats.ambiguous_count == 1
    assert graph.stats.unresolved_count == 1


def test_phase7_self_reference_and_duplicate_reference_are_skipped():
    nodes = {
        "main_contract:1": _node(scope="main_contract", raw_uid="1"),
        "main_contract:2": _node(scope="main_contract", raw_uid="2"),
    }

    elements = [
        {"id": "e1", "text": "см. п. 1. см. п. 2. см. п. 2"},
    ]
    element_to_effective_uid = {
        "e1": "main_contract:1",
    }

    graph = build_cross_reference_graph(
        elements=elements,
        element_to_effective_uid=element_to_effective_uid,
        nodes=nodes,
        document_id="doc-self",
        stable_element_id_resolver=_stable_element_id_resolver,
    )

    assert len(graph.references) == 1
    ref = graph.references[0]
    assert ref.source_effective_uid == "main_contract:1"
    assert ref.target_effective_uid == "main_contract:2"
    assert graph.stats.skipped_self_reference_count == 1
    assert graph.stats.duplicate_reference_count == 1


def test_phase7_invalid_source_mapping_and_missing_element_id_are_counted():
    nodes = {
        "main_contract:1": _node(scope="main_contract", raw_uid="1"),
        "main_contract:2": _node(scope="main_contract", raw_uid="2"),
    }

    elements = [
        {"id": "e1", "text": "см. п. 2"},
        {"id": "e2", "text": "см. п. 2"},
        {"id": "", "text": "см. п. 2"},
    ]
    element_to_effective_uid = {
        "e1": "main_contract:999",
        "e2": "main_contract:1",
    }

    def resolver(el: dict, idx: int) -> str:
        return str(el.get("id", "")).strip()

    graph = build_cross_reference_graph(
        elements=elements,
        element_to_effective_uid=element_to_effective_uid,
        nodes=nodes,
        document_id="doc-invalid",
        stable_element_id_resolver=resolver,
    )

    assert len(graph.references) == 1
    assert graph.stats.invalid_source_mapping_count == 1
    assert graph.stats.malformed_stable_element_id_count == 1


def test_phase7_clause_tree_accepts_cross_reference_graph():
    child = _node(scope="main_contract", raw_uid="1.1")
    parent = FrozenHierarchyNode(
        effective_uid="main_contract:1",
        raw_uid="1",
        scope="main_contract",
        title="Section 1",
        level=1,
        node_kind="section",
        structural_hash="hash_parent",
        own_element_ids=("el_main_contract_1",),
        subtree_element_ids=("el_main_contract_1", "el_main_contract_1.1"),
        own_text="Parent text",
        subtree_text="Parent + child",
        start_page=1,
        end_page=2,
        children=(child,),
        range_end_reason=None,
        diagnostics={},
    )

    nodes_index = {
        parent.effective_uid: parent,
        child.effective_uid: child,
    }

    elements = [{"id": "e1", "text": "см. п. 1.1"}]
    element_to_effective_uid = {"e1": "main_contract:1"}

    graph = build_cross_reference_graph(
        elements=elements,
        element_to_effective_uid=element_to_effective_uid,
        nodes=nodes_index,
        document_id="doc-tree",
        stable_element_id_resolver=_stable_element_id_resolver,
    )

    tree = ClauseTree(
        document_id="doc-tree",
        root=[parent],
        cross_reference_graph=graph,
        structure_confidence=STRUCTURE_CONFIDENCE_HIGH,
        nodes_index=nodes_index,
        scope_name="main_contract",
        segment_page_range=(1, 2),
    )

    data = tree.to_dict()
    assert data["document_id"] == "doc-tree"
    assert data["cross_reference_graph"]["stats"]["references_count"] == 1
    assert data["root"][0]["children"][0]["effective_uid"] == "main_contract:1.1"


def test_phase7_graph_validation_rejects_inconsistent_indexes():
    from services.structure.models import CrossReference, CrossReferenceStats

    ref = CrossReference(
        source_effective_uid="main_contract:1",
        target_effective_uid="main_contract:2",
        reference_text="см. п. 2",
    )

    with pytest.raises(ValueError, match="outgoing_index does not match references exactly"):
        CrossReferenceGraph(
            document_id="doc-bad",
            references=(ref,),
            outgoing_index={"main_contract:1": ("main_contract:999",)},
            incoming_index={"main_contract:2": ("main_contract:1",)},
            stats=CrossReferenceStats(
                references_count=1,
                unique_sources_count=1,
                unique_targets_count=1,
            ),
        )


        