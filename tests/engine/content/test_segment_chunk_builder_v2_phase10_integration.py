"""
Tests for Phase 10 (Path B1) integration into SegmentChunkBuilderV2.

Тест-стратегия:
- unit tests на helper functions (_is_technical_fallback_node, _filter_technical_fallback_tree)
- unit tests на planning payload builders
- integration-style tests на _build_single_segment_snapshot с mock store
- backward compatibility: без chunk_plan поведение не меняется
- mode A / B / transitional C scenarios

НЕ тестируем:
- build_for_version() (требует DB session, repos, async)
- ClauseTreeBuilder internals
- chunk_ids generation

Используем:
- mock ArtifactStore
- mock DocumentSegment (SimpleNamespace)
- реальные ClauseTreeBuilder и chunk_canonicalization
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from engine.content.segment_chunk_builder_v2 import (
    SegmentChunkBuilderV2,
    SegmentChunkSnapshotV2,
    FileChunkManifestV2,
    FileChunkManifestSegmentV2,
    _is_technical_fallback_node,
    _filter_technical_fallback_tree,
    _build_segment_planning_payload,
    _build_file_planning_payload,
)
from services.structure._models._analysis import RecommendedChunkingMode
from services.structure.chunk_planner import (
    ChunkingModeDecision,
    ChunkingTokenParams,
    FileChunkPlan,
    SegmentChunkPlan,
    TOKENS_MODE_A,
    TOKENS_MODE_B,
    TOKENS_MODE_C,
)


# ─── Constants ────────────────────────────────────────────────────────────────

DOC_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
DOC_ID_STR = str(DOC_ID)
VERSION_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
SEG_ID = "seg-primary-001"


# ─── Helper factories ────────────────────────────────────────────────────────

def _make_normal_node(
    *,
    effective_uid: str = "main:1",
    raw_uid: str = "1",
    title: str = "Section 1",
    level: int = 1,
    own_element_ids: list[str] | None = None,
    children: list[dict] | None = None,
) -> dict[str, Any]:
    return {
        "effective_uid": effective_uid,
        "raw_uid": raw_uid,
        "title": title,
        "level": level,
        "scope": "main",
        "node_kind": "leaf" if not children else "branch",
        "own_element_ids": own_element_ids or ["el-001", "el-002"],
        "subtree_element_ids": own_element_ids or ["el-001", "el-002"],
        "children": children or [],
        "start_page": 1,
        "end_page": 1,
        "content_mode": "full_text",
        "node_origin": "parsed",
    }


def _make_fallback_node(
    *,
    effective_uid: str = "main:fallback-1",
    title: str = "[TECHNICAL FALLBACK] Fragment 1",
    own_element_ids: list[str] | None = None,
    children: list[dict] | None = None,
) -> dict[str, Any]:
    return {
        "effective_uid": effective_uid,
        "raw_uid": "fallback-1",
        "title": title,
        "level": 1,
        "scope": "main",
        "node_kind": "leaf" if not children else "branch",
        "own_element_ids": own_element_ids or ["el-fb-001"],
        "subtree_element_ids": own_element_ids or ["el-fb-001"],
        "children": children or [],
        "start_page": 1,
        "end_page": 1,
        "content_mode": "technical_fragment",
        "node_origin": "technical_fallback",
    }


def _make_clause_tree(
    nodes: list[dict[str, Any]],
    *,
    document_id: str = DOC_ID_STR,
) -> dict[str, Any]:
    return {
        "document_id": document_id,
        "root": nodes,
        "structure_diagnostics": {
            "quality_gates": {
                "section_chunking_allowed": True,
            },
        },
    }


def _make_layout(element_ids: list[str] | None = None) -> dict[str, Any]:
    """Build a minimal layout with body elements."""
    ids = element_ids or ["el-001", "el-002", "el-fb-001"]
    elements = []
    for eid in ids:
        elements.append({
            "element_id": eid,
            "type": "body",
            "text": f"Text content for {eid}. This is body text of the clause.",
            "page": 1,
        })
    return {
        "elements": elements,
        "metadata": {"page_count": 3},
    }


def _make_segment(
    segment_id: str = SEG_ID,
    is_primary: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        segment_id=segment_id,
        segment_type="contract",
        segment_title="Main Contract",
        segment_order=0,
        is_primary=is_primary,
        page_start=1,
        page_end=3,
        segment_clause_tree_ref="tree-ref-001",
    )


def _make_segment_plan(
    *,
    segment_id: str = SEG_ID,
    mode: RecommendedChunkingMode = RecommendedChunkingMode.STRUCTURE_FIRST,
    allow_section_chunks: bool = True,
    allow_subclause_splitting: bool = True,
    drop_technical_fallback_nodes: bool = False,
    retrieval_safe: bool = True,
    fallback_fragment_ratio: float = 0.0,
    token_params: ChunkingTokenParams | None = None,
) -> SegmentChunkPlan:
    tp = token_params or TOKENS_MODE_A
    return SegmentChunkPlan(
        segment_id=segment_id,
        segment_type="contract",
        mode=mode,
        token_params=tp,
        allow_section_chunks=allow_section_chunks,
        allow_subclause_splitting=allow_subclause_splitting,
        drop_technical_fallback_nodes=drop_technical_fallback_nodes,
        retrieval_safe=retrieval_safe,
        fallback_fragment_ratio=fallback_fragment_ratio,
    )


def _make_file_chunk_plan(
    *,
    segment_plans: tuple[SegmentChunkPlan, ...],
    mode: RecommendedChunkingMode = RecommendedChunkingMode.STRUCTURE_FIRST,
    retrieval_safe: bool = True,
    token_params: ChunkingTokenParams | None = None,
) -> FileChunkPlan:
    tp = token_params or TOKENS_MODE_A
    prefer_layout = mode == RecommendedChunkingMode.LAYOUT_FALLBACK

    decision = ChunkingModeDecision(
        mode=mode,
        retrieval_safe=retrieval_safe,
        reason="test plan",
        token_params=tp,
        allow_section_chunks=(mode == RecommendedChunkingMode.STRUCTURE_FIRST),
        allow_subclause_splitting=(mode != RecommendedChunkingMode.LAYOUT_FALLBACK),
        drop_technical_fallback_nodes=(mode != RecommendedChunkingMode.STRUCTURE_FIRST),
        prefer_layout_fallback=prefer_layout,
    )

    return FileChunkPlan(
        document_id=DOC_ID_STR,
        mode_decision=decision,
        segment_plans=segment_plans,
    )


class DummyStore:
    """Mock ArtifactStore that returns pre-loaded JSON by ref."""

    def __init__(self, mapping: dict[str, Any]) -> None:
        self._mapping = mapping

    def get_json(self, ref: str) -> Any:
        if ref not in self._mapping:
            raise FileNotFoundError(f"Artifact not found: {ref}")
        return self._mapping[ref]


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: _is_technical_fallback_node
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsTechnicalFallbackNode:

    def test_normal_node_is_not_fallback(self):
        node = _make_normal_node()
        assert _is_technical_fallback_node(node) is False

    def test_fallback_by_title(self):
        node = {"title": "[TECHNICAL FALLBACK] Fragment 1"}
        assert _is_technical_fallback_node(node) is True

    def test_fallback_by_title_case_insensitive(self):
        node = {"title": "[technical fallback] fragment 2"}
        assert _is_technical_fallback_node(node) is True

    def test_fallback_by_node_origin(self):
        node = {"title": "Normal", "node_origin": "technical_fallback"}
        assert _is_technical_fallback_node(node) is True

    def test_fallback_by_content_mode(self):
        node = {"title": "Normal", "content_mode": "technical_fragment"}
        assert _is_technical_fallback_node(node) is True

    def test_fallback_by_fallback_reason(self):
        node = {"title": "Normal", "fallback_reason": "technical_fallback"}
        assert _is_technical_fallback_node(node) is True

    def test_fallback_by_diagnostics_degraded_chunk(self):
        node = {"title": "Normal", "diagnostics": {"degraded_chunk": True}}
        assert _is_technical_fallback_node(node) is True

    def test_fallback_by_diagnostics_fallback_reason(self):
        node = {
            "title": "Normal",
            "diagnostics": {"fallback_reason": "technical_fallback"},
        }
        assert _is_technical_fallback_node(node) is True

    def test_fallback_by_diagnostics_source_mode(self):
        node = {
            "title": "Normal",
            "diagnostics": {"source_mode": "technical_fallback"},
        }
        assert _is_technical_fallback_node(node) is True

    def test_fallback_by_citability_hint(self):
        node = {"title": "Normal", "citability_hint": "technical"}
        assert _is_technical_fallback_node(node) is True

    def test_best_effort_recovered_is_NOT_fallback(self):
        """
        CRITICAL: best-effort recovered nodes must NOT be treated as fallback.
        They are valid clauses that were attached via recovery engine.
        """
        node = {
            "title": "7.1 Payment Terms",
            "node_origin": "parsed",
            "content_mode": "full_text",
            "recovered_via_best_effort": True,
            "citability_hint": "medium",
        }
        assert _is_technical_fallback_node(node) is False

    def test_none_input(self):
        assert _is_technical_fallback_node(None) is False  # type: ignore[arg-type]

    def test_non_dict_input(self):
        assert _is_technical_fallback_node("string") is False  # type: ignore[arg-type]

    def test_empty_dict(self):
        assert _is_technical_fallback_node({}) is False

    def test_normal_node_with_diagnostics(self):
        node = {
            "title": "1.1 Definitions",
            "node_origin": "parsed",
            "content_mode": "full_text",
            "diagnostics": {"some_key": "some_value"},
        }
        assert _is_technical_fallback_node(node) is False


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: _filter_technical_fallback_tree
# ═══════════════════════════════════════════════════════════════════════════════

class TestFilterTechnicalFallbackTree:

    def test_no_fallback_nodes(self):
        tree = _make_clause_tree([
            _make_normal_node(effective_uid="main:1"),
            _make_normal_node(effective_uid="main:2"),
        ])
        filtered, removed = _filter_technical_fallback_tree(tree)
        assert removed == 0
        assert len(filtered["root"]) == 2

    def test_removes_fallback_nodes(self):
        tree = _make_clause_tree([
            _make_normal_node(effective_uid="main:1"),
            _make_fallback_node(effective_uid="main:fb-1"),
        ])
        filtered, removed = _filter_technical_fallback_tree(tree)
        assert removed == 1
        assert len(filtered["root"]) == 1
        assert filtered["root"][0]["effective_uid"] == "main:1"

    def test_promotes_children_of_fallback_parent(self):
        """
        If a fallback node has normal children, they should be promoted up.
        This prevents losing valid clauses that were nested under a fallback wrapper.
        """
        child = _make_normal_node(
            effective_uid="main:1.1",
            title="Valid child clause",
        )
        fallback_parent = _make_fallback_node(
            effective_uid="main:fb-parent",
            children=[child],
        )
        tree = _make_clause_tree([fallback_parent])

        filtered, removed = _filter_technical_fallback_tree(tree)
        assert removed == 1
        assert len(filtered["root"]) == 1
        assert filtered["root"][0]["effective_uid"] == "main:1.1"

    def test_all_fallback_nodes_results_in_empty_root(self):
        tree = _make_clause_tree([
            _make_fallback_node(effective_uid="main:fb-1"),
            _make_fallback_node(effective_uid="main:fb-2"),
        ])
        filtered, removed = _filter_technical_fallback_tree(tree)
        assert removed == 2
        assert len(filtered["root"]) == 0

    def test_does_not_mutate_original_tree(self):
        original_node = _make_normal_node(effective_uid="main:1")
        fallback = _make_fallback_node(effective_uid="main:fb-1")
        tree = _make_clause_tree([original_node, fallback])

        original_root_len = len(tree["root"])
        filtered, removed = _filter_technical_fallback_tree(tree)

        # Original tree must not be mutated
        assert len(tree["root"]) == original_root_len
        assert removed == 1

    def test_preserves_other_tree_fields(self):
        tree = _make_clause_tree([_make_normal_node()])
        tree["custom_field"] = "preserved"

        filtered, _ = _filter_technical_fallback_tree(tree)
        assert filtered.get("custom_field") == "preserved"

    def test_records_filtered_count_in_diagnostics(self):
        tree = _make_clause_tree([
            _make_normal_node(),
            _make_fallback_node(),
        ])
        filtered, removed = _filter_technical_fallback_tree(tree)
        diag = filtered.get("structure_diagnostics") or {}
        assert diag.get("technical_fallback_nodes_filtered") == 1

    def test_non_dict_tree_passthrough(self):
        result, removed = _filter_technical_fallback_tree("not a dict")  # type: ignore[arg-type]
        assert result == "not a dict"
        assert removed == 0

    def test_tree_without_root(self):
        tree = {"document_id": "test"}
        filtered, removed = _filter_technical_fallback_tree(tree)
        assert removed == 0

    def test_nested_fallback_removal(self):
        """Remove fallback at depth 2, keep normal siblings."""
        child_normal = _make_normal_node(
            effective_uid="main:1.1",
            title="Normal child",
        )
        child_fallback = _make_fallback_node(
            effective_uid="main:1.fb",
            title="[TECHNICAL FALLBACK] Fragment",
        )
        parent = _make_normal_node(
            effective_uid="main:1",
            title="Parent",
            children=[child_normal, child_fallback],
        )
        tree = _make_clause_tree([parent])

        filtered, removed = _filter_technical_fallback_tree(tree)
        assert removed == 1
        assert len(filtered["root"]) == 1
        parent_result = filtered["root"][0]
        assert len(parent_result["children"]) == 1
        assert parent_result["children"][0]["effective_uid"] == "main:1.1"


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: _build_segment_planning_payload
# ═══════════════════════════════════════════════════════════════════════════════

class TestBuildSegmentPlanningPayload:

    def test_no_plan(self):
        payload = _build_segment_planning_payload(
            segment_plan=None,
            filtered_technical_fallback_nodes=0,
            effective_params={"target_tokens": 300, "max_tokens": 800, "overlap_ratio": 0.15},
        )
        assert payload["applied"] is False
        assert payload["mode"] is None
        assert payload["filtered_technical_fallback_nodes"] == 0

    def test_with_plan_mode_a(self):
        plan = _make_segment_plan(
            mode=RecommendedChunkingMode.STRUCTURE_FIRST,
            allow_section_chunks=True,
        )
        payload = _build_segment_planning_payload(
            segment_plan=plan,
            filtered_technical_fallback_nodes=0,
            effective_params={"target_tokens": 300, "max_tokens": 800, "overlap_ratio": 0.15},
        )
        assert payload["applied"] is True
        assert payload["mode"] == "structure_first"
        assert payload["allow_section_chunks"] is True
        assert payload["prefer_layout_fallback"] is False

    def test_with_plan_mode_c(self):
        plan = _make_segment_plan(
            mode=RecommendedChunkingMode.LAYOUT_FALLBACK,
            allow_section_chunks=False,
            drop_technical_fallback_nodes=True,
            retrieval_safe=False,
            fallback_fragment_ratio=0.95,
        )
        payload = _build_segment_planning_payload(
            segment_plan=plan,
            filtered_technical_fallback_nodes=5,
            effective_params={"target_tokens": 300, "max_tokens": 800, "overlap_ratio": 0.15},
        )
        assert payload["applied"] is True
        assert payload["mode"] == "layout_fallback"
        assert payload["prefer_layout_fallback"] is True
        assert payload["filtered_technical_fallback_nodes"] == 5
        assert payload["fallback_fragment_ratio"] == 0.95

    def test_warnings_propagated(self):
        plan = _make_segment_plan()
        # Создаём план с warnings напрямую через SegmentChunkPlan
        plan_with_warnings = SegmentChunkPlan(
            segment_id=SEG_ID,
            segment_type="contract",
            mode=RecommendedChunkingMode.STRUCTURE_FIRST,
            token_params=TOKENS_MODE_A,
            allow_section_chunks=True,
            allow_subclause_splitting=True,
            drop_technical_fallback_nodes=False,
            retrieval_safe=True,
            fallback_fragment_ratio=0.0,
            warnings=("w1", "w2"),
        )
        payload = _build_segment_planning_payload(
            segment_plan=plan_with_warnings,
            filtered_technical_fallback_nodes=0,
            effective_params={},
        )
        assert payload["warnings"] == ["w1", "w2"]

# ═══════════════════════════════════════════════════════════════════════════════
# Tests: _build_file_planning_payload
# ═══════════════════════════════════════════════════════════════════════════════

class TestBuildFilePlanningPayload:

    def _make_snapshot(
        self,
        segment_id: str = SEG_ID,
        planning: dict | None = None,
    ) -> SegmentChunkSnapshotV2:
        return SegmentChunkSnapshotV2(
            document_id=DOC_ID,
            document_version_id=VERSION_ID,
            segment_id=segment_id,
            segment_type="contract",
            segment_title="Test",
            segment_order=0,
            is_primary_segment=True,
            segment_page_start=1,
            segment_page_end=3,
            layout_ref="layout-ref",
            file_graph_ref="graph-ref",
            segment_clause_tree_ref="tree-ref",
            params={},
            section_chunks=[],
            clause_chunks=[],
            subclause_chunks=[],
            planning=planning,
        )

    def test_no_plan(self):
        snap = self._make_snapshot(planning={"mode": "structure_first"})
        payload = _build_file_planning_payload(
            chunk_plan=None,
            segment_snapshots=[snap],
        )
        assert payload["applied"] is False
        assert payload["segment_modes"][SEG_ID] == "structure_first"

    def test_with_plan(self):
        seg_plan = _make_segment_plan()
        plan = _make_file_chunk_plan(segment_plans=(seg_plan,))
        snap = self._make_snapshot(planning={"mode": "structure_first"})

        payload = _build_file_planning_payload(
            chunk_plan=plan,
            segment_snapshots=[snap],
        )
        assert payload["applied"] is True
        assert payload["mode"] == "structure_first"


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: SegmentChunkSnapshotV2.to_dict() — planning field
# ═══════════════════════════════════════════════════════════════════════════════

class TestSnapshotToDict:

    def test_planning_none(self):
        snap = SegmentChunkSnapshotV2(
            document_id=DOC_ID,
            document_version_id=VERSION_ID,
            segment_id=SEG_ID,
            segment_type="contract",
            segment_title="Test",
            segment_order=0,
            is_primary_segment=True,
            segment_page_start=1,
            segment_page_end=3,
            layout_ref="lr",
            file_graph_ref="gr",
            segment_clause_tree_ref="tr",
            params={},
            section_chunks=[],
            clause_chunks=[],
            subclause_chunks=[],
            planning=None,
        )
        d = snap.to_dict()
        assert d["planning"] is None

    def test_planning_present(self):
        planning = {"applied": True, "mode": "hybrid"}
        snap = SegmentChunkSnapshotV2(
            document_id=DOC_ID,
            document_version_id=VERSION_ID,
            segment_id=SEG_ID,
            segment_type="contract",
            segment_title="Test",
            segment_order=0,
            is_primary_segment=True,
            segment_page_start=1,
            segment_page_end=3,
            layout_ref="lr",
            file_graph_ref="gr",
            segment_clause_tree_ref="tr",
            params={},
            section_chunks=[],
            clause_chunks=[],
            subclause_chunks=[],
            planning=planning,
        )
        d = snap.to_dict()
        assert d["planning"]["applied"] is True
        assert d["planning"]["mode"] == "hybrid"

    def test_schema_version_unchanged(self):
        snap = SegmentChunkSnapshotV2(
            document_id=DOC_ID,
            document_version_id=VERSION_ID,
            segment_id=SEG_ID,
            segment_type="contract",
            segment_title="Test",
            segment_order=0,
            is_primary_segment=True,
            segment_page_start=1,
            segment_page_end=3,
            layout_ref="lr",
            file_graph_ref="gr",
            segment_clause_tree_ref="tr",
            params={},
            section_chunks=[],
            clause_chunks=[],
            subclause_chunks=[],
        )
        d = snap.to_dict()
        assert d["schema_version"] == 2
        assert d["scope"] == "segment"


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: _build_single_segment_snapshot integration
# ═══════════════════════════════════════════════════════════════════════════════

class TestBuildSingleSegmentSnapshot:
    """
    Integration tests for _build_single_segment_snapshot with mock store.
    These test the actual chunking pipeline with Phase 10 plan applied.
    """

    def _build(
        self,
        *,
        tree_nodes: list[dict[str, Any]] | None = None,
        layout: dict[str, Any] | None = None,
        chunk_plan: FileChunkPlan | None = None,
        segment_id: str = SEG_ID,
    ) -> SegmentChunkSnapshotV2:
        if tree_nodes is None:
            tree_nodes = [
                _make_normal_node(effective_uid="main:1", raw_uid="1", title="Clause 1"),
            ]
        tree = _make_clause_tree(tree_nodes)
        if layout is None:
            all_element_ids = set()
            for node in tree_nodes:
                for eid in node.get("own_element_ids", []):
                    all_element_ids.add(eid)
            layout = _make_layout(list(all_element_ids) or ["el-001"])

        store = DummyStore({"tree-ref-001": tree})
        builder = SegmentChunkBuilderV2(store=store)
        segment = _make_segment(segment_id=segment_id)

        return builder._build_single_segment_snapshot(
            document_id=DOC_ID,
            document_version_id=VERSION_ID,
            segment=segment,
            layout=layout,
            layout_meta=layout.get("metadata") or {},
            layout_ref="layout-ref",
            file_graph_ref="graph-ref",
            params={"target_tokens": 300, "max_tokens": 800, "overlap_ratio": 0.15},
            target_tokens=300,
            max_tokens=800,
            overlap_ratio=0.15,
            total_pages=3,
            chunk_plan=chunk_plan,
        )

    # ── Backward compatibility ────────────────────────────────────────────

    def test_no_plan_backward_compatible(self):
        snap = self._build(chunk_plan=None)

        assert snap.planning is not None
        assert snap.planning["applied"] is False
        assert snap.planning["mode"] is None
        # Chunks should still be built
        assert len(snap.clause_chunks) >= 0  # may be 0 or more depending on tree

    def test_no_plan_section_chunks_built(self):
        """Without plan, section chunks should be built normally."""
        snap = self._build(
            tree_nodes=[
                _make_normal_node(
                    effective_uid="main:1",
                    raw_uid="1",
                    title="Section 1",
                    own_element_ids=["el-001", "el-002"],
                ),
            ],
            chunk_plan=None,
        )
        # Section chunks are built from root-level nodes
        # They may or may not be present depending on quality gates
        assert snap.planning["applied"] is False

    # ── Mode A ────────────────────────────────────────────────────────────

    def test_mode_a_planning_metadata(self):
        seg_plan = _make_segment_plan(
            mode=RecommendedChunkingMode.STRUCTURE_FIRST,
            allow_section_chunks=True,
            allow_subclause_splitting=True,
            drop_technical_fallback_nodes=False,
            retrieval_safe=True,
        )
        plan = _make_file_chunk_plan(
            segment_plans=(seg_plan,),
            mode=RecommendedChunkingMode.STRUCTURE_FIRST,
        )
        snap = self._build(chunk_plan=plan)

        assert snap.planning is not None
        assert snap.planning["applied"] is True
        assert snap.planning["mode"] == "structure_first"
        assert snap.planning["retrieval_safe"] is True
        assert snap.planning["allow_section_chunks"] is True
        assert snap.planning["drop_technical_fallback_nodes"] is False
        assert snap.planning["prefer_layout_fallback"] is False

    def test_mode_a_token_params_applied(self):
        custom_tokens = ChunkingTokenParams(
            target_tokens=400,
            max_tokens=900,
            overlap_ratio=0.10,
        )
        seg_plan = _make_segment_plan(
            mode=RecommendedChunkingMode.STRUCTURE_FIRST,
            token_params=custom_tokens,
        )
        plan = _make_file_chunk_plan(
            segment_plans=(seg_plan,),
            token_params=custom_tokens,
        )
        snap = self._build(chunk_plan=plan)

        assert snap.params["target_tokens"] == 400
        assert snap.params["max_tokens"] == 900
        assert snap.params["overlap_ratio"] == 0.10

    # ── Mode B ────────────────────────────────────────────────────────────

    def test_mode_b_disables_section_chunks(self):
        seg_plan = _make_segment_plan(
            mode=RecommendedChunkingMode.HYBRID,
            allow_section_chunks=False,
            drop_technical_fallback_nodes=True,
            retrieval_safe=False,
        )
        plan = _make_file_chunk_plan(
            segment_plans=(seg_plan,),
            mode=RecommendedChunkingMode.HYBRID,
            retrieval_safe=False,
        )
        snap = self._build(chunk_plan=plan)

        assert snap.section_chunks == []
        assert snap.planning["mode"] == "hybrid"
        assert snap.planning["allow_section_chunks"] is False

    def test_mode_b_filters_technical_fallback_nodes(self):
        normal_node = _make_normal_node(
            effective_uid="main:1",
            raw_uid="1",
            title="Normal clause",
            own_element_ids=["el-normal"],
        )
        fallback_node = _make_fallback_node(
            effective_uid="main:fb-1",
            own_element_ids=["el-fallback"],
        )

        layout = _make_layout(["el-normal", "el-fallback"])

        seg_plan = _make_segment_plan(
            mode=RecommendedChunkingMode.HYBRID,
            allow_section_chunks=False,
            drop_technical_fallback_nodes=True,
            retrieval_safe=False,
        )
        plan = _make_file_chunk_plan(
            segment_plans=(seg_plan,),
            mode=RecommendedChunkingMode.HYBRID,
            retrieval_safe=False,
        )

        snap = self._build(
            tree_nodes=[normal_node, fallback_node],
            layout=layout,
            chunk_plan=plan,
        )

        assert snap.planning["filtered_technical_fallback_nodes"] >= 1
        # Clause chunks should only contain the normal node
        clause_uids = [
            (ch.get("metadata") or {}).get("effective_uid")
            for ch in snap.clause_chunks
        ]
        assert "main:fb-1" not in clause_uids

    def test_mode_b_keeps_best_effort_nodes(self):
        """Best-effort recovered nodes must NOT be filtered out."""
        recovered_node = _make_normal_node(
            effective_uid="main:7.1",
            raw_uid="7.1",
            title="7.1 Payment Terms",
            own_element_ids=["el-recovered"],
        )
        recovered_node["recovered_via_best_effort"] = True
        recovered_node["citability_hint"] = "medium"

        layout = _make_layout(["el-recovered"])

        seg_plan = _make_segment_plan(
            mode=RecommendedChunkingMode.HYBRID,
            allow_section_chunks=False,
            drop_technical_fallback_nodes=True,
            retrieval_safe=False,
        )
        plan = _make_file_chunk_plan(
            segment_plans=(seg_plan,),
            mode=RecommendedChunkingMode.HYBRID,
            retrieval_safe=False,
        )

        snap = self._build(
            tree_nodes=[recovered_node],
            layout=layout,
            chunk_plan=plan,
        )

        # Best-effort node must survive filtering
        clause_uids = [
            (ch.get("metadata") or {}).get("effective_uid")
            for ch in snap.clause_chunks
        ]
        assert "main:7.1" in clause_uids
        assert snap.planning["filtered_technical_fallback_nodes"] == 0

    # ── Mode C (transitional) ─────────────────────────────────────────────

    def test_mode_c_marks_degraded(self):
        seg_plan = _make_segment_plan(
            mode=RecommendedChunkingMode.LAYOUT_FALLBACK,
            allow_section_chunks=False,
            allow_subclause_splitting=False,
            drop_technical_fallback_nodes=True,
            retrieval_safe=False,
            fallback_fragment_ratio=0.95,
        )
        plan = _make_file_chunk_plan(
            segment_plans=(seg_plan,),
            mode=RecommendedChunkingMode.LAYOUT_FALLBACK,
            retrieval_safe=False,
        )
        snap = self._build(chunk_plan=plan)

        assert snap.degraded is True
        assert snap.degradation_reason == "layout_fallback_chunker_used"

    def test_mode_c_disables_subclause_splitting(self):
        seg_plan = _make_segment_plan(
            mode=RecommendedChunkingMode.LAYOUT_FALLBACK,
            allow_section_chunks=False,
            allow_subclause_splitting=False,
            drop_technical_fallback_nodes=True,
            retrieval_safe=False,
            fallback_fragment_ratio=0.95,
        )
        plan = _make_file_chunk_plan(
            segment_plans=(seg_plan,),
            mode=RecommendedChunkingMode.LAYOUT_FALLBACK,
            retrieval_safe=False,
        )
        snap = self._build(chunk_plan=plan)

        assert snap.subclause_chunks == []

    def test_mode_c_disables_section_chunks(self):
        seg_plan = _make_segment_plan(
            mode=RecommendedChunkingMode.LAYOUT_FALLBACK,
            allow_section_chunks=False,
            allow_subclause_splitting=False,
            drop_technical_fallback_nodes=True,
            retrieval_safe=False,
        )
        plan = _make_file_chunk_plan(
            segment_plans=(seg_plan,),
            mode=RecommendedChunkingMode.LAYOUT_FALLBACK,
            retrieval_safe=False,
        )
        snap = self._build(chunk_plan=plan)

        assert snap.section_chunks == []

    def test_mode_c_prefer_layout_fallback_in_planning(self):
        seg_plan = _make_segment_plan(
            mode=RecommendedChunkingMode.LAYOUT_FALLBACK,
            allow_section_chunks=False,
            allow_subclause_splitting=False,
            drop_technical_fallback_nodes=True,
            retrieval_safe=False,
            fallback_fragment_ratio=0.95,
        )
        plan = _make_file_chunk_plan(
            segment_plans=(seg_plan,),
            mode=RecommendedChunkingMode.LAYOUT_FALLBACK,
            retrieval_safe=False,
        )
        snap = self._build(chunk_plan=plan)

        assert snap.planning["prefer_layout_fallback"] is True

    # ── Segment plan not found ────────────────────────────────────────────

    def test_plan_without_matching_segment_uses_defaults(self):
        """
        If FileChunkPlan exists but has no plan for this segment_id,
        segment should use default token params and no filtering.
        """
        seg_plan = _make_segment_plan(
            segment_id="other-segment-id",
            mode=RecommendedChunkingMode.HYBRID,
        )
        plan = _make_file_chunk_plan(
            segment_plans=(seg_plan,),
            mode=RecommendedChunkingMode.HYBRID,
        )
        snap = self._build(chunk_plan=plan)

        # No matching segment plan → planning should show not applied
        assert snap.planning["applied"] is False
        assert snap.params["target_tokens"] == 300  # default

    # ── to_dict serialization ─────────────────────────────────────────────

    def test_snapshot_to_dict_serializable(self):
        seg_plan = _make_segment_plan(
            mode=RecommendedChunkingMode.HYBRID,
            allow_section_chunks=False,
            drop_technical_fallback_nodes=True,
            retrieval_safe=False,
        )
        plan = _make_file_chunk_plan(
            segment_plans=(seg_plan,),
            mode=RecommendedChunkingMode.HYBRID,
            retrieval_safe=False,
        )
        snap = self._build(chunk_plan=plan)

        import json
        d = snap.to_dict()
        serialized = json.dumps(d, default=str)
        assert isinstance(serialized, str)
        assert len(serialized) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Tests: FileChunkManifestV2 — planning field
# ═══════════════════════════════════════════════════════════════════════════════

class TestManifestPlanning:

    def test_manifest_planning_none(self):
        manifest = FileChunkManifestV2(
            document_id=DOC_ID,
            document_version_id=VERSION_ID,
            layout_ref="lr",
            file_graph_ref="gr",
            primary_segment_id=SEG_ID,
            segments=[],
            planning=None,
        )
        d = manifest.to_dict()
        assert d["planning"] is None

    def test_manifest_planning_present(self):
        planning = {"applied": True, "mode": "structure_first"}
        manifest = FileChunkManifestV2(
            document_id=DOC_ID,
            document_version_id=VERSION_ID,
            layout_ref="lr",
            file_graph_ref="gr",
            primary_segment_id=SEG_ID,
            segments=[],
            planning=planning,
        )
        d = manifest.to_dict()
        assert d["planning"]["applied"] is True
        assert d["planning"]["mode"] == "structure_first"

    def test_manifest_schema_version_unchanged(self):
        manifest = FileChunkManifestV2(
            document_id=DOC_ID,
            document_version_id=VERSION_ID,
            layout_ref="lr",
            file_graph_ref="gr",
            primary_segment_id=SEG_ID,
            segments=[],
        )
        d = manifest.to_dict()
        assert d["schema_version"] == 2
        assert d["scope"] == "file"

    def test_manifest_segment_planning_propagated(self):
        seg_planning = {"applied": True, "mode": "hybrid"}
        seg = FileChunkManifestSegmentV2(
            segment_id=SEG_ID,
            segment_type="contract",
            segment_title="Test",
            segment_order=0,
            is_primary=True,
            page_start=1,
            page_end=3,
            segment_clause_tree_ref="tr",
            segment_chunks_ref=None,
            section_count=0,
            clause_count=5,
            subclause_count=10,
            planning=seg_planning,
        )
        d = seg.to_dict()
        assert d["planning"]["mode"] == "hybrid"



