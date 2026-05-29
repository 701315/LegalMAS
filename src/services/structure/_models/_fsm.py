# src/services/structure/_models/_fsm.py

"""
Phase 3 — Deterministic FSM contracts.

FSMEvent   — secondary artifact, фиксирует что произошло при attach.
FSMStack   — типизированный stack entry.

ВАЖНО:
- FSM отвечает ТОЛЬКО за: stack transitions, parent-child attach,
  node closing, hierarchy traversal.
- FSM НЕ отвечает за: semantics, recovery, confidence, chunking, LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FSMEventType(str, Enum):
    """
    Тип события FSM — secondary artifact.

    Используется для: debugging, audit, telemetry, retrieval diagnostics.
    НЕ используется для: reconstruct tree (дерево строится напрямую).
    """

    ATTACHED_CHILD = "attached_child"
    ATTACHED_ROOT = "attached_root"
    STACK_CLOSED = "stack_closed"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    SKIPPED_INVALID = "skipped_invalid"
    BEST_EFFORT_ROOT = "best_effort_root"


@dataclass(slots=True)
class FSMEvent:
    """
    Событие FSM — secondary artifact.

    Фиксирует что произошло при обработке одного heading candidate.
    Порядок событий в списке = порядок обработки = порядок в документе.
    """

    event_type: FSMEventType
    raw_uid: str
    scope: str
    level: int
    parent_raw_uid: str | None = None
    reject_reason: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "raw_uid": self.raw_uid,
            "scope": self.scope,
            "level": self.level,
            "parent_raw_uid": self.parent_raw_uid,
            "reject_reason": self.reject_reason,
        }


@dataclass(slots=True)
class FSMAttachResult:
    """
    Результат операции attach одного узла.

    attached:    True если узел прикреплён в дерево.
    event_type:  что именно произошло.
    parent_raw_uid: к какому parent прикреплён (None если root).
    reject_reason:  причина пропуска (только если not attached).
    """

    attached: bool
    event_type: FSMEventType
    parent_raw_uid: str | None = None
    reject_reason: str | None = None

    @property
    def is_root(self) -> bool:
        return self.event_type in {
            FSMEventType.ATTACHED_ROOT,
            FSMEventType.BEST_EFFORT_ROOT,
        }

    @property
    def is_best_effort(self) -> bool:
        return self.event_type == FSMEventType.BEST_EFFORT_ROOT


        