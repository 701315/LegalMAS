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


def propagate_subtree_page_ranges(
    root_nodes: list[MutableHierarchyNode],
    *,
    document_id: str,
) -> None:
    """
    Нормализовать page ranges mutable hierarchy nodes так, чтобы каждый parent
    покрывал диапазоны всех своих детей (bottom-up propagation).

    Почему это нужно:
    - own range узла задаётся по собственному heading/body span;
    - дети могут располагаться на страницах вне own range родителя;
    - freeze() валидирует инвариант: child range ⊆ parent range;
    - перед freeze() parent range должен быть расширен до subtree bounds.

    Свойства:
    - deterministic;
    - universal;
    - idempotent;
    - не меняет topology дерева, только диапазоны страниц.
    """

    def _is_valid_page(value: object) -> bool:
        return isinstance(value, int) and value > 0

    def _visit(node: MutableHierarchyNode) -> tuple[int | None, int | None]:
        child_ranges: list[tuple[int | None, int | None]] = [
            _visit(child) for child in node.children
        ]

        starts: list[int] = []
        ends: list[int] = []

        if _is_valid_page(node.start_page):
            starts.append(node.start_page)
        if _is_valid_page(node.end_page):
            ends.append(node.end_page)

        for child_start, child_end in child_ranges:
            if _is_valid_page(child_start):
                starts.append(child_start)  # type: ignore[arg-type]
            if _is_valid_page(child_end):
                ends.append(child_end)  # type: ignore[arg-type]

        if not starts or not ends:
            return (
                node.start_page if _is_valid_page(node.start_page) else None,
                node.end_page if _is_valid_page(node.end_page) else None,
            )

        old_start = node.start_page
        old_end = node.end_page

        new_start = min(starts)
        new_end = max(ends)

        node.start_page = new_start
        node.end_page = new_end

        if (old_start, old_end) != (new_start, new_end):
            diagnostics = dict(node.diagnostics or {})
            diagnostics["range_expanded_to_cover_children"] = True
            diagnostics["range_before_expand"] = {
                "start_page": old_start,
                "end_page": old_end,
            }
            diagnostics["range_after_expand"] = {
                "start_page": new_start,
                "end_page": new_end,
            }
            node.diagnostics = diagnostics

        return new_start, new_end

    for root in root_nodes:
        _visit(root)
        
                    
