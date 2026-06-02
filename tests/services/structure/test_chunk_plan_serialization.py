"""
Tests for FileChunkPlan serialization roundtrip.

Проверяет что to_dict() + from_dict() = identity для всех типов.
Это критично для Вариант B: structure_builder сохраняет plan,
chunk_builder загружает и десериализует.
"""

from __future__ import annotations

import pytest

from services.structure._models._analysis import RecommendedChunkingMode
from services.structure.chunk_planner._types import (
    ChunkingModeDecision,
    ChunkingTokenParams,
    FileChunkPlan,
    SegmentChunkPlan,
    TOKENS_MODE_A,
    TOKENS_MODE_B,
)


# ─── ChunkingTokenParams ──────────────────────────────────────────────────────

class TestChunkingTokenParamsFromDict:

    def test_roundtrip_defaults(self) -> None:
        params = ChunkingTokenParams()
        restored = ChunkingTokenParams.from_dict(params.to_dict())
        assert restored == params

    def test_roundtrip_custom(self) -> None:
        params = ChunkingTokenParams(
            target_tokens=250,
            max_tokens=700,
            overlap_ratio=0.20,
        )
        restored = ChunkingTokenParams.from_dict(params.to_dict())
        assert restored == params

    def test_from_dict_tolerant_missing_fields(self) -> None:
        """Пустой dict → production defaults."""
        restored = ChunkingTokenParams.from_dict({})
        assert restored.target_tokens == 300
        assert restored.max_tokens == 800
        assert restored.overlap_ratio == 0.15

    def test_from_dict_partial(self) -> None:
        restored = ChunkingTokenParams.from_dict({"target_tokens": 200})
        assert restored.target_tokens == 200
        assert restored.max_tokens == 800  # default


# ─── ChunkingModeDecision ─────────────────────────────────────────────────────

class TestChunkingModeDecisionFromDict:

    def _make_decision(
        self,
        mode: RecommendedChunkingMode = RecommendedChunkingMode.STRUCTURE_FIRST,
    ) -> ChunkingModeDecision:
        return ChunkingModeDecision(
            mode=mode,
            retrieval_safe=True,
            reason="test reason",
            token_params=TOKENS_MODE_A,
            allow_section_chunks=True,
            allow_subclause_splitting=True,
            drop_technical_fallback_nodes=False,
            prefer_layout_fallback=False,
            warnings=("warn1", "warn2"),
        )

    def test_roundtrip_structure_first(self) -> None:
        decision = self._make_decision(RecommendedChunkingMode.STRUCTURE_FIRST)
        restored = ChunkingModeDecision.from_dict(decision.to_dict())
        assert restored == decision

    def test_roundtrip_hybrid(self) -> None:
        decision = self._make_decision(RecommendedChunkingMode.HYBRID)
        restored = ChunkingModeDecision.from_dict(decision.to_dict())
        assert restored.mode == RecommendedChunkingMode.HYBRID
        assert restored.retrieval_safe is True

    def test_roundtrip_layout_fallback(self) -> None:
        decision = ChunkingModeDecision(
            mode=RecommendedChunkingMode.LAYOUT_FALLBACK,
            retrieval_safe=False,
            reason="layout fallback",
            token_params=TOKENS_MODE_B,
            allow_section_chunks=False,
            allow_subclause_splitting=False,
            drop_technical_fallback_nodes=True,
            prefer_layout_fallback=True,
            warnings=(),
        )
        restored = ChunkingModeDecision.from_dict(decision.to_dict())
        assert restored == decision

    def test_warnings_preserved(self) -> None:
        decision = self._make_decision()
        restored = ChunkingModeDecision.from_dict(decision.to_dict())
        assert restored.warnings == ("warn1", "warn2")

    def test_token_params_preserved(self) -> None:
        decision = self._make_decision()
        restored = ChunkingModeDecision.from_dict(decision.to_dict())
        assert restored.token_params == TOKENS_MODE_A


# ─── SegmentChunkPlan ─────────────────────────────────────────────────────────

class TestSegmentChunkPlanFromDict:

    def _make_plan(
        self,
        segment_id: str | None = "seg-001",
        fallback_ratio: float = 0.0,
        mode: RecommendedChunkingMode = RecommendedChunkingMode.STRUCTURE_FIRST,
    ) -> SegmentChunkPlan:
        return SegmentChunkPlan(
            segment_id=segment_id,
            segment_type="contract",
            mode=mode,
            token_params=TOKENS_MODE_A,
            allow_section_chunks=True,
            allow_subclause_splitting=True,
            drop_technical_fallback_nodes=False,
            retrieval_safe=True,
            fallback_fragment_ratio=fallback_ratio,
            warnings=(),
        )

    def test_roundtrip_clean_segment(self) -> None:
        plan = self._make_plan()
        restored = SegmentChunkPlan.from_dict(plan.to_dict())
        assert restored.segment_id == "seg-001"
        assert restored.mode == RecommendedChunkingMode.STRUCTURE_FIRST
        assert restored.retrieval_safe is True

    def test_roundtrip_degraded_segment(self) -> None:
        plan = self._make_plan(
            fallback_ratio=0.95,
            mode=RecommendedChunkingMode.LAYOUT_FALLBACK,
        )
        restored = SegmentChunkPlan.from_dict(plan.to_dict())
        assert restored.fallback_fragment_ratio == pytest.approx(0.95, abs=1e-4)
        assert restored.is_full_fallback is True
        assert restored.has_significant_fallback is True

    def test_roundtrip_none_segment_id(self) -> None:
        plan = self._make_plan(segment_id=None)
        restored = SegmentChunkPlan.from_dict(plan.to_dict())
        assert restored.segment_id is None

    def test_computed_properties_not_stored(self) -> None:
        """is_full_fallback и has_significant_fallback — computed, не хранятся."""
        plan = self._make_plan(fallback_ratio=0.95)
        data = plan.to_dict()
        # to_dict сохраняет их для audit, но from_dict не читает
        assert "is_full_fallback" in data
        restored = SegmentChunkPlan.from_dict(data)
        assert restored.is_full_fallback is True  # computed from fallback_ratio


