"""
Tests for subtree page range propagation in hierarchy builder.

Проверяет что propagate_subtree_page_ranges() корректно расширяет
parent page ranges так, чтобы freeze()-инвариант child ⊆ parent
выполнялся для любого дерева.
"""

from __future__ import annotations

import pytest

from services.structure._models._nodes import (
    MutableHierarchyNode,
    freeze,
)
from services.structure._hierarchy_builder._traversal import (
    propagate_subtree_page_ranges,
)


def _make_node(
    uid: str,
    level: int,
    start_page: int,
    end_page: int,
    children: list[MutableHierarchyNode] | None = None,
    scope: str = "main_contract",
) -> MutableHierarchyNode:
    node = MutableHierarchyNode(
        effective_uid=f"{scope}:{uid}",
        title=f"Section {uid}",
        level=level,
        raw_uid=uid,
        scope=scope,
        node_kind="section" if children else "leaf",
    )
    node.start_page = start_page
    node.end_page = end_page
    node.children = children or []
    node.own_element_ids = []
    node.subtree_element_ids = []
    node.diagnostics = {}
    node.structural_hash = f"hash_{uid}"
    node.range_end_reason = None
    return node


def _prepare_for_freeze(node: MutableHierarchyNode) -> None:
    if not node.structural_hash:
        node.structural_hash = f"hash_{node.effective_uid}"
    if not node.subtree_element_ids:
        node.subtree_element_ids = list(node.own_element_ids)
    for child in node.children:
        _prepare_for_freeze(child)
        for eid in child.subtree_element_ids:
            if eid not in node.subtree_element_ids:
                node.subtree_element_ids.append(eid)
    if node.children and node.node_kind == "leaf":
        node.node_kind = "section"


class TestPropagateSubtreePageRanges:

    def test_parent_expands_to_cover_child(self) -> None:
        child = _make_node("4.3", level=2, start_page=3, end_page=3)
        parent = _make_node("4", level=1, start_page=2, end_page=2, children=[child])

        propagate_subtree_page_ranges([parent], document_id="doc-test")

        assert parent.start_page == 2
        assert parent.end_page == 3
        assert child.start_page == 3
        assert child.end_page == 3

    def test_parent_expands_start_and_end(self) -> None:
        child1 = _make_node("3.a", level=2, start_page=2, end_page=2)
        child2 = _make_node("3.b", level=2, start_page=4, end_page=4)
        parent = _make_node("3", level=1, start_page=3, end_page=3, children=[child1, child2])

        propagate_subtree_page_ranges([parent], document_id="doc-test")

        assert parent.start_page == 2
        assert parent.end_page == 4

    def test_leaf_node_unchanged(self) -> None:
        leaf = _make_node("5", level=1, start_page=5, end_page=5)

        propagate_subtree_page_ranges([leaf], document_id="doc-test")

        assert leaf.start_page == 5
        assert leaf.end_page == 5

    def test_parent_already_covers_children(self) -> None:
        child = _make_node("2.1", level=2, start_page=3, end_page=5)
        parent = _make_node("2", level=1, start_page=1, end_page=10, children=[child])

        propagate_subtree_page_ranges([parent], document_id="doc-test")

        assert parent.start_page == 1
        assert parent.end_page == 10

    def test_deep_tree_propagation(self) -> None:
        grandchild = _make_node("1.1.1", level=3, start_page=3, end_page=3)
        child = _make_node("1.1", level=2, start_page=1, end_page=1, children=[grandchild])
        root = _make_node("1", level=1, start_page=1, end_page=1, children=[child])

        propagate_subtree_page_ranges([root], document_id="doc-test")

        assert grandchild.start_page == 3
        assert grandchild.end_page == 3
        assert child.start_page == 1
        assert child.end_page == 3
        assert root.start_page == 1
        assert root.end_page == 3

    def test_multiple_roots(self) -> None:
        child_a = _make_node("1.1", level=2, start_page=3, end_page=3)
        root_a = _make_node("1", level=1, start_page=1, end_page=2, children=[child_a])

        child_b = _make_node("2.1", level=2, start_page=6, end_page=7)
        root_b = _make_node("2", level=1, start_page=4, end_page=5, children=[child_b])

        propagate_subtree_page_ranges([root_a, root_b], document_id="doc-test")

        assert root_a.start_page == 1
        assert root_a.end_page == 3
        assert root_b.start_page == 4
        assert root_b.end_page == 7

    def test_child_page_before_parent(self) -> None:
        child = _make_node("5.1", level=2, start_page=2, end_page=3)
        parent = _make_node("5", level=1, start_page=4, end_page=4, children=[child])

        propagate_subtree_page_ranges([parent], document_id="doc-test")

        assert parent.start_page == 2
        assert parent.end_page == 4


