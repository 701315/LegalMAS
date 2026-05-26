"""
Sprint 3 tests: ClauseTreeBuilder canonical identity contract.

Проверяем:
- metadata leaf chunks содержит effective_uid/raw_uid/scope/node_kind
- metadata section chunks аналогично
- quality gate блокирует section chunking на degraded tree
- own_element_ids guard работает корректно
- single-heading fallback работает
- legacy clause_uid НЕ используется
"""

import pytest
import uuid
from engine.content.clause_tree_builder import ClauseTreeBuilder


class TestLeafChunksCanonicalMetadata:
    """Проверка canonical metadata в leaf chunks."""

    def test_leaf_chunk_has_canonical_fields(self):
        """Leaf chunk metadata содержит effective_uid/raw_uid/scope/node_kind."""
        doc_id = uuid.uuid4()
        
        tree = {
            "root": [
                {
                    "effective_uid": "main_contract::1",
                    "raw_uid": "1",
                    "scope": "main_contract",
                    "title": "Definitions",
                    "level": 1,
                    "children": [],
                    "own_element_ids": ["elem_1", "elem_2"],
                }
            ]
        }
        
        layout = {
            "elements": [
                {"element_id": "elem_1", "type": "heading", "text": "1. Definitions", "page": 1},
                {"element_id": "elem_2", "type": "text", "text": "Contract means this agreement.", "page": 1},
            ]
        }
        
        result = ClauseTreeBuilder.build_leaf_chunks(doc_id, tree, layout)
        chunks = result.chunks
        
        assert len(chunks) == 1
        
        meta = chunks[0]["metadata"]
        assert meta["effective_uid"] == "main_contract::1"
        assert meta["raw_uid"] == "1"
        assert meta["scope"] == "main_contract"
        assert meta["node_kind"] == "leaf"
        assert meta["chunk_kind"] == "clause"
        
        # Убедимся что clause_uid НЕ в metadata
        assert "clause_uid" not in meta

    def test_leaf_chunk_without_effective_uid_uses_raw_uid(self):
        """Если effective_uid нет, raw_uid остаётся в metadata как есть."""
        doc_id = uuid.uuid4()
        
        tree = {
            "root": [
                {
                    "raw_uid": "1.1",
                    "scope": "annex_a",
                    "title": "Payment Terms",
                    "level": 2,
                    "children": [],
                    "own_element_ids": ["elem_1"],
                }
            ]
        }
        
        layout = {
            "elements": [
                {"element_id": "elem_1", "type": "text", "text": "Payment within 30 days.", "page": 2},
            ]
        }
        
        result = ClauseTreeBuilder.build_leaf_chunks(doc_id, tree, layout)
        chunks = result.chunks
        
        assert len(chunks) == 1
        meta = chunks[0]["metadata"]
        
        assert meta["effective_uid"] is None
        assert meta["raw_uid"] == "1.1"
        assert meta["scope"] == "annex_a"

    def test_leaf_node_without_own_element_ids_skipped(self):
        """Leaf без own_element_ids пропускается (не fallback на legacy element_ids)."""
        doc_id = uuid.uuid4()
        
        tree = {
            "root": [
                {
                    "effective_uid": "main_contract::1",
                    "raw_uid": "1",
                    "scope": "main_contract",
                    "title": "Empty clause",
                    "level": 1,
                    "children": [],
                    # own_element_ids отсутствует
                }
            ]
        }
        
        layout = {"elements": []}
        
        result = ClauseTreeBuilder.build_leaf_chunks(doc_id, tree, layout)
        
        assert len(result.chunks) == 0
        assert result.total_leaf_nodes == 1
        assert result.leaf_nodes_without_element_ids == 1

    def test_single_heading_fallback_uses_heading_text(self):
        """Если у leaf только heading element, используем его text как body."""
        doc_id = uuid.uuid4()
        
        tree = {
            "root": [
                {
                    "effective_uid": "main_contract::2",
                    "raw_uid": "2",
                    "scope": "main_contract",
                    "title": "Short Section",
                    "level": 1,
                    "children": [],
                    "own_element_ids": ["elem_heading_only"],
                }
            ]
        }
        
        layout = {
            "elements": [
                {"element_id": "elem_heading_only", "type": "heading", "text": "2. This is the heading", "page": 3},
            ]
        }
        
        result = ClauseTreeBuilder.build_leaf_chunks(doc_id, tree, layout)
        chunks = result.chunks
        
        assert len(chunks) == 1
        assert chunks[0]["text"] == "2. This is the heading"

    def test_multiple_leaves_preserve_identity(self):
        """Несколько leaf nodes — у каждого корректный effective_uid/raw_uid."""
        doc_id = uuid.uuid4()
        
        tree = {
            "root": [
                {
                    "effective_uid": "main_contract::1",
                    "raw_uid": "1",
                    "scope": "main_contract",
                    "title": "First",
                    "level": 1,
                    "children": [],
                    "own_element_ids": ["e1"],
                },
                {
                    "effective_uid": "main_contract::2",
                    "raw_uid": "2",
                    "scope": "main_contract",
                    "title": "Second",
                    "level": 1,
                    "children": [],
                    "own_element_ids": ["e2"],
                },
            ]
        }
        
        layout = {
            "elements": [
                {"element_id": "e1", "type": "text", "text": "Text one.", "page": 1},
                {"element_id": "e2", "type": "text", "text": "Text two.", "page": 2},
            ]
        }
        
        result = ClauseTreeBuilder.build_leaf_chunks(doc_id, tree, layout)
        chunks = result.chunks
        
        assert len(chunks) == 2
        
        assert chunks[0]["metadata"]["effective_uid"] == "main_contract::1"
        assert chunks[0]["metadata"]["raw_uid"] == "1"
        
        assert chunks[1]["metadata"]["effective_uid"] == "main_contract::2"
        assert chunks[1]["metadata"]["raw_uid"] == "2"


