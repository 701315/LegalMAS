"""
Regression test suite for ClauseTree and LLMClauseDetector.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from services.structure._clause_detector.detector import LLMClauseDetector
from services.structure._models._nodes import (
    FrozenHierarchyNode,
    MutableHierarchyNode,
    refreeze_forest,
)


def test_clause_detector_frozen_safe_and_merge_strategy(
    golden_manifest: dict[str, Any],
    regression_fixtures_dir: Any,
    mock_llm_client: Any,
):
    """
    Проверяет паттерн Frozen-Safe и слияние деревьев:
    1. На вход подается жестко замороженное дерево (FrozenHierarchyNode)
    2. Детектор должен безопасно разморозить его, выполнить refinement,
       слить с FSM узлами без дубликатов и вернуть полностью замороженное дерево.
    """
    detector = LLMClauseDetector()

    for doc_key, spec in golden_manifest.items():
        tree_path = regression_fixtures_dir / f"{doc_key}_initial_tree.json"
        layout_path = regression_fixtures_dir / f"{doc_key}_primary_layout.json"

        if not tree_path.exists() or not layout_path.exists():
            pytest.skip(f"Fixtures for {doc_key} not found, skipping.")

        # 1. Сборка замороженного дерева
        with open(tree_path, "r", encoding="utf-8") as f:
            raw_tree = json.load(f)
            mutable_roots = [MutableHierarchyNode.model_validate(r) for r in raw_tree]
            frozen_roots = refreeze_forest(mutable_roots)

        with open(layout_path, "r", encoding="utf-8") as f:
            elements = json.load(f)

        # 2. Refinement дерева
        result = detector.refine_tree(frozen_roots, elements)

        # 3. Проверка качества по Assurance Gates
        assert isinstance(result.roots[0], FrozenHierarchyNode), "Immutability violated!"
        assert result.clauses_added >= spec["min_clause_nodes"], (
            f"Clause Detection Regression in {doc_key}! "
            f"Added: {result.clauses_added}, expected at least: {spec['min_clause_nodes']}"
        )

        # 4. Проверка на коллизии UID и дублирование
        uids: set[str] = set()

        def _verify_node_integrity(node: Any):
            # Уникальность
            assert node.effective_uid not in uids, f"Collision detected! Duplicate UID: {node.effective_uid}"
            uids.add(node.effective_uid)
            
            # Clamp-наследование страниц
            if node.children:
                for child in node.children:
                    assert child.start_page >= node.start_page, f"Page inheritance bug at {child.effective_uid}"
                    assert child.end_page <= node.end_page, f"Page inheritance bug at {child.effective_uid}"
                    _verify_node_integrity(child)

        for root in result.roots:
            _verify_node_integrity(root)


            