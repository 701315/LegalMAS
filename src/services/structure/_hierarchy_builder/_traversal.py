# src/services/structure/_hierarchy_builder/_traversal.py

"""Обход дерева и агрегация structural свойств."""

from __future__ import annotations

from collections.abc import Generator

from core.logging import get_logger
from services.structure.models import (
    MutableHierarchyNode,
    NODE_KIND_LEAF,
    NODE_KIND_SECTION,
)

logger = get_logger(__name__)

_SUSPICIOUS_OWN_SHARE_RATIO = 0.8


def _walk_postorder(
    node: MutableHierarchyNode,
) -> Generator[MutableHierarchyNode, None, None]:
    for child in node.children:
        yield from _walk_postorder(child)
    yield node


def populate_subtree_element_ids(
    root_nodes: list[MutableHierarchyNode],
    *,
    document_id: str,
) -> None:
    if not root_nodes:
        return

    for root_node in root_nodes:
        for node in _walk_postorder(root_node):
            node.node_kind = NODE_KIND_SECTION if node.children else NODE_KIND_LEAF

            subtree_ids: list[str] = list(node.own_element_ids or [])
            for child in node.children:
                subtree_ids.extend(child.subtree_element_ids or [])
            node.subtree_element_ids = list(dict.fromkeys(subtree_ids))

            text_parts: list[str] = []
            if node.own_text:
                text_parts.append(node.own_text)
            for child in node.children:
                if child.subtree_text:
                    text_parts.append(child.subtree_text)
            node.subtree_text = " ".join(text_parts) if text_parts else None

            own_count = len(node.own_element_ids or [])
            subtree_count = len(node.subtree_element_ids or [])
            node.diagnostics["suspicious_own_scope"] = bool(
                node.children
                and subtree_count > 0
                and own_count >= _SUSPICIOUS_OWN_SHARE_RATIO * subtree_count
            )
            node.diagnostics["document_id"] = document_id


            
