# src/services/structure/_hierarchy_builder/_core.py

"""Основной оркестратор сборки hierarchy в immutable artifact tree."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Generator
from typing import Any, TYPE_CHECKING

from core.logging import get_logger
from services.structure.hierarchy_state_machine import HierarchyStateMachine
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


def _assign_structural_hashes(root_nodes: list[MutableHierarchyNode]) -> None:
    def _walk(siblings: list[MutableHierarchyNode]) -> None:
        for sibling_index, node in enumerate(siblings):
            normalized_path = node.raw_uid or str(sibling_index + 1)
            node.compute_and_set_structural_hash(
                normalized_path=normalized_path,
                sibling_index=sibling_index,
            )
            _walk(node.children)

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
    return u.startswith("appendix-") or u.startswith("приложение-")


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
) -> dict[str, Any]:
    if structure_evidence is None:
        return {
            "present": False,
            "toc_detected": False,
            "main_chain_len": 0,
            "appendix_chain_len": 0,
            "crossref_anchor_count": 0,
            "heading_candidates_count": 0,
            "appendix_marker_count": 0,
            "numbering_sequences_count": 0,
            "document_quality_signals": {},
        }

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

        return {
            "present": True,
            "toc_detected": toc_detected,
            "main_chain_len": main_chain_len,
            "appendix_chain_len": appendix_chain_len,
            "crossref_anchor_count": crossref_anchor_count,
            "heading_candidates_count": heading_candidates_count,
            "appendix_marker_count": len(appendix_markers),
            "numbering_sequences_count": len(numbering_sequences),
            "document_quality_signals": document_quality_signals,
        }
    except Exception:
        logger.exception("STRUCTURE hierarchy_builder_evidence_signal_extraction_failed")
        return {
            "present": True,
            "toc_detected": False,
            "main_chain_len": 0,
            "appendix_chain_len": 0,
            "crossref_anchor_count": 0,
            "heading_candidates_count": 0,
            "appendix_marker_count": 0,
            "numbering_sequences_count": 0,
            "document_quality_signals": {},
        }


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
    if recovery_mode == "none":
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


def build_clause_hierarchy(
    headings: list[HeadingCandidate],
    elements: list[dict[str, Any]],
    *,
    document_id: str,
    stable_element_id_resolver: Callable[[dict[str, Any], int], str],
    structure_evidence: StructureEvidenceBundle | None = None,
) -> tuple[list[FrozenHierarchyNode], dict[str, FrozenHierarchyNode], dict[str, str], bool]:
    """Строит immutable дерево hierarchy и индексы идентификаторов элементов."""
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
                "structure_evidence_present": evidence_signals["present"],
                "toc_detected_from_evidence": evidence_signals["toc_detected"],
                "main_chain_len_from_evidence": evidence_signals["main_chain_len"],
                "appendix_chain_len_from_evidence": evidence_signals["appendix_chain_len"],
                "crossref_anchor_count_from_evidence": evidence_signals["crossref_anchor_count"],
            },
        )
        return [], {}, element_to_effective_uid, False

    invalid_heading_candidates_count = 0
    duplicate_effective_uid_skipped_count = 0
    own_range_missing_count = 0
    element_ownership_conflicts = 0

    semantic_negative_skipped_count = 0
    recovered_via_best_effort_count = 0

    headings_by_scope = _group_headings_by_scope(headings)
    scope_boundaries = _build_scope_boundaries(elements)
    key_to_elem_i, key_to_idx = _build_heading_positions(headings)

    machines: dict[str, HierarchyStateMachine] = {}

    scope_heading_counts: dict[str, int] = {
        _safe_scope_name(scope): len(scope_headings)
        for scope, scope_headings in headings_by_scope.items()
    }
    scope_root_counts: dict[str, int] = {}
    scope_node_counts: dict[str, int] = defaultdict(int)

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

    root_numeric_chain_len = _longest_consecutive_chain(root_numeric_values)

    for scope, scope_headings in headings_by_scope.items():
        machine = HierarchyStateMachine(scope=scope, document_id=doc_id)
        machines[scope] = machine

        for heading in scope_headings:
            try:
                raw_uid = _heading_raw_uid(heading)
                effective_uid = _heading_effective_uid(heading)
                if effective_uid in mutable_nodes:
                    duplicate_effective_uid_skipped_count += 1
                    continue

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

                node = MutableHierarchyNode(
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
                        "structure_evidence_present": evidence_signals["present"],
                        "toc_detected_from_evidence": evidence_signals["toc_detected"],
                    },
                )
                mutable_nodes[effective_uid] = node
                scope_node_counts[_safe_scope_name(scope)] += 1

                attach_res = machine.attach(node, raw_uid=raw_uid, semantic_type=sem_type)

                if not attach_res.attached and attach_res.attach_mode == "skipped":
                    if "semantic_negative" in str(attach_res.reject_reason):
                        semantic_negative_skipped_count += 1
                        del mutable_nodes[effective_uid]
                        scope_node_counts[_safe_scope_name(scope)] = max(
                            0,
                            scope_node_counts[_safe_scope_name(scope)] - 1,
                        )
                    continue

                if attach_res.attach_mode == "best_effort_root":
                    recovered_via_best_effort_count += 1
                    node.diagnostics["recovered_via_best_effort"] = True
                    node.diagnostics["fallback_reason"] = str(attach_res.reject_reason)
                    if node.citability == "high":
                        node.citability = "medium"

            except Exception:
                invalid_heading_candidates_count += 1
                continue

        mutable_root_nodes.extend(machine.root_nodes)
        scope_root_counts[_safe_scope_name(scope)] = len(machine.root_nodes)

    suspicious_leaf_range_span_count = 0

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
                        element_ownership_conflicts += 1
                else:
                    element_to_effective_uid[s_id] = eff_uid

            node.own_element_ids = list(dict.fromkeys(own_ids))
            node.own_text = _collect_own_text(elements, range_info.start_elem_i, range_info.end_elem_i)
            own_range_span = range_info.end_elem_i - range_info.start_elem_i
            node.diagnostics["own_range_span"] = own_range_span

            if not node.children and own_range_span >= _SUSPICIOUS_LEAF_RANGE_SPAN_THRESHOLD:
                node.diagnostics["suspicious_leaf_range_span"] = True
                suspicious_leaf_range_span_count += 1

            if not node.own_text and bool(getattr(heading, "toc_entry", False)):
                node.content_mode = "skeleton"
                node.citability = "low"

        except Exception:
            own_range_missing_count += 1
            continue

    summaries = [machine.build_summary() for machine in machines.values()]
    machine_structure_degraded = any(summary.structure_degraded for summary in summaries)

    pre_recovery_nodes_count = len(mutable_nodes)
    pre_recovery_root_nodes_count = len(mutable_root_nodes)

    appendix_root_count = sum(
        1
        for node in mutable_root_nodes
        if _looks_like_appendix_uid(getattr(node, "raw_uid", None))
    )
    root_numeric_root_count = sum(
        1
        for node in mutable_root_nodes
        if _looks_like_root_numeric_uid(getattr(node, "raw_uid", None))
    )

    recoverable_invalid_ratio = invalid_heading_candidates_count / max(len(headings), 1)
    recoverable_own_range_ratio = own_range_missing_count / max(len(headings), 1)

    recovery_mode, recovery_reason = _plan_recovery_mode(
        headings_total=len(headings),
        root_nodes_count=pre_recovery_root_nodes_count,
        nodes_count=pre_recovery_nodes_count,
        appendix_root_count=appendix_root_count,
        root_numeric_root_count=root_numeric_root_count,
        root_numeric_chain_len=root_numeric_chain_len,
        recoverable_invalid_ratio=recoverable_invalid_ratio,
        recoverable_own_range_ratio=recoverable_own_range_ratio,
        element_ownership_conflicts=element_ownership_conflicts,
        toc_detected=evidence_signals["toc_detected"],
        main_chain_len_from_evidence=evidence_signals["main_chain_len"],
        appendix_chain_len_from_evidence=evidence_signals["appendix_chain_len"],
        crossref_anchor_count=evidence_signals["crossref_anchor_count"],
    )

    mutable_root_nodes, postbuild_recovery_applied = _apply_postbuild_recovery(
        root_nodes=mutable_root_nodes,
        recovery_mode=recovery_mode,
        recovery_reason=recovery_reason,
    )

    populate_subtree_element_ids(mutable_root_nodes, document_id=doc_id)
    _assign_structural_hashes(mutable_root_nodes)

    frozen_root_nodes = [freeze(node) for node in mutable_root_nodes]
    frozen_nodes = _build_frozen_index(frozen_root_nodes)

    nodes_count = len(frozen_nodes)
    root_nodes_count = len(frozen_root_nodes)

    appendix_root_count_after = sum(
        1
        for node in frozen_root_nodes
        if _looks_like_appendix_uid(getattr(node, "raw_uid", None))
    )
    root_numeric_root_count_after = sum(
        1
        for node in frozen_root_nodes
        if _looks_like_root_numeric_uid(getattr(node, "raw_uid", None))
    )

    structure_degraded_after_recovery = bool(
        machine_structure_degraded and not postbuild_recovery_applied
    )
    structure_degraded = structure_degraded_after_recovery

    hierarchy_diagnostics = {
        "document_id": doc_id,
        "headings_total": len(headings),
        "root_nodes_count": root_nodes_count,
        "nodes_count": nodes_count,
        "invalid_heading_candidates_count": invalid_heading_candidates_count,
        "duplicate_effective_uid_skipped_count": duplicate_effective_uid_skipped_count,
        "semantic_negative_skipped_count": semantic_negative_skipped_count,
        "recovered_via_best_effort_count": recovered_via_best_effort_count,
        "own_range_missing_count": own_range_missing_count,
        "element_ownership_conflicts": element_ownership_conflicts,
        "suspicious_leaf_range_span_count": suspicious_leaf_range_span_count,
        "structure_degraded": bool(machine_structure_degraded),
        "structure_degraded_after_recovery": structure_degraded_after_recovery,
        "postbuild_recovery_applied": postbuild_recovery_applied,
        "postbuild_recovery_mode": recovery_mode,
        "postbuild_recovery_reason": recovery_reason,
        "scope_heading_counts": dict(scope_heading_counts),
        "scope_root_counts": dict(scope_root_counts),
        "scope_node_counts": dict(scope_node_counts),
        "appendix_heading_count": appendix_heading_count,
        "appendix_root_count": appendix_root_count_after,
        "root_numeric_root_count": root_numeric_root_count_after,
        "root_numeric_chain_len": root_numeric_chain_len,
        "recoverable_invalid_heading_ratio": round(recoverable_invalid_ratio, 4),
        "recoverable_own_range_anomaly_ratio": round(recoverable_own_range_ratio, 4),
        "duplicate_raw_uid_count": sum(1 for _, count in raw_uid_counter.items() if count > 1),
        "machine_summaries": [summary.__dict__ for summary in summaries],
        "structure_evidence_present": evidence_signals["present"],
        "toc_detected_from_evidence": evidence_signals["toc_detected"],
        "main_chain_len_from_evidence": evidence_signals["main_chain_len"],
        "appendix_chain_len_from_evidence": evidence_signals["appendix_chain_len"],
        "crossref_anchor_count_from_evidence": evidence_signals["crossref_anchor_count"],
        "heading_candidates_count_from_evidence": evidence_signals["heading_candidates_count"],
        "appendix_marker_count_from_evidence": evidence_signals["appendix_marker_count"],
        "numbering_sequences_count_from_evidence": evidence_signals["numbering_sequences_count"],
        "document_quality_signals_from_evidence": dict(
            evidence_signals["document_quality_signals"]
        ),
    }

    logger.info(
        "STRUCTURE hierarchy_builder_completed",
        extra=hierarchy_diagnostics,
    )

    return frozen_root_nodes, frozen_nodes, element_to_effective_uid, structure_degraded


