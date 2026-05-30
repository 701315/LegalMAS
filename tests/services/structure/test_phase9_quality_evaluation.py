"""
Tests — Phase 9 Quality Evaluation.

Покрытие:
- data contracts (_analysis.py)
- evaluator (_quality_evaluation.py)
- postbuild orchestrator (_postbuild_analysis.py)
- fallback fragment detection
- graceful degradation
- determinism
"""

from __future__ import annotations

import pytest
from typing import Any
from unittest.mock import patch

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
from services.structure._pipeline._quality_evaluation import (
    evaluate_structure_quality,
    _extract_structure_metrics,
    _extract_cohesion_metrics,
    _generate_warnings,
    _calculate_retrieval_safety_score,
    _select_chunking_mode,
    _is_fallback_fragment_node,
    _compute_fallback_fragment_metrics,
)
from services.structure._pipeline._postbuild_analysis import (
    analyze_segment_tree,
    analyze_file_structure,
    _build_fallback_quality_report,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fake objects
# ═══════════════════════════════════════════════════════════════════════════════

class FakeCrossRefStats:
    def __init__(
        self,
        references_count: int = 20,
        unresolved_count: int = 2,
    ):
        self.references_count = references_count
        self.unresolved_count = unresolved_count


class FakeCrossRefGraph:
    def __init__(
        self,
        document_id: str = "doc_001",
        references_count: int = 20,
        unresolved_count: int = 2,
    ):
        self.document_id = document_id
        self.stats = FakeCrossRefStats(
            references_count=references_count,
            unresolved_count=unresolved_count,
        )
        self.references = []
        self.outgoing_index = {}
        self.incoming_index = {}


class FakeFrozenNode:
    """Обычный (non-fallback) узел."""

    def __init__(
        self,
        effective_uid: str,
        scope: str = "main_contract",
        title: str = "Section 1",
    ):
        self.effective_uid = effective_uid
        self.scope = scope
        self.children = ()
        self.start_page = 1
        self.end_page = 5
        self.title = title
        self.node_origin = "parsed"
        self.content_mode = "normal"
        self.citability = "high"
        self.diagnostics = {}


class FakeFallbackNode:
    """Technical fallback fragment узел."""

    def __init__(
        self,
        effective_uid: str,
        scope: str = "main_contract",
    ):
        self.effective_uid = effective_uid
        self.scope = scope
        self.children = ()
        self.start_page = 1
        self.end_page = 2
        self.title = "[TECHNICAL FALLBACK] Fragment 1"
        self.node_origin = "technical_fallback"
        self.content_mode = "technical_fragment"
        self.citability = "technical"
        self.diagnostics = {
            "fallback_reason": "technical_fallback",
            "source_mode": "pipeline_fallback",
            "degraded_chunk": True,
            "is_technical_fallback": True,
            "fallback_mode": "technical_fallback",
        }


class FakeClauseTree:
    """Минимальный fake ClauseTree для тестов Phase 9."""

    def __init__(
        self,
        document_id: str = "doc_001",
        segment_id: str | None = "seg_001",
        degraded: bool = False,
        root: list | None = None,
        nodes_index: dict | None = None,
        cross_reference_graph: Any = None,
        structure_diagnostics: dict | None = None,
    ):
        self.document_id = document_id
        self.segment_id = segment_id
        self.degraded = degraded
        self.root = root or []
        self.nodes_index = nodes_index or {}
        self.cross_reference_graph = (
            cross_reference_graph
            or FakeCrossRefGraph(document_id=document_id)
        )
        self.structure_diagnostics = structure_diagnostics or {}


def _make_healthy_diagnostics() -> dict:
    return {
        "hierarchy_builder": {
            "fsm_summary": {
                "total_candidates": 55,
                "total_attached": 50,
                "attached_best_effort": 2,
                "attached_as_child": 40,
                "attached_as_root": 5,
                "parent_level_rejected": 1,
                "deferred_total": 3,
                "deferred_unresolved": 0,
            },
            "recovery_audit": {
                "orphans_detected": 3,
                "orphans_recovered": 3,
                "orphans_unresolved": 0,
                "fallback_triggered": False,
            },
            "resolution_audit": {
                "resolution_applied": False,
                "strategy": "none",
                "unresolved_count": 0,
            },
        },
        "structure_confidence": {
            "overall_score": 0.82,
            "retrieval_safe": True,
            "degraded": False,
            "confidence": "high",
        },
        "quality_gates": {
            "quality_gate_mode": "ALLOW_SECTION_CHUNKING",
            "section_chunking_allowed": True,
            "technical_fallback_only": False,
            "final_mode": "semantic_tree",
            "assessment": {
                "overall_score": 0.82,
                "retrieval_safe": True,
            },
        },
    }


def _make_degraded_diagnostics() -> dict:
    return {
        "hierarchy_builder": {
            "fsm_summary": {
                "total_candidates": 20,
                "total_attached": 10,
                "attached_best_effort": 4,
                "attached_as_child": 5,
                "attached_as_root": 1,
                "parent_level_rejected": 3,
                "deferred_total": 5,
                "deferred_unresolved": 3,
            },
            "recovery_audit": {
                "orphans_detected": 5,
                "orphans_recovered": 1,
                "orphans_unresolved": 4,
                "fallback_triggered": True,
                "fallback_mode": "technical_fallback_only",
            },
            "resolution_audit": {
                "resolution_applied": False,
                "strategy": "none",
                "unresolved_count": 0,
            },
        },
        "structure_confidence": {
            "overall_score": 0.35,
            "retrieval_safe": False,
            "degraded": True,
            "confidence": "low",
        },
        "quality_gates": {
            "quality_gate_mode": "BLOCK_AND_FALLBACK",
            "section_chunking_allowed": False,
            "technical_fallback_only": True,
            "final_mode": "technical_fallback",
        },
    }


def _make_fallback_diagnostics() -> dict:
    """Diagnostics для early fallback case (no_headings_in_pass_1)."""
    return {
        "quality_gates": {
            "headings_pre_count": 0,
            "early_fallback_reason": "no_headings_in_pass_1",
            "section_chunking_allowed": False,
            "technical_fallback_only": True,
            "quality_gate_mode": "BLOCK_AND_FALLBACK",
            "final_mode": "technical_fallback",
            "structure_confidence": "LOW",
            "coverage": 0,
        },
        "fallback": {
            "mode": "technical_fallback",
            "reason": "technical_fallback",
            "chunk_count": 1,
        },
    }


def _make_healthy_tree(
    document_id: str = "doc_001",
    segment_id: str = "seg_001",
    total_nodes: int = 50,
) -> FakeClauseTree:
    nodes = {}
    root_nodes = []
    for i in range(total_nodes):
        uid = f"main_contract::{i + 1}"
        node = FakeFrozenNode(effective_uid=uid)
        nodes[uid] = node
        if i < 5:
            root_nodes.append(node)

    return FakeClauseTree(
        document_id=document_id,
        segment_id=segment_id,
        degraded=False,
        root=root_nodes,
        nodes_index=nodes,
        structure_diagnostics=_make_healthy_diagnostics(),
    )


def _make_degraded_tree(
    document_id: str = "doc_002",
    segment_id: str = "seg_002",
) -> FakeClauseTree:
    nodes = {}
    root_nodes = []
    for i in range(10):
        uid = f"main_contract::{i + 1}"
        node = FakeFrozenNode(effective_uid=uid)
        nodes[uid] = node
        if i < 2:
            root_nodes.append(node)

    return FakeClauseTree(
        document_id=document_id,
        segment_id=segment_id,
        degraded=True,
        root=root_nodes,
        nodes_index=nodes,
        structure_diagnostics=_make_degraded_diagnostics(),
    )


def _make_empty_tree(
    document_id: str = "doc_003",
    segment_id: str = "seg_003",
) -> FakeClauseTree:
    return FakeClauseTree(
        document_id=document_id,
        segment_id=segment_id,
        degraded=True,
        root=[],
        nodes_index={},
        structure_diagnostics={
            "structure_confidence": {
                "overall_score": 0.0,
                "degraded": True,
                "retrieval_safe": False,
            },
            "quality_gates": {
                "technical_fallback_only": True,
                "final_mode": "technical_fallback",
                "quality_gate_mode": "BLOCK_AND_FALLBACK",
            },
        },
    )


def _make_full_fallback_tree(
    document_id: str = "doc_fb",
    segment_id: str = "seg_fb",
    total_nodes: int = 1,
) -> FakeClauseTree:
    """Дерево из технических fallback узлов (как в реальных выгрузках)."""
    nodes = {}
    root_nodes = []
    for i in range(total_nodes):
        uid = f"main_contract::{i + 1}"
        node = FakeFallbackNode(effective_uid=uid)
        nodes[uid] = node
        root_nodes.append(node)

    return FakeClauseTree(
        document_id=document_id,
        segment_id=segment_id,
        degraded=True,
        root=root_nodes,
        nodes_index=nodes,
        structure_diagnostics=_make_fallback_diagnostics(),
    )


def _make_mixed_tree(
    document_id: str = "doc_mix",
    segment_id: str = "seg_mix",
    total_nodes: int = 10,
    fallback_nodes: int = 3,
) -> FakeClauseTree:
    """Дерево с mix обычных и fallback узлов."""
    nodes = {}
    root_nodes = []
    for i in range(total_nodes):
        uid = f"main_contract::{i + 1}"
        if i < fallback_nodes:
            node = FakeFallbackNode(effective_uid=uid)
        else:
            node = FakeFrozenNode(effective_uid=uid)
        nodes[uid] = node
        if i < 2:
            root_nodes.append(node)

    return FakeClauseTree(
        document_id=document_id,
        segment_id=segment_id,
        degraded=False,
        root=root_nodes,
        nodes_index=nodes,
        structure_diagnostics=_make_healthy_diagnostics(),
    )


class FakeCohesionStats:
    def __init__(
        self,
        total_edges: int = 30,
        avg_score: float = 0.72,
        strong_boundaries_count: int = 3,
        cohesive_pairs_count: int = 20,
    ):
        self.total_edges = total_edges
        self.avg_score = avg_score
        self.strong_boundaries_count = strong_boundaries_count
        self.cohesive_pairs_count = cohesive_pairs_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_edges": self.total_edges,
            "avg_score": self.avg_score,
            "strong_boundaries_count": self.strong_boundaries_count,
            "cohesive_pairs_count": self.cohesive_pairs_count,
        }


