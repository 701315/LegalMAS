"""
Tests for P3b: Honest Degraded Contract.

Проверяет:
1. _is_tree_technical_fallback_only() — три независимых сигнала
2. _remark_as_technical_fragments() — корректность перемаркировки
3. Integration: degraded tree без plan → technical_fragment chunks
"""

from __future__ import annotations

import pytest

from engine.content.segment_chunk_builder_v2 import (
    _is_tree_technical_fallback_only,
    _remark_as_technical_fragments,
)


# ─── _is_tree_technical_fallback_only ────────────────────────────────────────

class TestIsTreeTechnicalFallbackOnly:

    def _clean_tree(self) -> dict:
        """Дерево без признаков технического fallback."""
        return {
            "root": [
                {
                    "title": "1. Предмет договора",
                    "node_origin": "heading",
                    "content_mode": "structured",
                    "children": [],
                }
            ],
            "structure_diagnostics": {},
        }

    def _degraded_tree_signal1(self) -> dict:
        """Сигнал 1: явный флаг technical_fallback_only."""
        return {
            "root": [],
            "structure_diagnostics": {
                "technical_fallback_only": True,
            },
        }

    def _degraded_tree_signal2(self) -> dict:
        """Сигнал 2: technical_fallback_contract."""
        return {
            "root": [],
            "structure_diagnostics": {
                "technical_fallback_contract": {
                    "fallback_nodes_are_semantic": False,
                }
            },
        }

    def _degraded_tree_signal3(self) -> dict:
        """Сигнал 3: все root nodes — technical fallback."""
        return {
            "root": [
                {
                    "title": "[TECHNICAL FALLBACK] Fragment 1",
                    "node_origin": "technical_fallback",
                    "content_mode": "technical_fragment",
                    "children": [],
                },
                {
                    "title": "[TECHNICAL FALLBACK] Fragment 2",
                    "node_origin": "technical_fallback",
                    "content_mode": "technical_fragment",
                    "children": [],
                },
            ],
            "structure_diagnostics": {},
        }

    def test_clean_tree_is_not_fallback(self) -> None:
        assert _is_tree_technical_fallback_only(self._clean_tree()) is False

    def test_signal1_explicit_flag(self) -> None:
        assert _is_tree_technical_fallback_only(self._degraded_tree_signal1()) is True

    def test_signal2_contract(self) -> None:
        assert _is_tree_technical_fallback_only(self._degraded_tree_signal2()) is True

    def test_signal3_all_root_nodes_fallback(self) -> None:
        assert _is_tree_technical_fallback_only(self._degraded_tree_signal3()) is True

    def test_mixed_tree_is_not_fallback(self) -> None:
        """Один clean node среди fallback → не считается full fallback."""
        tree = {
            "root": [
                {
                    "title": "[TECHNICAL FALLBACK] Fragment 1",
                    "node_origin": "technical_fallback",
                    "content_mode": "technical_fragment",
                    "children": [],
                },
                {
                    "title": "1. Предмет договора",
                    "node_origin": "heading",
                    "content_mode": "structured",
                    "children": [],
                },
            ],
            "structure_diagnostics": {},
        }
        assert _is_tree_technical_fallback_only(tree) is False

    def test_empty_root_without_flags_is_not_fallback(self) -> None:
        """Пустое дерево без флагов — не деградация (edge case)."""
        tree = {"root": [], "structure_diagnostics": {}}
        assert _is_tree_technical_fallback_only(tree) is False

    def test_non_dict_input_safe(self) -> None:
        assert _is_tree_technical_fallback_only(None) is False  # type: ignore[arg-type]
        assert _is_tree_technical_fallback_only([]) is False  # type: ignore[arg-type]
        assert _is_tree_technical_fallback_only("string") is False  # type: ignore[arg-type]

    def test_signal1_false_does_not_trigger(self) -> None:
        """technical_fallback_only=False не триггерит."""
        tree = {
            "root": [],
            "structure_diagnostics": {"technical_fallback_only": False},
        }
        assert _is_tree_technical_fallback_only(tree) is False

    def test_signal2_true_does_not_trigger(self) -> None:
        """fallback_nodes_are_semantic=True — семантические, не technical."""
        tree = {
            "root": [],
            "structure_diagnostics": {
                "technical_fallback_contract": {
                    "fallback_nodes_are_semantic": True,
                }
            },
        }
        assert _is_tree_technical_fallback_only(tree) is False