# ─── FileChunkPlan ────────────────────────────────────────────────────────────

class TestFileChunkPlanFromDict:

    def _make_plan(self) -> FileChunkPlan:
        mode_decision = ChunkingModeDecision(
            mode=RecommendedChunkingMode.STRUCTURE_FIRST,
            retrieval_safe=True,
            reason="all segments clean",
            token_params=TOKENS_MODE_A,
            allow_section_chunks=True,
            allow_subclause_splitting=True,
            drop_technical_fallback_nodes=False,
            prefer_layout_fallback=False,
        )
        seg_plan_1 = SegmentChunkPlan(
            segment_id="seg-001",
            segment_type="contract",
            mode=RecommendedChunkingMode.STRUCTURE_FIRST,
            token_params=TOKENS_MODE_A,
            allow_section_chunks=True,
            allow_subclause_splitting=True,
            drop_technical_fallback_nodes=False,
            retrieval_safe=True,
            fallback_fragment_ratio=0.0,
        )
        seg_plan_2 = SegmentChunkPlan(
            segment_id="seg-002",
            segment_type="appendix",
            mode=RecommendedChunkingMode.HYBRID,
            token_params=TOKENS_MODE_B,
            allow_section_chunks=False,
            allow_subclause_splitting=False,
            drop_technical_fallback_nodes=True,
            retrieval_safe=False,
            fallback_fragment_ratio=0.85,
        )
        return FileChunkPlan(
            document_id="doc-test-001",
            mode_decision=mode_decision,
            segment_plans=(seg_plan_1, seg_plan_2),
        )

    def test_roundtrip_full(self) -> None:
        plan = self._make_plan()
        data = plan.to_dict()
        restored = FileChunkPlan.from_dict(data)

        assert restored.document_id == "doc-test-001"
        assert restored.mode_decision.mode == RecommendedChunkingMode.STRUCTURE_FIRST
        assert len(restored.segment_plans) == 2

    def test_segment_plans_order_preserved(self) -> None:
        plan = self._make_plan()
        restored = FileChunkPlan.from_dict(plan.to_dict())
        assert restored.segment_plans[0].segment_id == "seg-001"
        assert restored.segment_plans[1].segment_id == "seg-002"

    def test_computed_properties_correct_after_roundtrip(self) -> None:
        plan = self._make_plan()
        restored = FileChunkPlan.from_dict(plan.to_dict())
        # seg-002 retrieval_safe=False → overall_retrieval_safe=False
        assert restored.overall_retrieval_safe is False
        # seg-002 mode=HYBRID ≠ LAYOUT_FALLBACK → any_layout_fallback=False
        assert restored.any_layout_fallback is False
        # seg-002 fallback=0.85 < 0.90 → all_segments_full_fallback=False
        assert restored.all_segments_full_fallback is False

    def test_plan_for_segment_works_after_roundtrip(self) -> None:
        plan = self._make_plan()
        restored = FileChunkPlan.from_dict(plan.to_dict())
        seg2 = restored.plan_for_segment("seg-002")
        assert seg2 is not None
        assert seg2.segment_type == "appendix"
        assert seg2.fallback_fragment_ratio == pytest.approx(0.85, abs=1e-4)

    def test_schema_version_preserved(self) -> None:
        plan = self._make_plan()
        restored = FileChunkPlan.from_dict(plan.to_dict())
        assert restored.schema_version == "1.0"

    def test_empty_segment_plans(self) -> None:
        """FileChunkPlan без сегментов — edge case."""
        mode_decision = ChunkingModeDecision(
            mode=RecommendedChunkingMode.STRUCTURE_FIRST,
            retrieval_safe=True,
            reason="no segments",
            token_params=TOKENS_MODE_A,
            allow_section_chunks=True,
            allow_subclause_splitting=True,
            drop_technical_fallback_nodes=False,
            prefer_layout_fallback=False,
        )
        plan = FileChunkPlan(
            document_id="doc-empty",
            mode_decision=mode_decision,
            segment_plans=(),
        )
        restored = FileChunkPlan.from_dict(plan.to_dict())
        assert len(restored.segment_plans) == 0
        # Без segment_plans — берём из mode_decision
        assert restored.overall_retrieval_safe is True

    def test_from_dict_missing_document_id_raises(self) -> None:
        plan = self._make_plan()
        data = plan.to_dict()
        del data["document_id"]
        with pytest.raises(KeyError):
            FileChunkPlan.from_dict(data)

    def test_from_dict_invalid_mode_raises(self) -> None:
        plan = self._make_plan()
        data = plan.to_dict()
        data["mode_decision"]["mode"] = "INVALID_MODE_XYZ"
        with pytest.raises(ValueError):
            FileChunkPlan.from_dict(data)


            