class FakeCohesionGraph:
    def __init__(
        self,
        document_id: str = "doc_001",
        total_edges: int = 30,
        avg_score: float = 0.72,
        strong_boundaries_count: int = 3,
        cohesive_pairs_count: int = 20,
    ):
        self.document_id = document_id
        self.stats = FakeCohesionStats(
            total_edges=total_edges,
            avg_score=avg_score,
            strong_boundaries_count=strong_boundaries_count,
            cohesive_pairs_count=cohesive_pairs_count,
        )
        self.local_edges = ()


class FakeFileStructureResult:
    def __init__(
        self,
        primary_tree: Any = None,
        segment_trees: list | None = None,
    ):
        self.primary_tree = primary_tree or _make_healthy_tree()
        self.segment_trees = segment_trees or [self.primary_tree]


# ═══════════════════════════════════════════════════════════════════════════════
# Tests — Data Contracts
# ═══════════════════════════════════════════════════════════════════════════════

class TestQualityThresholds:

    def test_default_thresholds_valid(self):
        t = QualityThresholds()
        assert t.orphan_ratio_warning == 0.10
        assert t.grammar_violation_ratio_warning == 0.15
        assert t.rewrite_ratio_warning == 0.10
        assert t.retrieval_safety_threshold == 0.70
        assert t.fallback_fragment_ratio_warning == 0.50
        assert t.fallback_fragment_ratio_critical == 0.90

    def test_custom_thresholds(self):
        t = QualityThresholds(orphan_ratio_warning=0.05)
        assert t.orphan_ratio_warning == 0.05

    def test_invalid_threshold_raises(self):
        with pytest.raises(ValueError):
            QualityThresholds(orphan_ratio_warning=1.5)

    def test_negative_threshold_raises(self):
        with pytest.raises(ValueError):
            QualityThresholds(orphan_ratio_warning=-0.1)

    def test_to_dict_contains_fallback_thresholds(self):
        t = QualityThresholds()
        d = t.to_dict()
        assert "fallback_fragment_ratio_warning" in d
        assert "fallback_fragment_ratio_critical" in d