class TestPropagationDiagnostics:

    def test_diagnostics_set_when_expanded(self) -> None:
        child = _make_node("4.3", level=2, start_page=3, end_page=3)
        parent = _make_node("4", level=1, start_page=2, end_page=2, children=[child])

        propagate_subtree_page_ranges([parent], document_id="doc-test")

        diag = parent.diagnostics
        assert diag.get("range_expanded_to_cover_children") is True
        assert diag["range_before_expand"]["start_page"] == 2
        assert diag["range_before_expand"]["end_page"] == 2
        assert diag["range_after_expand"]["start_page"] == 2
        assert diag["range_after_expand"]["end_page"] == 3

    def test_diagnostics_not_set_when_unchanged(self) -> None:
        child = _make_node("2.1", level=2, start_page=3, end_page=5)
        parent = _make_node("2", level=1, start_page=1, end_page=10, children=[child])

        propagate_subtree_page_ranges([parent], document_id="doc-test")

        assert "range_expanded_to_cover_children" not in parent.diagnostics

    def test_diagnostics_on_intermediate_nodes(self) -> None:
        grandchild = _make_node("1.1.1", level=3, start_page=5, end_page=5)
        child = _make_node("1.1", level=2, start_page=2, end_page=2, children=[grandchild])
        root = _make_node("1", level=1, start_page=1, end_page=1, children=[child])

        propagate_subtree_page_ranges([root], document_id="doc-test")

        assert child.diagnostics.get("range_expanded_to_cover_children") is True
        assert root.diagnostics.get("range_expanded_to_cover_children") is True


class TestPropagationIdempotency:

    def test_double_propagation_same_result(self) -> None:
        child = _make_node("4.3", level=2, start_page=3, end_page=3)
        parent = _make_node("4", level=1, start_page=2, end_page=2, children=[child])

        propagate_subtree_page_ranges([parent], document_id="doc-test")
        first_start = parent.start_page
        first_end = parent.end_page

        propagate_subtree_page_ranges([parent], document_id="doc-test")
        second_start = parent.start_page
        second_end = parent.end_page

        assert (first_start, first_end) == (second_start, second_end)


class TestFreezeAfterPropagation:

    def test_freeze_fails_without_propagation(self) -> None:
        child = _make_node("4.3", level=2, start_page=3, end_page=3)
        parent = _make_node("4", level=1, start_page=2, end_page=2, children=[child])
        _prepare_for_freeze(parent)

        with pytest.raises(ValueError, match="Child page range must be within parent range"):
            freeze(parent)

    def test_freeze_succeeds_after_propagation(self) -> None:
        child = _make_node("4.3", level=2, start_page=3, end_page=3)
        parent = _make_node("4", level=1, start_page=2, end_page=2, children=[child])

        propagate_subtree_page_ranges([parent], document_id="doc-test")
        _prepare_for_freeze(parent)

        frozen = freeze(parent)
        assert frozen.start_page == 2
        assert frozen.end_page == 3
        assert len(frozen.children) == 1
        assert frozen.children[0].start_page == 3
        assert frozen.children[0].end_page == 3

    def test_freeze_deep_tree_after_propagation(self) -> None:
        grandchild = _make_node("1.1.1", level=3, start_page=5, end_page=5)
        child = _make_node("1.1", level=2, start_page=2, end_page=3, children=[grandchild])
        root = _make_node("1", level=1, start_page=1, end_page=1, children=[child])

        propagate_subtree_page_ranges([root], document_id="doc-test")
        _prepare_for_freeze(root)

        frozen = freeze(root)
        assert frozen.start_page == 1
        assert frozen.end_page == 5
        assert frozen.children[0].start_page == 2
        assert frozen.children[0].end_page == 5
        assert frozen.children[0].children[0].start_page == 5
        assert frozen.children[0].children[0].end_page == 5


class TestPropagationEdgeCases:

    def test_empty_root_list(self) -> None:
        propagate_subtree_page_ranges([], document_id="doc-test")

    def test_single_leaf_root(self) -> None:
        root = _make_node("1", level=1, start_page=1, end_page=1)

        propagate_subtree_page_ranges([root], document_id="doc-test")

        assert root.start_page == 1
        assert root.end_page == 1

    def test_many_children_different_pages(self) -> None:
        children = [
            _make_node(f"1.{i}", level=2, start_page=i, end_page=i)
            for i in range(1, 11)
        ]
        parent = _make_node("1", level=1, start_page=5, end_page=5, children=children)

        propagate_subtree_page_ranges([parent], document_id="doc-test")

        assert parent.start_page == 1
        assert parent.end_page == 10

    def test_parent_with_same_page_as_child(self) -> None:
        child = _make_node("1.1", level=2, start_page=3, end_page=3)
        parent = _make_node("1", level=1, start_page=3, end_page=3, children=[child])

        propagate_subtree_page_ranges([parent], document_id="doc-test")

        assert parent.start_page == 3
        assert parent.end_page == 3
        assert "range_expanded_to_cover_children" not in parent.diagnostics


        