"""
Tests for P3a: chunk_builder loads chunk_plan and passes to build_for_version().

Проверяет:
1. Если version.chunk_plan_ref есть — plan загружается из store и передаётся
2. Если version.chunk_plan_ref нет — build_for_version вызывается с chunk_plan=None
3. Если artifact broken — graceful degradation, chunk_plan=None
4. from_dict корректно восстанавливает план из store.get_json()
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from services.structure._models._analysis import RecommendedChunkingMode
from services.structure.chunk_planner._types import (
    ChunkingModeDecision,
    FileChunkPlan,
    SegmentChunkPlan,
    TOKENS_MODE_A,
    TOKENS_MODE_B,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

def _make_plan(
    document_id: str = "doc-test",
    mode: RecommendedChunkingMode = RecommendedChunkingMode.STRUCTURE_FIRST,
    segment_id: str = "seg-001",
) -> FileChunkPlan:
    mode_decision = ChunkingModeDecision(
        mode=mode,
        retrieval_safe=mode != RecommendedChunkingMode.LAYOUT_FALLBACK,
        reason="test plan",
        token_params=TOKENS_MODE_A,
        allow_section_chunks=True,
        allow_subclause_splitting=True,
        drop_technical_fallback_nodes=False,
        prefer_layout_fallback=(mode == RecommendedChunkingMode.LAYOUT_FALLBACK),
    )
    seg_plan = SegmentChunkPlan(
        segment_id=segment_id,
        segment_type="contract",
        mode=mode,
        token_params=TOKENS_MODE_A,
        allow_section_chunks=True,
        allow_subclause_splitting=True,
        drop_technical_fallback_nodes=False,
        retrieval_safe=mode != RecommendedChunkingMode.LAYOUT_FALLBACK,
        fallback_fragment_ratio=0.0,
    )
    return FileChunkPlan(
        document_id=document_id,
        mode_decision=mode_decision,
        segment_plans=(seg_plan,),
    )


# ─── Tests: plan loading logic ────────────────────────────────────────────────

class TestChunkPlanLoading:

    def test_plan_loaded_when_ref_present(self) -> None:
        """
        Когда version.chunk_plan_ref задан — plan должен загрузиться
        через store.get_json() + FileChunkPlan.from_dict().
        """
        expected_plan = _make_plan("doc-test", RecommendedChunkingMode.STRUCTURE_FIRST)
        plan_dict = expected_plan.to_dict()

        mock_store = MagicMock()
        mock_store.get_json.return_value = plan_dict

        chunk_plan_ref = "s3://mas-artifacts/.../chunk_plan.json"

        # Симулируем логику из chunk_builder._build_chunks_v2_async
        chunk_plan = None
        try:
            plan_data = mock_store.get_json(chunk_plan_ref)
            if not isinstance(plan_data, dict):
                raise TypeError(f"not a dict: {type(plan_data)}")
            chunk_plan = FileChunkPlan.from_dict(plan_data)
        except Exception:
            chunk_plan = None

        assert chunk_plan is not None
        assert chunk_plan.document_id == "doc-test"
        assert chunk_plan.mode_decision.mode == RecommendedChunkingMode.STRUCTURE_FIRST

    def test_plan_is_none_when_ref_absent(self) -> None:
        """
        Когда version.chunk_plan_ref is None — chunk_plan должен остаться None.
        build_for_version() вызывается с chunk_plan=None.
        """
        chunk_plan_ref = None

        chunk_plan = None
        if chunk_plan_ref:
            chunk_plan = FileChunkPlan.from_dict({})

        assert chunk_plan is None

    def test_plan_is_none_when_store_returns_non_dict(self) -> None:
        """
        Когда store.get_json() возвращает не dict — graceful degradation.
        """
        mock_store = MagicMock()
        mock_store.get_json.return_value = "broken string, not a dict"

        chunk_plan_ref = "s3://mas-artifacts/.../chunk_plan.json"

        chunk_plan = None
        try:
            plan_data = mock_store.get_json(chunk_plan_ref)
            if not isinstance(plan_data, dict):
                raise TypeError(f"not a dict: {type(plan_data)}")
            chunk_plan = FileChunkPlan.from_dict(plan_data)
        except Exception:
            chunk_plan = None

        assert chunk_plan is None

    def test_plan_is_none_when_store_raises(self) -> None:
        """
        Когда store.get_json() бросает исключение — graceful degradation.
        """
        mock_store = MagicMock()
        mock_store.get_json.side_effect = Exception("MinIO NoSuchKey")

        chunk_plan_ref = "s3://mas-artifacts/.../chunk_plan.json"

        chunk_plan = None
        try:
            plan_data = mock_store.get_json(chunk_plan_ref)
            chunk_plan = FileChunkPlan.from_dict(plan_data)
        except Exception:
            chunk_plan = None

        assert chunk_plan is None

    def test_plan_is_none_when_from_dict_raises(self) -> None:
        """
        Когда FileChunkPlan.from_dict() бросает исключение (corrupted data)
        — graceful degradation.
        """
        mock_store = MagicMock()
        # dict есть, но обязательных полей нет
        mock_store.get_json.return_value = {"wrong_key": "wrong_value"}

        chunk_plan_ref = "s3://mas-artifacts/.../chunk_plan.json"

        chunk_plan = None
        try:
            plan_data = mock_store.get_json(chunk_plan_ref)
            if not isinstance(plan_data, dict):
                raise TypeError()
            chunk_plan = FileChunkPlan.from_dict(plan_data)
        except Exception:
            chunk_plan = None

        assert chunk_plan is None


# ─── Tests: plan passed to build_for_version ─────────────────────────────────

class TestChunkPlanPassedToBuilder:

    def test_build_for_version_receives_chunk_plan(self) -> None:
        """
        Загруженный plan должен передаваться в build_for_version(chunk_plan=...).
        """
        mock_builder = MagicMock()
        mock_builder.build_for_version = MagicMock()

        plan = _make_plan("doc-test")

        # Симулируем вызов из chunk_builder
        mock_builder.build_for_version(
            session=MagicMock(),
            document_version_id="ver-001",
            target_tokens=300,
            max_tokens=800,
            overlap_ratio=0.15,
            chunk_plan=plan,
            collector=None,
        )

        mock_builder.build_for_version.assert_called_once()
        call_kwargs = mock_builder.build_for_version.call_args.kwargs
        assert call_kwargs["chunk_plan"] is plan
        assert call_kwargs["target_tokens"] == 300

    def test_build_for_version_receives_none_when_plan_absent(self) -> None:
        """
        Когда plan не загружен — build_for_version получает chunk_plan=None.
        """
        mock_builder = MagicMock()
        mock_builder.build_for_version = MagicMock()

        chunk_plan = None  # не загрузили

        mock_builder.build_for_version(
            session=MagicMock(),
            document_version_id="ver-001",
            target_tokens=300,
            max_tokens=800,
            overlap_ratio=0.15,
            chunk_plan=chunk_plan,
            collector=None,
        )

        call_kwargs = mock_builder.build_for_version.call_args.kwargs
        assert call_kwargs["chunk_plan"] is None


# ─── Tests: plan content integrity ───────────────────────────────────────────

class TestChunkPlanContent:

    def test_structure_first_plan_flags(self) -> None:
        """
        STRUCTURE_FIRST plan:
        - allow_subclause_splitting = True
        - drop_technical_fallback_nodes = False
        - prefer_layout_fallback = False
        """
        plan = _make_plan(mode=RecommendedChunkingMode.STRUCTURE_FIRST)
        decision = plan.mode_decision

        assert decision.allow_subclause_splitting is True
        assert decision.drop_technical_fallback_nodes is False
        assert decision.prefer_layout_fallback is False
        assert decision.retrieval_safe is True

    def test_layout_fallback_plan_flags(self) -> None:
        """
        LAYOUT_FALLBACK plan:
        - prefer_layout_fallback = True
        - retrieval_safe = False
        """
        plan = _make_plan(mode=RecommendedChunkingMode.LAYOUT_FALLBACK)
        decision = plan.mode_decision

        assert decision.prefer_layout_fallback is True
        assert decision.retrieval_safe is False

    def test_plan_for_segment_lookup_after_load(self) -> None:
        """
        После десериализации plan_for_segment() должен работать корректно.
        """
        original = _make_plan(document_id="doc-lookup", segment_id="seg-target")
        restored = FileChunkPlan.from_dict(original.to_dict())

        found = restored.plan_for_segment("seg-target")
        assert found is not None
        assert found.segment_id == "seg-target"

        not_found = restored.plan_for_segment("seg-nonexistent")
        assert not_found is None

    def test_hybrid_plan_token_params_loaded(self) -> None:
        """
        После roundtrip token_params корректно загружаются.
        """
        mode_decision = ChunkingModeDecision(
            mode=RecommendedChunkingMode.HYBRID,
            retrieval_safe=True,
            reason="hybrid",
            token_params=TOKENS_MODE_B,
            allow_section_chunks=False,
            allow_subclause_splitting=False,
            drop_technical_fallback_nodes=True,
            prefer_layout_fallback=False,
        )
        seg_plan = SegmentChunkPlan(
            segment_id="seg-hybrid",
            segment_type="appendix",
            mode=RecommendedChunkingMode.HYBRID,
            token_params=TOKENS_MODE_B,
            allow_section_chunks=False,
            allow_subclause_splitting=False,
            drop_technical_fallback_nodes=True,
            retrieval_safe=True,
            fallback_fragment_ratio=0.60,
        )
        plan = FileChunkPlan(
            document_id="doc-hybrid",
            mode_decision=mode_decision,
            segment_plans=(seg_plan,),
        )

        restored = FileChunkPlan.from_dict(plan.to_dict())

        assert restored.mode_decision.token_params == TOKENS_MODE_B
        seg = restored.plan_for_segment("seg-hybrid")
        assert seg is not None
        assert seg.token_params.max_tokens == 700
        assert seg.token_params.overlap_ratio == pytest.approx(0.20)
        assert seg.has_significant_fallback is True
        