class TestCohesionMetrics:

    def test_unavailable(self):
        m = CohesionMetrics.unavailable()
        assert m.available is False
        assert m.avg_score == 1.0
        assert m.total_edges == 0
        assert m.boundary_ratio == 0.0

    def test_available(self):
        m = CohesionMetrics(
            available=True,
            total_edges=20,
            avg_score=0.75,
            strong_boundaries_count=3,
            cohesive_pairs_count=15,
            boundary_ratio=0.15,
        )
        assert m.available is True
        assert m.avg_score == 0.75

    def test_to_dict(self):
        m = CohesionMetrics.unavailable()
        d = m.to_dict()
        assert "available" in d
        assert "avg_score" in d


class TestQualityWarning:

    def test_basic_warning(self):
        w = QualityWarning(
            code=QualityWarningCode.ORPHAN_RATIO_HIGH,
            severity=WarningSeverity.WARNING,
            message="test warning",
            metric="orphan_ratio",
            value=0.15,
            threshold=0.10,
        )
        assert w.code == QualityWarningCode.ORPHAN_RATIO_HIGH
        assert w.severity == WarningSeverity.WARNING

    def test_to_dict(self):
        w = QualityWarning(
            code=QualityWarningCode.EMPTY_TREE,
            severity=WarningSeverity.CRITICAL,
            message="empty",
        )
        d = w.to_dict()
        assert d["code"] == "empty_tree"
        assert d["severity"] == "critical"
        assert d["value"] is None
        assert d["threshold"] is None


class TestStructureMetrics:

    def test_to_dict_has_fallback_fields(self):
        tree = _make_healthy_tree()
        metrics = _extract_structure_metrics(tree)
        d = metrics.to_dict()
        assert "fallback_fragment_nodes" in d
        assert "fallback_fragment_ratio" in d


class TestStructureQualityReport:

    def test_is_full_fallback_property(self):
        tree = _make_full_fallback_tree()
        report = evaluate_structure_quality(tree)
        assert isinstance(report.is_full_fallback, bool)

    def test_to_dict_has_is_full_fallback(self):
        tree = _make_healthy_tree()
        report = evaluate_structure_quality(tree)
        d = report.to_dict()
        assert "is_full_fallback" in d


# ═══════════════════════════════════════════════════════════════════════════════
# Tests — Fallback Fragment Detection
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsFallbackFragmentNode:

    def test_title_prefix_detected(self):
        node = FakeFallbackNode("uid_1")
        assert _is_fallback_fragment_node(node) is True

    def test_normal_node_not_detected(self):
        node = FakeFrozenNode("uid_1")
        assert _is_fallback_fragment_node(node) is False

    def test_node_origin_detection(self):
        class NodeWithOrigin:
            title = "Normal Title"
            node_origin = "technical_fallback"
            content_mode = "normal"
            citability = "high"
            diagnostics = {}

        assert _is_fallback_fragment_node(NodeWithOrigin()) is True

    def test_content_mode_detection(self):
        class NodeWithMode:
            title = "Normal Title"
            node_origin = "parsed"
            content_mode = "technical_fragment"
            citability = "high"
            diagnostics = {}

        assert _is_fallback_fragment_node(NodeWithMode()) is True

    def test_citability_detection(self):
        class NodeWithCit:
            title = "Normal Title"
            node_origin = "parsed"
            content_mode = "normal"
            citability = "technical"
            diagnostics = {}

        assert _is_fallback_fragment_node(NodeWithCit()) is True

    def test_diagnostics_fallback_reason(self):
        class NodeWithDiag:
            title = "Normal Title"
            node_origin = "parsed"
            content_mode = "normal"
            citability = "high"
            diagnostics = {"fallback_reason": "technical_fallback"}

        assert _is_fallback_fragment_node(NodeWithDiag()) is True

    def test_diagnostics_degraded_chunk(self):
        class NodeWithDegradedChunk:
            title = "Normal Title"
            node_origin = "parsed"
            content_mode = "normal"
            citability = "high"
            diagnostics = {"degraded_chunk": True}

        assert _is_fallback_fragment_node(NodeWithDegradedChunk()) is True

    def test_none_node_returns_false(self):
        assert _is_fallback_fragment_node(None) is False

    def test_empty_node_returns_false(self):
        class EmptyNode:
            pass

        assert _is_fallback_fragment_node(EmptyNode()) is False


