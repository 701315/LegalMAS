from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from services.structure.models import ClauseTree


DATA_DIR = Path(__file__).parent / "data" / "spa_simonova"


def _load_json(name: str) -> dict[str, Any]:
    path = DATA_DIR / name
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def spa_primary_layout_raw() -> dict[str, Any]:
    return _load_json("primary.json")


@pytest.fixture(scope="session")
def spa_clause_tree_raw() -> dict[str, Any]:
    return _load_json("clause_tree.json")


@pytest.fixture(scope="session")
def spa_file_graph_raw() -> dict[str, Any]:
    return _load_json("file_graph.json")


@pytest.fixture(scope="session")
def spa_chunks_manifest_raw() -> dict[str, Any]:
    return _load_json("chunks_manifest_v2.json")


@pytest.fixture(scope="session")
def spa_legal_units_raw() -> dict[str, Any]:
    return _load_json("legal_units_a044a577.json")


@pytest.fixture(scope="session")
def spa_elements(spa_primary_layout_raw: dict[str, Any]) -> list[dict[str, Any]]:
    elements = spa_primary_layout_raw.get("elements")
    assert isinstance(elements, list), "primary.json must contain list field 'elements'"
    assert elements, "primary.json contains no elements"
    return elements


@pytest.fixture(scope="session")
def spa_clause_tree(spa_clause_tree_raw: dict[str, Any]) -> ClauseTree:
    return ClauseTree(**spa_clause_tree_raw)


@pytest.fixture(scope="session")
def spa_nodes_index(spa_clause_tree: ClauseTree):
    nodes_index = spa_clause_tree.nodes_index
    assert nodes_index, "ClauseTree.nodes_index is empty"
    return nodes_index


@pytest.fixture(scope="session")
def spa_document_id(spa_clause_tree: ClauseTree) -> str:
    assert spa_clause_tree.document_id, "ClauseTree.document_id is empty"
    return spa_clause_tree.document_id


def _extract_node_element_ids(node: Any) -> list[str]:
    candidates = [
        "element_ids",
        "source_element_ids",
        "layout_element_ids",
    ]
    for attr in candidates:
        value = getattr(node, attr, None)
        if value:
            return [str(v).strip() for v in value if str(v).strip()]
    return []


@pytest.fixture(scope="session")
def spa_element_to_uid(spa_nodes_index) -> dict[str, str]:
    mapping: dict[str, str] = {}

    for effective_uid, node in spa_nodes_index.items():
        for element_id in _extract_node_element_ids(node):
            mapping[element_id] = str(effective_uid)

    assert mapping, "Failed to reconstruct element_to_effective_uid from ClauseTree.nodes_index"
    return mapping


@pytest.fixture(scope="session")
def spa_leaf_uids(spa_nodes_index) -> list[str]:
    leaf_uids: list[str] = []

    for uid, node in spa_nodes_index.items():
        is_leaf = getattr(node, "is_leaf", None)
        children = getattr(node, "children", None)

        if is_leaf is True:
            leaf_uids.append(str(uid))
        elif children in (None, [], ()):
            leaf_uids.append(str(uid))

    assert leaf_uids, "No leaf UIDs detected in nodes_index"
    return leaf_uids

    
