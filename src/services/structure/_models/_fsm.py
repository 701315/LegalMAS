# src/services/structure/_models/_fsm.py

"""
Deterministic FSM contracts.

FSMEvent        — secondary artifact, фиксирует что произошло при attach.
FSMStackEntry   — типизированный stack entry.
FSMAttachResult — результат attach-операции одного узла.

ВАЖНО:
- FSM отвечает ТОЛЬКО за: stack transitions, parent-child attach,
  node closing, hierarchy traversal.
- FSM НЕ отвечает за: semantics, recovery policy, confidence,
  chunking, LLM, retrieval quality gates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


def _norm_required_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be str, got {type(value).__name__}")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _norm_optional_str(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be str|None, got {type(value).__name__}")
    normalized = value.strip()
    return normalized or None


def _norm_positive_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{field_name} must be int, got {type(value).__name__}")
    if value < 1:
        raise ValueError(f"{field_name} must be >= 1, got {value}")
    return value


def _ensure_extra_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"extra must be dict[str, Any], got {type(value).__name__}")
    return dict(value)


class FSMEventType(str, Enum):
    """
    Тип события FSM — secondary artifact.

    Используется для:
    - debugging;
    - audit;
    - telemetry;
    - retrieval diagnostics.

    НЕ используется для reconstruct tree:
    дерево строится напрямую, а не по event stream.
    """

    ATTACHED_CHILD = "attached_child"
    ATTACHED_ROOT = "attached_root"
    STACK_CLOSED = "stack_closed"

    DEFERRED_CHILD = "deferred_child"
    PARENT_LEVEL_REJECTED = "parent_level_rejected"

    SKIPPED_DUPLICATE = "skipped_duplicate"
    SKIPPED_INVALID = "skipped_invalid"
    SKIPPED_SEMANTIC_NEGATIVE = "skipped_semantic_negative"

    BEST_EFFORT_ROOT = "best_effort_root"


@dataclass(slots=True, frozen=True)
class FSMStackEntry:
    """
    Типизированный stack entry для deterministic FSM.

    Хранит только stable metadata, необходимую для stack traversal.
    """

    raw_uid: str
    level: int
    effective_uid: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "raw_uid",
            _norm_required_str(self.raw_uid, "FSMStackEntry.raw_uid"),
        )
        object.__setattr__(
            self,
            "level",
            _norm_positive_int(self.level, "FSMStackEntry.level"),
        )
        object.__setattr__(
            self,
            "effective_uid",
            _norm_required_str(self.effective_uid, "FSMStackEntry.effective_uid"),
        )


@dataclass(slots=True)
class FSMEvent:
    """
    Событие FSM — secondary artifact.

    Фиксирует outcome обработки одного heading candidate.
    Порядок событий = порядок обработки в документе.
    """

    event_type: FSMEventType
    raw_uid: str
    scope: str
    level: int
    parent_raw_uid: str | None = None
    reject_reason: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, FSMEventType):
            raise ValueError(
                f"FSMEvent.event_type must be FSMEventType, got {type(self.event_type).__name__}"
            )

        self.raw_uid = _norm_required_str(self.raw_uid, "FSMEvent.raw_uid")
        self.scope = _norm_required_str(self.scope, "FSMEvent.scope")
        self.level = _norm_positive_int(self.level, "FSMEvent.level")
        self.parent_raw_uid = _norm_optional_str(self.parent_raw_uid, "FSMEvent.parent_raw_uid")
        self.reject_reason = _norm_optional_str(self.reject_reason, "FSMEvent.reject_reason")
        self.extra = _ensure_extra_dict(self.extra)

    @property
    def is_attach(self) -> bool:
        return self.event_type in {
            FSMEventType.ATTACHED_CHILD,
            FSMEventType.ATTACHED_ROOT,
            FSMEventType.BEST_EFFORT_ROOT,
        }

    @property
    def is_skip(self) -> bool:
        return self.event_type in {
            FSMEventType.SKIPPED_DUPLICATE,
            FSMEventType.SKIPPED_INVALID,
            FSMEventType.SKIPPED_SEMANTIC_NEGATIVE,
        }

    @property
    def is_deferred(self) -> bool:
        return self.event_type == FSMEventType.DEFERRED_CHILD

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "raw_uid": self.raw_uid,
            "scope": self.scope,
            "level": self.level,
            "parent_raw_uid": self.parent_raw_uid,
            "reject_reason": self.reject_reason,
            "extra": dict(self.extra),
        }


@dataclass(slots=True)
class FSMAttachResult:
    """
    Результат attach-операции для одного узла.

    attached:
        True если узел реально attach-нут в дерево.
        False если узел skipped или deferred.

    event_type:
        Typed outcome attach attempt.

    parent_raw_uid:
        raw_uid parent, если attach произошёл как child.

    reject_reason:
        Причина skip / defer / best-effort fallback.
    """

    attached: bool
    event_type: FSMEventType
    parent_raw_uid: str | None = None
    reject_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.attached, bool):
            raise ValueError(
                f"FSMAttachResult.attached must be bool, got {type(self.attached).__name__}"
            )
        if not isinstance(self.event_type, FSMEventType):
            raise ValueError(
                f"FSMAttachResult.event_type must be FSMEventType, got {type(self.event_type).__name__}"
            )

        self.parent_raw_uid = _norm_optional_str(
            self.parent_raw_uid,
            "FSMAttachResult.parent_raw_uid",
        )
        self.reject_reason = _norm_optional_str(
            self.reject_reason,
            "FSMAttachResult.reject_reason",
        )

    @property
    def is_root(self) -> bool:
        return self.event_type in {
            FSMEventType.ATTACHED_ROOT,
            FSMEventType.BEST_EFFORT_ROOT,
        }

    @property
    def is_child(self) -> bool:
        return self.event_type == FSMEventType.ATTACHED_CHILD

    @property
    def is_best_effort(self) -> bool:
        return self.event_type == FSMEventType.BEST_EFFORT_ROOT

    @property
    def is_deferred(self) -> bool:
        return self.event_type == FSMEventType.DEFERRED_CHILD

    @property
    def is_skipped(self) -> bool:
        return self.event_type in {
            FSMEventType.SKIPPED_DUPLICATE,
            FSMEventType.SKIPPED_INVALID,
            FSMEventType.SKIPPED_SEMANTIC_NEGATIVE,
            FSMEventType.PARENT_LEVEL_REJECTED,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "attached": self.attached,
            "event_type": self.event_type.value,
            "parent_raw_uid": self.parent_raw_uid,
            "reject_reason": self.reject_reason,
            "is_root": self.is_root,
            "is_child": self.is_child,
            "is_best_effort": self.is_best_effort,
            "is_deferred": self.is_deferred,
            "is_skipped": self.is_skipped,
        }

        