class TestComputeFallbackFragmentMetrics:

    def test_all_fallback(self):
        nodes = {
            "uid_1": FakeFallbackNode("uid_1"),
            "uid_2": FakeFallbackNode("uid_2"),
        }
        count, ratio = _compute_fallback_fragment_metrics(nodes, 2)
        assert count == 2
        assert ratio == pytest.approx(1.0)

    def test_no_fallback(self):
        nodes = {
            "uid_1": FakeFrozenNode("uid_1"),
            "uid_2": FakeFrozenNode("uid_2"),
        }
        count, ratio = _compute_fallback_fragment_metrics(nodes, 2)
        assert count == 0
        assert ratio == 0.0

    def test_mixed(self):
        nodes = {
            "uid_1": FakeFallbackNode("uid_1"),
            "uid_2": FakeFrozenNode("uid_2"),
            "uid_3": FakeFrozenNode("uid_3"),
            "uid_4": FakeFrozenNode("uid_4"),
        }
        count, ratio = _compute_fallback_fragment_metrics(nodes, 4)
        assert count == 1
        assert ratio == pytest.approx(0.25)

    def test_empty_nodes(self):
        count, ratio = _compute_fallback_fragment_metrics({}, 0)
        assert count == 0
        assert ratio == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Tests — Metric Extraction
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtractStructureMetrics:

    def test_healthy_tree(self):
        tree = _make_healthy_tree()
        metrics = _extract_structure_metrics(tree)

        assert metrics.total_nodes == 50
        assert metrics.root_nodes_count == 5
        assert metrics.orphan_ratio == 0.0
        assert metrics.recovery_ratio == 1.0
        assert metrics.overall_score == pytest.approx(0.82)
        assert metrics.degraded is False
        assert metrics.technical_fallback_only is False
        assert metrics.fallback_fragment_nodes == 0
        assert metrics.fallback_fragment_ratio == 0.0

    def test_degraded_tree(self):
        tree = _make_degraded_tree()
        metrics = _extract_structure_metrics(tree)

        assert metrics.total_nodes == 10
        assert metrics.orphans_unresolved == 4
        assert metrics.orphan_ratio == pytest.approx(0.4)
        assert metrics.recovery_ratio == pytest.approx(0.2)
        assert metrics.degraded is True
        assert metrics.technical_fallback_only is True
        assert metrics.fallback_triggered is True

    def test_empty_tree(self):
        tree = _make_empty_tree()
        metrics = _extract_structure_metrics(tree)

        assert metrics.total_nodes == 0
        assert metrics.orphan_ratio == 0.0
        assert metrics.recovery_ratio == 1.0
        assert metrics.fallback_fragment_nodes == 0
        assert metrics.fallback_fragment_ratio == 0.0

    def test_full_fallback_tree(self):
        tree = _make_full_fallback_tree(total_nodes=1)
        metrics = _extract_structure_metrics(tree)

        assert metrics.total_nodes == 1
        assert metrics.fallback_fragment_nodes == 1
        assert metrics.fallback_fragment_ratio == pytest.approx(1.0)
        assert metrics.technical_fallback_only is True

    def test_mixed_tree(self):
        tree = _make_mixed_tree(total_nodes=10, fallback_nodes=3)
        metrics = _extract_structure_metrics(tree)

        assert metrics.total_nodes == 10
        assert metrics.fallback_fragment_nodes == 3
        assert metrics.fallback_fragment_ratio == pytest.approx(0.3)

    def test_missing_diagnostics_no_crash(self):
        tree = FakeClauseTree(structure_diagnostics={})
        metrics = _extract_structure_metrics(tree)

        assert metrics.total_nodes == 0
        assert metrics.grammar_violation_ratio == 0.0
        assert metrics.fallback_fragment_nodes == 0


class TestExtractCohesionMetrics:

    def test_none_cohesion(self):
        m = _extract_cohesion_metrics(None)
        assert m.available is False
        assert m.avg_score == 1.0

    def test_valid_cohesion(self):
        graph = FakeCohesionGraph(
            total_edges=40,
            avg_score=0.68,
            strong_boundaries_count=8,
            cohesive_pairs_count=25,
        )
        m = _extract_cohesion_metrics(graph)
        assert m.available is True
        assert m.avg_score == pytest.approx(0.68)
        assert m.boundary_ratio == pytest.approx(0.2)

    def test_empty_cohesion_graph(self):
        graph = FakeCohesionGraph(total_edges=0)
        m = _extract_cohesion_metrics(graph)
        assert m.available is False