class TestSectionChunksCanonicalMetadata:
    """Проверка canonical metadata в section chunks."""

    def test_section_chunk_has_canonical_fields(self):
        """Section chunk metadata содержит effective_uid/raw_uid/scope/node_kind."""
        doc_id = uuid.uuid4()
        
        tree = {
            "root": [
                {
                    "effective_uid": "main_contract::1",
                    "raw_uid": "1",
                    "scope": "main_contract",
                    "title": "General Provisions",
                    "level": 1,
                    "subtree_element_ids": ["e1", "e2"],
                    "children": [
                        {
                            "effective_uid": "main_contract::1.1",
                            "raw_uid": "1.1",
                            "scope": "main_contract",
                            "title": "Definitions",
                            "level": 2,
                            "children": [],
                            "own_element_ids": ["e2"],
                        }
                    ],
                }
            ]
        }
        
        layout = {
            "elements": [
                {"element_id": "e1", "type": "heading", "text": "1. General Provisions", "page": 1},
                {"element_id": "e2", "type": "text", "text": "1.1 Definitions clause body.", "page": 1},
            ]
        }
        
        chunks = ClauseTreeBuilder.build_section_chunks(doc_id, tree, layout)
        
        assert len(chunks) == 1
        
        meta = chunks[0]["metadata"]
        assert meta["effective_uid"] == "main_contract::1"
        assert meta["raw_uid"] == "1"
        assert meta["scope"] == "main_contract"
        assert meta["node_kind"] == "section"
        assert meta["chunk_kind"] == "section"

    def test_section_without_subtree_element_ids_skipped(self):
        """Section node без subtree_element_ids пропускается."""
        doc_id = uuid.uuid4()
        
        tree = {
            "root": [
                {
                    "effective_uid": "main_contract::1",
                    "raw_uid": "1",
                    "scope": "main_contract",
                    "title": "Empty section",
                    "level": 1,
                    # subtree_element_ids отсутствует
                    "children": [],
                }
            ]
        }
        
        layout = {"elements": []}
        
        chunks = ClauseTreeBuilder.build_section_chunks(doc_id, tree, layout)
        
        assert len(chunks) == 0


