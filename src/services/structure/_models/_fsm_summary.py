# src/services/structure/_models/_fsm_summary.py

"""
FSMBuildSummary.

Итоговая статистика сборки дерева через FSM.
Отделена от quality gates и structural confidence (Phase 5).

ВАЖНО:
- это Phase 3 diagnostic artifact;
- summary не содержит quality gates;
- summary не содержит structure confidence;
- summary не содержит chunking decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ._fsm import FSMEvent


def _normalize_non_negative_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{field_name} must be int, got {type(value).__name__}")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0, got {value}")
    return value


def _ensure_fsm_events(values: Any) -> list[FSMEvent]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError(f"events must be list[FSMEvent], got {type(values).__name__}")

    normalized: list[FSMEvent] = []
    for idx, value in enumerate(values):
        if not isinstance(value, FSMEvent):
            raise ValueError(f"events[{idx}] must be FSMEvent")
        normalized.append(value)
    return normalized


@dataclass(slots=True)
class FSMBuildSummary:
    """
    Статистика FSM после обработки всех heading candidates.

    Используется для:
    - Phase 5 (Structural Confidence) как input;
    - debugging и telemetry;
    - audit log.

    НЕ содержит:
    - quality gates;
    - structure confidence;
    - chunking decisions.

    Это responsibility downstream layers.
    """

    total_candidates: int = 0

    attached_as_child: int = 0
    attached_as_root: int = 0
    attached_best_effort: int = 0
    attached_deferred_child: int = 0

    skipped_duplicate: int = 0
    skipped_invalid: int = 0
    skipped_semantic_negative: int = 0
    parent_level_rejected: int = 0

    deferred_total: int = 0
    deferred_resolved: int = 0
    deferred_unresolved: int = 0

    root_count: int = 0
    max_depth_reached: int = 0

    events: list[FSMEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.total_candidates = _normalize_non_negative_int(
            self.total_candidates,
            "FSMBuildSummary.total_candidates",
        )

        self.attached_as_child = _normalize_non_negative_int(
            self.attached_as_child,
            "FSMBuildSummary.attached_as_child",
        )
        self.attached_as_root = _normalize_non_negative_int(
            self.attached_as_root,
            "FSMBuildSummary.attached_as_root",
        )
        self.attached_best_effort = _normalize_non_negative_int(
            self.attached_best_effort,
            "FSMBuildSummary.attached_best_effort",
        )
        self.attached_deferred_child = _normalize_non_negative_int(
            self.attached_deferred_child,
            "FSMBuildSummary.attached_deferred_child",
        )

        self.skipped_duplicate = _normalize_non_negative_int(
            self.skipped_duplicate,
            "FSMBuildSummary.skipped_duplicate",
        )
        self.skipped_invalid = _normalize_non_negative_int(
            self.skipped_invalid,
            "FSMBuildSummary.skipped_invalid",
        )
        self.skipped_semantic_negative = _normalize_non_negative_int(
            self.skipped_semantic_negative,
            "FSMBuildSummary.skipped_semantic_negative",
        )
        self.parent_level_rejected = _normalize_non_negative_int(
            self.parent_level_rejected,
            "FSMBuildSummary.parent_level_rejected",
        )

        self.deferred_total = _normalize_non_negative_int(
            self.deferred_total,
            "FSMBuildSummary.deferred_total",
        )
        self.deferred_resolved = _normalize_non_negative_int(
            self.deferred_resolved,
            "FSMBuildSummary.deferred_resolved",
        )
        self.deferred_unresolved = _normalize_non_negative_int(
            self.deferred_unresolved,
            "FSMBuildSummary.deferred_unresolved",
        )

        self.root_count = _normalize_non_negative_int(
            self.root_count,
            "FSMBuildSummary.root_count",
        )
        self.max_depth_reached = _normalize_non_negative_int(
            self.max_depth_reached,
            "FSMBuildSummary.max_depth_reached",
        )

        self.events = _ensure_fsm_events(self.events)

        if self.deferred_resolved + self.deferred_unresolved > self.deferred_total:
            raise ValueError(
                "FSMBuildSummary invariant violated: "
                "deferred_resolved + deferred_unresolved must be <= deferred_total"
            )

    @property
    def total_attached(self) -> int:
        return (
            self.attached_as_child
            + self.attached_as_root
            + self.attached_best_effort
            + self.attached_deferred_child
        )

    @property
    def total_skipped(self) -> int:
        return (
            self.skipped_duplicate
            + self.skipped_invalid
            + self.skipped_semantic_negative
            + self.parent_level_rejected
        )

    @property
    def best_effort_ratio(self) -> float:
        if self.total_attached == 0:
            return 0.0
        return round(self.attached_best_effort / self.total_attached, 4)

    @property
    def deferred_resolution_rate(self) -> float:
        if self.deferred_total == 0:
            return 1.0
        return round(self.deferred_resolved / self.deferred_total, 4)

    @property
    def has_valid_roots(self) -> bool:
        """
        Convenience diagnostic flag.

        Не является заменой Phase 5 structural confidence.
        """
        return self.root_count > 0 and self.total_attached > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_candidates": self.total_candidates,
            "attached_as_child": self.attached_as_child,
            "attached_as_root": self.attached_as_root,
            "attached_best_effort": self.attached_best_effort,
            "attached_deferred_child": self.attached_deferred_child,
            "skipped_duplicate": self.skipped_duplicate,
            "skipped_invalid": self.skipped_invalid,
            "skipped_semantic_negative": self.skipped_semantic_negative,
            "parent_level_rejected": self.parent_level_rejected,
            "deferred_total": self.deferred_total,
            "deferred_resolved": self.deferred_resolved,
            "deferred_unresolved": self.deferred_unresolved,
            "root_count": self.root_count,
            "max_depth_reached": self.max_depth_reached,
            "total_attached": self.total_attached,
            "total_skipped": self.total_skipped,
            "best_effort_ratio": self.best_effort_ratio,
            "deferred_resolution_rate": self.deferred_resolution_rate,
            "has_valid_roots": self.has_valid_roots,
            "events": [event.to_dict() for event in self.events],
        }

    