# ═══════════════════════════════════════════════════════════════════════════════
# Tests — Warning Generation
# ═══════════════════════════════════════════════════════════════════════════════

class TestWarningGeneration:

    def test_healthy_no_critical_warnings(self):
        tree = _make_healthy_tree()
        metrics = _extract_structure_metrics(tree)
        cohesion = CohesionMetrics.unavailable()
        thresholds = QualityThresholds()

        warnings = _generate_warnings(metrics, cohesion, thresholds)

        assert not any(
            w.severity == WarningSeverity.CRITICAL for w in warnings
        )

    def test_empty_tree_critical_and_returns_early(self):
        tree = _make_empty_tree()
        metrics = _extract_structure_metrics(tree)
        cohesion = CohesionMetrics.unavailable()
        thresholds = QualityThresholds()

        warnings = _generate_warnings(metrics, cohesion, thresholds)
        codes = {w.code for w in warnings}

        assert QualityWarningCode.EMPTY_TREE in codes
        # После EMPTY_TREE → early return, других warnings нет
        assert len(warnings) == 1

    def test_degraded_tree_warnings(self):
        tree = _make_degraded_tree()
        metrics = _extract_structure_metrics(tree)
        cohesion = CohesionMetrics.unavailable()
        thresholds = QualityThresholds()

        warnings = _generate_warnings(metrics, cohesion, thresholds)
        codes = {w.code for w in warnings}

        assert QualityWarningCode.DEGRADED_TREE in codes
        assert QualityWarningCode.TECHNICAL_FALLBACK_FORCED in codes
        assert QualityWarningCode.ORPHAN_RATIO_HIGH in codes

    def test_fallback_fragment_nodes_warning(self):
        tree = _make_full_fallback_tree(total_nodes=1)
        metrics = _extract_structure_metrics(tree)
        cohesion = CohesionMetrics.unavailable()
        thresholds = QualityThresholds()

        warnings = _generate_warnings(metrics, cohesion, thresholds)
        codes = {w.code for w in warnings}

        assert QualityWarningCode.FALLBACK_FRAGMENT_NODES_PRESENT in codes

    def test_fallback_fragment_ratio_warning(self):
        tree = _make_mixed_tree(total_nodes=10, fallback_nodes=6)
        metrics = _extract_structure_metrics(tree)
        cohesion = CohesionMetrics.unavailable()
        thresholds = QualityThresholds()

        warnings = _generate_warnings(metrics, cohesion, thresholds)
        codes = {w.code for w in warnings}

        assert QualityWarningCode.FALLBACK_FRAGMENT_RATIO_HIGH in codes

    def test_fallback_ratio_critical_at_09(self):
        """ratio >= 0.90 → CRITICAL severity."""
        tree = _make_mixed_tree(total_nodes=10, fallback_nodes=9)
        metrics = _extract_structure_metrics(tree)
        cohesion = CohesionMetrics.unavailable()
        thresholds = QualityThresholds()

        warnings = _generate_warnings(metrics, cohesion, thresholds)
        ratio_w = next(
            (w for w in warnings
             if w.code == QualityWarningCode.FALLBACK_FRAGMENT_RATIO_HIGH),
            None,
        )
        assert ratio_w is not None
        assert ratio_w.severity == WarningSeverity.CRITICAL

    def test_no_fallback_warnings_for_clean_tree(self):
        tree = _make_healthy_tree()
        metrics = _extract_structure_metrics(tree)
        cohesion = CohesionMetrics.unavailable()
        thresholds = QualityThresholds()

        warnings = _generate_warnings(metrics, cohesion, thresholds)
        codes = {w.code for w in warnings}

        assert QualityWarningCode.FALLBACK_FRAGMENT_NODES_PRESENT not in codes
        assert QualityWarningCode.FALLBACK_FRAGMENT_RATIO_HIGH not in codes

    def test_cohesion_low_score_warning(self):
        metrics = _extract_structure_metrics(_make_healthy_tree())
        cohesion = CohesionMetrics(
            available=True,
            total_edges=30,
            avg_score=0.30,
            strong_boundaries_count=3,
            cohesive_pairs_count=10,
            boundary_ratio=0.10,
        )
        thresholds = QualityThresholds()

        warnings = _generate_warnings(metrics, cohesion, thresholds)
        codes = {w.code for w in warnings}
        assert QualityWarningCode.COHESION_AVG_SCORE_LOW in codes

    def test_cohesion_unavailable_no_cohesion_warnings(self):
        metrics = _extract_structure_metrics(_make_healthy_tree())
        cohesion = CohesionMetrics.unavailable()
        thresholds = QualityThresholds()

        warnings = _generate_warnings(metrics, cohesion, thresholds)
        codes = {w.code for w in warnings}
        assert QualityWarningCode.COHESION_AVG_SCORE_LOW not in codes


# ═══════════════════════════════════════════════════════════════════════════════
# Tests — Retrieval Safety Score
# ═══════════════════════════════════════════════════════════════════════════════

