# src/services/structure/hierarchy_state_machine.py

"""
HierarchyStateMachine — state machine для сборки mutable дерева иерархии.

Роль модуля:
- инкапсулировать логику transitions между узлами дерева;
- правильно закрывать peer-level sections при встрече следующего peer heading;
- не поднимать definition_item в sibling sections;
- строить best-effort tree даже при средних confidence headings;
- запрещать total downgrade при наличии валидных headings;
- минимизировать ложные root-level best-effort узлы для numeric descendants.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from core.logging import get_logger
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
class AttachResult:
    attached: bool
    attach_mode: str
    parent_effective_uid: str | None = None
    reject_reason: str | None = None


@dataclass(slots=True)
class _DeferredNode:
    node: MutableHierarchyNode
    raw_uid: str
    semantic_type: str | None = None


@dataclass
class HierarchyBuildSummary:
    total_candidates: int = 0
    attached_as_child: int = 0
    attached_as_root: int = 0
    attached_best_effort: int = 0
    attached_deferred_child: int = 0

    skipped_semantic_negative: int = 0
    skipped_invalid: int = 0
    duplicate_uid_skipped: int = 0
    parent_level_rejected: int = 0

    deferred_numeric_total: int = 0
    deferred_numeric_attached: int = 0
    deferred_numeric_unresolved: int = 0
    numeric_parent_chain_attach_count: int = 0
    best_effort_due_to_missing_parent: int = 0
    best_effort_due_to_deferred_failure: int = 0

    root_count: int = 0
    max_depth_reached: int = 0
    has_valid_root_sections: bool = False
    structure_degraded: bool = False
    degradation_reasons: list[str] = field(default_factory=list)

    numeric_root_count: int = 0
    appendix_root_count: int = 0
    consecutive_root_numeric_chain_len: int = 0

    quality_gates: dict[str, Any] = field(default_factory=dict)

    def mark_degraded(self, reason: str) -> None:
        if not self.structure_degraded:
            self.structure_degraded = True
        if reason not in self.degradation_reasons:
            self.degradation_reasons.append(reason)

    def clear_degraded(self, reason: str | None = None) -> None:
        self.structure_degraded = False
        if reason and reason not in self.degradation_reasons:
            self.degradation_reasons.append(reason)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_candidates": self.total_candidates,
            "attached_as_child": self.attached_as_child,
            "attached_as_root": self.attached_as_root,
            "attached_best_effort": self.attached_best_effort,
            "attached_deferred_child": self.attached_deferred_child,
            "skipped_semantic_negative": self.skipped_semantic_negative,
            "skipped_invalid": self.skipped_invalid,
            "duplicate_uid_skipped": self.duplicate_uid_skipped,
            "parent_level_rejected": self.parent_level_rejected,
            "deferred_numeric_total": self.deferred_numeric_total,
            "deferred_numeric_attached": self.deferred_numeric_attached,
            "deferred_numeric_unresolved": self.deferred_numeric_unresolved,
            "numeric_parent_chain_attach_count": self.numeric_parent_chain_attach_count,
            "best_effort_due_to_missing_parent": self.best_effort_due_to_missing_parent,
            "best_effort_due_to_deferred_failure": self.best_effort_due_to_deferred_failure,
            "root_count": self.root_count,
            "max_depth_reached": self.max_depth_reached,
            "has_valid_root_sections": self.has_valid_root_sections,
            "structure_degraded": self.structure_degraded,
            "degradation_reasons": list(self.degradation_reasons),
            "numeric_root_count": self.numeric_root_count,
            "appendix_root_count": self.appendix_root_count,
            "consecutive_root_numeric_chain_len": self.consecutive_root_numeric_chain_len,
            "quality_gates": dict(self.quality_gates),
        }


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
    uid = _normalize_uid(uid).lower()
    return uid.startswith("appendix-") or uid.startswith("приложение-")


def _extract_root_numeric_value(uid: str) -> int | None:
    if not _is_root_numeric_uid(uid):
        return None
    try:
        return int(uid.strip())
    except Exception:
        return None


def _longest_consecutive_chain(values: list[int]) -> int:
    if not values:
        return 0
    uniq = sorted(set(v for v in values if v >= 1))
    if not uniq:
        return 0
    best = 1
    cur = 1
    for i in range(1, len(uniq)):
        if uniq[i] == uniq[i - 1] + 1:
            cur += 1
            best = max(best, cur)
        else:
            cur = 1
    return best


def _uid_level(uid: str) -> int:
    uid = _normalize_uid(uid)
    if not _is_numeric_uid(uid):
        return 1
    return uid.count(".") + 1


def _uid_parent_raw(uid: str) -> str | None:
    uid = _normalize_uid(uid)
    if not _is_numeric_uid(uid) or "." not in uid:
        return None
    return uid.rsplit(".", 1)[0]


def _is_semantic_negative_for_section(semantic_type: str | None) -> bool:
    if not semantic_type:
        return False
    return semantic_type.lower().strip() in NEGATIVE_HEADING_SEMANTIC_TYPES


class HierarchyStateMachine:
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
        self._max_uid_depth = int(max_uid_depth)

        self._root_nodes: list[MutableHierarchyNode] = []
        self._nodes_by_raw_uid: dict[str, MutableHierarchyNode] = {}
        self._open_stack: list[tuple[str, MutableHierarchyNode]] = []
        self._last_node_by_level: dict[int, MutableHierarchyNode] = {}
        self._deferred_numeric_nodes: list[_DeferredNode] = []

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
        self._numeric_parent_chain_attach_count = 0
        self._best_effort_due_to_missing_parent = 0
        self._best_effort_due_to_deferred_failure = 0

    @property
    def root_nodes(self) -> list[MutableHierarchyNode]:
        self.resolve_deferred()
        return list(self._root_nodes)

    @property
    def nodes_by_raw_uid(self) -> dict[str, MutableHierarchyNode]:
        return dict(self._nodes_by_raw_uid)

    def attach(
        self,
        node: MutableHierarchyNode,
        *,
        raw_uid: str,
        semantic_type: str | None = None,
    ) -> AttachResult:
        self._total += 1
        raw_uid = _normalize_uid(raw_uid)

        if not raw_uid:
            self._skipped_invalid += 1
            logger.warning(
                "STRUCTURE hsm_attach_skipped_empty_uid",
                extra={
                    "document_id": self._document_id,
                    "scope": self._scope,
                    "effective_uid": node.effective_uid,
                },
            )
            return AttachResult(
                attached=False,
                attach_mode="skipped",
                reject_reason="empty_raw_uid",
            )

        if raw_uid in self._nodes_by_raw_uid:
            self._duplicate_skipped += 1
            logger.warning(
                "STRUCTURE hsm_attach_skipped_duplicate_uid",
                extra={
                    "document_id": self._document_id,
                    "scope": self._scope,
                    "raw_uid": raw_uid,
                    "existing_effective_uid": self._nodes_by_raw_uid[raw_uid].effective_uid,
                    "new_effective_uid": node.effective_uid,
                },
            )
            return AttachResult(
                attached=False,
                attach_mode="skipped",
                reject_reason="duplicate_uid",
            )

        if _is_semantic_negative_for_section(semantic_type):
            self._skipped_semantic += 1
            node.diagnostics["semantic_attach_skipped"] = True
            node.diagnostics["semantic_type_at_attach"] = semantic_type
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
            self._nodes_by_raw_uid[raw_uid] = node
            return AttachResult(
                attached=False,
                attach_mode="skipped",
                reject_reason=f"semantic_negative:{semantic_type}",
            )

        numeric = _is_numeric_uid(raw_uid)
        level = _uid_level(raw_uid) if numeric else 1
        if level > self._max_uid_depth:
            level = self._max_uid_depth

        self._max_depth = max(self._max_depth, level)

        node.level = max(1, level)
        node.diagnostics["semantic_type_at_attach"] = semantic_type
        node.diagnostics["attach_level"] = level
        node.diagnostics["numeric_uid"] = numeric
        node.diagnostics["scope"] = self._scope
        node.diagnostics["raw_uid"] = raw_uid

        self._nodes_by_raw_uid[raw_uid] = node

        if self._is_plausible_root(raw_uid=raw_uid, semantic_type=semantic_type):
            node.diagnostics["parent_attach_status"] = "root"
            node.diagnostics["root_reason"] = self._classify_root_reason(raw_uid, semantic_type)
            self._attach_to_root(node, raw_uid=raw_uid)
            self._attached_root += 1
            return AttachResult(
                attached=True,
                attach_mode="root",
                parent_effective_uid=None,
            )

        parent_node = self._find_parent_candidate(raw_uid=raw_uid, level=level)

        if parent_node is not None:
            if parent_node.level >= level:
                self._parent_level_rejected += 1
                node.diagnostics["parent_attach_status"] = "rejected_invalid_parent_level"
                node.diagnostics["parent_level_mismatch"] = True
                node.diagnostics["parent_raw_uid_candidate"] = parent_node.raw_uid

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
                    return AttachResult(
                        attached=True,
                        attach_mode="best_effort_root",
                        parent_effective_uid=None,
                        reject_reason="parent_level_mismatch",
                    )

                self._skipped_invalid += 1
                return AttachResult(
                    attached=False,
                    attach_mode="skipped",
                    reject_reason="parent_level_mismatch",
                )

            self._attach_as_child(parent_node=parent_node, node=node, raw_uid=raw_uid)
            if numeric:
                self._numeric_parent_chain_attach_count += 1
                node.diagnostics["attached_via_numeric_parent_chain"] = True
            return AttachResult(
                attached=True,
                attach_mode="child",
                parent_effective_uid=parent_node.effective_uid,
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
            return AttachResult(
                attached=False,
                attach_mode="skipped",
                reject_reason="parent_not_found_best_effort_disabled",
            )

        self._attach_best_effort_root(
            node=node,
            raw_uid=raw_uid,
            reason="parent_not_found_in_stack",
        )
        self._best_effort_due_to_missing_parent += 1
        return AttachResult(
            attached=True,
            attach_mode="best_effort_root",
            parent_effective_uid=None,
            reject_reason="parent_not_found_in_stack",
        )

    def resolve_deferred(self) -> None:
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
                    node.diagnostics["deferred_resolution_status"] = "attached"
                    self._deferred_numeric_attached += 1
                    self._attached_deferred_child += 1
                    progress = True
                    continue

                still_pending.append(item)

            pending = still_pending

        if pending:
            for item in pending:
                node = item.node
                raw_uid = item.raw_uid
                self._deferred_numeric_unresolved += 1
                if self._allow_best_effort:
                    self._attach_best_effort_root(
                        node=node,
                        raw_uid=raw_uid,
                        reason="deferred_resolution_failed",
                    )
                    self._best_effort_due_to_deferred_failure += 1
                else:
                    self._skipped_invalid += 1
                    node.diagnostics["parent_attach_status"] = "skipped"
                    node.diagnostics["skip_reason"] = "deferred_resolution_failed"

    def build_summary(self) -> HierarchyBuildSummary:
        self.resolve_deferred()

        summary = HierarchyBuildSummary(
            total_candidates=self._total,
            attached_as_child=self._attached_child,
            attached_as_root=self._attached_root,
            attached_best_effort=self._attached_best_effort,
            attached_deferred_child=self._attached_deferred_child,
            skipped_semantic_negative=self._skipped_semantic,
            skipped_invalid=self._skipped_invalid,
            duplicate_uid_skipped=self._duplicate_skipped,
            parent_level_rejected=self._parent_level_rejected,
            deferred_numeric_total=self._deferred_numeric_total,
            deferred_numeric_attached=self._deferred_numeric_attached,
            deferred_numeric_unresolved=self._deferred_numeric_unresolved,
            numeric_parent_chain_attach_count=self._numeric_parent_chain_attach_count,
            best_effort_due_to_missing_parent=self._best_effort_due_to_missing_parent,
            best_effort_due_to_deferred_failure=self._best_effort_due_to_deferred_failure,
            root_count=len(self._root_nodes),
            max_depth_reached=self._max_depth,
        )

        summary.has_valid_root_sections = bool(
            self._root_nodes
            and any(not node.diagnostics.get("semantic_attach_skipped") for node in self._root_nodes)
        )

        summary.numeric_root_count = sum(
            1 for node in self._root_nodes if _is_root_numeric_uid(_normalize_uid(node.raw_uid))
        )
        summary.appendix_root_count = sum(
            1 for node in self._root_nodes if _is_appendix_uid(_normalize_uid(node.raw_uid))
        )
        summary.consecutive_root_numeric_chain_len = _longest_consecutive_chain(
            [
                value
                for value in (
                    _extract_root_numeric_value(_normalize_uid(node.raw_uid))
                    for node in self._root_nodes
                )
                if value is not None
            ]
        )

        total_attached = (
            self._attached_child
            + self._attached_root
            + self._attached_best_effort
            + self._attached_deferred_child
        )

        if self._total > 0 and total_attached == 0:
            summary.mark_degraded("no_nodes_attached")

        if self._total > 0 and not self._root_nodes:
            summary.mark_degraded("no_root_nodes")

        if self._duplicate_skipped > 0:
            dup_ratio = self._duplicate_skipped / max(self._total, 1)
            if dup_ratio >= 0.3:
                summary.mark_degraded("high_duplicate_ratio")

        if self._parent_level_rejected > 0:
            reject_ratio = self._parent_level_rejected / max(self._total, 1)
            if reject_ratio >= 0.25:
                summary.mark_degraded("high_parent_level_rejection")

        if total_attached > 0:
            be_ratio = self._attached_best_effort / max(total_attached, 1)
            if be_ratio >= 0.4:
                summary.mark_degraded("high_best_effort_ratio")

        if self._deferred_numeric_unresolved > 0:
            unresolved_ratio = self._deferred_numeric_unresolved / max(self._deferred_numeric_total, 1)
            if unresolved_ratio >= 0.4:
                summary.mark_degraded("high_unresolved_deferred_numeric_ratio")

        if (
            summary.structure_degraded
            and summary.has_valid_root_sections
            and summary.numeric_root_count >= 3
            and summary.consecutive_root_numeric_chain_len >= 3
        ):
            retained_reasons = [
                reason
                for reason in summary.degradation_reasons
                if reason in {"no_nodes_attached", "no_root_nodes"}
            ]
            if not retained_reasons:
                summary.clear_degraded("recovered_by_numeric_root_chain")

        summary.quality_gates = self._compute_quality_gates(summary)
        return summary

    def _is_plausible_root(self, *, raw_uid: str, semantic_type: str | None) -> bool:
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

    def _pop_stack_to_level(self, incoming_level: int) -> None:
        while self._open_stack:
            top_uid, _top_node = self._open_stack[-1]
            top_level = _uid_level(top_uid) if _is_numeric_uid(top_uid) else 1
            if top_level >= incoming_level:
                self._open_stack.pop()
            else:
                break

    def _find_numeric_parent(self, raw_uid: str) -> MutableHierarchyNode | None:
        parent_raw = _uid_parent_raw(raw_uid)
        while parent_raw:
            parent = self._nodes_by_raw_uid.get(parent_raw)
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
        numeric = _is_numeric_uid(raw_uid)

        if numeric and level > 1:
            parent = self._find_numeric_parent(raw_uid)
            if parent is not None:
                return parent

        self._pop_stack_to_level(level)

        for top_uid, top_node in reversed(self._open_stack):
            top_level = _uid_level(top_uid) if _is_numeric_uid(top_uid) else 1
            if top_level < level:
                return top_node

        if numeric and level > 1:
            for candidate_level in range(level - 1, 0, -1):
                candidate = self._last_node_by_level.get(candidate_level)
                if candidate is not None:
                    return candidate

        return None

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

        self._open_stack.append((raw_uid, node))
        self._last_node_by_level[node.level] = node
        self._attached_child += 1

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

        node_level = node.level
        while self._open_stack:
            top_uid, _top_node = self._open_stack[-1]
            top_level = _uid_level(top_uid) if _is_numeric_uid(top_uid) else 1
            if top_level >= node_level:
                self._open_stack.pop()
            else:
                break

        self._open_stack.append((raw_uid, node))
        self._last_node_by_level[node.level] = node

    def _attach_best_effort_root(
        self,
        *,
        node: MutableHierarchyNode,
        raw_uid: str,
        reason: str,
    ) -> None:
        node.diagnostics["parent_attach_status"] = "best_effort_root"
        node.diagnostics["best_effort_reason"] = reason
        node.citability = "low" if node.citability != "technical" else node.citability

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
        self._attached_best_effort += 1

    def _defer_numeric_node(
        self,
        *,
        node: MutableHierarchyNode,
        raw_uid: str,
        semantic_type: str | None,
        reason: str,
    ) -> AttachResult:
        node.diagnostics["parent_attach_status"] = "deferred_child"
        node.diagnostics["deferred_reason"] = reason
        node.diagnostics["deferred_scope"] = self._scope

        self._deferred_numeric_nodes.append(
            _DeferredNode(node=node, raw_uid=raw_uid, semantic_type=semantic_type)
        )
        self._deferred_numeric_total += 1

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

        return AttachResult(
            attached=False,
            attach_mode="deferred_child",
            parent_effective_uid=None,
            reject_reason=reason,
        )

    def _compute_quality_gates(
        self,
        summary: HierarchyBuildSummary,
    ) -> dict[str, Any]:
        total_attached = (
            self._attached_child
            + self._attached_root
            + self._attached_best_effort
            + self._attached_deferred_child
        )
        best_effort_ratio = (
            self._attached_best_effort / max(total_attached, 1) if total_attached > 0 else 0.0
        )

        recoverable_numeric_backbone = (
            summary.has_valid_root_sections
            and summary.numeric_root_count >= 3
            and summary.consecutive_root_numeric_chain_len >= 3
        )

        deferred_resolution_good = (
            summary.deferred_numeric_total == 0
            or summary.deferred_numeric_attached >= summary.deferred_numeric_unresolved
        )

        if not summary.has_valid_root_sections:
            structure_confidence = "LOW"
        elif summary.structure_degraded:
            structure_confidence = "MEDIUM" if recoverable_numeric_backbone else "LOW"
        else:
            if best_effort_ratio < 0.25 and deferred_resolution_good:
                structure_confidence = "HIGH"
            elif best_effort_ratio < 0.45 or recoverable_numeric_backbone:
                structure_confidence = "MEDIUM"
            else:
                structure_confidence = "LOW"

        section_chunking_allowed = (
            summary.has_valid_root_sections
            and (
                not summary.structure_degraded
                or recoverable_numeric_backbone
            )
            and (
                best_effort_ratio < 0.5
                or recoverable_numeric_backbone
            )
            and summary.root_count > 0
        )

        technical_fallback_only = (
            not summary.has_valid_root_sections
            or (summary.structure_degraded and not recoverable_numeric_backbone)
        )

        hierarchy_quality = (
            "good"
            if structure_confidence == "HIGH"
            else "partial"
            if structure_confidence == "MEDIUM"
            else "failed"
        )

        return {
            "section_chunking_allowed": section_chunking_allowed,
            "technical_fallback_only": technical_fallback_only,
            "structure_confidence": structure_confidence,
            "recoverable_hierarchy_used": (
                self._attached_best_effort > 0
                or recoverable_numeric_backbone
                or self._deferred_numeric_attached > 0
            ),
            "recoverable_numeric_backbone": recoverable_numeric_backbone,
            "deferred_resolution_good": deferred_resolution_good,
            "total_fallback_blocked": self._skipped_invalid + self._skipped_semantic,
            "hierarchy_quality": hierarchy_quality,
            "best_effort_ratio": round(best_effort_ratio, 4),
            "numeric_root_count": summary.numeric_root_count,
            "appendix_root_count": summary.appendix_root_count,
            "consecutive_root_numeric_chain_len": summary.consecutive_root_numeric_chain_len,
            "deferred_numeric_total": summary.deferred_numeric_total,
            "deferred_numeric_attached": summary.deferred_numeric_attached,
            "deferred_numeric_unresolved": summary.deferred_numeric_unresolved,
            "numeric_parent_chain_attach_count": summary.numeric_parent_chain_attach_count,
        }
    

    
