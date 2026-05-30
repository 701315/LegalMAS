"""
Tests for Phase 11 Extension — Layout Fallback Chunker.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from engine.content.layout_fallback_chunker import (
    build_layout_fallback_chunks,
    _make_fallback_effective_uid,
)

DOC_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _make_layout(elements: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "elements": elements,
        "metadata": {"page_count": 10},
    }


def _el(
    text: str,
    el_type: str = "text",
    page: int = 1,
    element_id: str | None = None,
) -> dict[str, Any]:
    return {
        "element_id": element_id or f"el-{text[:8]}",
        "type": el_type,
        "text": text,
        "page": page,
    }


# ─── Basic functionality ──────────────────────────────────────────────────────

class TestBuildLayoutFallbackChunks:

    def test_empty_layout_returns_empty(self):
        layout = _make_layout([])
        result = build_layout_fallback_chunks(
            doc_id=DOC_ID,
            layout=layout,
        )
        assert result == []

    def test_single_body_element(self):
        layout = _make_layout([
            _el("Some clause text here.", "text", page=1),
        ])
        result = build_layout_fallback_chunks(
            doc_id=DOC_ID,
            layout=layout,
        )
        assert len(result) == 1
        assert "Some clause text" in result[0]["text"]

    def test_heading_starts_new_chunk(self):
        layout = _make_layout([
            _el("1. Definitions", "heading", page=1),
            _el("Term means...", "text", page=1),
            _el("2. Payment", "heading", page=2),
            _el("Payment shall be...", "text", page=2),
        ])
        result = build_layout_fallback_chunks(
            doc_id=DOC_ID,
            layout=layout,
        )
        assert len(result) == 2
        assert "1. Definitions" in result[0]["text"]
        assert "Term means" in result[0]["text"]
        assert "2. Payment" in result[1]["text"]
        assert "Payment shall be" in result[1]["text"]

    def test_body_only_no_headings(self):
        layout = _make_layout([
            _el("First paragraph.", "text", page=1),
            _el("Second paragraph.", "text", page=1),
            _el("Third paragraph.", "text", page=2),
        ])
        result = build_layout_fallback_chunks(
            doc_id=DOC_ID,
            layout=layout,
        )
        # All body → one chunk (if within max_tokens)
        assert len(result) >= 1
        assert "First paragraph" in result[0]["text"]

    def test_chunk_kind_is_layout_fallback(self):
        layout = _make_layout([
            _el("Some text.", "text"),
        ])
        result = build_layout_fallback_chunks(
            doc_id=DOC_ID,
            layout=layout,
        )
        assert len(result) == 1
        meta = result[0].get("metadata") or {}
        assert meta["chunk_kind"] == "layout_fallback"

    def test_retrieval_safe_is_false(self):
        layout = _make_layout([
            _el("Some text.", "text"),
        ])
        result = build_layout_fallback_chunks(
            doc_id=DOC_ID,
            layout=layout,
        )
        meta = result[0].get("metadata") or {}
        assert meta["retrieval_safe"] is False

    def test_prefer_layout_fallback_is_true(self):
        layout = _make_layout([
            _el("Some text.", "text"),
        ])
        result = build_layout_fallback_chunks(
            doc_id=DOC_ID,
            layout=layout,
        )
        meta = result[0].get("metadata") or {}
        assert meta["prefer_layout_fallback"] is True

    def test_is_layout_fallback_flag(self):
        layout = _make_layout([
            _el("Some text.", "text"),
        ])
        result = build_layout_fallback_chunks(
            doc_id=DOC_ID,
            layout=layout,
        )
        meta = result[0].get("metadata") or {}
        assert meta["is_layout_fallback"] is True

    def test_effective_uid_format(self):
        layout = _make_layout([
            _el("Some text.", "text", page=3),
        ])
        result = build_layout_fallback_chunks(
            doc_id=DOC_ID,
            layout=layout,
        )
        meta = result[0].get("metadata") or {}
        uid = meta["effective_uid"]
        assert str(DOC_ID) in uid
        assert "layout_fallback" in uid

    def test_chunk_id_matches_effective_uid(self):
        layout = _make_layout([
            _el("Some text.", "text"),
        ])
        result = build_layout_fallback_chunks(
            doc_id=DOC_ID,
            layout=layout,
        )
        chunk = result[0]
        meta = chunk.get("metadata") or {}
        assert chunk["id"] == meta["effective_uid"]

    def test_segment_id_propagated(self):
        layout = _make_layout([
            _el("Some text.", "text"),
        ])
        result = build_layout_fallback_chunks(
            doc_id=DOC_ID,
            layout=layout,
            segment_id="seg-test-001",
        )
        meta = result[0].get("metadata") or {}
        assert meta["segment_id"] == "seg-test-001"

    def test_segment_type_propagated(self):
        layout = _make_layout([
            _el("Some text.", "text"),
        ])
        result = build_layout_fallback_chunks(
            doc_id=DOC_ID,
            layout=layout,
            segment_type="appendix",
        )
        meta = result[0].get("metadata") or {}
        assert meta["segment_type"] == "appendix"

    def test_empty_text_elements_skipped(self):
        layout = _make_layout([
            _el("", "text"),
            _el("   ", "text"),
            _el("Real content.", "text"),
        ])
        result = build_layout_fallback_chunks(
            doc_id=DOC_ID,
            layout=layout,
        )
        assert len(result) == 1
        assert "Real content" in result[0]["text"]

    def test_page_range_in_metadata(self):
        layout = _make_layout([
            _el("1. Definitions", "heading", page=2),
            _el("Term means...", "text", page=3),
        ])
        result = build_layout_fallback_chunks(
            doc_id=DOC_ID,
            layout=layout,
        )
        assert len(result) == 1
        meta = result[0].get("metadata") or {}
        assert meta["start_page"] == 2
        assert meta["end_page"] == 3

    def test_max_tokens_splits_large_body(self):
        # Создаём много текста чтобы превысить max_tokens
        long_text = "Word " * 200  # ~200 tokens
        layout = _make_layout([
            _el("1. Section", "heading", page=1),
            _el(long_text, "text", page=1),
            _el(long_text, "text", page=2),
            _el(long_text, "text", page=3),
        ])
        result = build_layout_fallback_chunks(
            doc_id=DOC_ID,
            layout=layout,
            max_tokens=300,
        )
        # При max_tokens=300 и ~200 tokens на элемент
        # heading + first body ≈ 200 tokens → ok
        # добавление second body → ~400 → split
        assert len(result) >= 2

    def test_multiple_headings_multiple_chunks(self):
        layout = _make_layout([
            _el("1. Definitions", "heading", page=1),
            _el("Term A means...", "text", page=1),
            _el("2. Obligations", "heading", page=2),
            _el("Party shall...", "text", page=2),
            _el("3. Payment", "heading", page=3),
            _el("Amount is...", "text", page=3),
        ])
        result = build_layout_fallback_chunks(
            doc_id=DOC_ID,
            layout=layout,
        )
        assert len(result) == 3

    def test_listitem_type_treated_as_body(self):
        layout = _make_layout([
            _el("1. Section", "heading", page=1),
            _el("First item", "listitem", page=1),
            _el("Second item", "listitem", page=1),
        ])
        result = build_layout_fallback_chunks(
            doc_id=DOC_ID,
            layout=layout,
        )
        assert len(result) == 1
        assert "First item" in result[0]["text"]
        assert "Second item" in result[0]["text"]

    def test_unknown_element_type_treated_as_body(self):
        layout = _make_layout([
            _el("Some unknown type text.", "unknown_type", page=1),
        ])
        result = build_layout_fallback_chunks(
            doc_id=DOC_ID,
            layout=layout,
        )
        assert len(result) == 1

    def test_has_summary(self):
        layout = _make_layout([
            _el("1. Definitions", "heading", page=1),
            _el("Term means X.", "text", page=1),
        ])
        result = build_layout_fallback_chunks(
            doc_id=DOC_ID,
            layout=layout,
        )
        meta = result[0].get("metadata") or {}
        assert meta.get("summary") is not None

    def test_heading_only_no_body(self):
        layout = _make_layout([
            _el("1. Definitions", "heading", page=1),
        ])
        result = build_layout_fallback_chunks(
            doc_id=DOC_ID,
            layout=layout,
        )
        assert len(result) == 1
        assert "1. Definitions" in result[0]["text"]

    def test_non_dict_elements_skipped(self):
        layout = {
            "elements": [
                "not a dict",
                None,
                _el("Real text.", "text"),
            ],
            "metadata": {},
        }
        result = build_layout_fallback_chunks(
            doc_id=DOC_ID,
            layout=layout,
        )
        assert len(result) == 1

    def test_no_elements_key_in_layout(self):
        layout = {"metadata": {"page_count": 5}}
        result = build_layout_fallback_chunks(
            doc_id=DOC_ID,
            layout=layout,
        )
        assert result == []

    def test_chunk_indices_unique(self):
        layout = _make_layout([
            _el("H1", "heading", page=1),
            _el("Body1", "text", page=1),
            _el("H2", "heading", page=2),
            _el("Body2", "text", page=2),
            _el("H3", "heading", page=3),
            _el("Body3", "text", page=3),
        ])
        result = build_layout_fallback_chunks(
            doc_id=DOC_ID,
            layout=layout,
        )
        ids = [ch["id"] for ch in result]
        assert len(ids) == len(set(ids)), "All chunk IDs must be unique"


# ─── effective_uid helper ─────────────────────────────────────────────────────

class TestMakeFallbackEffectiveUid:

    def test_format_with_page(self):
        uid = _make_fallback_effective_uid(DOC_ID, page=3, index=0)
        assert str(DOC_ID) in uid
        assert "layout_fallback" in uid
        assert "3" in uid
        assert "0" in uid

    def test_format_without_page(self):
        uid = _make_fallback_effective_uid(DOC_ID, page=None, index=0)
        assert "layout_fallback" in uid
        assert "0" in uid

    def test_different_indices_different_uids(self):
        uid1 = _make_fallback_effective_uid(DOC_ID, page=1, index=0)
        uid2 = _make_fallback_effective_uid(DOC_ID, page=1, index=1)
        assert uid1 != uid2

    def test_different_pages_different_uids(self):
        uid1 = _make_fallback_effective_uid(DOC_ID, page=1, index=0)
        uid2 = _make_fallback_effective_uid(DOC_ID, page=2, index=0)
        assert uid1 != uid2


# ─── Integration: Mode C в SegmentChunkBuilderV2 ──────────────────────────────

class TestSegmentChunkBuilderModeCIntegration:
    """
    Проверяет что SegmentChunkBuilderV2 при Mode C
    использует layout fallback builder.
    """

    def _make_layout_for_builder(self) -> dict[str, Any]:
        return {
            "elements": [
                {
                    "element_id": "el-001",
                    "type": "heading",
                    "text": "1. Definitions",
                    "page": 1,
                },
                {
                    "element_id": "el-002",
                    "type": "text",
                    "text": "Term means the following...",
                    "page": 1,
                },
            ],
            "metadata": {"page_count": 5},
        }

    def _make_mode_c_plan(self, segment_id: str) -> Any:
        from services.structure._models._analysis import RecommendedChunkingMode
        from services.structure.chunk_planner import (
            ChunkingModeDecision,
            ChunkingTokenParams,
            FileChunkPlan,
            SegmentChunkPlan,
            TOKENS_MODE_C,
        )

        seg_plan = SegmentChunkPlan(
            segment_id=segment_id,
            segment_type="contract",
            mode=RecommendedChunkingMode.LAYOUT_FALLBACK,
            token_params=TOKENS_MODE_C,
            allow_section_chunks=False,
            allow_subclause_splitting=False,
            drop_technical_fallback_nodes=True,
            retrieval_safe=False,
            fallback_fragment_ratio=0.95,
        )

        decision = ChunkingModeDecision(
            mode=RecommendedChunkingMode.LAYOUT_FALLBACK,
            retrieval_safe=False,
            reason="test mode C",
            token_params=TOKENS_MODE_C,
            allow_section_chunks=False,
            allow_subclause_splitting=False,
            drop_technical_fallback_nodes=True,
            prefer_layout_fallback=True,
        )

        return FileChunkPlan(
            document_id="doc-001",
            mode_decision=decision,
            segment_plans=(seg_plan,),
        )

    def test_mode_c_uses_layout_fallback_chunks(self):
        from types import SimpleNamespace
        from engine.content.segment_chunk_builder_v2 import SegmentChunkBuilderV2

        segment_id = "seg-primary-001"
        tree = {
            "document_id": str(DOC_ID),
            "root": [],
            "structure_diagnostics": {},
        }
        layout = self._make_layout_for_builder()

        class DummyStore:
            def get_json(self, ref: str) -> Any:
                return tree

        segment = SimpleNamespace(
            segment_id=segment_id,
            segment_type="contract",
            segment_title="Main Contract",
            segment_order=0,
            is_primary=True,
            page_start=1,
            page_end=5,
            segment_clause_tree_ref="tree-ref",
        )

        plan = self._make_mode_c_plan(segment_id)
        store = DummyStore()
        builder = SegmentChunkBuilderV2(store=store)

        snapshot = builder._build_single_segment_snapshot(
            document_id=DOC_ID,
            document_version_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
            segment=segment,
            layout=layout,
            layout_meta=layout.get("metadata") or {},
            layout_ref="layout-ref",
            file_graph_ref="graph-ref",
            params={},
            target_tokens=300,
            max_tokens=800,
            overlap_ratio=0.15,
            total_pages=5,
            chunk_plan=plan,
        )

        # Проверяем что snapshot построен через layout fallback
        assert snapshot.degraded is True
        assert snapshot.degradation_reason == "layout_fallback_chunker_used"

        # clause_chunks содержат layout fallback chunks
        assert len(snapshot.clause_chunks) > 0

        first_chunk_meta = snapshot.clause_chunks[0].get("metadata") or {}
        assert first_chunk_meta.get("chunk_kind") == "layout_fallback"
        assert first_chunk_meta.get("is_layout_fallback") is True
        assert first_chunk_meta.get("retrieval_safe") is False

        # section и subclause пусты
        assert snapshot.section_chunks == []
        assert snapshot.subclause_chunks == []

        # planning metadata корректна
        assert snapshot.planning is not None
        assert snapshot.planning["mode"] == "layout_fallback"
        assert snapshot.planning["prefer_layout_fallback"] is True


        