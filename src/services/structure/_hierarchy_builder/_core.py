# src/services/structure/_hierarchy_builder/_core.py

"""Основной оркестратор сборки hierarchy в immutable artifact tree."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.logging import get_logger
from services.structure.hierarchy_state_machine import HierarchyStateMachine
from services.structure._models._fsm_summary import FSMBuildSummary
from services.structure.models import (
    FrozenHierarchyNode,
    MutableHierarchyNode,
    freeze,
)

if TYPE_CHECKING:
    from services.structure._heading_scoring._types import StructureEvidenceBundle

from ._range_logic import _collect_own_text, _compute_own_range
from ._scope_logic import (
    _build_heading_positions,
    _build_scope_boundaries,
    _group_headings_by_scope,
)
from ._traversal import populate_subtree_element_ids
from ._types import HeadingCandidate
from ._utils import (
    _heading_effective_uid,
    _heading_raw_uid,
    _heading_scope,
    _is_strict_numeric_uid,
    _normalize_title,
    level_from_uid,
)

logger = get_logger(__name__)

_SUSPICIOUS_LEAF_RANGE_SPAN_THRESHOLD = 200
_RECOVERABLE_INVALID_HEADING_RATIO = 0.35
_RECOVERABLE_OWN_RANGE_ANOMALY_RATIO = 0.35
_FATAL_ROOTLESS_WITH_NODES = True


def _is_fsm_summary_degraded(summary: Any) -> bool:
    if summary is None:
        return False

    attached_best_effort = int(getattr(summary, "attached_best_effort", 0) or 0)
    parent_level_rejected = int(getattr(summary, "parent_level_rejected", 0) or 0)
    deferred_unresolved = int(getattr(summary, "deferred_unresolved", 0) or 0)
    skipped_invalid = int(getattr(summary, "skipped_invalid", 0) or 0)

    return any(
        value > 0
        for value in (
            attached_best_effort,
            parent_level_rejected,
            deferred_unresolved,
            skipped_invalid,
        )
    )


def _aggregate_fsm_summaries(summaries: list[Any]) -> Any | None:
    if not summaries:
        return None

    summary_type = type(summaries[0])

    return summary_type(
        total_candidates=sum(int(getattr(s, "total_candidates", 0) or 0) for s in summaries),
        attached_as_child=sum(int(getattr(s, "attached_as_child", 0) or 0) for s in summaries),
        attached_as_root=sum(int(getattr(s, "attached_as_root", 0) or 0) for s in summaries),
        attached_best_effort=sum(int(getattr(s, "attached_best_effort", 0) or 0) for s in summaries),
        attached_deferred_child=sum(int(getattr(s, "attached_deferred_child", 0) or 0) for s in summaries),
        skipped_duplicate=sum(int(getattr(s, "skipped_duplicate", 0) or 0) for s in summaries),
        skipped_invalid=sum(int(getattr(s, "skipped_invalid", 0) or 0) for s in summaries),
        skipped_semantic_negative=sum(int(getattr(s, "skipped_semantic_negative", 0) or 0) for s in summaries),
        parent_level_rejected=sum(int(getattr(s, "parent_level_rejected", 0) or 0) for s in summaries),
        deferred_total=sum(int(getattr(s, "deferred_total", 0) or 0) for s in summaries),
        deferred_resolved=sum(int(getattr(s, "deferred_resolved", 0) or 0) for s in summaries),
        deferred_unresolved=sum(int(getattr(s, "deferred_unresolved", 0) or 0) for s in summaries),
        root_count=sum(int(getattr(s, "root_count", 0) or 0) for s in summaries),
        max_depth_reached=max(int(getattr(s, "max_depth_reached", 0) or 0) for s in summaries),
        events=[
            event
            for s in summaries
            for event in list(getattr(s, "events", []) or [])
        ],
    )


@dataclass(slots=True)
class EvidenceSignals:
    present: bool = False
    toc_detected: bool = False
    main_chain_len: int = 0
    appendix_chain_len: int = 0
    crossref_anchor_count: int = 0
    heading_candidates_count: int = 0
    appendix_marker_count: int = 0
    numbering_sequences_count: int = 0
    document_quality_signals: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "present": self.present,
            "toc_detected": self.toc_detected,
            "main_chain_len": self.main_chain_len,
            "appendix_chain_len": self.appendix_chain_len,
            "crossref_anchor_count": self.crossref_anchor_count,
            "heading_candidates_count": self.heading_candidates_count,
            "appendix_marker_count": self.appendix_marker_count,
            "numbering_sequences_count": self.numbering_sequences_count,
            "document_quality_signals": dict(self.document_quality_signals or {}),
        }


@dataclass(slots=True)
class BuildCounters:
    invalid_heading_candidates_count: int = 0
    duplicate_effective_uid_skipped_count: int = 0
    own_range_missing_count: int = 0
    element_ownership_conflicts: int = 0
    semantic_negative_skipped_count: int = 0
    recovered_via_best_effort_count: int = 0
    suspicious_leaf_range_span_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "invalid_heading_candidates_count": self.invalid_heading_candidates_count,
            "duplicate_effective_uid_skipped_count": self.duplicate_effective_uid_skipped_count,
            "own_range_missing_count": self.own_range_missing_count,
            "element_ownership_conflicts": self.element_ownership_conflicts,
            "semantic_negative_skipped_count": self.semantic_negative_skipped_count,
            "recovered_via_best_effort_count": self.recovered_via_best_effort_count,
            "suspicious_leaf_range_span_count": self.suspicious_leaf_range_span_count,
        }


@dataclass(slots=True)
class ScopeStats:
    heading_counts: dict[str, int]
    root_counts: dict[str, int]
    node_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope_heading_counts": dict(self.heading_counts),
            "scope_root_counts": dict(self.root_counts),
            "scope_node_counts": dict(self.node_counts),
        }


@dataclass(slots=True)
class RootBackboneStats:
    appendix_heading_count: int
    appendix_root_count_before: int
    appendix_root_count_after: int
    root_numeric_root_count_before: int
    root_numeric_root_count_after: int
    root_numeric_chain_len: int
    duplicate_raw_uid_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "appendix_heading_count": self.appendix_heading_count,
            "appendix_root_count_before": self.appendix_root_count_before,
            "appendix_root_count_after": self.appendix_root_count_after,
            "root_numeric_root_count_before": self.root_numeric_root_count_before,
            "root_numeric_root_count_after": self.root_numeric_root_count_after,
            "root_numeric_chain_len": self.root_numeric_chain_len,
            "duplicate_raw_uid_count": self.duplicate_raw_uid_count,
        }


@dataclass(slots=True)
class RecoveryDecision:
    mode: str
    reason: str | None
    applied: bool
    invalid_ratio: float
    own_range_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "postbuild_recovery_mode": self.mode,
            "postbuild_recovery_reason": self.reason,
            "postbuild_recovery_applied": self.applied,
            "recoverable_invalid_heading_ratio": round(self.invalid_ratio, 4),
            "recoverable_own_range_anomaly_ratio": round(self.own_range_ratio, 4),
        }


@dataclass(slots=True)
class RecoveryAudit:
    orphans_detected: int = 0
    orphans_recovered: int = 0
    orphans_unresolved: int = 0
    fallback_triggered: bool = False
    fallback_mode: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "orphans_detected": self.orphans_detected,
            "orphans_recovered": self.orphans_recovered,
            "orphans_unresolved": self.orphans_unresolved,
            "fallback_triggered": self.fallback_triggered,
            "fallback_mode": self.fallback_mode,
        }
    

@dataclass(slots=True)
class HierarchyResolutionAudit:
    """
    Артефакт resolution-стадии Phase 3.5 — inline внутри hierarchy builder.

    Назван HierarchyResolutionAudit чтобы не путать с ResolutionAuditLog
    из services.structure.models (_models._resolution) который является
    отдельным публичным типом Phase 6+ resolution layer.
    """
    resolution_applied: bool = False
    strategy: str = "none"
    unresolved_count: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolution_applied": self.resolution_applied,
            "strategy": self.strategy,
            "unresolved_count": self.unresolved_count,
            "notes": list(self.notes),
        }


@dataclass(slots=True)
class DegradationInfo:
    """
    Структурированное описание degradation state.

    Заменяет голый bool structure_degraded в возвращаемом значении
    build_clause_hierarchy. Содержит breakdown — что именно деградировало
    и было ли применено recovery.

    Свойство structure_degraded сохранено для backward-compatibility
    с downstream кодом который проверяет bool.
    """

    fsm_degraded: bool = False
    recovery_applied: bool = False
    recovery_mode: str = "none"
    residual_issues: list[str] = field(default_factory=list)

    @property
    def structure_degraded(self) -> bool:
        """
        Backward-compatible: True если FSM деградировал И recovery не применялся.

        Это то же значение что раньше возвращалось как structure_degraded bool
        из build_clause_hierarchy.
        """
        return self.fsm_degraded and not self.recovery_applied

    def to_dict(self) -> dict[str, Any]:
        return {
            "fsm_degraded": self.fsm_degraded,
            "recovery_applied": self.recovery_applied,
            "recovery_mode": self.recovery_mode,
            "residual_issues": list(self.residual_issues),
            "structure_degraded": self.structure_degraded,
        }


@dataclass(slots=True)
class HierarchyBuildResult:
    """
    Typed результат build_clause_hierarchy.

    Заменяет tuple из 7 значений. Все поля соответствуют
    элементам старого tuple — backward-compatibility обеспечивается
    через свойства и адаптеры в _core_builder.py.

    Порядок полей соответствует старому tuple для наглядности:
    [0] root_nodes
    [1] nodes_index
    [2] element_to_effective_uid
    [3] structure_degraded  → теперь degradation.structure_degraded
    [4] fsm_summary
    [5] resolution_audit    → раньше всегда None
    [6] recovery_audit
    """

    # Дерево
    root_nodes: list[FrozenHierarchyNode]
    nodes_index: dict[str, FrozenHierarchyNode]
    element_to_effective_uid: dict[str, str]

    # FSM diagnostics
    fsm_summary: FSMBuildSummary | None

    # Recovery и resolution
    recovery_audit: RecoveryAudit
    resolution_audit: HierarchyResolutionAudit

    # Degradation (заменяет bare bool)
    degradation: DegradationInfo

    # Полные diagnostics (для логов и downstream)
    hierarchy_diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def structure_degraded(self) -> bool:
        """
        Backward-compatible свойство.

        Позволяет downstream коду использовать:
            result.structure_degraded
        вместо:
            result.degradation.structure_degraded
        до момента полного перехода на typed result.
        """
        return self.degradation.structure_degraded
    

def _assign_structural_hashes(root_nodes: list[MutableHierarchyNode]) -> None:
    """
    Назначает deterministic structural hash для каждого mutable node.

    Важно:
    - hash должен быть стабилен на одном и том же входе;
    - hash не должен зависеть от OCR wording;
    - пока используем текущий контракт node.compute_and_set_structural_hash(...),
      не переписывая модель целиком.
    """

    def _walk(
        siblings: list[MutableHierarchyNode],
        *,
        parent_path: str = "",
        scope_name: str = "global",
    ) -> None:
        for sibling_index, node in enumerate(siblings):
            raw_uid = str(node.raw_uid or "").strip()
            level = int(getattr(node, "level", 1) or 1)
            path_token = raw_uid or f"node-{sibling_index + 1}"
            normalized_path = f"{parent_path}/{path_token}" if parent_path else path_token

            node.compute_and_set_structural_hash(
                normalized_path=normalized_path,
                sibling_index=sibling_index,
            )
            node.diagnostics["structural_hash_scope"] = scope_name
            node.diagnostics["structural_hash_normalized_path"] = normalized_path
            node.diagnostics["structural_hash_level"] = level

            _walk(
                node.children,
                parent_path=normalized_path,
                scope_name=str(getattr(node, "scope", None) or scope_name or "global"),
            )

    _walk(root_nodes)


def _walk_frozen(node: FrozenHierarchyNode) -> Generator[FrozenHierarchyNode, None, None]:
    yield node
    for child in node.children:
        yield from _walk_frozen(child)


def _build_frozen_index(root_nodes: list[FrozenHierarchyNode]) -> dict[str, FrozenHierarchyNode]:
    index: dict[str, FrozenHierarchyNode] = {}
    for root in root_nodes:
        for node in _walk_frozen(root):
            if node.effective_uid in index:
                raise ValueError(f"Duplicate effective_uid in frozen tree: {node.effective_uid!r}")
            index[node.effective_uid] = node
    return index


def _safe_scope_name(scope: Any) -> str:
    value = str(scope or "").strip()
    return value or "global"


def _looks_like_appendix_uid(uid: str | None) -> bool:
    u = str(uid or "").strip().lower()
    return u.startswith(("appendix-", "приложение-", "annex-", "schedule-", "exhibit-"))


def _looks_like_root_numeric_uid(uid: str | None) -> bool:
    u = str(uid or "").strip()
    return u.isdigit()


def _extract_root_numeric_value(uid: str | None) -> int | None:
    if not _looks_like_root_numeric_uid(uid):
        return None
    try:
        return int(str(uid).strip())
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


def _extract_evidence_signals(
    structure_evidence: StructureEvidenceBundle | None,
) -> EvidenceSignals:
    if structure_evidence is None:
        return EvidenceSignals(document_quality_signals={})

    try:
        global_signals = getattr(structure_evidence, "global_signals", None)
        numbering_sequences = list(getattr(structure_evidence, "numbering_sequences", []) or [])
        appendix_markers = list(getattr(structure_evidence, "appendix_markers", []) or [])
        crossref_anchors = list(getattr(structure_evidence, "crossref_anchors", []) or [])
        heading_candidates = list(getattr(structure_evidence, "heading_candidates", []) or [])

        toc_detected = bool(getattr(global_signals, "toc_detected", False))
        main_chain_len = int(getattr(global_signals, "main_section_chain_length", 0) or 0)
        appendix_chain_len = int(getattr(global_signals, "appendix_chain_length", 0) or 0)
        crossref_anchor_count = int(getattr(global_signals, "crossref_anchor_count", 0) or 0)
        heading_candidates_count = int(getattr(global_signals, "heading_candidates_count", 0) or 0)
        document_quality_signals = dict(
            getattr(global_signals, "document_quality_signals", {}) or {}
        )

        if heading_candidates_count <= 0:
            heading_candidates_count = len(heading_candidates)
        if crossref_anchor_count <= 0:
            crossref_anchor_count = len(crossref_anchors)

        return EvidenceSignals(
            present=True,
            toc_detected=toc_detected,
            main_chain_len=main_chain_len,
            appendix_chain_len=appendix_chain_len,
            crossref_anchor_count=crossref_anchor_count,
            heading_candidates_count=heading_candidates_count,
            appendix_marker_count=len(appendix_markers),
            numbering_sequences_count=len(numbering_sequences),
            document_quality_signals=document_quality_signals,
        )
    except Exception:
        logger.exception("STRUCTURE hierarchy_builder_evidence_signal_extraction_failed")
        return EvidenceSignals(
            present=True,
            document_quality_signals={},
        )


def _plan_recovery_mode(
    *,
    headings_total: int,
    root_nodes_count: int,
    nodes_count: int,
    appendix_root_count: int,
    root_numeric_root_count: int,
    root_numeric_chain_len: int,
    recoverable_invalid_ratio: float,
    recoverable_own_range_ratio: float,
    element_ownership_conflicts: int,
    toc_detected: bool = False,
    main_chain_len_from_evidence: int = 0,
    appendix_chain_len_from_evidence: int = 0,
    crossref_anchor_count: int = 0,
) -> tuple[str, str | None]:
    """
    Планирует только bounded post-build recovery policy.

    Важно:
    - это не "магический починить всё";
    - здесь нет semantic/LLM логики;
    - recovery допускается только если deterministic backbone уже виден.
    """
    if headings_total <= 0:
        return "none", None

    if nodes_count == 0:
        if toc_detected and (
            main_chain_len_from_evidence >= 3
            or appendix_chain_len_from_evidence >= 1
            or crossref_anchor_count > 0
        ):
            return "rebuild_from_evidence_backbone", "evidence_backbone_without_materialized_nodes"
        return "none", None

    if _FATAL_ROOTLESS_WITH_NODES and root_nodes_count == 0:
        evidence_backbone_ok = (
            toc_detected
            or main_chain_len_from_evidence >= 5
            or appendix_chain_len_from_evidence >= 3
            or crossref_anchor_count > 0
        )
        if evidence_backbone_ok:
            return "rebuild_from_evidence_backbone", "recoverable_rootless_with_strong_evidence"
        return "technical_fallback_only", "fatal_rootless_with_nodes"

    strong_numeric_roots = root_numeric_root_count >= max(3, root_nodes_count // 2 or 1)
    strong_numeric_chain = root_numeric_chain_len >= 3

    numeric_backbone_ok = strong_numeric_roots and strong_numeric_chain
    evidence_backbone_ok = (
        toc_detected
        or main_chain_len_from_evidence >= 5
        or appendix_chain_len_from_evidence >= 3
        or crossref_anchor_count > 0
    )

    invalid_ok = recoverable_invalid_ratio <= _RECOVERABLE_INVALID_HEADING_RATIO
    own_range_ok = recoverable_own_range_ratio <= _RECOVERABLE_OWN_RANGE_ANOMALY_RATIO
    ownership_ok = element_ownership_conflicts == 0

    appendix_only_roots = (
        root_nodes_count > 0
        and appendix_root_count == root_nodes_count
        and root_numeric_root_count == 0
    )

    if appendix_only_roots and (appendix_chain_len_from_evidence >= 3 or headings_total >= 1):
        return "appendix_only_recovery", "appendix_only_roots_recoverable"

    if numeric_backbone_ok and invalid_ok and own_range_ok and ownership_ok:
        return "rebuild_from_numeric_backbone", "numeric_backbone_recoverable"

    if numeric_backbone_ok and invalid_ok and own_range_ok:
        return "rebuild_from_numeric_backbone", "numeric_backbone_recoverable_with_conflicts"

    if evidence_backbone_ok and invalid_ok and own_range_ok and ownership_ok:
        return "rebuild_from_evidence_backbone", "evidence_backbone_recoverable"

    if evidence_backbone_ok and invalid_ok and own_range_ok:
        return "rebuild_from_evidence_backbone", "evidence_backbone_recoverable_with_conflicts"

    return "none", None


def _walk_mutable(node: MutableHierarchyNode) -> Generator[MutableHierarchyNode, None, None]:
    yield node
    for child in node.children:
        yield from _walk_mutable(child)


def _collect_all_mutable_nodes(root_nodes: list[MutableHierarchyNode]) -> list[MutableHierarchyNode]:
    out: list[MutableHierarchyNode] = []
    seen: set[str] = set()
    for root in root_nodes:
        for node in _walk_mutable(root):
            if node.effective_uid in seen:
                continue
            seen.add(node.effective_uid)
            out.append(node)
    return out


def _sort_nodes_stably(nodes: list[MutableHierarchyNode]) -> list[MutableHierarchyNode]:
    def _sort_key(node: MutableHierarchyNode) -> tuple[Any, ...]:
        raw_uid = str(node.raw_uid or "")
        numeric_root = _extract_root_numeric_value(raw_uid)
        return (
            0 if numeric_root is not None else 1,
            numeric_root if numeric_root is not None else 10**9,
            0 if _looks_like_appendix_uid(raw_uid) else 1,
            int(node.start_page),
            int(node.level),
            raw_uid,
            node.effective_uid,
        )

    return sorted(nodes, key=_sort_key)


def _mark_recovered_subtree(
    node: MutableHierarchyNode,
    *,
    mode: str,
    reason: str | None,
) -> None:
    stack = [node]
    while stack:
        cur = stack.pop()
        cur.diagnostics["recovered_via_postbuild_recovery"] = True
        cur.diagnostics["postbuild_recovery_mode"] = mode
        cur.diagnostics["postbuild_recovery_reason"] = reason

        if cur.node_origin == "unknown":
            if mode == "appendix_only_recovery":
                cur.node_origin = "appendix_recovery"
            elif mode in {"rebuild_from_numeric_backbone", "rebuild_from_evidence_backbone"}:
                cur.node_origin = "toc_rebuild"

        if cur.citability == "low":
            cur.citability = "medium"

        stack.extend(reversed(cur.children))


def _apply_postbuild_recovery(
    *,
    root_nodes: list[MutableHierarchyNode],
    recovery_mode: str,
    recovery_reason: str | None,
) -> tuple[list[MutableHierarchyNode], bool]:
    """
    Применяет только root-level deterministic recovery.

    Важно:
    - не пересобирает дерево заново;
    - не меняет parent-child связи внутри поддеревьев;
    - только восстанавливает корректный root set, если backbone уже найден.
    """
    if recovery_mode == "none":
        return root_nodes, False

    if recovery_mode == "technical_fallback_only":
        return root_nodes, False

    all_nodes = _collect_all_mutable_nodes(root_nodes)
    if not all_nodes:
        return root_nodes, False

    recovered_roots: list[MutableHierarchyNode] = []

    if recovery_mode == "appendix_only_recovery":
        appendix_roots = [
            node
            for node in all_nodes
            if _looks_like_appendix_uid(node.raw_uid)
            and node.level == 1
        ]
        recovered_roots = _sort_nodes_stably(appendix_roots)

    elif recovery_mode in {"rebuild_from_numeric_backbone", "rebuild_from_evidence_backbone"}:
        preferred_roots = [
            node
            for node in all_nodes
            if node.level == 1
            and (
                _looks_like_root_numeric_uid(node.raw_uid)
                or _looks_like_appendix_uid(node.raw_uid)
            )
        ]

        if not preferred_roots:
            preferred_roots = [
                node
                for node in all_nodes
                if node.level == 1
            ]

        recovered_roots = _sort_nodes_stably(preferred_roots)

    else:
        return root_nodes, False

    if not recovered_roots:
        return root_nodes, False

    seen: set[str] = set()
    deduped: list[MutableHierarchyNode] = []
    for node in recovered_roots:
        if node.effective_uid in seen:
            continue
        seen.add(node.effective_uid)
        _mark_recovered_subtree(node, mode=recovery_mode, reason=recovery_reason)
        deduped.append(node)

    if not deduped:
        return root_nodes, False

    return deduped, True


def _collect_backbone_stats(
    *,
    headings: list[HeadingCandidate],
    mutable_root_nodes: list[MutableHierarchyNode],
) -> tuple[Counter[str], int, list[int], int, int]:
    raw_uid_counter: Counter[str] = Counter()
    appendix_heading_count = 0
    root_numeric_values: list[int] = []

    for heading in headings:
        raw_uid = _heading_raw_uid(heading)
        if raw_uid:
            raw_uid_counter[raw_uid] += 1
            root_value = _extract_root_numeric_value(raw_uid)
            if root_value is not None:
                root_numeric_values.append(root_value)
            if _looks_like_appendix_uid(raw_uid):
                appendix_heading_count += 1

    appendix_root_count_before = sum(
        1 for node in mutable_root_nodes if _looks_like_appendix_uid(getattr(node, "raw_uid", None))
    )
    root_numeric_root_count_before = sum(
        1 for node in mutable_root_nodes if _looks_like_root_numeric_uid(getattr(node, "raw_uid", None))
    )

    return (
        raw_uid_counter,
        appendix_heading_count,
        root_numeric_values,
        appendix_root_count_before,
        root_numeric_root_count_before,
    )


def _build_scope_stats(headings_by_scope: dict[Any, list[HeadingCandidate]]) -> ScopeStats:
    return ScopeStats(
        heading_counts={
            _safe_scope_name(scope): len(scope_headings)
            for scope, scope_headings in headings_by_scope.items()
        },
        root_counts={},
        node_counts=defaultdict(int),
    )


def _create_mutable_node(
    *,
    heading: HeadingCandidate,
    scope: Any,
    evidence_signals: EvidenceSignals,
) -> MutableHierarchyNode:
    raw_uid = _heading_raw_uid(heading)
    effective_uid = _heading_effective_uid(heading)
    h_meta = heading.metadata or {}
    sem_type = str(h_meta.get("semantic_element_type") or "").strip().lower() or None

    level = level_from_uid(raw_uid) if _is_strict_numeric_uid(raw_uid) else 1

    node_origin = "semantic_heading"
    content_mode = "full_text"
    citability = "high" if level <= 2 else "medium"

    if getattr(heading, "toc_entry", False):
        node_origin = "toc_rebuild"
        content_mode = "skeleton"
        citability = "medium"
    elif getattr(heading, "is_appendix", False):
        node_origin = "appendix_recovery"
        citability = "medium"

    return MutableHierarchyNode(
        effective_uid=effective_uid,
        raw_uid=raw_uid,
        scope=scope,
        title=_normalize_title(heading.title),
        level=level,
        start_page=int(heading.page),
        end_page=int(heading.page),
        node_origin=node_origin,
        content_mode=content_mode,
        citability=citability,
        diagnostics={
            "source_elem_i": getattr(heading, "elem_i", None),
            "semantic_element_type": sem_type,
            "is_appendix_uid": _looks_like_appendix_uid(raw_uid),
            "is_root_numeric_uid": _looks_like_root_numeric_uid(raw_uid),
            "toc_entry": bool(getattr(heading, "toc_entry", False)),
            "toc_match_type": getattr(heading, "toc_match_type", None),
            "toc_match_score": getattr(heading, "toc_match_score", None),
            "structure_evidence_present": evidence_signals.present,
            "toc_detected_from_evidence": evidence_signals.toc_detected,
        },
    )


def _attach_scope_headings(
    *,
    scope: Any,
    scope_headings: list[HeadingCandidate],
    machine: HierarchyStateMachine,
    mutable_nodes: dict[str, MutableHierarchyNode],
    counters: BuildCounters,
    scope_stats: ScopeStats,
    evidence_signals: EvidenceSignals,
) -> None:
    scope_name = _safe_scope_name(scope)

    for heading in scope_headings:
        try:
            effective_uid = _heading_effective_uid(heading)
            if effective_uid in mutable_nodes:
                counters.duplicate_effective_uid_skipped_count += 1
                continue

            node = _create_mutable_node(
                heading=heading,
                scope=scope,
                evidence_signals=evidence_signals,
            )
            mutable_nodes[effective_uid] = node
            scope_stats.node_counts[scope_name] += 1

            sem_type = str(
                (heading.metadata or {}).get("semantic_element_type") or ""
            ).strip().lower() or None

            attach_res = machine.attach(node, raw_uid=node.raw_uid, semantic_type=sem_type)

            if not attach_res.attached and attach_res.attach_mode == "skipped":
                if "semantic_negative" in str(attach_res.reject_reason):
                    counters.semantic_negative_skipped_count += 1
                    mutable_nodes.pop(effective_uid, None)
                    scope_stats.node_counts[scope_name] = max(
                        0,
                        scope_stats.node_counts[scope_name] - 1,
                    )
                continue

            if attach_res.attach_mode == "best_effort_root":
                counters.recovered_via_best_effort_count += 1
                node.diagnostics["recovered_via_best_effort"] = True
                node.diagnostics["fallback_reason"] = str(attach_res.reject_reason)
                if node.citability == "high":
                    node.citability = "medium"

        except Exception:
            counters.invalid_heading_candidates_count += 1
            continue


def _assign_own_ranges_and_elements(
    *,
    headings: list[HeadingCandidate],
    headings_by_scope: dict[Any, list[HeadingCandidate]],
    elements: list[dict[str, Any]],
    mutable_nodes: dict[str, MutableHierarchyNode],
    element_to_effective_uid: dict[str, str],
    stable_element_id_resolver: Callable[[dict[str, Any], int], str],
    key_to_elem_i: dict[Any, int],
    key_to_idx: dict[Any, int],
    scope_boundaries: dict[Any, Any],
    counters: BuildCounters,
) -> None:
    for heading in headings:
        try:
            eff_uid = _heading_effective_uid(heading)
            node = mutable_nodes.get(eff_uid)
            if not node:
                continue

            scope = _heading_scope(heading)
            range_info = _compute_own_range(
                raw_uid=_heading_raw_uid(heading),
                node=node,
                headings=headings_by_scope.get(scope, []),
                elements=elements,
                key_to_elem_i=key_to_elem_i,
                key_to_heading_index=key_to_idx,
                scope=scope,
                scope_boundaries=scope_boundaries,
            )

            node.range_end_reason = range_info.range_end_reason

            own_ids: list[str] = []
            for j in range(range_info.start_elem_i, range_info.end_elem_i):
                s_id = str(stable_element_id_resolver(elements[j], j) or "").strip()
                if not s_id:
                    continue
                own_ids.append(s_id)

                if s_id in element_to_effective_uid:
                    if element_to_effective_uid[s_id] != eff_uid:
                        counters.element_ownership_conflicts += 1
                else:
                    element_to_effective_uid[s_id] = eff_uid

            node.own_element_ids = list(dict.fromkeys(own_ids))
            node.own_text = _collect_own_text(
                elements,
                range_info.start_elem_i,
                range_info.end_elem_i,
            )

            own_range_span = range_info.end_elem_i - range_info.start_elem_i
            node.diagnostics["own_range_span"] = own_range_span

            if not node.children and own_range_span >= _SUSPICIOUS_LEAF_RANGE_SPAN_THRESHOLD:
                node.diagnostics["suspicious_leaf_range_span"] = True
                counters.suspicious_leaf_range_span_count += 1

            if not node.own_text and bool(getattr(heading, "toc_entry", False)):
                node.content_mode = "skeleton"
                node.citability = "low"

        except Exception:
            counters.own_range_missing_count += 1
            continue


def _build_hierarchy_diagnostics(
    *,
    doc_id: str,
    headings_total: int,
    root_nodes_count: int,
    nodes_count: int,
    counters: BuildCounters,
    machine_structure_degraded: bool,
    structure_degraded_after_recovery: bool,
    scope_stats: ScopeStats,
    backbone_stats: RootBackboneStats,
    recovery_decision: RecoveryDecision,
    machine_summaries: list[Any],
    evidence_signals: EvidenceSignals,
) -> dict[str, Any]:
    diagnostics = {
        "document_id": doc_id,
        "headings_total": headings_total,
        "root_nodes_count": root_nodes_count,
        "nodes_count": nodes_count,
        "structure_degraded": bool(machine_structure_degraded),
        "structure_degraded_after_recovery": bool(structure_degraded_after_recovery),
        "machine_summaries": [
            summary.to_dict() if callable(getattr(summary, "to_dict", None)) else {}
            for summary in machine_summaries
        ],
    }
    diagnostics.update(counters.to_dict())
    diagnostics.update(scope_stats.to_dict())
    diagnostics.update(backbone_stats.to_dict())
    diagnostics.update(recovery_decision.to_dict())

    diagnostics.update(
        {
            "structure_evidence_present": evidence_signals.present,
            "toc_detected_from_evidence": evidence_signals.toc_detected,
            "main_chain_len_from_evidence": evidence_signals.main_chain_len,
            "appendix_chain_len_from_evidence": evidence_signals.appendix_chain_len,
            "crossref_anchor_count_from_evidence": evidence_signals.crossref_anchor_count,
            "heading_candidates_count_from_evidence": evidence_signals.heading_candidates_count,
            "appendix_marker_count_from_evidence": evidence_signals.appendix_marker_count,
            "numbering_sequences_count_from_evidence": evidence_signals.numbering_sequences_count,
            "document_quality_signals_from_evidence": dict(evidence_signals.document_quality_signals or {}),
        }
    )
    return diagnostics


def build_clause_hierarchy(
    headings: list[HeadingCandidate],
    elements: list[dict[str, Any]],
    *,
    document_id: str,
    stable_element_id_resolver: Callable[[dict[str, Any], int], str],
    structure_evidence: StructureEvidenceBundle | None = None,
) -> HierarchyBuildResult:
    """
    Строит immutable hierarchy tree и индексы.

    Контракт:
    - на вход получает уже отфильтрованные heading candidates;
    - FSM отвечает только за deterministic attach;
    - post-build recovery ограничен и не пересобирает дерево целиком;
    - на выходе возвращается immutable tree + node index + element ownership index.
    """
    doc_id = str(document_id or "").strip()

    mutable_nodes: dict[str, MutableHierarchyNode] = {}
    mutable_root_nodes: list[MutableHierarchyNode] = []
    element_to_effective_uid: dict[str, str] = {}

    evidence_signals = _extract_evidence_signals(structure_evidence)

    if not headings:
        logger.info(
            "STRUCTURE hierarchy_builder_completed",
            extra={
                "document_id": doc_id,
                "root_nodes_count": 0,
                "nodes_count": 0,
                "invalid_heading_candidates_count": 0,
                "duplicate_effective_uid_skipped_count": 0,
                "own_range_missing_count": 0,
                "element_ownership_conflicts": 0,
                "structure_degraded": False,
                "structure_degraded_after_recovery": False,
                "postbuild_recovery_applied": False,
                "postbuild_recovery_mode": "none",
                "postbuild_recovery_reason": None,
                "reason": "empty_headings",
                "structure_evidence_present": evidence_signals.present,
                "toc_detected_from_evidence": evidence_signals.toc_detected,
                "main_chain_len_from_evidence": evidence_signals.main_chain_len,
                "appendix_chain_len_from_evidence": evidence_signals.appendix_chain_len,
                "crossref_anchor_count_from_evidence": evidence_signals.crossref_anchor_count,
            },
        )
        return HierarchyBuildResult(
            root_nodes=[],
            nodes_index={},
            element_to_effective_uid=element_to_effective_uid,
            fsm_summary=None,
            recovery_audit=RecoveryAudit(),
            resolution_audit=HierarchyResolutionAudit(),
            degradation=DegradationInfo(),
            hierarchy_diagnostics={},
        )

    counters = BuildCounters()

    headings_by_scope = _group_headings_by_scope(headings)
    scope_boundaries = _build_scope_boundaries(elements)
    key_to_elem_i, key_to_idx = _build_heading_positions(headings)

    machines: dict[str, HierarchyStateMachine] = {}
    scope_stats = _build_scope_stats(headings_by_scope)

    for scope, scope_headings in headings_by_scope.items():
        machine = HierarchyStateMachine(scope=scope, document_id=doc_id)
        machines[str(scope)] = machine

        _attach_scope_headings(
            scope=scope,
            scope_headings=scope_headings,
            machine=machine,
            mutable_nodes=mutable_nodes,
            counters=counters,
            scope_stats=scope_stats,
            evidence_signals=evidence_signals,
        )

        mutable_root_nodes.extend(machine.root_nodes)
        scope_stats.root_counts[_safe_scope_name(scope)] = len(machine.root_nodes)

    (
        raw_uid_counter,
        appendix_heading_count,
        root_numeric_values,
        appendix_root_count_before,
        root_numeric_root_count_before,
    ) = _collect_backbone_stats(
        headings=headings,
        mutable_root_nodes=mutable_root_nodes,
    )

    # ── Phase 13.4: Embedding Recovery pass ──────────────────────────────────
    # Выполняется ПОСЛЕ FSM (все scopes обработаны), ДО range assignment.
    # Ищет семантически близкий parent для best_effort_root orphan nodes.
    # Failure-isolated: любая ошибка → оставляем FSM-решение, pipeline не падает.
    _embedding_recovery_result = None
    try:
        from ._embedding_recovery import EmbeddingRecoveryEngine
        _emb_engine = EmbeddingRecoveryEngine()
        _embedding_recovery_result = _emb_engine.recover(
            mutable_nodes,
            document_id=doc_id,
        )
        if _embedding_recovery_result.recovered_count > 0:
            _emb_recovered_uids: set[str] = {
                d.orphan_uid
                for d in _embedding_recovery_result.decisions
                if d.recovered
            }
            mutable_root_nodes = [
                n for n in mutable_root_nodes
                if str(n.effective_uid or "") not in _emb_recovered_uids
            ]
    except Exception:
        logger.exception(
            "STRUCTURE embedding_recovery_pass_failed",
            extra={"document_id": doc_id},
        )
    # ── End Phase 13.4 ───────────────────────────────────────────────────────


    root_numeric_chain_len = _longest_consecutive_chain(root_numeric_values)

    _assign_own_ranges_and_elements(
        headings=headings,
        headings_by_scope=headings_by_scope,
        elements=elements,
        mutable_nodes=mutable_nodes,
        element_to_effective_uid=element_to_effective_uid,
        stable_element_id_resolver=stable_element_id_resolver,
        key_to_elem_i=key_to_elem_i,
        key_to_idx=key_to_idx,
        scope_boundaries=scope_boundaries,
        counters=counters,
    )

    summaries = [machine.build_summary() for machine in machines.values()]
    fsm_summary = _aggregate_fsm_summaries(summaries)
    machine_structure_degraded = any(_is_fsm_summary_degraded(summary) for summary in summaries)

    pre_recovery_nodes_count = len(mutable_nodes)
    pre_recovery_root_nodes_count = len(mutable_root_nodes)

    recoverable_invalid_ratio = counters.invalid_heading_candidates_count / max(len(headings), 1)
    recoverable_own_range_ratio = counters.own_range_missing_count / max(len(headings), 1)

    recovery_mode, recovery_reason = _plan_recovery_mode(
        headings_total=len(headings),
        root_nodes_count=pre_recovery_root_nodes_count,
        nodes_count=pre_recovery_nodes_count,
        appendix_root_count=appendix_root_count_before,
        root_numeric_root_count=root_numeric_root_count_before,
        root_numeric_chain_len=root_numeric_chain_len,
        recoverable_invalid_ratio=recoverable_invalid_ratio,
        recoverable_own_range_ratio=recoverable_own_range_ratio,
        element_ownership_conflicts=counters.element_ownership_conflicts,
        toc_detected=evidence_signals.toc_detected,
        main_chain_len_from_evidence=evidence_signals.main_chain_len,
        appendix_chain_len_from_evidence=evidence_signals.appendix_chain_len,
        crossref_anchor_count=evidence_signals.crossref_anchor_count,
    )

    mutable_root_nodes, postbuild_recovery_applied = _apply_postbuild_recovery(
        root_nodes=mutable_root_nodes,
        recovery_mode=recovery_mode,
        recovery_reason=recovery_reason,
    )

    _emb_recovered_count = (
        _embedding_recovery_result.recovered_count
        if _embedding_recovery_result is not None else 0
    )
    _postbuild_recovered = pre_recovery_root_nodes_count if postbuild_recovery_applied else 0
    _total_recovered = _postbuild_recovered + _emb_recovered_count
    _orphans_detected = pre_recovery_root_nodes_count if recovery_mode != "none" else 0
    recovery_audit = RecoveryAudit(
        orphans_detected=_orphans_detected,
        orphans_recovered=min(_total_recovered, _orphans_detected),
        orphans_unresolved=max(0, _orphans_detected - _total_recovered),
        fallback_triggered=recovery_mode == "technical_fallback_only",
        fallback_mode=recovery_mode if recovery_mode != "none" else None,
    )

    populate_subtree_element_ids(mutable_root_nodes, document_id=doc_id)
    _assign_structural_hashes(mutable_root_nodes)

    frozen_root_nodes = [freeze(node) for node in mutable_root_nodes]
    frozen_nodes = _build_frozen_index(frozen_root_nodes)

    root_nodes_count = len(frozen_root_nodes)
    nodes_count = len(frozen_nodes)

    appendix_root_count_after = sum(
        1 for node in frozen_root_nodes if _looks_like_appendix_uid(getattr(node, "raw_uid", None))
    )
    root_numeric_root_count_after = sum(
        1 for node in frozen_root_nodes if _looks_like_root_numeric_uid(getattr(node, "raw_uid", None))
    )

    structure_degraded_after_recovery = bool(
        machine_structure_degraded and not postbuild_recovery_applied
    )
    structure_degraded = structure_degraded_after_recovery

    backbone_stats = RootBackboneStats(
        appendix_heading_count=appendix_heading_count,
        appendix_root_count_before=appendix_root_count_before,
        appendix_root_count_after=appendix_root_count_after,
        root_numeric_root_count_before=root_numeric_root_count_before,
        root_numeric_root_count_after=root_numeric_root_count_after,
        root_numeric_chain_len=root_numeric_chain_len,
        duplicate_raw_uid_count=sum(1 for _, count in raw_uid_counter.items() if count > 1),
    )

    recovery_decision = RecoveryDecision(
        mode=recovery_mode,
        reason=recovery_reason,
        applied=postbuild_recovery_applied,
        invalid_ratio=recoverable_invalid_ratio,
        own_range_ratio=recoverable_own_range_ratio,
    )

    hierarchy_diagnostics = _build_hierarchy_diagnostics(
        doc_id=doc_id,
        headings_total=len(headings),
        root_nodes_count=root_nodes_count,
        nodes_count=nodes_count,
        counters=counters,
        machine_structure_degraded=machine_structure_degraded,
        structure_degraded_after_recovery=structure_degraded_after_recovery,
        scope_stats=scope_stats,
        backbone_stats=backbone_stats,
        recovery_decision=recovery_decision,
        machine_summaries=summaries,
        evidence_signals=evidence_signals,
    )

    logger.info(
        "STRUCTURE hierarchy_builder_completed",
        extra=hierarchy_diagnostics,
    )

    # Resolution audit: resolution выполняется inline как часть post-build recovery.
    # Отдельной resolution-стадии пока нет — фиксируем факт через ResolutionAudit.
    resolution_audit = HierarchyResolutionAudit(
        resolution_applied=postbuild_recovery_applied,
        strategy="inline_recovery" if postbuild_recovery_applied else "none",
        unresolved_count=int(
            getattr(fsm_summary, "deferred_unresolved", 0) or 0
        ),
        notes=(
            [f"recovery_mode:{recovery_mode}"]
            if postbuild_recovery_applied
            else []
        ),
    )

    # Degradation info: структурированное описание вместо bare bool.
    residual: list[str] = []
    if fsm_summary is not None:
        if int(getattr(fsm_summary, "deferred_unresolved", 0) or 0) > 0:
            residual.append(
                f"unresolved_deferred:{fsm_summary.deferred_unresolved}"
            )
        if int(getattr(fsm_summary, "attached_best_effort", 0) or 0) > 0:
            residual.append(
                f"best_effort_roots:{fsm_summary.attached_best_effort}"
            )

    degradation = DegradationInfo(
        fsm_degraded=machine_structure_degraded,
        recovery_applied=postbuild_recovery_applied,
        recovery_mode=recovery_mode,
        residual_issues=residual,
    )

    return HierarchyBuildResult(
        root_nodes=frozen_root_nodes,
        nodes_index=frozen_nodes,
        element_to_effective_uid=element_to_effective_uid,
        fsm_summary=fsm_summary,
        recovery_audit=recovery_audit,
        resolution_audit=resolution_audit,
        degradation=degradation,
        hierarchy_diagnostics=hierarchy_diagnostics,
    )





