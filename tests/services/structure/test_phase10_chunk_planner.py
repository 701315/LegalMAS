"""
Tests for Phase 10 — Chunk Planner.

Тест-стратегия:
- тесты на ChunkingTokenParams validation;
- тесты на ChunkingModeDecision свойства;
- тесты на SegmentChunkPlan свойства;
- тесты на FileChunkPlan properties;
- тесты на plan_chunking() с разными Phase 9 scenarios;
- тесты на graceful degradation (no report, full fallback, etc.);
- тесты на to_dict() сериализацию;
- тесты что plan_chunking() детерминирован.

Для тестов plan_chunking() создаём минимальные stub объекты —
не используем реальный pipeline чтобы тесты были быстрыми и изолированными.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, PropertyMock

from services.structure._models._analysis import (
    CohesionMetrics,
    FileStructureAnalysisResult,
    QualityThresholds,
    QualityWarning,
    QualityWarningCode,
    RecommendedChunkingMode,
    SegmentAnalysisArtifacts,
    StructureMetrics,
    StructureQualityReport,
    WarningSeverity,
)
from services.structure.chunk_planner._types import (
    ChunkingModeDecision,
    ChunkingTokenParams,
    FileChunkPlan,
    SegmentChunkPlan,
    TOKENS_MODE_A,
    TOKENS_MODE_B,
    TOKENS_MODE_C,
)
from services.structure.chunk_planner._planner import plan_chunking


# ─── Fixtures & helpers ───────────────────────────────────────────────────────

DEFAULT_THRESHOLDS = QualityThresholds()

DOC_ID = "test-document-001"
SEG_ID = "seg-primary-001"


def _make_structure_metrics(
    *,
    total_nodes: int = 20,
    fallback_fragment_ratio: float = 0.0,
    orphan_ratio: float = 0.0,
    grammar_violation_ratio: float = 0.0,
    degraded: bool = False,
    technical_fallback_only: bool = False,
    overall_score: float = 0.9,
    retrieval_safe_phase5: bool = True,
) -> StructureMetrics:
    return StructureMetrics(
        total_nodes=total_nodes,
        root_nodes_count=max(1, total_nodes // 5),
        orphans_detected=0,
        orphans_recovered=0,
        orphans_unresolved=0,
        orphan_ratio=orphan_ratio,
        recovery_ratio=1.0,
        fallback_triggered=False,
        total_candidates=total_nodes,
        attached_best_effort=0,
        parent_level_rejected=0,
        deferred_unresolved=0,
        grammar_violation_ratio=grammar_violation_ratio,
        rewrite_ratio=None,
        overall_score=overall_score,
        retrieval_safe_phase5=retrieval_safe_phase5,
        degraded=degraded,
        technical_fallback_only=technical_fallback_only,
        final_mode="structure_first" if not degraded else "technical_fallback",
        quality_gate_mode="normal" if not degraded else "degraded",
        crossref_references_count=0,
        crossref_unresolved_count=0,
        crossref_unresolved_ratio=0.0,
        fallback_fragment_nodes=int(total_nodes * fallback_fragment_ratio),
        fallback_fragment_ratio=fallback_fragment_ratio,
    )


def _make_quality_report(
    *,
    mode: RecommendedChunkingMode = RecommendedChunkingMode.STRUCTURE_FIRST,
    retrieval_safe: bool = True,
    retrieval_safety_score: float = 0.90,
    orphan_ratio: float = 0.0,
    grammar_violation_ratio: float = 0.0,
    fallback_fragment_ratio: float = 0.0,
    thresholds: QualityThresholds | None = None,
    warnings: tuple[QualityWarning, ...] = (),
    total_nodes: int = 20,
) -> StructureQualityReport:
    t = thresholds or DEFAULT_THRESHOLDS
    sm = _make_structure_metrics(
        total_nodes=total_nodes,
        fallback_fragment_ratio=fallback_fragment_ratio,
        orphan_ratio=orphan_ratio,
        grammar_violation_ratio=grammar_violation_ratio,
        overall_score=retrieval_safety_score,
        retrieval_safe_phase5=retrieval_safe,
    )
    return StructureQualityReport(
        document_id=DOC_ID,
        segment_id=SEG_ID,
        orphan_ratio=orphan_ratio,
        grammar_violation_ratio=grammar_violation_ratio,
        rewrite_ratio=None,
        recovery_ratio=1.0,
        retrieval_safety_score=retrieval_safety_score,
        retrieval_safe=retrieval_safe,
        recommended_chunking_mode=mode,
        warnings=warnings,
        structure_metrics=sm,
        cohesion_metrics=CohesionMetrics.unavailable(),
        thresholds=t,
    )


def _make_segment_artifacts(
    *,
    segment_id: str = SEG_ID,
    report: StructureQualityReport | None = None,
) -> SegmentAnalysisArtifacts:
    return SegmentAnalysisArtifacts(
        segment_id=segment_id,
        cohesion_graph=None,
        quality_report=report,
    )


def _make_analysis(
    *,
    document_id: str = DOC_ID,
    segment_artifacts: tuple[SegmentAnalysisArtifacts, ...] = (),
    overall_retrieval_safe: bool = True,
    all_segments_full_fallback: bool = False,
    primary_report: StructureQualityReport | None = None,
) -> FileStructureAnalysisResult:
    """
    Строит mock FileStructureAnalysisResult для тестов.
    Используем MagicMock для file_structure чтобы не поднимать весь pipeline.
    """
    mock_tree = MagicMock()
    mock_tree.document_id = document_id
    mock_tree.segment_id = SEG_ID

    mock_file_structure = MagicMock()
    mock_file_structure.primary_tree = mock_tree

    # Если нет артефактов и есть primary_report — создаём один артефакт
    if not segment_artifacts and primary_report is not None:
        segment_artifacts = (
            _make_segment_artifacts(
                segment_id=SEG_ID,
                report=primary_report,
            ),
        )

    analysis = MagicMock(spec=FileStructureAnalysisResult)
    analysis.file_structure = mock_file_structure
    analysis.segment_artifacts = segment_artifacts
    type(analysis).overall_retrieval_safe = PropertyMock(
        return_value=overall_retrieval_safe
    )
    type(analysis).all_segments_full_fallback = PropertyMock(
        return_value=all_segments_full_fallback
    )

    # primary_artifacts
    if segment_artifacts:
        analysis.primary_artifacts = segment_artifacts[0]
    else:
        analysis.primary_artifacts = None

    return analysis


# ─── ChunkingTokenParams ──────────────────────────────────────────────────────

class TestChunkingTokenParams:

    def test_default_values(self):
        p = ChunkingTokenParams()
        assert p.target_tokens == 300
        assert p.max_tokens == 800
        assert p.overlap_ratio == 0.15

    def test_custom_values(self):
        p = ChunkingTokenParams(
            target_tokens=400,
            max_tokens=1000,
            overlap_ratio=0.20,
        )
        assert p.target_tokens == 400
        assert p.max_tokens == 1000
        assert p.overlap_ratio == 0.20

    def test_invalid_target_tokens_zero(self):
        with pytest.raises(ValueError, match="target_tokens must be > 0"):
            ChunkingTokenParams(target_tokens=0, max_tokens=800)

    def test_invalid_target_tokens_negative(self):
        with pytest.raises(ValueError, match="target_tokens must be > 0"):
            ChunkingTokenParams(target_tokens=-1, max_tokens=800)

    def test_invalid_max_tokens_less_than_target(self):
        with pytest.raises(ValueError, match="max_tokens.*must be >= target_tokens"):
            ChunkingTokenParams(target_tokens=500, max_tokens=300)

    def test_invalid_overlap_ratio_negative(self):
        with pytest.raises(ValueError, match="overlap_ratio must be in"):
            ChunkingTokenParams(overlap_ratio=-0.1)

    def test_invalid_overlap_ratio_too_large(self):
        with pytest.raises(ValueError, match="overlap_ratio must be in"):
            ChunkingTokenParams(overlap_ratio=1.1)

    def test_equal_target_and_max_tokens(self):
        # Допустимо: max == target
        p = ChunkingTokenParams(target_tokens=300, max_tokens=300)
        assert p.target_tokens == 300
        assert p.max_tokens == 300

    def test_to_dict(self):
        p = ChunkingTokenParams(
            target_tokens=300, max_tokens=800, overlap_ratio=0.15
        )
        d = p.to_dict()
        assert d["target_tokens"] == 300
        assert d["max_tokens"] == 800
        assert d["overlap_ratio"] == 0.15

    def test_frozen(self):
        p = ChunkingTokenParams()
        with pytest.raises((AttributeError, TypeError)):
            p.target_tokens = 500  # type: ignore[misc]

    def test_mode_a_defaults(self):
        assert TOKENS_MODE_A.target_tokens == 300
        assert TOKENS_MODE_A.max_tokens == 800
        assert TOKENS_MODE_A.overlap_ratio == 0.15

    def test_mode_b_more_overlap(self):
        # Mode B должен иметь больше overlap чем Mode A
        assert TOKENS_MODE_B.overlap_ratio > TOKENS_MODE_A.overlap_ratio

    def test_mode_b_smaller_max(self):
        # Mode B должен иметь меньший max чем Mode A
        assert TOKENS_MODE_B.max_tokens <= TOKENS_MODE_A.max_tokens


# ─── ChunkingModeDecision ─────────────────────────────────────────────────────

class TestChunkingModeDecision:

    def _make(
        self,
        mode: RecommendedChunkingMode = RecommendedChunkingMode.STRUCTURE_FIRST,
        retrieval_safe: bool = True,
        reason: str = "test reason",
        **kwargs,
    ) -> ChunkingModeDecision:
        defaults = {
            "allow_section_chunks": True,
            "allow_subclause_splitting": True,
            "drop_technical_fallback_nodes": False,
            "prefer_layout_fallback": False,
            "token_params": TOKENS_MODE_A,
        }
        defaults.update(kwargs)
        return ChunkingModeDecision(
            mode=mode,
            retrieval_safe=retrieval_safe,
            reason=reason,
            **defaults,
        )

    def test_structure_first_properties(self):
        d = self._make(mode=RecommendedChunkingMode.STRUCTURE_FIRST)
        assert d.is_structure_first is True
        assert d.is_hybrid is False
        assert d.is_layout_fallback is False

    def test_hybrid_properties(self):
        d = self._make(mode=RecommendedChunkingMode.HYBRID)
        assert d.is_structure_first is False
        assert d.is_hybrid is True
        assert d.is_layout_fallback is False

    def test_layout_fallback_properties(self):
        d = self._make(mode=RecommendedChunkingMode.LAYOUT_FALLBACK)
        assert d.is_structure_first is False
        assert d.is_hybrid is False
        assert d.is_layout_fallback is True

    def test_empty_reason_raises(self):
        with pytest.raises(ValueError, match="reason must not be empty"):
            self._make(reason="")

    def test_frozen(self):
        d = self._make()
        with pytest.raises((AttributeError, TypeError)):
            d.mode = RecommendedChunkingMode.HYBRID  # type: ignore[misc]

    def test_to_dict_contains_required_keys(self):
        d = self._make()
        result = d.to_dict()
        required_keys = {
            "mode", "retrieval_safe", "reason", "token_params",
            "allow_section_chunks", "allow_subclause_splitting",
            "drop_technical_fallback_nodes", "prefer_layout_fallback",
            "warnings",
        }
        assert required_keys.issubset(result.keys())

    def test_to_dict_mode_value(self):
        d = self._make(mode=RecommendedChunkingMode.STRUCTURE_FIRST)
        assert d.to_dict()["mode"] == "structure_first"

    def test_warnings_tuple(self):
        d = self._make(warnings=("w1", "w2"))
        assert d.warnings == ("w1", "w2")
        assert d.to_dict()["warnings"] == ["w1", "w2"]

    def test_empty_warnings(self):
        d = self._make()
        assert d.warnings == ()
        assert d.to_dict()["warnings"] == []


# ─── SegmentChunkPlan ─────────────────────────────────────────────────────────

class TestSegmentChunkPlan:

    def _make(
        self,
        *,
        segment_id: str | None = SEG_ID,
        mode: RecommendedChunkingMode = RecommendedChunkingMode.STRUCTURE_FIRST,
        retrieval_safe: bool = True,
        fallback_fragment_ratio: float = 0.0,
        **kwargs,
    ) -> SegmentChunkPlan:
        defaults = {
            "segment_type": "contract",
            "token_params": TOKENS_MODE_A,
            "allow_section_chunks": True,
            "allow_subclause_splitting": True,
            "drop_technical_fallback_nodes": False,
        }
        defaults.update(kwargs)
        return SegmentChunkPlan(
            segment_id=segment_id,
            mode=mode,
            retrieval_safe=retrieval_safe,
            fallback_fragment_ratio=fallback_fragment_ratio,
            **defaults,
        )

    def test_is_full_fallback_below_threshold(self):
        p = self._make(fallback_fragment_ratio=0.89)
        assert p.is_full_fallback is False

    def test_is_full_fallback_at_threshold(self):
        p = self._make(fallback_fragment_ratio=0.90)
        assert p.is_full_fallback is True

    def test_is_full_fallback_above_threshold(self):
        p = self._make(fallback_fragment_ratio=1.0)
        assert p.is_full_fallback is True

    def test_has_significant_fallback_below(self):
        p = self._make(fallback_fragment_ratio=0.49)
        assert p.has_significant_fallback is False

    def test_has_significant_fallback_at(self):
        p = self._make(fallback_fragment_ratio=0.50)
        assert p.has_significant_fallback is True

    def test_invalid_fallback_ratio_negative(self):
        with pytest.raises(ValueError, match="fallback_fragment_ratio must be in"):
            self._make(fallback_fragment_ratio=-0.1)

    def test_invalid_fallback_ratio_too_large(self):
        with pytest.raises(ValueError, match="fallback_fragment_ratio must be in"):
            self._make(fallback_fragment_ratio=1.1)

    def test_frozen(self):
        p = self._make()
        with pytest.raises((AttributeError, TypeError)):
            p.mode = RecommendedChunkingMode.HYBRID  # type: ignore[misc]

    def test_to_dict_keys(self):
        p = self._make()
        d = p.to_dict()
        required = {
            "segment_id", "segment_type", "mode", "token_params",
            "allow_section_chunks", "allow_subclause_splitting",
            "drop_technical_fallback_nodes", "retrieval_safe",
            "fallback_fragment_ratio", "is_full_fallback",
            "has_significant_fallback", "warnings",
        }
        assert required.issubset(d.keys())

    def test_none_segment_id(self):
        p = self._make(segment_id=None)
        assert p.segment_id is None
        assert p.to_dict()["segment_id"] is None


# ─── FileChunkPlan ────────────────────────────────────────────────────────────

class TestFileChunkPlan:

    def _make_decision(
        self,
        mode: RecommendedChunkingMode = RecommendedChunkingMode.STRUCTURE_FIRST,
        retrieval_safe: bool = True,
    ) -> ChunkingModeDecision:
        flags = {
            RecommendedChunkingMode.STRUCTURE_FIRST: {
                "allow_section_chunks": True,
                "allow_subclause_splitting": True,
                "drop_technical_fallback_nodes": False,
                "prefer_layout_fallback": False,
                "token_params": TOKENS_MODE_A,
            },
            RecommendedChunkingMode.HYBRID: {
                "allow_section_chunks": False,
                "allow_subclause_splitting": True,
                "drop_technical_fallback_nodes": True,
                "prefer_layout_fallback": False,
                "token_params": TOKENS_MODE_B,
            },
            RecommendedChunkingMode.LAYOUT_FALLBACK: {
                "allow_section_chunks": False,
                "allow_subclause_splitting": False,
                "drop_technical_fallback_nodes": True,
                "prefer_layout_fallback": True,
                "token_params": TOKENS_MODE_C,
            },
        }
        f = flags[mode]
        return ChunkingModeDecision(
            mode=mode,
            retrieval_safe=retrieval_safe,
            reason="test",
            **f,
        )

    def _make_seg_plan(
        self,
        segment_id: str = SEG_ID,
        mode: RecommendedChunkingMode = RecommendedChunkingMode.STRUCTURE_FIRST,
        retrieval_safe: bool = True,
        fallback_fragment_ratio: float = 0.0,
    ) -> SegmentChunkPlan:
        return SegmentChunkPlan(
            segment_id=segment_id,
            segment_type="contract",
            mode=mode,
            token_params=TOKENS_MODE_A,
            allow_section_chunks=True,
            allow_subclause_splitting=True,
            drop_technical_fallback_nodes=False,
            retrieval_safe=retrieval_safe,
            fallback_fragment_ratio=fallback_fragment_ratio,
        )

    def test_empty_document_id_raises(self):
        decision = self._make_decision()
        with pytest.raises(ValueError, match="document_id must not be empty"):
            FileChunkPlan(
                document_id="",
                mode_decision=decision,
                segment_plans=(),
            )

    def test_overall_retrieval_safe_no_segments(self):
        decision = self._make_decision(retrieval_safe=True)
        plan = FileChunkPlan(
            document_id=DOC_ID,
            mode_decision=decision,
            segment_plans=(),
        )
        # Нет сегментов → берём из mode_decision
        assert plan.overall_retrieval_safe is True

    def test_overall_retrieval_safe_all_safe(self):
        decision = self._make_decision(retrieval_safe=True)
        seg1 = self._make_seg_plan("seg1", retrieval_safe=True)
        seg2 = self._make_seg_plan("seg2", retrieval_safe=True)
        plan = FileChunkPlan(
            document_id=DOC_ID,
            mode_decision=decision,
            segment_plans=(seg1, seg2),
        )
        assert plan.overall_retrieval_safe is True

    def test_overall_retrieval_safe_one_unsafe(self):
        decision = self._make_decision(retrieval_safe=True)
        seg1 = self._make_seg_plan("seg1", retrieval_safe=True)
        seg2 = self._make_seg_plan("seg2", retrieval_safe=False)
        plan = FileChunkPlan(
            document_id=DOC_ID,
            mode_decision=decision,
            segment_plans=(seg1, seg2),
        )
        # Консервативная политика: один unsafe → всё unsafe
        assert plan.overall_retrieval_safe is False

    def test_any_layout_fallback_false(self):
        decision = self._make_decision()
        seg = self._make_seg_plan(
            mode=RecommendedChunkingMode.STRUCTURE_FIRST
        )
        plan = FileChunkPlan(
            document_id=DOC_ID,
            mode_decision=decision,
            segment_plans=(seg,),
        )
        assert plan.any_layout_fallback is False

    def test_any_layout_fallback_true(self):
        decision = self._make_decision()
        seg = self._make_seg_plan(
            mode=RecommendedChunkingMode.LAYOUT_FALLBACK
        )
        plan = FileChunkPlan(
            document_id=DOC_ID,
            mode_decision=decision,
            segment_plans=(seg,),
        )
        assert plan.any_layout_fallback is True

    def test_all_segments_full_fallback_true(self):
        decision = self._make_decision()
        seg = self._make_seg_plan(fallback_fragment_ratio=0.95)
        plan = FileChunkPlan(
            document_id=DOC_ID,
            mode_decision=decision,
            segment_plans=(seg,),
        )
        assert plan.all_segments_full_fallback is True

    def test_all_segments_full_fallback_mixed(self):
        decision = self._make_decision()
        seg1 = self._make_seg_plan("seg1", fallback_fragment_ratio=0.95)
        seg2 = self._make_seg_plan("seg2", fallback_fragment_ratio=0.20)
        plan = FileChunkPlan(
            document_id=DOC_ID,
            mode_decision=decision,
            segment_plans=(seg1, seg2),
        )
        assert plan.all_segments_full_fallback is False

    def test_all_segments_full_fallback_no_segments(self):
        decision = self._make_decision()
        plan = FileChunkPlan(
            document_id=DOC_ID,
            mode_decision=decision,
            segment_plans=(),
        )
        assert plan.all_segments_full_fallback is False

    def test_plan_for_segment_found(self):
        decision = self._make_decision()
        seg = self._make_seg_plan(segment_id="seg-target")
        plan = FileChunkPlan(
            document_id=DOC_ID,
            mode_decision=decision,
            segment_plans=(seg,),
        )
        result = plan.plan_for_segment("seg-target")
        assert result is seg

    def test_plan_for_segment_not_found(self):
        decision = self._make_decision()
        plan = FileChunkPlan(
            document_id=DOC_ID,
            mode_decision=decision,
            segment_plans=(),
        )
        assert plan.plan_for_segment("nonexistent") is None

    def test_plan_for_segment_none_id(self):
        decision = self._make_decision()
        seg = SegmentChunkPlan(
            segment_id=None,
            segment_type="unknown",
            mode=RecommendedChunkingMode.STRUCTURE_FIRST,
            token_params=TOKENS_MODE_A,
            allow_section_chunks=True,
            allow_subclause_splitting=True,
            drop_technical_fallback_nodes=False,
            retrieval_safe=True,
            fallback_fragment_ratio=0.0,
        )
        plan = FileChunkPlan(
            document_id=DOC_ID,
            mode_decision=decision,
            segment_plans=(seg,),
        )
        assert plan.plan_for_segment(None) is seg

    def test_to_dict_keys(self):
        decision = self._make_decision()
        plan = FileChunkPlan(
            document_id=DOC_ID,
            mode_decision=decision,
            segment_plans=(),
        )
        d = plan.to_dict()
        required = {
            "schema_version", "document_id", "overall_retrieval_safe",
            "any_layout_fallback", "all_segments_full_fallback",
            "mode_decision", "segment_count", "segment_plans",
        }
        assert required.issubset(d.keys())

    def test_frozen(self):
        decision = self._make_decision()
        plan = FileChunkPlan(
            document_id=DOC_ID,
            mode_decision=decision,
            segment_plans=(),
        )
        with pytest.raises((AttributeError, TypeError)):
            plan.document_id = "other"  # type: ignore[misc]


# ─── plan_chunking() ──────────────────────────────────────────────────────────

class TestPlanChunking:

    def test_raises_on_none(self):
        with pytest.raises(ValueError, match="analysis must not be None"):
            plan_chunking(None)  # type: ignore[arg-type]

    def test_mode_a_from_report(self):
        report = _make_quality_report(
            mode=RecommendedChunkingMode.STRUCTURE_FIRST,
            retrieval_safe=True,
            retrieval_safety_score=0.90,
        )
        analysis = _make_analysis(primary_report=report)
        plan = plan_chunking(analysis)

        assert plan.mode_decision.mode == RecommendedChunkingMode.STRUCTURE_FIRST
        assert plan.mode_decision.retrieval_safe is True
        assert plan.mode_decision.allow_section_chunks is True
        assert plan.mode_decision.drop_technical_fallback_nodes is False
        assert plan.mode_decision.prefer_layout_fallback is False

    def test_mode_b_from_report(self):
        report = _make_quality_report(
            mode=RecommendedChunkingMode.HYBRID,
            retrieval_safe=False,
            retrieval_safety_score=0.60,
        )
        analysis = _make_analysis(primary_report=report)
        plan = plan_chunking(analysis)

        assert plan.mode_decision.mode == RecommendedChunkingMode.HYBRID
        assert plan.mode_decision.retrieval_safe is False
        assert plan.mode_decision.allow_section_chunks is False
        assert plan.mode_decision.drop_technical_fallback_nodes is True
        assert plan.mode_decision.prefer_layout_fallback is False

    def test_mode_c_from_report(self):
        report = _make_quality_report(
            mode=RecommendedChunkingMode.LAYOUT_FALLBACK,
            retrieval_safe=False,
            retrieval_safety_score=0.30,
            fallback_fragment_ratio=0.95,
        )
        analysis = _make_analysis(primary_report=report)
        plan = plan_chunking(analysis)

        assert plan.mode_decision.mode == RecommendedChunkingMode.LAYOUT_FALLBACK
        assert plan.mode_decision.retrieval_safe is False
        assert plan.mode_decision.allow_section_chunks is False
        assert plan.mode_decision.drop_technical_fallback_nodes is True
        assert plan.mode_decision.prefer_layout_fallback is True

    def test_no_primary_report_fallback_to_hybrid(self):
        # Нет report → консервативный HYBRID
        analysis = _make_analysis(
            segment_artifacts=(
                _make_segment_artifacts(report=None),
            ),
        )
        plan = plan_chunking(analysis)

        assert plan.mode_decision.mode == RecommendedChunkingMode.HYBRID
        assert plan.mode_decision.retrieval_safe is False
        assert plan.mode_decision.drop_technical_fallback_nodes is True

    def test_no_artifacts_fallback(self):
        # Нет артефактов вообще → HYBRID
        analysis = _make_analysis(segment_artifacts=())
        plan = plan_chunking(analysis)

        assert plan.mode_decision.mode == RecommendedChunkingMode.HYBRID
        assert plan.mode_decision.retrieval_safe is False

    def test_document_id_propagated(self):
        report = _make_quality_report()
        analysis = _make_analysis(
            document_id="my-doc-123",
            primary_report=report,
        )
        plan = plan_chunking(analysis)
        assert plan.document_id == "my-doc-123"

    def test_segment_plans_count(self):
        report = _make_quality_report()
        artifacts = (
            _make_segment_artifacts(segment_id="seg1", report=report),
            _make_segment_artifacts(segment_id="seg2", report=report),
        )
        analysis = _make_analysis(
            segment_artifacts=artifacts,
        )
        analysis.primary_artifacts = artifacts[0]
        plan = plan_chunking(analysis)

        assert len(plan.segment_plans) == 2

    def test_segment_plan_inherits_mode(self):
        report = _make_quality_report(
            mode=RecommendedChunkingMode.STRUCTURE_FIRST,
            retrieval_safe=True,
            retrieval_safety_score=0.90,
        )
        artifacts = (
            _make_segment_artifacts(segment_id="seg1", report=report),
        )
        analysis = _make_analysis(segment_artifacts=artifacts)
        analysis.primary_artifacts = artifacts[0]
        plan = plan_chunking(analysis)

        seg_plan = plan.plan_for_segment("seg1")
        assert seg_plan is not None
        assert seg_plan.mode == RecommendedChunkingMode.STRUCTURE_FIRST

    def test_segment_no_report_inherits_file_mode(self):
        # File-level report = STRUCTURE_FIRST
        # Segment has no report → inherits STRUCTURE_FIRST
        report = _make_quality_report(
            mode=RecommendedChunkingMode.STRUCTURE_FIRST,
            retrieval_safe=True,
            retrieval_safety_score=0.90,
        )
        primary_artifact = _make_segment_artifacts(
            segment_id="seg-primary", report=report
        )
        secondary_artifact = _make_segment_artifacts(
            segment_id="seg-secondary", report=None
        )
        analysis = _make_analysis(
            segment_artifacts=(primary_artifact, secondary_artifact),
        )
        analysis.primary_artifacts = primary_artifact
        plan = plan_chunking(analysis)

        secondary_plan = plan.plan_for_segment("seg-secondary")
        assert secondary_plan is not None
        assert secondary_plan.mode == RecommendedChunkingMode.STRUCTURE_FIRST
        assert "inheriting file-level mode" in secondary_plan.warnings[0]

    def test_high_fallback_ratio_upgrades_to_hybrid(self):
        # Segment report says STRUCTURE_FIRST
        # Но fallback_fragment_ratio=0.70 → planner должен upgrade до HYBRID
        report = _make_quality_report(
            mode=RecommendedChunkingMode.STRUCTURE_FIRST,
            retrieval_safe=True,
            retrieval_safety_score=0.90,
            fallback_fragment_ratio=0.70,  # высокий!
        )
        artifact = _make_segment_artifacts(report=report)
        analysis = _make_analysis(
            segment_artifacts=(artifact,),
        )
        analysis.primary_artifacts = artifact
        plan = plan_chunking(analysis)

        seg_plan = plan.segment_plans[0]
        # Phase 10 должна upgrade до HYBRID из-за высокого fallback ratio
        assert seg_plan.mode == RecommendedChunkingMode.HYBRID
        assert any("upgraded" in w for w in seg_plan.warnings)

    def test_warnings_contain_safety_info_when_unsafe(self):
        report = _make_quality_report(
            mode=RecommendedChunkingMode.HYBRID,
            retrieval_safe=False,
            retrieval_safety_score=0.60,
        )
        analysis = _make_analysis(primary_report=report)
        plan = plan_chunking(analysis)

        # Warnings должны объяснять почему retrieval unsafe
        assert any("retrieval_safe=False" in w for w in plan.mode_decision.warnings)

    def test_warnings_contain_fallback_fragment_info_when_high(self):
        report = _make_quality_report(
            mode=RecommendedChunkingMode.LAYOUT_FALLBACK,
            retrieval_safe=False,
            retrieval_safety_score=0.10,
            fallback_fragment_ratio=0.95,
        )
        analysis = _make_analysis(primary_report=report)
        plan = plan_chunking(analysis)

        # Warnings должны объяснять fallback fragment ratio
        all_warnings = " ".join(plan.mode_decision.warnings)
        assert "fallback_fragment_ratio" in all_warnings

    def test_full_fallback_tree_gets_layout_fallback(self):
        # is_full_fallback=True → ожидаем LAYOUT_FALLBACK
        report = _make_quality_report(
            mode=RecommendedChunkingMode.LAYOUT_FALLBACK,
            retrieval_safe=False,
            retrieval_safety_score=0.05,
            fallback_fragment_ratio=0.95,
        )
        analysis = _make_analysis(primary_report=report)
        plan = plan_chunking(analysis)

        assert plan.mode_decision.mode == RecommendedChunkingMode.LAYOUT_FALLBACK
        assert plan.mode_decision.prefer_layout_fallback is True
        assert plan.overall_retrieval_safe is False

    def test_deterministic_same_input_same_output(self):
        # Одинаковый input → одинаковый output
        report = _make_quality_report(
            mode=RecommendedChunkingMode.STRUCTURE_FIRST,
            retrieval_safe=True,
            retrieval_safety_score=0.90,
        )
        analysis = _make_analysis(primary_report=report)

        plan1 = plan_chunking(analysis)
        plan2 = plan_chunking(analysis)

        assert plan1.mode_decision.mode == plan2.mode_decision.mode
        assert plan1.mode_decision.retrieval_safe == plan2.mode_decision.retrieval_safe
        assert len(plan1.segment_plans) == len(plan2.segment_plans)

    def test_to_dict_serializable(self):
        report = _make_quality_report()
        analysis = _make_analysis(primary_report=report)
        plan = plan_chunking(analysis)

        d = plan.to_dict()
        # Должно быть сериализуемо (нет non-JSON типов)
        import json
        serialized = json.dumps(d)
        assert isinstance(serialized, str)
        assert len(serialized) > 0

    def test_token_params_mode_a(self):
        report = _make_quality_report(
            mode=RecommendedChunkingMode.STRUCTURE_FIRST,
            retrieval_safe=True,
            retrieval_safety_score=0.90,
        )
        analysis = _make_analysis(primary_report=report)
        plan = plan_chunking(analysis)

        assert plan.mode_decision.token_params == TOKENS_MODE_A

    def test_token_params_mode_b(self):
        report = _make_quality_report(
            mode=RecommendedChunkingMode.HYBRID,
            retrieval_safe=False,
            retrieval_safety_score=0.60,
        )
        analysis = _make_analysis(primary_report=report)
        plan = plan_chunking(analysis)

        assert plan.mode_decision.token_params == TOKENS_MODE_B

    def test_token_params_mode_c(self):
        report = _make_quality_report(
            mode=RecommendedChunkingMode.LAYOUT_FALLBACK,
            retrieval_safe=False,
            retrieval_safety_score=0.30,
            fallback_fragment_ratio=0.95,
        )
        analysis = _make_analysis(primary_report=report)
        plan = plan_chunking(analysis)

        assert plan.mode_decision.token_params == TOKENS_MODE_C

    def test_schema_version(self):
        report = _make_quality_report()
        analysis = _make_analysis(primary_report=report)
        plan = plan_chunking(analysis)

        assert plan.schema_version == "1.0"
        assert plan.to_dict()["schema_version"] == "1.0"

    def test_critical_warnings_in_decision(self):
        critical_warning = QualityWarning(
            code=QualityWarningCode.TECHNICAL_FALLBACK_FORCED,
            severity=WarningSeverity.CRITICAL,
            message="technical fallback forced",
            metric="test",
        )
        report = _make_quality_report(
            mode=RecommendedChunkingMode.LAYOUT_FALLBACK,
            retrieval_safe=False,
            retrieval_safety_score=0.10,
            warnings=(critical_warning,),
        )
        analysis = _make_analysis(primary_report=report)
        plan = plan_chunking(analysis)

        # Critical warnings должны попасть в mode_decision warnings
        decision_warnings = " ".join(plan.mode_decision.warnings)
        assert "critical" in decision_warnings.lower()

    def test_orphan_ratio_warning_in_decision(self):
        # Высокий orphan_ratio → должен быть в warnings
        report = _make_quality_report(
            mode=RecommendedChunkingMode.HYBRID,
            retrieval_safe=False,
            retrieval_safety_score=0.60,
            orphan_ratio=0.20,  # > threshold 0.10
        )
        analysis = _make_analysis(primary_report=report)
        plan = plan_chunking(analysis)

        decision_warnings = " ".join(plan.mode_decision.warnings)
        assert "orphan_ratio" in decision_warnings

    def test_grammar_violation_warning_in_decision(self):
        report = _make_quality_report(
            mode=RecommendedChunkingMode.HYBRID,
            retrieval_safe=False,
            retrieval_safety_score=0.60,
            grammar_violation_ratio=0.20,  # > threshold 0.15
        )
        analysis = _make_analysis(primary_report=report)
        plan = plan_chunking(analysis)

        decision_warnings = " ".join(plan.mode_decision.warnings)
        assert "grammar_violation_ratio" in decision_warnings


        