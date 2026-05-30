# src/services/structure/hierarchy_state_machine.py

"""
HierarchyStateMachine — deterministic FSM runtime для сборки mutable дерева иерархии.

Роль модуля:
- инкапсулировать deterministic transitions между узлами дерева;
- корректно закрывать peer-level branches при встрече следующего heading;
- строить scoped mutable tree без semantic/LLM логики;
- минимизировать ложные root-level best-effort узлы для numeric descendants;
- поддерживать bounded deferred resolution для numeric children без известного parent.

Важно:
- FSM не занимается chunking;
- FSM не выполняет quality gate policy для pipeline;
- FSM не вычисляет structural confidence;
- FSM не делает global recovery;
- FSM summary здесь остаётся только как Phase 3 diagnostic artifact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from core.logging import get_logger
from services.structure._models._fsm import (
    FSMEvent,
    FSMEventType,
    FSMAttachResult,
    FSMStackEntry,
)
from services.structure._models._fsm_summary import FSMBuildSummary
from services.structure.models import (
    DEFAULT_SCOPE,
    NEGATIVE_HEADING_SEMANTIC_TYPES,
    MutableHierarchyNode,
    NODE_KIND_LEAF,
    NODE_KIND_SECTION,
)

logger = get_logger(__name__)

_NUMERIC_UID_RE = re.compile(r"^\d+(?:\.\d+)*$")
_ROOT_NUMERIC_UID_RE = re.compile(r"^\d+$")


@dataclass(slots=True)
class _DeferredNode:
    node: MutableHierarchyNode
    raw_uid: str
    semantic_type: str | None = None


def _normalize_uid(value: Any) -> str:
    return str(value or "").strip()


def _normalize_scope(value: Any) -> str:
    scope = _normalize_uid(value)
    return scope or DEFAULT_SCOPE


def _is_numeric_uid(uid: str) -> bool:
    return bool(_NUMERIC_UID_RE.fullmatch(_normalize_uid(uid)))


def _is_root_numeric_uid(uid: str) -> bool:
    return bool(_ROOT_NUMERIC_UID_RE.fullmatch(_normalize_uid(uid)))


def _is_appendix_uid(uid: str) -> bool:
    normalized = _normalize_uid(uid).lower()
    return normalized.startswith(
        ("appendix-", "приложение-", "annex-", "schedule-", "exhibit-")
    )


def _uid_level(uid: str) -> int:
    normalized = _normalize_uid(uid)
    if not _is_numeric_uid(normalized):
        return 1
    return normalized.count(".") + 1


def _uid_parent_raw(uid: str) -> str | None:
    normalized = _normalize_uid(uid)
    if not _is_numeric_uid(normalized) or "." not in normalized:
        return None
    return normalized.rsplit(".", 1)[0]


def _is_semantic_negative_for_section(semantic_type: str | None) -> bool:
    if not semantic_type:
        return False
    return semantic_type.lower().strip() in NEGATIVE_HEADING_SEMANTIC_TYPES


class HierarchyStateMachine:
    """
    Deterministic FSM runtime for one scope.

    Инварианты:
    - _attached_nodes_by_raw_uid содержит только реально attach-нутые узлы;
    - _seen_raw_uids содержит все raw_uid, уже обработанные attach();
    - root_nodes property не имеет side effects;
    - deferred resolution запускается только через finalize()/build_summary().
    """

    def __init__(
        self,
        *,
        scope: str,
        document_id: str,
        allow_best_effort: bool = True,
        max_uid_depth: int = 8,
    ) -> None:
        self._scope = _normalize_scope(scope)
        self._document_id = str(document_id or "").strip()
        self._allow_best_effort = bool(allow_best_effort)
        self._max_uid_depth = max(1, int(max_uid_depth))

        self._root_nodes: list[MutableHierarchyNode] = []
        self._attached_nodes_by_raw_uid: dict[str, MutableHierarchyNode] = {}
        self._seen_raw_uids: set[str] = set()

        self._stack_entries: list[FSMStackEntry] = []
        self._stack_nodes: list[MutableHierarchyNode] = []
        self._last_node_by_level: dict[int, MutableHierarchyNode] = {}

        self._deferred_numeric_nodes: list[_DeferredNode] = []
        self._events: list[FSMEvent] = []
        self._finalized: bool = False

        self._total = 0
        self._attached_child = 0
        self._attached_root = 0
        self._attached_best_effort = 0
        self._attached_deferred_child = 0

        self._skipped_semantic = 0
        self._skipped_invalid = 0
        self._duplicate_skipped = 0
        self._parent_level_rejected = 0
        self._max_depth = 0

        self._deferred_numeric_total = 0
        self._deferred_numeric_attached = 0
        self._deferred_numeric_unresolved = 0

    @property
    def root_nodes(self) -> list[MutableHierarchyNode]:
        return list(self._root_nodes)

    @property
    def nodes_by_raw_uid(self) -> dict[str, MutableHierarchyNode]:
        return dict(self._attached_nodes_by_raw_uid)

    @property
    def events(self) -> list[FSMEvent]:
        return list(self._events)

    @property
    def is_finalized(self) -> bool:
        return self._finalized

    def finalize(self) -> None:
        if self._finalized:
            return
        self.resolve_deferred()
        self._finalized = True

    def attach(
        self,
        node: MutableHierarchyNode,
        *,
        raw_uid: str,
        semantic_type: str | None = None,
    ) -> FSMAttachResult:
        """
        Основная attach-операция FSM.

        Приоритеты:
        1. Валидный root — attach в root set.
        2. Валидный parent — attach as child.
        3. Numeric descendant без parent — defer.
        4. Non-numeric / non-recoverable — best effort root только если разрешено.
        """
        if self._finalized:
            raise RuntimeError("HierarchyStateMachine.attach() called after finalize()")

        self._total += 1
        raw_uid = _normalize_uid(raw_uid)

        if not raw_uid:
            self._skipped_invalid += 1
            self._emit_event(
                event_type=FSMEventType.SKIPPED_INVALID,
                raw_uid="<empty>",
                level=1,
                reject_reason="empty_raw_uid",
            )
            logger.warning(
                "STRUCTURE hsm_attach_skipped_empty_uid",
                extra={
                    "document_id": self._document_id,
                    "scope": self._scope,
                    "effective_uid": node.effective_uid,
                },
            )
            return FSMAttachResult(
                attached=False,
                event_type=FSMEventType.SKIPPED_INVALID,
                reject_reason="empty_raw_uid",
            )

        if raw_uid in self._seen_raw_uids:
            self._duplicate_skipped += 1
            self._emit_event(
                event_type=FSMEventType.SKIPPED_DUPLICATE,
                raw_uid=raw_uid,
                level=_uid_level(raw_uid),
                reject_reason="duplicate_uid",
            )
            logger.warning(
                "STRUCTURE hsm_attach_skipped_duplicate_uid",
                extra={
                    "document_id": self._document_id,
                    "scope": self._scope,
                    "raw_uid": raw_uid,
                    "new_effective_uid": node.effective_uid,
                },
            )
            return FSMAttachResult(
                attached=False,
                event_type=FSMEventType.SKIPPED_DUPLICATE,
                reject_reason="duplicate_uid",
            )

        self._seen_raw_uids.add(raw_uid)

        if _is_semantic_negative_for_section(semantic_type):
            self._skipped_semantic += 1
            node.diagnostics["semantic_attach_skipped"] = True
            node.diagnostics["semantic_type_at_attach"] = semantic_type
            node.diagnostics["scope"] = self._scope
            node.diagnostics["raw_uid"] = raw_uid

            self._emit_event(
                event_type=FSMEventType.SKIPPED_SEMANTIC_NEGATIVE,
                raw_uid=raw_uid,
                level=_uid_level(raw_uid),
                reject_reason=f"semantic_negative:{semantic_type}",
            )

            logger.debug(
                "STRUCTURE hsm_attach_skipped_semantic_negative",
                extra={
                    "document_id": self._document_id,
                    "scope": self._scope,
                    "raw_uid": raw_uid,
                    "semantic_type": semantic_type,
                    "effective_uid": node.effective_uid,
                },
            )
            return FSMAttachResult(
                attached=False,
                event_type=FSMEventType.SKIPPED_SEMANTIC_NEGATIVE,
                reject_reason=f"semantic_negative:{semantic_type}",
            )

        numeric = _is_numeric_uid(raw_uid)
        level = _uid_level(raw_uid) if numeric else 1
        level = min(level, self._max_uid_depth)
        self._max_depth = max(self._max_depth, level)

        node.level = max(1, level)
        node.diagnostics["semantic_type_at_attach"] = semantic_type
        node.diagnostics["attach_level"] = level
        node.diagnostics["numeric_uid"] = numeric
        node.diagnostics["scope"] = self._scope
        node.diagnostics["raw_uid"] = raw_uid

        if self._is_plausible_root(raw_uid=raw_uid, semantic_type=semantic_type):
            node.diagnostics["parent_attach_status"] = "root"
            node.diagnostics["root_reason"] = self._classify_root_reason(raw_uid, semantic_type)
            self._attach_to_root(node, raw_uid=raw_uid)
            self._attached_root += 1

            self._emit_event(
                event_type=FSMEventType.ATTACHED_ROOT,
                raw_uid=raw_uid,
                level=node.level,
                extra={"root_reason": node.diagnostics["root_reason"]},
            )

            return FSMAttachResult(
                attached=True,
                event_type=FSMEventType.ATTACHED_ROOT,
                parent_raw_uid=None,
            )

        parent_node = self._find_parent_candidate(raw_uid=raw_uid, level=level)

        if parent_node is not None:
            if parent_node.level >= level:
                self._parent_level_rejected += 1
                node.diagnostics["parent_attach_status"] = "rejected_invalid_parent_level"
                node.diagnostics["parent_level_mismatch"] = True
                node.diagnostics["parent_raw_uid_candidate"] = parent_node.raw_uid

                self._emit_event(
                    event_type=FSMEventType.PARENT_LEVEL_REJECTED,
                    raw_uid=raw_uid,
                    level=level,
                    parent_raw_uid=parent_node.raw_uid,
                    reject_reason="parent_level_mismatch",
                )

                logger.warning(
                    "STRUCTURE hsm_parent_level_mismatch",
                    extra={
                        "document_id": self._document_id,
                        "scope": self._scope,
                        "raw_uid": raw_uid,
                        "level": level,
                        "parent_raw_uid": parent_node.raw_uid,
                        "parent_level": parent_node.level,
                    },
                )

                if numeric and level > 1:
                    return self._defer_numeric_node(
                        node=node,
                        raw_uid=raw_uid,
                        semantic_type=semantic_type,
                        reason="parent_level_mismatch",
                    )

                if self._allow_best_effort:
                    self._attach_best_effort_root(
                        node=node,
                        raw_uid=raw_uid,
                        reason="parent_level_mismatch",
                    )
                    self._attached_best_effort += 1
                    self._emit_event(
                        event_type=FSMEventType.BEST_EFFORT_ROOT,
                        raw_uid=raw_uid,
                        level=node.level,
                        reject_reason="parent_level_mismatch",
                    )
                    return FSMAttachResult(
                        attached=True,
                        event_type=FSMEventType.BEST_EFFORT_ROOT,
                        parent_raw_uid=None,
                        reject_reason="parent_level_mismatch",
                    )

                self._skipped_invalid += 1
                self._emit_event(
                    event_type=FSMEventType.SKIPPED_INVALID,
                    raw_uid=raw_uid,
                    level=node.level,
                    parent_raw_uid=parent_node.raw_uid,
                    reject_reason="parent_level_mismatch",
                )
                return FSMAttachResult(
                    attached=False,
                    event_type=FSMEventType.SKIPPED_INVALID,
                    reject_reason="parent_level_mismatch",
                )

            attach_path = self._classify_attach_path(raw_uid=raw_uid, level=level, parent_node=parent_node)
            self._attach_as_child(parent_node=parent_node, node=node, raw_uid=raw_uid)
            self._attached_child += 1

            self._emit_event(
                event_type=FSMEventType.ATTACHED_CHILD,
                raw_uid=raw_uid,
                level=node.level,
                parent_raw_uid=parent_node.raw_uid,
                extra={"attach_path": attach_path},
            )

            return FSMAttachResult(
                attached=True,
                event_type=FSMEventType.ATTACHED_CHILD,
                parent_raw_uid=parent_node.raw_uid,
            )

        if numeric and level > 1:
            return self._defer_numeric_node(
                node=node,
                raw_uid=raw_uid,
                semantic_type=semantic_type,
                reason="numeric_parent_missing",
            )

        if not self._allow_best_effort:
            self._skipped_invalid += 1
            node.diagnostics["parent_attach_status"] = "skipped"
            node.diagnostics["skip_reason"] = "parent_not_found_best_effort_disabled"

            self._emit_event(
                event_type=FSMEventType.SKIPPED_INVALID,
                raw_uid=raw_uid,
                level=node.level,
                reject_reason="parent_not_found_best_effort_disabled",
            )

            return FSMAttachResult(
                attached=False,
                event_type=FSMEventType.SKIPPED_INVALID,
                reject_reason="parent_not_found_best_effort_disabled",
            )

        self._attach_best_effort_root(
            node=node,
            raw_uid=raw_uid,
            reason="parent_not_found_in_stack",
        )
        self._attached_best_effort += 1

        self._emit_event(
            event_type=FSMEventType.BEST_EFFORT_ROOT,
            raw_uid=raw_uid,
            level=node.level,
            reject_reason="parent_not_found_in_stack",
        )

        return FSMAttachResult(
            attached=True,
            event_type=FSMEventType.BEST_EFFORT_ROOT,
            parent_raw_uid=None,
            reject_reason="parent_not_found_in_stack",
        )

    def resolve_deferred(self) -> None:
        """
        Bounded deferred resolution.

        Важно:
        - attach только через уже известный deterministic parent;
        - не создаём synthetic parent;
        - не делаем global recovery;
        - unresolved numeric descendant может стать best-effort root только в конце.
        """
        if not self._deferred_numeric_nodes:
            return

        pending = list(self._deferred_numeric_nodes)
        self._deferred_numeric_nodes = []

        progress = True
        while pending and progress:
            progress = False
            still_pending: list[_DeferredNode] = []

            for item in pending:
                node = item.node
                raw_uid = item.raw_uid
                parent = self._find_parent_candidate(raw_uid=raw_uid, level=node.level)

                if parent is not None and parent.level < node.level:
                    self._attach_as_child(parent_node=parent, node=node, raw_uid=raw_uid)
                    self._attached_child += 1
                    self._attached_deferred_child += 1
                    self._deferred_numeric_attached += 1

                    node.diagnostics["deferred_resolution_status"] = "attached"

                    self._emit_event(
                        event_type=FSMEventType.ATTACHED_CHILD,
                        raw_uid=raw_uid,
                        level=node.level,
                        parent_raw_uid=parent.raw_uid,
                        extra={"attach_path": "deferred_resolution"},
                    )

                    progress = True
                    continue

                still_pending.append(item)

            pending = still_pending

        if pending:
            for item in pending:
                node = item.node
                raw_uid = item.raw_uid
                self._deferred_numeric_unresolved += 1
                node.diagnostics["deferred_resolution_status"] = "unresolved"

                if self._allow_best_effort:
                    self._attach_best_effort_root(
                        node=node,
                        raw_uid=raw_uid,
                        reason="deferred_resolution_failed",
                    )
                    self._attached_best_effort += 1

                    self._emit_event(
                        event_type=FSMEventType.BEST_EFFORT_ROOT,
                        raw_uid=raw_uid,
                        level=node.level,
                        reject_reason="deferred_resolution_failed",
                        extra={"attach_path": "deferred_fallback"},
                    )
                else:
                    self._skipped_invalid += 1
                    node.diagnostics["parent_attach_status"] = "skipped"
                    node.diagnostics["skip_reason"] = "deferred_resolution_failed"

                    self._emit_event(
                        event_type=FSMEventType.SKIPPED_INVALID,
                        raw_uid=raw_uid,
                        level=node.level,
                        reject_reason="deferred_resolution_failed",
                    )

    def build_summary(self) -> FSMBuildSummary:
        """
        Возвращает Phase 3 diagnostic summary по FSM run.

        Важно:
        - summary не содержит quality gates;
        - summary не содержит structure confidence;
        - summary не содержит chunking decisions.
        """
        self.finalize()

        return FSMBuildSummary(
            total_candidates=self._total,
            attached_as_child=self._attached_child,
            attached_as_root=self._attached_root,
            attached_best_effort=self._attached_best_effort,
            attached_deferred_child=self._attached_deferred_child,
            skipped_duplicate=self._duplicate_skipped,
            skipped_invalid=self._skipped_invalid,
            skipped_semantic_negative=self._skipped_semantic,
            parent_level_rejected=self._parent_level_rejected,
            deferred_total=self._deferred_numeric_total,
            deferred_resolved=self._deferred_numeric_attached,
            deferred_unresolved=self._deferred_numeric_unresolved,
            root_count=len(self._root_nodes),
            max_depth_reached=self._max_depth,
            events=list(self._events),
        )

    def _emit_event(
        self,
        *,
        event_type: FSMEventType,
        raw_uid: str,
        level: int,
        parent_raw_uid: str | None = None,
        reject_reason: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self._events.append(
            FSMEvent(
                event_type=event_type,
                raw_uid=raw_uid,
                scope=self._scope,
                level=max(1, int(level)),
                parent_raw_uid=parent_raw_uid,
                reject_reason=reject_reason,
                extra=extra or {},
            )
        )

    def _rebuild_last_node_by_level(self) -> None:
        rebuilt: dict[int, MutableHierarchyNode] = {}
        for node in self._stack_nodes:
            rebuilt[node.level] = node
        self._last_node_by_level = rebuilt

    def _push_stack(self, *, raw_uid: str, node: MutableHierarchyNode) -> None:
        self._stack_entries.append(
            FSMStackEntry(
                raw_uid=raw_uid,
                level=node.level,
                effective_uid=node.effective_uid,
            )
        )
        self._stack_nodes.append(node)
        self._rebuild_last_node_by_level()

    def _pop_stack_to_level(self, incoming_level: int) -> None:
        """
        Закрывает peer/superior branches перед attach нового узла.
        """
        while self._stack_entries:
            top_entry = self._stack_entries[-1]
            if top_entry.level >= incoming_level:
                closed_entry = self._stack_entries.pop()
                self._stack_nodes.pop()
                self._emit_event(
                    event_type=FSMEventType.STACK_CLOSED,
                    raw_uid=closed_entry.raw_uid,
                    level=closed_entry.level,
                )
            else:
                break
        self._rebuild_last_node_by_level()

    def _is_plausible_root(self, *, raw_uid: str, semantic_type: str | None) -> bool:
        """
        Root допустим только для:
        - root numeric uid;
        - appendix-like uid;
        - некоторых document-level headings без numeric UID.
        """
        if _is_root_numeric_uid(raw_uid):
            return True
        if _is_appendix_uid(raw_uid):
            return True

        semantic = str(semantic_type or "").strip().lower()
        if semantic in {
            "section_heading",
            "appendix_heading",
            "document_heading",
            "title",
            "contract_heading",
        } and not _is_numeric_uid(raw_uid):
            return True

        return False

    def _classify_root_reason(self, raw_uid: str, semantic_type: str | None) -> str:
        if _is_root_numeric_uid(raw_uid):
            return "root_numeric_uid"
        if _is_appendix_uid(raw_uid):
            return "appendix_uid"
        semantic = str(semantic_type or "").strip().lower()
        if semantic:
            return f"semantic_root:{semantic}"
        return "root_fallback"

    def _find_numeric_parent(self, raw_uid: str) -> MutableHierarchyNode | None:
        parent_raw = _uid_parent_raw(raw_uid)
        while parent_raw:
            parent = self._attached_nodes_by_raw_uid.get(parent_raw)
            if parent is not None:
                return parent
            parent_raw = _uid_parent_raw(parent_raw)
        return None

    def _find_parent_candidate(
        self,
        *,
        raw_uid: str,
        level: int,
    ) -> MutableHierarchyNode | None:
        """
        Ищет parent в порядке приоритета:
        1. exact numeric parent chain;
        2. current open stack;
        3. last node by lower level (explicit fallback only for numeric descendants).
        """
        numeric = _is_numeric_uid(raw_uid)

        if numeric and level > 1:
            parent = self._find_numeric_parent(raw_uid)
            if parent is not None:
                return parent

        self._pop_stack_to_level(level)

        for idx in range(len(self._stack_entries) - 1, -1, -1):
            stack_entry = self._stack_entries[idx]
            stack_node = self._stack_nodes[idx]
            if stack_entry.level < level:
                return stack_node

        if numeric and level > 1:
            for candidate_level in range(level - 1, 0, -1):
                candidate = self._last_node_by_level.get(candidate_level)
                if candidate is not None:
                    return candidate

        return None

    def _classify_attach_path(
        self,
        *,
        raw_uid: str,
        level: int,
        parent_node: MutableHierarchyNode,
    ) -> str:
        if _is_numeric_uid(raw_uid) and level > 1:
            exact_parent_raw = _uid_parent_raw(raw_uid)
            if exact_parent_raw and parent_node.raw_uid == exact_parent_raw:
                return "exact_numeric_parent"
            if parent_node.raw_uid in {entry.raw_uid for entry in self._stack_entries}:
                return "stack_parent"
            return "last_node_by_level_fallback"
        return "stack_parent"

    def _attach_as_child(
        self,
        *,
        parent_node: MutableHierarchyNode,
        node: MutableHierarchyNode,
        raw_uid: str,
    ) -> None:
        if parent_node.node_kind != NODE_KIND_SECTION:
            parent_node.node_kind = NODE_KIND_SECTION

        parent_node.children.append(node)
        node.diagnostics["parent_attach_status"] = "attached_as_child"
        node.diagnostics["parent_effective_uid"] = parent_node.effective_uid
        node.diagnostics["parent_raw_uid"] = parent_node.raw_uid

        self._attached_nodes_by_raw_uid[raw_uid] = node
        self._push_stack(raw_uid=raw_uid, node=node)

        logger.debug(
            "STRUCTURE hsm_attached_as_child",
            extra={
                "document_id": self._document_id,
                "scope": self._scope,
                "raw_uid": raw_uid,
                "level": node.level,
                "parent_raw_uid": parent_node.raw_uid,
                "parent_level": parent_node.level,
            },
        )

    def _attach_to_root(self, node: MutableHierarchyNode, *, raw_uid: str) -> None:
        node.node_kind = NODE_KIND_LEAF if not node.children else NODE_KIND_SECTION
        self._root_nodes.append(node)
        self._attached_nodes_by_raw_uid[raw_uid] = node

        self._pop_stack_to_level(node.level)
        self._push_stack(raw_uid=raw_uid, node=node)

    def _attach_best_effort_root(
        self,
        *,
        node: MutableHierarchyNode,
        raw_uid: str,
        reason: str,
    ) -> None:
        node.diagnostics["parent_attach_status"] = "best_effort_root"
        node.diagnostics["best_effort_root"] = True
        node.diagnostics["best_effort_reason"] = reason

        logger.debug(
            "STRUCTURE hsm_best_effort_root",
            extra={
                "document_id": self._document_id,
                "scope": self._scope,
                "raw_uid": raw_uid,
                "level": node.level,
                "reason": reason,
            },
        )

        self._attach_to_root(node, raw_uid=raw_uid)

    def _defer_numeric_node(
        self,
        *,
        node: MutableHierarchyNode,
        raw_uid: str,
        semantic_type: str | None,
        reason: str,
    ) -> FSMAttachResult:
        node.diagnostics["parent_attach_status"] = "deferred_child"
        node.diagnostics["deferred_reason"] = reason
        node.diagnostics["deferred_scope"] = self._scope
        node.diagnostics["semantic_type_at_attach"] = semantic_type

        self._deferred_numeric_nodes.append(
            _DeferredNode(node=node, raw_uid=raw_uid, semantic_type=semantic_type)
        )
        self._deferred_numeric_total += 1

        self._emit_event(
            event_type=FSMEventType.DEFERRED_CHILD,
            raw_uid=raw_uid,
            level=node.level,
            reject_reason=reason,
        )

        logger.debug(
            "STRUCTURE hsm_deferred_numeric_child",
            extra={
                "document_id": self._document_id,
                "scope": self._scope,
                "raw_uid": raw_uid,
                "level": node.level,
                "reason": reason,
            },
        )

        return FSMAttachResult(
            attached=False,
            event_type=FSMEventType.DEFERRED_CHILD,
            parent_raw_uid=None,
            reject_reason=reason,
        )

    
