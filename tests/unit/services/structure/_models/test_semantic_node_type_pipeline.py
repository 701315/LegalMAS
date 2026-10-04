"""Тест: semantic_node_type доходит через Mutable → freeze → to_dict."""
from services.structure._models._nodes import (
    MutableHierarchyNode,
    FrozenHierarchyNode,
    freeze,
)


def _make_preamble_like_node():
    return MutableHierarchyNode(
        effective_uid="main_contract:__preamble__",
        title="",
        level=1,
        raw_uid="__preamble__",
        scope="main_contract",
        node_kind="leaf",
        node_origin="synthetic_preamble",
        content_mode="full_text",
        citability="high",
        own_element_ids=["el_1", "el_2"],
        subtree_element_ids=["el_1", "el_2"],
        own_text="preamble text",
        subtree_text="preamble text",
        start_page=1,
        end_page=2,
        children=[],
        range_end_reason="segment_end",
        semantic_node_type="preamble",
    )


def test_mutable_has_semantic_node_type():
    node = _make_preamble_like_node()
    assert node.semantic_node_type == "preamble"


def test_freeze_preserves_semantic_node_type():
    node = _make_preamble_like_node()
    node.compute_and_set_structural_hash(normalized_path="1.1", sibling_index=0)
    frozen = freeze(node)
    assert isinstance(frozen, FrozenHierarchyNode)
    assert frozen.semantic_node_type == "preamble"


def test_frozen_to_dict_has_semantic_node_type():
    node = _make_preamble_like_node()
    node.compute_and_set_structural_hash(normalized_path="1.1", sibling_index=0)
    frozen = freeze(node)
    d = frozen.to_dict()
    assert d["semantic_node_type"] == "preamble"


def test_none_stays_none():
    node = MutableHierarchyNode(
        effective_uid="main_contract:1",
        title="Clause 1",
        level=1,
        raw_uid="1",
        scope="main_contract",
        node_kind="leaf",
        own_element_ids=["el_1"],
        subtree_element_ids=["el_1"],
        own_text="text",
        subtree_text="text",
        start_page=1,
        end_page=1,
        children=[],
        range_end_reason="next_same_or_higher",
    )
    assert node.semantic_node_type is None
