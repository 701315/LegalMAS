# tests/services/structure/models/test_fsm.py

"""Tests for Phase 3 — FSM contracts."""

from __future__ import annotations

import pytest

from services.structure.models import (
    FSMAttachResult,
    FSMBuildSummary,
    FSMEvent,
    FSMEventType,
)


class TestFSMEventType:
    def test_all_values_exist(self):
        values = {e.value for e in FSMEventType}
        assert "attached_child" in values
        assert "attached_root" in values
        assert "stack_closed" in values
        assert "skipped_duplicate" in values
        assert "skipped_invalid" in values
        assert "best_effort_root" in values

    def test_string_comparison(self):
        assert FSMEventType.ATTACHED_CHILD == "attached_child"


class TestFSMEvent:
    def test_basic_creation(self):
        e = FSMEvent(
            event_type=FSMEventType.ATTACHED_CHILD,
            raw_uid="1.1",
            scope="main_contract",
            level=2,
            parent_raw_uid="1",
        )
        assert e.raw_uid == "1.1"
        assert e.parent_raw_uid == "1"
        assert e.level == 2

    def test_to_dict(self):
        e = FSMEvent(
            event_type=FSMEventType.ATTACHED_ROOT,
            raw_uid="1",
            scope="main_contract",
            level=1,
        )
        d = e.to_dict()
        assert d["event_type"] == "attached_root"
        assert d["raw_uid"] == "1"
        assert d["parent_raw_uid"] is None

    def test_skipped_has_reject_reason(self):
        e = FSMEvent(
            event_type=FSMEventType.SKIPPED_DUPLICATE,
            raw_uid="2",
            scope="main_contract",
            level=1,
            reject_reason="duplicate_uid",
        )
        assert e.reject_reason == "duplicate_uid"


class TestFSMAttachResult:
    def test_child_attach(self):
        r = FSMAttachResult(
            attached=True,
            event_type=FSMEventType.ATTACHED_CHILD,
            parent_raw_uid="1",
        )
        assert r.attached is True
        assert r.is_root is False
        assert r.is_best_effort is False

    def test_root_attach(self):
        r = FSMAttachResult(
            attached=True,
            event_type=FSMEventType.ATTACHED_ROOT,
        )
        assert r.is_root is True
        assert r.is_best_effort is False

    def test_best_effort_attach(self):
        r = FSMAttachResult(
            attached=True,
            event_type=FSMEventType.BEST_EFFORT_ROOT,
        )
        assert r.is_root is True
        assert r.is_best_effort is True

    def test_skipped(self):
        r = FSMAttachResult(
            attached=False,
            event_type=FSMEventType.SKIPPED_INVALID,
            reject_reason="empty_raw_uid",
        )
        assert r.attached is False
        assert r.reject_reason == "empty_raw_uid"


class TestFSMBuildSummary:
    def test_empty_summary(self):
        s = FSMBuildSummary()
        assert s.total_attached == 0
        assert s.best_effort_ratio == 0.0
        assert s.has_valid_roots is False

    def test_total_attached(self):
        s = FSMBuildSummary(
            attached_as_child=5,
            attached_as_root=2,
            attached_best_effort=1,
        )
        assert s.total_attached == 8

    def test_best_effort_ratio(self):
        s = FSMBuildSummary(
            attached_as_child=7,
            attached_as_root=2,
            attached_best_effort=1,
        )
        assert s.best_effort_ratio == round(1 / 10, 4)

    def test_has_valid_roots_true(self):
        s = FSMBuildSummary(
            attached_as_root=3,
            attached_as_child=5,
            root_count=3,
        )
        assert s.has_valid_roots is True

    def test_has_valid_roots_false_no_roots(self):
        s = FSMBuildSummary(attached_as_child=5, root_count=0)
        assert s.has_valid_roots is False

    def test_to_dict_keys(self):
        s = FSMBuildSummary(total_candidates=10, root_count=2)
        d = s.to_dict()
        assert "total_candidates" in d
        assert "best_effort_ratio" in d
        assert "has_valid_roots" in d
        # quality_gates НЕ должны быть здесь — это Phase 5
        assert "quality_gates" not in d
        assert "structure_confidence" not in d

    def test_deterministic_same_input(self):
        """FSM summary должен давать одинаковый результат при одинаковом input."""
        s1 = FSMBuildSummary(attached_as_child=3, attached_as_root=1, root_count=1)
        s2 = FSMBuildSummary(attached_as_child=3, attached_as_root=1, root_count=1)
        assert s1.to_dict() == s2.to_dict()

        