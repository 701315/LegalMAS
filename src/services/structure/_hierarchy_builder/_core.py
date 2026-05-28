# src/services/structure/_hierarchy_builder/_core.py

"""Основной оркестратор сборки ClauseHierarchy."""

from __future__ import annotations
import time
from typing import Any, Callable
from core.logging import get_logger
from services.structure._models._nodes import ClauseNode
from services.structure._models._identity import split_effective_uid
from services.structure._models._constants import VALID_SEMANTIC_ELEMENT_TYPES
from services.structure.hierarchy_state_machine import HierarchyStateMachine

from ._types import HeadingCandidate, OwnRangeComputation
from ._utils import (
    _safe_ratio, _normalize_title, _heading_raw_uid, _heading_effective_uid,
    _heading_scope, _is_strict_numeric_uid, level_from_uid
)
from ._scope_logic import (
    _group_headings_by_scope, _build_scope_boundaries, _build_heading_positions
)
from ._range_logic import _compute_own_range, _collect_own_text
from ._traversal import populate_subtree_element_ids

logger = get_logger(__name__)

_SUSPICIOUS_LEAF_RANGE_SPAN_THRESHOLD = 200
_RECOVERABLE_INVALID_HEADING_RATIO = 0.35
_RECOVERABLE_OWN_RANGE_ANOMALY_RATIO = 0.35
_FATAL_ROOTLESS_WITH_NODES = True

def build_clause_hierarchy(
    headings: list[HeadingCandidate],
    elements: list[dict[str, Any]],
    *,
    document_id: str,
    stable_element_id_resolver: Callable[[dict[str, Any], int], str],
) -> tuple[list[ClauseNode], dict[str, ClauseNode], dict[str, str], bool]:
    """Строит дерево ClauseNode и индексы идентификаторов элементов."""
    doc_id = str(document_id or "").strip()
    nodes: dict[str, ClauseNode] = {}
    root_nodes: list[ClauseNode] = []
    element_to_effective_uid: dict[str, str] = {}

    if not headings:
        return root_nodes, nodes, element_to_effective_uid, False

    invalid_heading_candidates_count = 0
    duplicate_effective_uid_skipped_count = 0
    own_range_invalid_count = 0
    own_range_missing_count = 0
    suspicious_leaf_nodes_count = 0
    element_ownership_conflicts = 0

    headings_by_scope = _group_headings_by_scope(headings)
    scope_boundaries = _build_scope_boundaries(elements)
    key_to_elem_i, key_to_idx = _build_heading_positions(headings)

    machines: dict[str, HierarchyStateMachine] = {}
    
    # Этап 1: Создание узлов и построение структуры
    for scope, scope_headings in headings_by_scope.items():
        machine = HierarchyStateMachine(scope=scope, document_id=doc_id)
        machines[scope] = machine

        for heading in scope_headings:
            try:
                raw_uid = _heading_raw_uid(heading)
                effective_uid = _heading_effective_uid(heading)
                if effective_uid in nodes:
                    duplicate_effective_uid_skipped_count += 1
                    continue

                # Обработка метаданных для типизации mypy
                h_meta = heading.metadata or {}
                sem_type = str(h_meta.get("semantic_element_type") or "").strip().lower() or None
                
                conf_raw = h_meta.get("heading_confidence")
                parse_conf: float | None = None
                if conf_raw is not None:
                    try:
                        parse_conf = float(conf_raw)
                        if not (0.0 <= parse_conf <= 1.0): parse_conf = None
                    except (ValueError, TypeError): parse_conf = None

                sem_node_type = sem_type if sem_type in VALID_SEMANTIC_ELEMENT_TYPES else None
                
                level = level_from_uid(raw_uid) if _is_strict_numeric_uid(raw_uid) else 1

                node = ClauseNode(
                    effective_uid=effective_uid, raw_uid=raw_uid, scope=scope,
                    title=_normalize_title(heading.title), level=level,
                    start_page=int(heading.page), end_page=int(heading.page),
                    semantic_node_type=sem_node_type, parse_confidence=parse_conf
                )
                nodes[effective_uid] = node

                attach_res = machine.attach(node, raw_uid=raw_uid, semantic_type=sem_type)
                if not attach_res.attached and attach_res.attach_mode == "skipped":
                    if "semantic_negative" in str(attach_res.reject_reason):
                        del nodes[effective_uid]

                if attach_res.attach_mode == "best_effort_root":
                    node.recovered_via_best_effort = True
                    node.fallback_reason = str(attach_res.reject_reason)

                if attach_res.attach_mode in {"root", "best_effort_root"}:
                    root_nodes.append(node)

            except Exception:
                invalid_heading_candidates_count += 1
                continue

    # Этап 2: Вычисление диапазонов владения (Own Range)
    for heading in headings:
        try:
            eff_uid = _heading_effective_uid(heading)
            node = nodes.get(eff_uid)
            if not node: continue

            scope = _heading_scope(heading)
            range_info = _compute_own_range(
                raw_uid=_heading_raw_uid(heading), node=node,
                headings=headings_by_scope.get(scope, []),
                elements=elements, key_to_elem_i=key_to_elem_i,
                key_to_heading_index=key_to_idx, scope=scope,
                scope_boundaries=scope_boundaries
            )

            node.range_end_reason = range_info.range_end_reason
            
            # Присваиваем element IDs
            own_ids: list[str] = []
            for j in range(range_info.start_elem_i, range_info.end_elem_i):
                s_id = str(stable_element_id_resolver(elements[j], j) or "").strip()
                if not s_id: continue
                own_ids.append(s_id)
                if s_id in element_to_effective_uid:
                    if element_to_effective_uid[s_id] != eff_uid:
                        element_ownership_conflicts += 1
                else:
                    element_to_effective_uid[s_id] = eff_uid
            
            node.own_element_ids = list(dict.fromkeys(own_ids))
            node.own_text = _collect_own_text(elements, range_info.start_elem_i, range_info.end_elem_i)
            node.diagnostics["own_range_span"] = range_info.end_elem_i - range_info.start_elem_i

        except Exception:
            own_range_missing_count += 1
            continue

    # Этап 3: Пост-обработка
    populate_subtree_element_ids(root_nodes, document_id=doc_id)
    
    # Расчёт деградации (упрощенно для примера)
    structure_degraded = bool(len(headings) > 0 and not nodes)
    
    return root_nodes, nodes, element_to_effective_uid, structure_degraded


