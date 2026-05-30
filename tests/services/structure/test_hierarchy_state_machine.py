from __future__ import annotations

from dataclasses import field
from typing import Any

import pytest

from services.structure._models._fsm import FSMEvent, FSMEventType, FSMAttachResult
from services.structure._models._fsm_summary import FSMBuildSummary
from services.structure.hierarchy_state_machine import HierarchyStateMachine


class MutableHierarchyNode:
    """
    Minimal test double for runtime FSM tests.

    Требуемые поля и поведение:
    - raw_uid
    - effective_uid
    - level
    - node_kind
    - children
    - diagnostics
    - citability
    """
    def __init__(
        self,
        *,
        raw_uid: str,
        effective_uid: str | None = None,
        level: int = 1,
        node_kind: str = "leaf",
        citability: str = "normal",
    ) -> None:
        self.raw_uid = raw_uid
        self.effective_uid = effective_uid or f"eff::{raw_uid}"
        self.level = level
        self.node_kind = node_kind
        self.children: list[MutableHierarchyNode] = []
        self.diagnostics: dict[str, Any] = {}
        self.citability = citability


@pytest.fixture
def node_factory():
    def _make(
        raw_uid: str,
        *,
        effective_uid: str | None = None,
        citability: str = "normal",
        level: int = 1,
        node_kind: str = "leaf",
    ) -> MutableHierarchyNode:
        return MutableHierarchyNode(
            raw_uid=raw_uid,
            effective_uid=effective_uid,
            citability=citability,
            level=level,
            node_kind=node_kind,
        )

    return _make


@pytest.fixture
def fsm() -> HierarchyStateMachine:
    return HierarchyStateMachine(
        scope="main",
        document_id="doc-001",
        allow_best_effort=True,
        max_uid_depth=8,
    )


@pytest.fixture
def strict_fsm() -> HierarchyStateMachine:
    return HierarchyStateMachine(
        scope="main",
        document_id="doc-001",
        allow_best_effort=False,
        max_uid_depth=8,
    )


def test_attach_returns_fsm_attach_result(fsm: HierarchyStateMachine, node_factory) -> None:
    node = node_factory("1")

    result = fsm.attach(node, raw_uid="1", semantic_type="section_heading")

    assert isinstance(result, FSMAttachResult)
    assert result.attached is True
    assert result.event_type == FSMEventType.ATTACHED_ROOT
    assert result.parent_raw_uid is None


def test_build_summary_returns_shared_fsm_build_summary(
    fsm: HierarchyStateMachine,
    node_factory,
) -> None:
    fsm.attach(node_factory("1"), raw_uid="1", semantic_type="section_heading")

    summary = fsm.build_summary()

    assert isinstance(summary, FSMBuildSummary)
    assert summary.total_candidates == 1
    assert summary.root_count == 1


def test_events_are_typed_fsm_events(fsm: HierarchyStateMachine, node_factory) -> None:
    fsm.attach(node_factory("1"), raw_uid="1", semantic_type="section_heading")

    events = fsm.events

    assert events
    assert all(isinstance(event, FSMEvent) for event in events)
    assert events[0].event_type == FSMEventType.ATTACHED_ROOT


def test_skipped_semantic_node_not_in_attached_index(
    fsm: HierarchyStateMachine,
    node_factory,
) -> None:
    node = node_factory("1")

    result = fsm.attach(node, raw_uid="1", semantic_type="paragraph_text")

    assert result.attached is False
    assert result.event_type == FSMEventType.SKIPPED_SEMANTIC_NEGATIVE
    assert "1" not in fsm.nodes_by_raw_uid
    assert node.diagnostics["semantic_attach_skipped"] is True


def test_duplicate_detection_uses_seen_uids(
    fsm: HierarchyStateMachine,
    node_factory,
) -> None:
    skipped = node_factory("dup")
    duplicate = node_factory("dup-second")

    first = fsm.attach(skipped, raw_uid="DUP-001", semantic_type="paragraph_text")
    second = fsm.attach(duplicate, raw_uid="DUP-001", semantic_type="section_heading")

    assert first.event_type == FSMEventType.SKIPPED_SEMANTIC_NEGATIVE
    assert second.event_type == FSMEventType.SKIPPED_DUPLICATE
    assert second.attached is False
    assert "DUP-001" not in fsm.nodes_by_raw_uid


