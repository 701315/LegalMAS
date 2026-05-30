from __future__ import annotations

import pytest

from services.structure._models._fsm import FSMEvent, FSMEventType
from services.structure._models._fsm_summary import FSMBuildSummary
from services.structure.fsm_legacy_diagnostics import compute_legacy_quality_gates


def make_summary(
    *,
    total_candidates: int = 0,
    attached_as_child: int = 0,
    attached_as_root: int = 0,
    attached_best_effort: int = 0,
    attached_deferred_child: int = 0,
    skipped_duplicate: int = 0,
    skipped_invalid: int = 0,
    skipped_semantic_negative: int = 0,
    parent_level_rejected: int = 0,
    deferred_total: int = 0,
    deferred_resolved: int = 0,
    deferred_unresolved: int = 0,
    root_count: int = 0,
    max_depth_reached: int = 0,
    events: list[FSMEvent] | None = None,
) -> FSMBuildSummary:
    return FSMBuildSummary(
        total_candidates=total_candidates,
        attached_as_child=attached_as_child,
        attached_as_root=attached_as_root,
        attached_best_effort=attached_best_effort,
        attached_deferred_child=attached_deferred_child,
        skipped_duplicate=skipped_duplicate,
        skipped_invalid=skipped_invalid,
        skipped_semantic_negative=skipped_semantic_negative,
        parent_level_rejected=parent_level_rejected,
        deferred_total=deferred_total,
        deferred_resolved=deferred_resolved,
        deferred_unresolved=deferred_unresolved,
        root_count=root_count,
        max_depth_reached=max_depth_reached,
        events=events or [],
    )


def test_legacy_quality_gates_returns_expected_keys() -> None:
    summary = make_summary(
        total_candidates=3,
        attached_as_root=2,
        attached_as_child=1,
        root_count=2,
        max_depth_reached=2,
    )

    result = compute_legacy_quality_gates(summary)

    expected_keys = {
        "section_chunking_allowed",
        "technical_fallback_only",
        "structure_confidence",
        "recoverable_hierarchy_used",
        "recoverable_numeric_backbone",
        "deferred_resolution_good",
        "total_fallback_blocked",
        "hierarchy_quality",
        "best_effort_ratio",
        "deferred_total",
        "deferred_resolved",
        "deferred_unresolved",
        "root_count",
        "total_attached",
        "total_skipped",
        "max_depth_reached",
    }

    assert set(result.keys()) == expected_keys


def test_legacy_quality_gates_high_confidence_case() -> None:
    summary = make_summary(
        total_candidates=6,
        attached_as_root=4,
        attached_as_child=2,
        attached_best_effort=0,
        deferred_total=1,
        deferred_resolved=1,
        deferred_unresolved=0,
        root_count=4,
        max_depth_reached=3,
    )

    result = compute_legacy_quality_gates(summary)

    assert result["structure_confidence"] == "HIGH"
    assert result["section_chunking_allowed"] is True
    assert result["technical_fallback_only"] is False
    assert result["hierarchy_quality"] == "good"
    assert result["best_effort_ratio"] == 0.0


def test_legacy_quality_gates_low_confidence_case() -> None:
    summary = make_summary(
        total_candidates=5,
        attached_as_root=1,
        attached_as_child=0,
        attached_best_effort=3,
        skipped_invalid=1,
        root_count=1,
        max_depth_reached=1,
    )

    result = compute_legacy_quality_gates(summary)

    assert result["structure_confidence"] == "LOW"
    assert result["section_chunking_allowed"] is False
    assert result["technical_fallback_only"] is True
    assert result["hierarchy_quality"] == "failed"
    assert result["best_effort_ratio"] > 0.45