# ─── _remark_as_technical_fragments ──────────────────────────────────────────

class TestRemarkAsTechnicalFragments:

    def _make_clause_chunks(self, count: int = 3) -> list[dict]:
        return [
            {
                "id": f"doc:clause-{i}",
                "text": f"Текст пункта {i}. Стороны договорились...",
                "metadata": {
                    "chunk_kind": "clause",
                    "effective_uid": f"1.{i}",
                    "segment_id": "seg-001",
                    "segment_type": "contract",
                    "start_page": i,
                    "end_page": i,
                    "token_count": 50,
                    "retrieval_safe": True,
                },
            }
            for i in range(1, count + 1)
        ]

    def test_chunk_kind_changed(self) -> None:
        chunks = self._make_clause_chunks(3)
        remarked = _remark_as_technical_fragments(chunks)
        assert all(
            ch["metadata"]["chunk_kind"] == "technical_fragment"
            for ch in remarked
        )

    def test_retrieval_safe_false(self) -> None:
        chunks = self._make_clause_chunks(2)
        remarked = _remark_as_technical_fragments(chunks)
        assert all(
            ch["metadata"]["retrieval_safe"] is False
            for ch in remarked
        )

    def test_is_technical_fallback_flag(self) -> None:
        chunks = self._make_clause_chunks(2)
        remarked = _remark_as_technical_fragments(chunks)
        assert all(
            ch["metadata"]["is_technical_fallback"] is True
            for ch in remarked
        )

    def test_chunking_mode_set(self) -> None:
        chunks = self._make_clause_chunks(2)
        remarked = _remark_as_technical_fragments(chunks)
        assert all(
            ch["metadata"]["chunking_mode"] == "technical_fallback"
            for ch in remarked
        )

    def test_text_preserved(self) -> None:
        """Текст чанка не должен меняться."""
        chunks = self._make_clause_chunks(2)
        original_texts = [ch["text"] for ch in chunks]
        remarked = _remark_as_technical_fragments(chunks)
        remarked_texts = [ch["text"] for ch in remarked]
        assert remarked_texts == original_texts

    def test_id_preserved(self) -> None:
        chunks = self._make_clause_chunks(2)
        original_ids = [ch["id"] for ch in chunks]
        remarked = _remark_as_technical_fragments(chunks)
        remarked_ids = [ch["id"] for ch in remarked]
        assert remarked_ids == original_ids

    def test_segment_metadata_preserved(self) -> None:
        """Segment context fields не должны меняться."""
        chunks = self._make_clause_chunks(1)
        remarked = _remark_as_technical_fragments(chunks)
        meta = remarked[0]["metadata"]
        assert meta["segment_id"] == "seg-001"
        assert meta["segment_type"] == "contract"
        assert meta["effective_uid"] == "1.1"
        assert meta["start_page"] == 1

    def test_page_info_preserved(self) -> None:
        chunks = self._make_clause_chunks(2)
        remarked = _remark_as_technical_fragments(chunks)
        for i, ch in enumerate(remarked, start=1):
            assert ch["metadata"]["start_page"] == i
            assert ch["metadata"]["end_page"] == i

    def test_count_preserved(self) -> None:
        chunks = self._make_clause_chunks(5)
        remarked = _remark_as_technical_fragments(chunks)
        assert len(remarked) == 5

    def test_empty_input(self) -> None:
        remarked = _remark_as_technical_fragments([])
        assert remarked == []

    def test_non_dict_items_skipped(self) -> None:
        """Non-dict items тихо пропускаются."""
        chunks = [
            {"id": "x", "text": "text", "metadata": {"chunk_kind": "clause"}},
            "not a dict",
            None,
        ]
        remarked = _remark_as_technical_fragments(chunks)  # type: ignore[arg-type]
        assert len(remarked) == 1
        assert remarked[0]["metadata"]["chunk_kind"] == "technical_fragment"

    def test_original_not_mutated(self) -> None:
        """Оригинальные chunks не должны мутироваться."""
        chunks = self._make_clause_chunks(2)
        original_kind = chunks[0]["metadata"]["chunk_kind"]
        _remark_as_technical_fragments(chunks)
        # Оригинал не изменён
        assert chunks[0]["metadata"]["chunk_kind"] == original_kind



        