# src/services/structure/_hierarchy_builder/_traversal.py

"""Обход дерева и агрегация текстовых свойств."""

from __future__ import annotations
from typing import Generator
from core.logging import get_logger
from services.structure._models._nodes import ClauseNode

logger = get_logger(__name__)

_SUSPICIOUS_OWN_SHARE_RATIO = 0.8

def _walk_postorder(node: ClauseNode) -> Generator[ClauseNode, None, None]:
    """Bottom-up обход дерева."""
    for child in node.children:
        yield from _walk_postorder(child)
    yield node

def populate_subtree_element_ids(
    root_nodes: list[ClauseNode],
    *,
    document_id: str,
) -> None:
    """Агрегация subtree_element_ids и текстов снизу вверх."""
    doc_id = str(document_id or "").strip()
    if not root_nodes:
        return

    for root_node in root_nodes:
        for node in _walk_postorder(root_node):
            node.node_kind = "section" if node.children else "leaf"

            if node.citability_hint is None:
                is_semantic_negative = node.semantic_node_type in {
                    "definition_item", "signature_block", "body_text"
                }
                has_own_text = bool(node.own_text and node.own_text.strip())
                has_children = bool(node.children)

                if is_semantic_negative:
                    node.citability_hint = "low"
                elif node.recovered_via_best_effort:
                    node.citability_hint = "medium"
                elif not has_own_text and not has_children:
                    node.citability_hint = "low"
                elif not has_own_text and has_children:
                    node.citability_hint = "medium"
                else:
                    node.citability_hint = "high"

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
                node.children and subtree_count > 0 and 
                own_count >= _SUSPICIOUS_OWN_SHARE_RATIO * subtree_count
            )

