# tests/services/structure/models/test_resolution.py

"""Tests for Phase 3.5 — Deterministic Resolution contracts."""

from __future__ import annotations

import pytest

from services.structure.models import (
    ResolutionAuditLog,
    ResolutionResult,
    RewriteType,
    StructuralRewrite,
)


class TestRewriteType:
    def test_all_values_exist(self):
        values = {r.value for r in RewriteType}
        assert "level_normalized" in values
        assert "depth_stabilized" in values
        assert "monotonicity_fixed" in values
        assert "orphan_reparented" in values
        assert "duplicate_resolved" in values

    def test_string_comparison(self):
        assert RewriteType.LEVEL_NORMALIZED == "level_normalized"


class TestStructuralRewrite:
    def test_basic_creation(self):
        r = StructuralRewrite(
            rewrite_type=RewriteType.LEVEL_NORMALIZED,
            node_uid="main_contract:1.1",
            original_state={"level": 3},
            rewritten_state={"level": 2},
            confidence=1.0,
            reason="inconsistent depth",
        )
        assert r.node_uid == "main_contract:1.1"
        assert r.confidence == 1.0
        assert r.rewrite_type == RewriteType.LEVEL_NORMALIZED

    def test_confidence_out_of_range_raises(self):
        with pytest.raises(ValueError, match="confidence"):
            StructuralRewrite(
                rewrite_type=RewriteType.LEVEL_NORMALIZED,
                node_uid="main_contract:1",
                original_state={"level": 1},
                rewritten_state={"level": 1},
                confidence=1.5,
            )

    def test_empty_node_uid_raises(self):
        with pytest.raises(ValueError, match="node_uid"):
            StructuralRewrite(
                rewrite_type=RewriteType.LEVEL_NORMALIZED,
                node_uid="",
                original_state={},
                rewritten_state={},
                confidence=1.0,
            )

    def test_to_dict(self):
        r = StructuralRewrite(
            rewrite_type=RewriteType.MONOTONICITY_FIXED,
            node_uid="main_contract:2.1",
            original_state={"level": 1},
            rewritten_state={"level": 2},
            confidence=0.9,
        )
        d = r.to_dict()
        assert d["rewrite_type"] == "monotonicity_fixed"
        assert d["confidence"] == 0.9
        assert d["node_uid"] == "main_contract:2.1"

    def test_heuristic_confidence(self):
        r = StructuralRewrite(
            rewrite_type=RewriteType.ORPHAN_REPARENTED,
            node_uid="main_contract:7.1",
            original_state={"parent_uid": None},
            rewritten_state={"parent_uid": "main_contract:7"},
            confidence=0.75,
        )
        assert r.confidence == 0.75