class TestRetrievalSafetyScore:

    def test_healthy_score_above_threshold(self):
        tree = _make_healthy_tree()
        metrics = _extract_structure_metrics(tree)
        cohesion = CohesionMetrics.unavailable()
        thresholds = QualityThresholds()
        warnings = _generate_warnings(metrics, cohesion, thresholds)

        score = _calculate_retrieval_safety_score(
            metrics, cohesion, warnings, thresholds
        )
        assert score >= 0.70

    def test_degraded_score_low(self):
        tree = _make_degraded_tree()
        metrics = _extract_structure_metrics(tree)
        cohesion = CohesionMetrics.unavailable()
        thresholds = QualityThresholds()
        warnings = _generate_warnings(metrics, cohesion, thresholds)

        score = _calculate_retrieval_safety_score(
            metrics, cohesion, warnings, thresholds
        )
        assert score < 0.55

    def test_full_fallback_score_very_low(self):
        tree = _make_full_fallback_tree(total_nodes=1)
        metrics = _extract_structure_metrics(tree)
        cohesion = CohesionMetrics.unavailable()
        thresholds = QualityThresholds()
        warnings = _generate_warnings(metrics, cohesion, thresholds)

        score = _calculate_retrieval_safety_score(
            metrics, cohesion, warnings, thresholds
        )
        assert score < 0.70
        assert score <= 0.30

    def test_score_clamped_0_1(self):
        tree = _make_degraded_tree()
        metrics = _extract_structure_metrics(tree)
        cohesion = CohesionMetrics.unavailable()
        thresholds = QualityThresholds()
        warnings = _generate_warnings(metrics, cohesion, thresholds)

        score = _calculate_retrieval_safety_score(
            metrics, cohesion, warnings, thresholds
        )
        assert 0.0 <= score <= 1.0

    def test_fallback_fragment_penalty_applied(self):
        healthy = _make_healthy_tree()
        fallback = _make_full_fallback_tree(total_nodes=1)

        m_h = _extract_structure_metrics(healthy)
        m_f = _extract_structure_metrics(fallback)
        cohesion = CohesionMetrics.unavailable()
        thresholds = QualityThresholds()
        w_h = _generate_warnings(m_h, cohesion, thresholds)
        w_f = _generate_warnings(m_f, cohesion, thresholds)

        score_h = _calculate_retrieval_safety_score(m_h, cohesion, w_h, thresholds)
        score_f = _calculate_retrieval_safety_score(m_f, cohesion, w_f, thresholds)

        assert score_f < score_h


# ═══════════════════════════════════════════════════════════════════════════════
# Tests — Chunking Mode Selection
# ═══════════════════════════════════════════════════════════════════════════════

class TestChunkingModeSelection:

    def test_mode_a_high_score(self):
        metrics = _extract_structure_metrics(_make_healthy_tree())
        thresholds = QualityThresholds()
        mode = _select_chunking_mode(0.85, metrics, thresholds)
        assert mode == RecommendedChunkingMode.STRUCTURE_FIRST

    def test_mode_b_medium_score(self):
        metrics = _extract_structure_metrics(_make_healthy_tree())
        thresholds = QualityThresholds()
        mode = _select_chunking_mode(0.65, metrics, thresholds)
        assert mode == RecommendedChunkingMode.HYBRID

    def test_mode_c_low_score(self):
        metrics = _extract_structure_metrics(_make_healthy_tree())
        thresholds = QualityThresholds()
        mode = _select_chunking_mode(0.40, metrics, thresholds)
        assert mode == RecommendedChunkingMode.LAYOUT_FALLBACK

    def test_technical_fallback_always_mode_c(self):
        metrics = _extract_structure_metrics(_make_degraded_tree())
        thresholds = QualityThresholds()
        mode = _select_chunking_mode(0.95, metrics, thresholds)
        assert mode == RecommendedChunkingMode.LAYOUT_FALLBACK

    def test_empty_tree_always_mode_c(self):
        metrics = _extract_structure_metrics(_make_empty_tree())
        thresholds = QualityThresholds()
        mode = _select_chunking_mode(0.90, metrics, thresholds)
        assert mode == RecommendedChunkingMode.LAYOUT_FALLBACK

    def test_full_fallback_ratio_always_mode_c(self):
        """fallback_fragment_ratio >= 0.90 → LAYOUT_FALLBACK независимо от score."""
        tree = _make_mixed_tree(total_nodes=10, fallback_nodes=9)
        metrics = _extract_structure_metrics(tree)
        thresholds = QualityThresholds()
        mode = _select_chunking_mode(0.95, metrics, thresholds)
        assert mode == RecommendedChunkingMode.LAYOUT_FALLBACK


# ═══════════════════════════════════════════════════════════════════════════════
# Tests — Full Evaluator
# ═══════════════════════════════════════════════════════════════════════════════

