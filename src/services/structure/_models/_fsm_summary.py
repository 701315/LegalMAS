# src/services/structure/_models/_fsm_summary.py

"""
Phase 3 — FSMBuildSummary.

Итоговая статистика сборки дерева через FSM.
Отделена от quality gates и structural confidence (Phase 5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FSMBuildSummary:
    """
    Статистика FSM после обработки всех heading candidates.

    Используется для:
    - Phase 5 (Structural Confidence) как input;
    - debugging и telemetry;
    - audit log.

    НЕ содержит: quality_gates, structure_confidence, chunking decisions.
    Это responsibility Phase 5.
    """

    total_candidates: int = 0
    attached_as_child: int = 0
    attached_as_root: int = 0
    attached_best_effort: int = 0
    skipped_duplicate: int = 0
    skipped_invalid: int = 0
    parent_level_rejected: int = 0

    root_count: int = 0
    max_depth_reached: int = 0

    events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def total_attached(self) -> int:
        return self.attached_as_child + self.attached_as_root + self.attached_best_effort

    @property
    def best_effort_ratio(self) -> float:
        if self.total_attached == 0:
            return 0.0
        return round(self.attached_best_effort / self.total_attached, 4)

    @property
    def has_valid_roots(self) -> bool:
        return self.root_count > 0 and self.total_attached > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_candidates": self.total_candidates,
            "attached_as_child": self.attached_as_child,
            "attached_as_root": self.attached_as_root,
            "attached_best_effort": self.attached_best_effort,
            "skipped_duplicate": self.skipped_duplicate,
            "skipped_invalid": self.skipped_invalid,
            "parent_level_rejected": self.parent_level_rejected,
            "root_count": self.root_count,
            "max_depth_reached": self.max_depth_reached,
            "total_attached": self.total_attached,
            "best_effort_ratio": self.best_effort_ratio,
            "has_valid_roots": self.has_valid_roots,
        }
    

    