def test_legacy_quality_gates_deferred_resolution_impacts_confidence() -> None:
    bad_summary = make_summary(
        total_candidates=6,
        attached_as_root=3,
        attached_as_child=1,
        attached_best_effort=1,
        deferred_total=3,
        deferred_resolved=0,
        deferred_unresolved=3,
        root_count=3,
        max_depth_reached=3,
    )
    good_summary = make_summary(
        total_candidates=6,
        attached_as_root=3,
        attached_as_child=1,
        attached_best_effort=1,
        deferred_total=3,
        deferred_resolved=3,
        deferred_unresolved=0,
        root_count=3,
        max_depth_reached=3,
    )

    bad_result = compute_legacy_quality_gates(bad_summary)
    good_result = compute_legacy_quality_gates(good_summary)

    assert bad_result["deferred_resolution_good"] is False
    assert good_result["deferred_resolution_good"] is True
    assert good_result["structure_confidence"] in {"MEDIUM", "HIGH"}


def test_legacy_quality_gates_chunking_allowed_false_when_no_roots() -> None:
    summary = make_summary(
        total_candidates=3,
        attached_as_child=0,
        attached_as_root=0,
        attached_best_effort=0,
        skipped_invalid=3,
        root_count=0,
        max_depth_reached=0,
    )

    result = compute_legacy_quality_gates(summary)

    assert result["structure_confidence"] == "LOW"
    assert result["section_chunking_allowed"] is False
    assert result["technical_fallback_only"] is True


def test_legacy_quality_gates_computed_from_summary_only() -> None:
    summary = make_summary(
        total_candidates=4,
        attached_as_root=2,
        attached_as_child=1,
        root_count=2,
        max_depth_reached=2,
        events=[
            FSMEvent(
                event_type=FSMEventType.ATTACHED_ROOT,
                raw_uid="1",
                scope="main",
                level=1,
            ),
            FSMEvent(
                event_type=FSMEventType.ATTACHED_CHILD,
                raw_uid="1.1",
                scope="main",
                level=2,
                parent_raw_uid="1",
            ),
        ],
    )

    result = compute_legacy_quality_gates(summary)

    assert result["root_count"] == 2
    assert result["total_attached"] == summary.total_attached
    assert result["total_skipped"] == summary.total_skipped
    assert result["max_depth_reached"] == 2


@pytest.mark.parametrize(
    ("attached_best_effort", "attached_total", "expected_quality"),
    [
        (0, 5, "HIGH"),
        (1, 5, "HIGH"),
        (2, 5, "MEDIUM"),
        (3, 5, "LOW"),
    ],
)
def test_legacy_quality_quality_changes_with_best_effort_ratio(
    attached_best_effort: int,
    attached_total: int,
    expected_quality: str,
) -> None:
    attached_as_root = 3
    attached_as_child = attached_total - attached_as_root - attached_best_effort
    if attached_as_child < 0:
        attached_as_child = 0

    summary = make_summary(
        total_candidates=attached_total,
        attached_as_root=attached_as_root,
        attached_as_child=attached_as_child,
        attached_best_effort=attached_best_effort,
        root_count=3,
        max_depth_reached=2,
    )

    result = compute_legacy_quality_gates(summary)

    assert result["structure_confidence"] == expected_quality


def test_legacy_quality_marks_recoverable_hierarchy_used_when_deferred_resolved() -> None:
    summary = make_summary(
        total_candidates=4,
        attached_as_root=2,
        attached_as_child=1,
        attached_deferred_child=1,
        deferred_total=1,
        deferred_resolved=1,
        deferred_unresolved=0,
        root_count=2,
        max_depth_reached=2,
    )

    result = compute_legacy_quality_gates(summary)

    assert result["recoverable_hierarchy_used"] is True


def test_legacy_quality_total_fallback_blocked_equals_total_skipped() -> None:
    summary = make_summary(
        total_candidates=5,
        skipped_duplicate=1,
        skipped_invalid=2,
        skipped_semantic_negative=1,
        parent_level_rejected=1,
        root_count=0,
        max_depth_reached=0,
    )

    result = compute_legacy_quality_gates(summary)

    assert summary.total_skipped == 5
    assert result["total_fallback_blocked"] == 5


    