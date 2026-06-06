from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from services.structure.models import FrozenHierarchyNode


DATA_DIR = Path(__file__).parent / "data" / "spa_simonova"


def _load_json(name: str) -> dict[str, Any]:
    path = DATA_DIR / name
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _deserialize_frozen_node(raw: dict[str, Any]) -> FrozenHierarchyNode:
    """
    Рекурсивно десериализовать raw JSON dict в FrozenHierarchyNode.

    Это локальный test helper, не production deserializer.
    Используется только для поднятия integration fixtures из JSON.
    """
    children_raw = raw.get("children") or []
    children = tuple(_deserialize_frozen_node(ch) for ch in children_raw)

    return FrozenHierarchyNode(
        effective_uid=raw["effective_uid"],
        raw_uid=raw.get("raw_uid", ""),
        scope=raw.get("scope", "main_contract"),
        title=raw.get("title", ""),
        level=raw.get("level", 1),
        node_kind=raw.get("node_kind", "leaf"),
        structural_hash=raw.get("structural_hash", "fixture_hash"),
        node_origin=raw.get("node_origin", "unknown"),
        content_mode=raw.get("content_mode", "full_text"),
        citability=raw.get("citability", "low"),
        own_element_ids=tuple(raw.get("own_element_ids") or []),
        subtree_element_ids=tuple(raw.get("subtree_element_ids") or []),
        own_text=raw.get("own_text"),
        subtree_text=raw.get("subtree_text"),
        start_page=raw.get("start_page", 1),
        end_page=raw.get("end_page", 1),
        children=children,
        range_end_reason=raw.get("range_end_reason"),
        diagnostics=raw.get("diagnostics") or {},
    )


def _build_nodes_index_from_raw_root(
    root: list[dict[str, Any]],
) -> tuple[list[FrozenHierarchyNode], dict[str, FrozenHierarchyNode]]:
    """
    Из raw JSON root построить:
    - list[FrozenHierarchyNode] для root
    - dict[effective_uid -> FrozenHierarchyNode] для nodes_index
    """
    frozen_root: list[FrozenHierarchyNode] = []
    index: dict[str, FrozenHierarchyNode] = {}

    def _walk(node: FrozenHierarchyNode) -> None:
        index[node.effective_uid] = node
        for child in node.children:
            _walk(child)

    for raw_node in root:
        frozen = _deserialize_frozen_node(raw_node)
        frozen_root.append(frozen)
        _walk(frozen)

    return frozen_root, index


# ---------------------------------------------------------------------------
# SPA Simonova real-document fixtures
# ---------------------------------------------------------------------------

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
def spa_document_id(spa_clause_tree_raw: dict[str, Any]) -> str:
    doc_id = str(spa_clause_tree_raw.get("document_id") or "").strip()
    assert doc_id, "clause_tree.json must contain non-empty document_id"
    return doc_id


@pytest.fixture(scope="session")
def spa_nodes_index(
    spa_clause_tree_raw: dict[str, Any],
) -> dict[str, FrozenHierarchyNode]:
    raw_root = spa_clause_tree_raw.get("root") or []
    assert isinstance(raw_root, list), "clause_tree.json must contain list field 'root'"
    _, index = _build_nodes_index_from_raw_root(raw_root)
    assert index, "ClauseTree nodes_index is empty after deserialization"
    return index


def _extract_node_element_ids(node: Any) -> list[str]:
    candidates = [
        "own_element_ids",
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


# ---------------------------------------------------------------------------
# Phase 7 synthetic multiscope fixtures
# ---------------------------------------------------------------------------

def _stable_element_id_resolver(el: dict[str, Any], idx: int) -> str:
    return str(el["id"])


def _phase7_node(
    *,
    scope: str,
    raw_uid: str,
    title: str | None = None,
    own_text: str | None = None,
    children: tuple[FrozenHierarchyNode, ...] = (),
    node_kind: str | None = None,
    start_page: int = 1,
    end_page: int = 1,
) -> FrozenHierarchyNode:
    effective_uid = f"{scope}:{raw_uid}"
    resolved_node_kind = node_kind or ("section" if children else "leaf")
    own_ids = (f"el_{scope}_{raw_uid}",)

    return FrozenHierarchyNode(
        effective_uid=effective_uid,
        raw_uid=raw_uid,
        scope=scope,
        title=title or raw_uid,
        level=len(raw_uid.split(".")),
        node_kind=resolved_node_kind,
        structural_hash=f"h_{scope}_{raw_uid.replace('.', '_')}",
        own_element_ids=own_ids,
        subtree_element_ids=own_ids,
        own_text=own_text,
        subtree_text=own_text,
        start_page=start_page,
        end_page=end_page,
        children=children,
        range_end_reason=None,
        diagnostics={},
    )


@pytest.fixture(scope="session")
def stable_element_id_resolver():
    return _stable_element_id_resolver


@pytest.fixture(scope="session")
def sample_multiscope_root() -> list[FrozenHierarchyNode]:
    main_1_1 = _phase7_node(
        scope="main_contract",
        raw_uid="1.1",
        title="Clause 1.1",
        own_text="см. п. 2 и Clause 3",
    )
    main_1_2 = _phase7_node(
        scope="main_contract",
        raw_uid="1.2",
        title="Clause 1.2",
        own_text="см. п. 2.1 and Clause 9",
    )
    main_2_1 = _phase7_node(
        scope="main_contract",
        raw_uid="2.1",
        title="Clause 2.1",
        own_text="см. п. 1.1",
    )

    main_1 = _phase7_node(
        scope="main_contract",
        raw_uid="1",
        title="Section 1",
        own_text="Section 1",
        children=(main_1_1, main_1_2),
        node_kind="section",
    )
    main_2 = _phase7_node(
        scope="main_contract",
        raw_uid="2",
        title="Section 2",
        own_text="Section 2",
        children=(main_2_1,),
        node_kind="section",
    )
    appendix_a_3 = _phase7_node(
        scope="appendix_a",
        raw_uid="3",
        title="Appendix A Clause 3",
        own_text="Clause 2",
        node_kind="leaf",
    )

    return [main_1, main_2, appendix_a_3]


def _build_phase7_nodes_index(
    root_nodes: list[FrozenHierarchyNode],
) -> dict[str, FrozenHierarchyNode]:
    index: dict[str, FrozenHierarchyNode] = {}

    def _walk(node: FrozenHierarchyNode) -> None:
        index[node.effective_uid] = node
        for child in node.children:
            _walk(child)

    for root in root_nodes:
        _walk(root)

    return index


@pytest.fixture(scope="session")
def sample_multiscope_tree(
    sample_multiscope_root: list[FrozenHierarchyNode],
) -> dict[str, FrozenHierarchyNode]:
    return _build_phase7_nodes_index(sample_multiscope_root)


@pytest.fixture(scope="session")
def sample_phase7_elements() -> list[dict[str, Any]]:
    return [
        {"id": "e1", "text": "см. п. 2 и Clause 3"},
        {"id": "e2", "text": "см. п. 2.1 and Clause 9"},
        {"id": "e3", "text": "Clause 2"},
        {"id": "e4", "text": "см. п. 1.1"},
    ]


@pytest.fixture(scope="session")
def sample_element_to_uid() -> dict[str, str]:
    return {
        "e1": "main_contract:1.1",
        "e2": "main_contract:1.2",
        "e3": "appendix_a:3",
        "e4": "main_contract:2.1",
    }