def test_root_nodes_property_has_no_side_effect(
    fsm: HierarchyStateMachine,
    node_factory,
) -> None:
    fsm.attach(node_factory("1.1"), raw_uid="1.1", semantic_type="clause_heading")

    before = list(fsm.root_nodes)

    assert before == []
    assert fsm.is_finalized is False
    assert fsm.build_summary().deferred_total == 1


def test_finalize_resolves_deferred_once(strict_fsm: HierarchyStateMachine, node_factory) -> None:
    strict_fsm.attach(node_factory("1.1"), raw_uid="1.1", semantic_type="clause_heading")

    strict_fsm.finalize()
    summary_first = strict_fsm.build_summary()
    strict_fsm.finalize()
    summary_second = strict_fsm.build_summary()

    assert strict_fsm.is_finalized is True
    assert summary_first.deferred_unresolved == 1
    assert summary_second.deferred_unresolved == 1
    assert summary_first.total_candidates == summary_second.total_candidates
    assert summary_first.total_attached == summary_second.total_attached


def test_root_numeric_uid_attaches_as_root(
    fsm: HierarchyStateMachine,
    node_factory,
) -> None:
    result = fsm.attach(node_factory("1"), raw_uid="1", semantic_type="section_heading")

    assert result.attached is True
    assert result.event_type == FSMEventType.ATTACHED_ROOT
    assert len(fsm.root_nodes) == 1
    assert fsm.root_nodes[0].raw_uid == "1"


def test_exact_numeric_parent_chain_preferred_over_last_level_fallback(
    fsm: HierarchyStateMachine,
    node_factory,
) -> None:
    parent = node_factory("1")
    sibling_root = node_factory("2")
    child = node_factory("1.1")

    fsm.attach(parent, raw_uid="1", semantic_type="section_heading")
    fsm.attach(sibling_root, raw_uid="2", semantic_type="section_heading")
    result = fsm.attach(child, raw_uid="1.1", semantic_type="clause_heading")

    assert result.attached is True
    assert result.event_type == FSMEventType.ATTACHED_CHILD
    assert result.parent_raw_uid == "1"
    assert child.diagnostics["parent_raw_uid"] == "1"

    attach_events = [e for e in fsm.events if e.event_type == FSMEventType.ATTACHED_CHILD]
    assert attach_events
    assert attach_events[-1].extra["attach_path"] == "exact_numeric_parent"


def test_parent_level_mismatch_emits_rejected_event(
    fsm: HierarchyStateMachine,
    node_factory,
) -> None:
    root = node_factory("1")
    child = node_factory("1.1")
    weird = node_factory("1.0")

    fsm.attach(root, raw_uid="1", semantic_type="section_heading")
    fsm.attach(child, raw_uid="1.1", semantic_type="clause_heading")
    result = fsm.attach(weird, raw_uid="1.0", semantic_type="clause_heading")

    assert result.event_type in {
        FSMEventType.DEFERRED_CHILD,
        FSMEventType.BEST_EFFORT_ROOT,
        FSMEventType.SKIPPED_INVALID,
    }

    rejected = [e for e in fsm.events if e.event_type == FSMEventType.PARENT_LEVEL_REJECTED]
    assert rejected
    assert rejected[-1].raw_uid == "1.0"
    assert rejected[-1].reject_reason == "parent_level_mismatch"


def test_numeric_descendant_without_parent_is_deferred(
    fsm: HierarchyStateMachine,
    node_factory,
) -> None:
    result = fsm.attach(node_factory("7.1"), raw_uid="7.1", semantic_type="clause_heading")

    assert result.attached is False
    assert result.event_type == FSMEventType.DEFERRED_CHILD

    summary = fsm.build_summary()
    assert summary.deferred_total == 1