class TestEvaluateStructureQuality:

    def test_healthy_document(self):
        tree = _make_healthy_tree()
        report = evaluate_structure_quality(tree)

        assert isinstance(report, StructureQualityReport)
        assert report.document_id == "doc_001"
        assert report.segment_id == "seg_001"
        assert report.retrieval_safe is True
        assert report.recommended_chunking_mode in {
            RecommendedChunkingMode.STRUCTURE_FIRST,
            RecommendedChunkingMode.HYBRID,
        }
        assert report.orphan_ratio == 0.0
        assert report.recovery_ratio == 1.0
        assert report.is_full_fallback is False

    def test_degraded_document(self):
        tree = _make_degraded_tree()
        report = evaluate_structure_quality(tree)

        assert report.retrieval_safe is False
        assert report.recommended_chunking_mode == (
            RecommendedChunkingMode.LAYOUT_FALLBACK
        )
        assert report.has_critical_warnings is True

    def test_empty_document(self):
        tree = _make_empty_tree()
        report = evaluate_structure_quality(tree)

        assert report.retrieval_safe is False
        assert report.recommended_chunking_mode == (
            RecommendedChunkingMode.LAYOUT_FALLBACK
        )
        assert QualityWarningCode.EMPTY_TREE.value in report.warning_codes

    def test_full_fallback_document(self):
        """Реальный кейс из выгрузок: early fallback, no_headings_in_pass_1."""
        tree = _make_full_fallback_tree(total_nodes=1)
        report = evaluate_structure_quality(tree)

        assert report.retrieval_safe is False
        assert report.recommended_chunking_mode == (
            RecommendedChunkingMode.LAYOUT_FALLBACK
        )
        assert report.is_full_fallback is True
        assert report.structure_metrics.fallback_fragment_nodes == 1
        assert report.structure_metrics.fallback_fragment_ratio == pytest.approx(1.0)

        codes = report.warning_codes
        assert QualityWarningCode.FALLBACK_FRAGMENT_NODES_PRESENT.value in codes
        assert QualityWarningCode.FALLBACK_FRAGMENT_RATIO_HIGH.value in codes

    def test_with_cohesion_graph(self):
        tree = _make_healthy_tree()
        cohesion = FakeCohesionGraph(avg_score=0.75)
        report = evaluate_structure_quality(tree, cohesion_graph=cohesion)

        assert report.cohesion_metrics.available is True
        assert report.cohesion_metrics.avg_score == pytest.approx(0.75)

    def test_without_cohesion_graph(self):
        tree = _make_healthy_tree()
        report = evaluate_structure_quality(tree, cohesion_graph=None)

        assert report.cohesion_metrics.available is False

    def test_custom_thresholds(self):
        tree = _make_healthy_tree()
        strict = QualityThresholds(
            orphan_ratio_warning=0.001,
            retrieval_safety_threshold=0.95,
        )
        report = evaluate_structure_quality(tree, thresholds=strict)
        assert isinstance(report, StructureQualityReport)

    def test_deterministic_same_input_same_output(self):
        tree = _make_healthy_tree()
        r1 = evaluate_structure_quality(tree)
        r2 = evaluate_structure_quality(tree)

        assert r1.retrieval_safety_score == r2.retrieval_safety_score
        assert r1.orphan_ratio == r2.orphan_ratio
        assert r1.grammar_violation_ratio == r2.grammar_violation_ratio
        assert r1.recommended_chunking_mode == r2.recommended_chunking_mode
        assert len(r1.warnings) == len(r2.warnings)

    def test_report_to_dict_complete(self):
        tree = _make_healthy_tree()
        report = evaluate_structure_quality(tree)
        d = report.to_dict()

        required_keys = [
            "document_id",
            "segment_id",
            "retrieval_safety_score",
            "recommended_chunking_mode",
            "warnings",
            "structure_metrics",
            "cohesion_metrics",
            "thresholds",
            "is_full_fallback",
            "has_critical_warnings",
            "has_warnings",
            "warning_codes",
        ]
        for key in required_keys:
            assert key in d, f"Missing key: {key}"

    def test_rewrite_ratio_none_when_unavailable(self):
        tree = _make_healthy_tree()
        report = evaluate_structure_quality(tree)
        assert report.rewrite_ratio is None

    def test_retrieval_safe_consistency_invariant(self):
        for tree in [
            _make_healthy_tree(),
            _make_degraded_tree(),
            _make_empty_tree(),
            _make_full_fallback_tree(),
        ]:
            report = evaluate_structure_quality(tree)
            expected = (
                report.retrieval_safety_score
                >= report.thresholds.retrieval_safety_threshold
            )
            assert report.retrieval_safe == expected, (
                f"Invariant violated for {tree.document_id}: "
                f"retrieval_safe={report.retrieval_safe}, "
                f"score={report.retrieval_safety_score}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Tests — Postbuild Orchestration
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnalyzeSegmentTree:

    def test_healthy_segment(self):
        tree = _make_healthy_tree()
        with patch(
            "services.structure._pipeline._postbuild_analysis.analyze_cohesion"
        ) as mock_cohesion:
            mock_cohesion.return_value = FakeCohesionGraph()
            result = analyze_segment_tree(tree)

        assert isinstance(result, SegmentAnalysisArtifacts)
        assert result.has_quality_report is True
        assert result.segment_id == "seg_001"
        assert result.is_full_fallback is False

    def test_full_fallback_segment(self):
        """Реальный кейс: technical fallback tree."""
        tree = _make_full_fallback_tree()
        with patch(
            "services.structure._pipeline._postbuild_analysis.analyze_cohesion"
        ) as mock_cohesion:
            mock_cohesion.return_value = FakeCohesionGraph()
            result = analyze_segment_tree(tree)

        # Дерево не пустое — cohesion вызывается
        # Но quality report должен корректно определить fallback
        assert result.has_quality_report is True
        assert result.recommended_chunking_mode == (
            RecommendedChunkingMode.LAYOUT_FALLBACK
        )
        assert result.retrieval_safe is False
        assert result.is_full_fallback is True

        codes = result.quality_report.warning_codes
        assert QualityWarningCode.FALLBACK_FRAGMENT_NODES_PRESENT.value in codes
        assert QualityWarningCode.FALLBACK_FRAGMENT_RATIO_HIGH.value in codes

    def test_empty_tree_no_crash(self):
        tree = _make_empty_tree()
        with patch(
            "services.structure._pipeline._postbuild_analysis.analyze_cohesion"
        ) as mock_cohesion:
            result = analyze_segment_tree(tree)
            mock_cohesion.assert_not_called()

        assert result.has_quality_report is True
        assert result.recommended_chunking_mode == (
            RecommendedChunkingMode.LAYOUT_FALLBACK
        )

    def test_cohesion_failure_graceful(self):
        tree = _make_healthy_tree()
        with patch(
            "services.structure._pipeline._postbuild_analysis.analyze_cohesion"
        ) as mock_cohesion:
            mock_cohesion.side_effect = RuntimeError("cohesion boom")
            result = analyze_segment_tree(tree)

        assert result.has_quality_report is True
        assert result.has_cohesion is False
        assert (
            QualityWarningCode.COHESION_ANALYSIS_FAILED.value
            in result.quality_report.warning_codes
        )

    def test_quality_evaluation_failure_graceful(self):
        tree = _make_healthy_tree()
        with patch(
            "services.structure._pipeline._postbuild_analysis.evaluate_structure_quality"
        ) as mock_eval:
            mock_eval.side_effect = RuntimeError("eval boom")
            result = analyze_segment_tree(tree)

        assert result.has_quality_report is True
        assert result.retrieval_safe is False
        assert (
            QualityWarningCode.QUALITY_EVALUATION_FAILED.value
            in result.quality_report.warning_codes
        )


class TestAnalyzeFileStructure:

    def test_single_segment(self):
        tree = _make_healthy_tree()
        fs = FakeFileStructureResult(
            primary_tree=tree,
            segment_trees=[tree],
        )
        with patch(
            "services.structure._pipeline._postbuild_analysis.analyze_cohesion"
        ) as mock_cohesion:
            mock_cohesion.return_value = FakeCohesionGraph()
            result = analyze_file_structure(fs)

        assert isinstance(result, FileStructureAnalysisResult)
        assert len(result.segment_artifacts) == 1
        assert result.file_structure is fs

    def test_multiple_segments(self):
        t1 = _make_healthy_tree(document_id="doc_m", segment_id="seg_1")
        t2 = _make_degraded_tree(document_id="doc_m", segment_id="seg_2")
        fs = FakeFileStructureResult(
            primary_tree=t1,
            segment_trees=[t1, t2],
        )
        with patch(
            "services.structure._pipeline._postbuild_analysis.analyze_cohesion"
        ) as mock_cohesion:
            mock_cohesion.return_value = FakeCohesionGraph()
            result = analyze_file_structure(fs)

        assert len(result.segment_artifacts) == 2

        a1 = result.artifacts_for_segment("seg_1")
        a2 = result.artifacts_for_segment("seg_2")
        assert a1 is not None
        assert a2 is not None

    def test_all_fallback_segments(self):
        t1 = _make_full_fallback_tree(
            document_id="doc_fb_all", segment_id="seg_1"
        )
        fs = FakeFileStructureResult(
            primary_tree=t1,
            segment_trees=[t1],
        )
        with patch(
            "services.structure._pipeline._postbuild_analysis.analyze_cohesion"
        ):
            result = analyze_file_structure(fs)

        assert result.all_segments_full_fallback is True
        assert result.overall_retrieval_safe is False

    def test_overall_retrieval_safe_conservative(self):
        """overall_retrieval_safe = False если хоть один сегмент небезопасен."""
        t1 = _make_healthy_tree(document_id="doc_mix", segment_id="seg_1")
        t2 = _make_degraded_tree(document_id="doc_mix", segment_id="seg_2")
        fs = FakeFileStructureResult(
            primary_tree=t1,
            segment_trees=[t1, t2],
        )
        with patch(
            "services.structure._pipeline._postbuild_analysis.analyze_cohesion"
        ) as mock_cohesion:
            mock_cohesion.return_value = FakeCohesionGraph()
            result = analyze_file_structure(fs)

        assert result.overall_retrieval_safe is False

    def test_to_dict_complete(self):
        tree = _make_healthy_tree()
        fs = FakeFileStructureResult(
            primary_tree=tree,
            segment_trees=[tree],
        )
        with patch(
            "services.structure._pipeline._postbuild_analysis.analyze_cohesion"
        ) as mock_cohesion:
            mock_cohesion.return_value = FakeCohesionGraph()
            result = analyze_file_structure(fs)

        d = result.to_dict()
        assert "document_id" in d
        assert "overall_retrieval_safe" in d
        assert "all_segments_full_fallback" in d
        assert "segment_artifacts" in d
        assert "recommended_chunking_modes" in d


class TestFallbackQualityReport:

    def test_fallback_always_layout(self):
        tree = _make_healthy_tree()
        thresholds = QualityThresholds()
        report = _build_fallback_quality_report(
            tree, thresholds=thresholds
        )

        assert report.retrieval_safe is False
        assert report.recommended_chunking_mode == (
            RecommendedChunkingMode.LAYOUT_FALLBACK
        )
        assert report.retrieval_safety_score == 0.0
        assert report.has_critical_warnings is True
        assert (
            QualityWarningCode.QUALITY_EVALUATION_FAILED.value
            in report.warning_codes
        )
        assert (
            QualityWarningCode.RETRIEVAL_SAFETY_LOW.value
            in report.warning_codes
        )



        