class TestQualityGateEnforcement:
    """Проверка quality gate блокировки section chunking."""

    def test_section_chunking_blocked_when_quality_gate_false(self):
        """Если quality_gates.section_chunking_allowed=False, section chunks не строятся."""
        doc_id = uuid.uuid4()
        
        tree = {
            "root": [
                {
                    "effective_uid": "main_contract::1",
                    "raw_uid": "1",
                    "scope": "main_contract",
                    "title": "Section One",
                    "level": 1,
                    "subtree_element_ids": ["e1"],
                    "children": [],
                }
            ],
            "structure_diagnostics": {
                "quality_gates": {
                    "section_chunking_allowed": False,
                    "technical_fallback_only": True,
                    "structure_confidence": "low",
                }
            }
        }
        
        layout = {
            "elements": [
                {"element_id": "e1", "type": "text", "text": "Some text.", "page": 1},
            ]
        }
        
        chunks = ClauseTreeBuilder.build_section_chunks(doc_id, tree, layout)
        
        # Quality gate должен заблокировать построение
        assert len(chunks) == 0

    def test_section_chunking_allowed_when_quality_gate_true(self):
        """Если quality_gates.section_chunking_allowed=True, section chunks строятся."""
        doc_id = uuid.uuid4()
        
        tree = {
            "root": [
                {
                    "effective_uid": "main_contract::1",
                    "raw_uid": "1",
                    "scope": "main_contract",
                    "title": "Section One",
                    "level": 1,
                    "subtree_element_ids": ["e1"],
                    "children": [],
                }
            ],
            "structure_diagnostics": {
                "quality_gates": {
                    "section_chunking_allowed": True,
                    "structure_confidence": "high",
                }
            }
        }
        
        layout = {
            "elements": [
                {"element_id": "e1", "type": "text", "text": "Some text.", "page": 1},
            ]
        }
        
        chunks = ClauseTreeBuilder.build_section_chunks(doc_id, tree, layout)
        
        assert len(chunks) == 1

    def test_section_chunking_allowed_when_no_quality_gates(self):
        """Если quality_gates отсутствует, дефолт — разрешить (backward compat)."""
        doc_id = uuid.uuid4()
        
        tree = {
            "root": [
                {
                    "effective_uid": "main_contract::1",
                    "raw_uid": "1",
                    "scope": "main_contract",
                    "title": "Section One",
                    "level": 1,
                    "subtree_element_ids": ["e1"],
                    "children": [],
                }
            ],
            # structure_diagnostics отсутствует
        }
        
        layout = {
            "elements": [
                {"element_id": "e1", "type": "text", "text": "Some text.", "page": 1},
            ]
        }
        
        chunks = ClauseTreeBuilder.build_section_chunks(doc_id, tree, layout)
        
        # Дефолт True — chunks должны построиться
        assert len(chunks) == 1


class TestNoLegacyClauseUid:
    """Убедимся, что clause_uid НЕ читается из tree и НЕ попадает в metadata."""

    def test_no_clause_uid_in_leaf_metadata(self):
        """clause_uid из tree НЕ читается и НЕ попадает в leaf metadata."""
        doc_id = uuid.uuid4()
        
        tree = {
            "root": [
                {
                    "effective_uid": "main_contract::1",
                    "raw_uid": "1",
                    "scope": "main_contract",
                    "clause_uid": "legacy_1",  # legacy поле в tree (может остаться в старых данных)
                    "title": "Clause",
                    "level": 1,
                    "children": [],
                    "own_element_ids": ["e1"],
                }
            ]
        }
        
        layout = {
            "elements": [
                {"element_id": "e1", "type": "text", "text": "Text.", "page": 1},
            ]
        }
        
        result = ClauseTreeBuilder.build_leaf_chunks(doc_id, tree, layout)
        chunks = result.chunks
        
        assert len(chunks) == 1
        meta = chunks[0]["metadata"]
        
        # clause_uid НЕ должен попадать в metadata
        assert "clause_uid" not in meta
        # Только canonical поля
        assert meta["effective_uid"] == "main_contract::1"
        assert meta["raw_uid"] == "1"
        assert meta["scope"] == "main_contract"

        