class TestResolutionAuditLog:
    def test_empty_log(self):
        log = ResolutionAuditLog(document_id="doc_001")
        assert log.total_rewrites == 0
        assert log.rewrite_ratio == 0.0
        assert log.by_type(RewriteType.LEVEL_NORMALIZED) == []

    def test_add_rewrite(self):
        log = ResolutionAuditLog(document_id="doc_001")
        log.add(StructuralRewrite(
            rewrite_type=RewriteType.LEVEL_NORMALIZED,
            node_uid="main_contract:1",
            original_state={"level": 2},
            rewritten_state={"level": 1},
            confidence=1.0,
        ))
        assert log.total_rewrites == 1

    def test_add_level_normalized_helper(self):
        log = ResolutionAuditLog(document_id="doc_001")
        log.add_level_normalized(
            node_uid="main_contract:1.1",
            original_level=3,
            rewritten_level=2,
        )
        assert log.total_rewrites == 1
        r = log.rewrites[0]
        assert r.rewrite_type == RewriteType.LEVEL_NORMALIZED
        assert r.original_state["level"] == 3
        assert r.rewritten_state["level"] == 2
        assert r.confidence == 1.0

    def test_add_monotonicity_fixed_helper(self):
        log = ResolutionAuditLog(document_id="doc_001")
        log.add_monotonicity_fixed(
            node_uid="main_contract:2.1",
            parent_uid="main_contract:2",
            original_level=1,
            rewritten_level=2,
        )
        r = log.rewrites[0]
        assert r.rewrite_type == RewriteType.MONOTONICITY_FIXED
        assert "parent_uid" in r.original_state

    def test_add_orphan_reparented_helper(self):
        log = ResolutionAuditLog(document_id="doc_001")
        log.add_orphan_reparented(
            node_uid="main_contract:7.1",
            original_parent_uid=None,
            new_parent_uid="main_contract:7",
            confidence=0.8,
        )
        r = log.rewrites[0]
        assert r.rewrite_type == RewriteType.ORPHAN_REPARENTED
        assert r.confidence == 0.8

    def test_by_type_filter(self):
        log = ResolutionAuditLog(document_id="doc_001")
        log.add_level_normalized(node_uid="main_contract:1", original_level=2, rewritten_level=1)
        log.add_monotonicity_fixed(
            node_uid="main_contract:2.1",
            parent_uid="main_contract:2",
            original_level=1,
            rewritten_level=2,
        )
        assert len(log.by_type(RewriteType.LEVEL_NORMALIZED)) == 1
        assert len(log.by_type(RewriteType.MONOTONICITY_FIXED)) == 1
        assert len(log.by_type(RewriteType.ORPHAN_REPARENTED)) == 0

    def test_to_dict_structure(self):
        log = ResolutionAuditLog(document_id="doc_001")
        log.add_level_normalized(node_uid="main_contract:1", original_level=2, rewritten_level=1)
        d = log.to_dict()
        assert d["document_id"] == "doc_001"
        assert d["total_rewrites"] == 1
        assert "rewrites_by_type" in d
        assert len(d["rewrites"]) == 1

    def test_no_silent_rewrites(self):
        """Каждое изменение должно быть в audit log — нельзя silently rewrite."""
        log = ResolutionAuditLog(document_id="doc_001")
        for i in range(5):
            log.add_level_normalized(
                node_uid=f"main_contract:{i}",
                original_level=i + 2,
                rewritten_level=i + 1,
            )
        assert log.total_rewrites == 5
        assert len(log.rewrites) == 5


class TestResolutionResult:
    def _make_log(self) -> ResolutionAuditLog:
        return ResolutionAuditLog(document_id="doc_001")

    def test_canonical_no_rewrites(self):
        log = self._make_log()
        result = ResolutionResult(is_canonical=True, is_stable=True, audit_log=log)
        assert result.is_canonical is True
        assert result.was_rewritten is False
        assert result.has_violations is False

    def test_rewritten_not_canonical(self):
        log = self._make_log()
        log.add_level_normalized(node_uid="main_contract:1", original_level=2, rewritten_level=1)
        result = ResolutionResult(is_canonical=False, is_stable=True, audit_log=log)
        assert result.was_rewritten is True
        assert result.is_canonical is False

    def test_violations(self):
        log = self._make_log()
        result = ResolutionResult(
            is_canonical=False,
            is_stable=False,
            audit_log=log,
            violations=["child_level_exceeds_max_depth", "illegal_jump_detected"],
        )
        assert result.has_violations is True
        assert len(result.violations) == 2

    def test_to_dict(self):
        log = self._make_log()
        result = ResolutionResult(is_canonical=True, is_stable=True, audit_log=log)
        d = result.to_dict()
        assert "is_canonical" in d
        assert "is_stable" in d
        assert "was_rewritten" in d
        assert "audit_log" in d
        assert "violations" in d

    def test_deterministic_same_input(self):
        """Resolution result должен быть воспроизводимым."""
        log1 = ResolutionAuditLog(document_id="doc_001")
        log1.add_level_normalized(node_uid="main_contract:1", original_level=2, rewritten_level=1)
        log2 = ResolutionAuditLog(document_id="doc_001")
        log2.add_level_normalized(node_uid="main_contract:1", original_level=2, rewritten_level=1)
        r1 = ResolutionResult(is_canonical=False, is_stable=True, audit_log=log1)
        r2 = ResolutionResult(is_canonical=False, is_stable=True, audit_log=log2)
        assert r1.to_dict() == r2.to_dict()

        