def test_unresolved_deferred_becomes_best_effort_only_if_enabled(
    fsm: HierarchyStateMachine,
    strict_fsm: HierarchyStateMachine,
    node_factory,
) -> None:
    fsm.attach(node_factory("9.1"), raw_uid="9.1", semantic_type="clause_heading")
    strict_fsm.attach(node_factory("9.1"), raw_uid="9.1", semantic_type="clause_heading")

    summary_best_effort = fsm.build_summary()
    summary_strict = strict_fsm.build_summary()

    assert summary_best_effort.attached_best_effort == 1
    assert summary_best_effort.deferred_unresolved == 1
    assert summary_best_effort.root_count == 1

    assert summary_strict.attached_best_effort == 0
    assert summary_strict.deferred_unresolved == 1
    assert summary_strict.root_count == 0


def test_best_effort_root_does_not_mutate_citability(
    fsm: HierarchyStateMachine,
    node_factory,
) -> None:
    node = node_factory("ANNEX-X", citability="technical")

    fsm.attach(node, raw_uid="ANNEX-X", semantic_type="unknown_heading")

    assert node.citability == "technical"


def test_summary_contains_expected_counters(
    fsm: HierarchyStateMachine,
    node_factory,
) -> None:
    fsm.attach(node_factory("1"), raw_uid="1", semantic_type="section_heading")
    fsm.attach(node_factory("1.1"), raw_uid="1.1", semantic_type="clause_heading")
    fsm.attach(node_factory("bad"), raw_uid="", semantic_type="section_heading")
    fsm.attach(node_factory("skip"), raw_uid="S-1", semantic_type="paragraph_text")

    summary = fsm.build_summary()

    assert summary.total_candidates == 4
    assert summary.attached_as_root == 1
    assert summary.attached_as_child >= 1
    assert summary.skipped_invalid == 1
    assert summary.skipped_semantic_negative == 1
    assert summary.root_count == 1
    assert summary.max_depth_reached >= 2


def test_summary_has_no_quality_gate_fields(
    fsm: HierarchyStateMachine,
    node_factory,
) -> None:
    fsm.attach(node_factory("1"), raw_uid="1", semantic_type="section_heading")
    summary = fsm.build_summary()

    summary_dict = summary.to_dict()

    assert "quality_gates" not in summary_dict
    assert "structure_confidence" not in summary_dict
    assert "section_chunking_allowed" not in summary_dict
    assert "technical_fallback_only" not in summary_dict


def test_attach_after_finalize_raises(
    fsm: HierarchyStateMachine,
    node_factory,
) -> None:
    fsm.attach(node_factory("1"), raw_uid="1", semantic_type="section_heading")
    fsm.finalize()

    with pytest.raises(RuntimeError):
        fsm.attach(node_factory("2"), raw_uid="2", semantic_type="section_heading")


def test_deferred_node_attaches_when_parent_appears_before_finalize(
    fsm: HierarchyStateMachine,
    node_factory,
) -> None:
    child = node_factory("7.1")
    parent = node_factory("7")

    deferred = fsm.attach(child, raw_uid="7.1", semantic_type="clause_heading")
    root = fsm.attach(parent, raw_uid="7", semantic_type="section_heading")

    summary = fsm.build_summary()

    assert deferred.event_type == FSMEventType.DEFERRED_CHILD
    assert root.event_type == FSMEventType.ATTACHED_ROOT
    assert summary.deferred_total == 1
    assert summary.deferred_resolved == 1
    assert summary.attached_deferred_child == 1
    assert child.diagnostics["deferred_resolution_status"] == "attached"
    assert child.diagnostics["parent_raw_uid"] == "7"


def test_stack_closed_event_emitted_on_new_root(
    fsm: HierarchyStateMachine,
    node_factory,
) -> None:
    fsm.attach(node_factory("1"), raw_uid="1", semantic_type="section_heading")
    fsm.attach(node_factory("1.1"), raw_uid="1.1", semantic_type="clause_heading")
    fsm.attach(node_factory("2"), raw_uid="2", semantic_type="section_heading")

    closed = [event for event in fsm.events if event.event_type == FSMEventType.STACK_CLOSED]

    assert closed
    assert any(event.raw_uid == "1.1" for event in closed)