# src/services/structure/_models/_resolution.py

"""
Phase 3.5 — Deterministic Resolution contracts.

После FSM дерево может быть локально валидным, но глобально нестабильным.
Resolution делает hierarchy canonical и globally stable.

Содержит:
- RewriteType        — тип изменения при canonicalization
- StructuralRewrite  — одна запись в audit log
- ResolutionAuditLog — полный лог всех изменений (per-document)
- ResolutionResult   — итог после normalize + stabilize + validate

ВАЖНО:
- Resolution НЕ скрывает изменения — каждый rewrite логируется.
- Downstream (debugging, telemetry, retrieval diagnostics) читают audit log.
- После resolution hierarchy canonical и stable across runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RewriteType(str, Enum):
    """
    Тип структурного изменения при canonicalization.

    LEVEL_NORMALIZED    — выровнен inconsistent depth
    DEPTH_STABILIZED    — исправлен нестабильный numbering depth
    MONOTONICITY_FIXED  — устранён illegal jump (child depth <= parent depth)
    ORPHAN_REPARENTED   — orphan узел получил нового parent
    DUPLICATE_RESOLVED  — разрешён конфликт duplicate uid в scope
    """

    LEVEL_NORMALIZED = "level_normalized"
    DEPTH_STABILIZED = "depth_stabilized"
    MONOTONICITY_FIXED = "monotonicity_fixed"
    ORPHAN_REPARENTED = "orphan_reparented"
    DUPLICATE_RESOLVED = "duplicate_resolved"


@dataclass(slots=True)
class StructuralRewrite:
    """
    Одна запись в ResolutionAuditLog.

    Фиксирует КАЖДОЕ изменение которое resolution внёс в hierarchy.
    Нельзя silently rewrite — каждое изменение должно быть здесь.

    rewrite_type:    тип изменения
    node_uid:        effective_uid узла который был изменён
    original_state:  состояние ДО изменения (что именно поменялось)
    rewritten_state: состояние ПОСЛЕ изменения
    confidence:      насколько resolution уверен в правильности rewrite
                     1.0 = детерминированное правило
                     < 1.0 = эвристика
    reason:          human-readable объяснение
    """

    rewrite_type: RewriteType
    node_uid: str
    original_state: dict[str, Any]
    rewritten_state: dict[str, Any]
    confidence: float
    reason: str = ""

    def __post_init__(self) -> None:
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"confidence must be in [0.0, 1.0], got {self.confidence}"
            )
        if not self.node_uid:
            raise ValueError("node_uid must not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "rewrite_type": self.rewrite_type.value,
            "node_uid": self.node_uid,
            "original_state": dict(self.original_state),
            "rewritten_state": dict(self.rewritten_state),
            "confidence": self.confidence,
            "reason": self.reason,
        }


@dataclass
class ResolutionAuditLog:
    """
    Полный лог всех structural rewrites для одного документа.

    Создаётся per-document, НЕ singleton.
    Используется downstream: debugging, audit, telemetry, retrieval diagnostics.
    """

    document_id: str
    rewrites: list[StructuralRewrite] = field(default_factory=list)

    def add(self, rewrite: StructuralRewrite) -> None:
        self.rewrites.append(rewrite)

    def add_level_normalized(
        self,
        *,
        node_uid: str,
        original_level: int,
        rewritten_level: int,
        confidence: float = 1.0,
        reason: str = "",
    ) -> None:
        self.add(StructuralRewrite(
            rewrite_type=RewriteType.LEVEL_NORMALIZED,
            node_uid=node_uid,
            original_state={"level": original_level},
            rewritten_state={"level": rewritten_level},
            confidence=confidence,
            reason=reason or f"level {original_level} → {rewritten_level}",
        ))

    def add_monotonicity_fixed(
        self,
        *,
        node_uid: str,
        parent_uid: str,
        original_level: int,
        rewritten_level: int,
        confidence: float = 1.0,
    ) -> None:
        self.add(StructuralRewrite(
            rewrite_type=RewriteType.MONOTONICITY_FIXED,
            node_uid=node_uid,
            original_state={"level": original_level, "parent_uid": parent_uid},
            rewritten_state={"level": rewritten_level, "parent_uid": parent_uid},
            confidence=confidence,
            reason=(
                f"child level {original_level} <= parent level, "
                f"fixed to {rewritten_level}"
            ),
        ))

    def add_orphan_reparented(
        self,
        *,
        node_uid: str,
        original_parent_uid: str | None,
        new_parent_uid: str | None,
        confidence: float,
        reason: str = "",
    ) -> None:
        self.add(StructuralRewrite(
            rewrite_type=RewriteType.ORPHAN_REPARENTED,
            node_uid=node_uid,
            original_state={"parent_uid": original_parent_uid},
            rewritten_state={"parent_uid": new_parent_uid},
            confidence=confidence,
            reason=reason or f"orphan reparented to {new_parent_uid!r}",
        ))

    @property
    def total_rewrites(self) -> int:
        return len(self.rewrites)

    @property
    def rewrite_ratio(self) -> float:
        """
        Отношение числа rewrites к числу уникальных затронутых узлов.
        Используется Phase 9 (Quality Evaluation) — warning если > 0.1.
        """
        if not self.rewrites:
            return 0.0
        unique_nodes = len({r.node_uid for r in self.rewrites})
        return round(unique_nodes / max(self.total_rewrites, 1), 4)

    def by_type(self, rewrite_type: RewriteType) -> list[StructuralRewrite]:
        return [r for r in self.rewrites if r.rewrite_type == rewrite_type]

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "total_rewrites": self.total_rewrites,
            "rewrite_ratio": self.rewrite_ratio,
            "rewrites_by_type": {
                rt.value: len(self.by_type(rt)) for rt in RewriteType
            },
            "rewrites": [r.to_dict() for r in self.rewrites],
        }


@dataclass(slots=True)
class ResolutionResult:
    """
    Итог после normalize_levels + stabilize_depths + validate_monotonicity.

    is_canonical:    True если hierarchy прошла все проверки без изменений
    is_stable:       True если hierarchy stable across runs
    audit_log:       все rewrites которые были сделаны
    violations:      список оставшихся нарушений (если не удалось исправить)
    """

    is_canonical: bool
    is_stable: bool
    audit_log: ResolutionAuditLog
    violations: list[str] = field(default_factory=list)

    @property
    def has_violations(self) -> bool:
        return bool(self.violations)

    @property
    def was_rewritten(self) -> bool:
        return self.audit_log.total_rewrites > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_canonical": self.is_canonical,
            "is_stable": self.is_stable,
            "was_rewritten": self.was_rewritten,
            "has_violations": self.has_violations,
            "violations": list(self.violations),
            "audit_log": self.audit_log.to_dict(),
        }
    

    