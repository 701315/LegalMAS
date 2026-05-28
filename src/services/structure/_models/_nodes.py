# src/services/structure/models/_nodes.py

"""
Модели узлов дерева и ссылок между узлами.

Содержит ClauseNode (узел дерева структуры документа), CrossReference
(внутрисегментная ссылка) и CrossSegmentRef (межсегментная ссылка).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ._constants import (
    NODE_KIND_LEAF,
    NODE_KIND_SECTION,
    VALID_SEMANTIC_ELEMENT_TYPES,
)
from ._identity import make_effective_uid, split_effective_uid
from ._normalization import (
    _ensure_dict,
    _norm_bool,
    _norm_opt_str,
    _norm_str,
    _normalize_node_kind,
    _normalize_positive_int,
    _normalize_probability,
    _normalize_range_end_reason,
    _normalize_unique_string_list,
    _validate_scope_name,
)


def _ensure_clause_nodes(values: Any, field_name: str) -> list["ClauseNode"]:
    """Валидирует list[ClauseNode]."""
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError(f"{field_name} must be a list[ClauseNode]")
    normalized: list[ClauseNode] = []
    for idx, value in enumerate(values):
        if not isinstance(value, ClauseNode):
            raise ValueError(f"{field_name}[{idx}] must be ClauseNode")
        normalized.append(value)
    return normalized


def _ensure_cross_refs(values: Any, field_name: str) -> list["CrossReference"]:
    """Валидирует list[CrossReference]."""
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError(f"{field_name} must be a list[CrossReference]")
    normalized: list[CrossReference] = []
    for idx, value in enumerate(values):
        if not isinstance(value, CrossReference):
            raise ValueError(f"{field_name}[{idx}] must be CrossReference")
        normalized.append(value)
    return normalized


def _ensure_cross_segment_refs(values: Any, field_name: str) -> list["CrossSegmentRef"]:
    """Валидирует list[CrossSegmentRef]."""
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError(f"{field_name} must be a list[CrossSegmentRef]")
    normalized: list[CrossSegmentRef] = []
    for idx, value in enumerate(values):
        if not isinstance(value, CrossSegmentRef):
            raise ValueError(f"{field_name}[{idx}] must be CrossSegmentRef")
        normalized.append(value)
    return normalized


@dataclass
class ClauseNode:
    """
    Узел дерева структуры документа.

    Canonical identity: effective_uid = "scope:raw_uid".
    Может быть leaf (без children) или section (с children).
    Содержит element IDs, text, page range и метаданные о качестве парсинга.
    """

    effective_uid: str
    title: str
    level: int
    raw_uid: str | None = None
    scope: str | None = None

    node_kind: str = NODE_KIND_LEAF

    own_element_ids: list[str] = field(default_factory=list)
    subtree_element_ids: list[str] = field(default_factory=list)
    own_text: str | None = None
    subtree_text: str | None = None

    start_page: int = 1
    end_page: int = 1
    children: list["ClauseNode"] = field(default_factory=list)

    range_end_reason: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    # Typed metadata полей для downstream consumers
    semantic_node_type: str | None = None
    parse_confidence: float | None = None
    citability_hint: str | None = None
    recovered_via_best_effort: bool = False
    fallback_reason: str | None = None

    def __post_init__(self) -> None:
        self.effective_uid = _norm_str(self.effective_uid)
        self.title = _norm_str(self.title)
        self.level = _normalize_positive_int(self.level, "ClauseNode.level")
        self.raw_uid = _norm_opt_str(self.raw_uid)
        self.scope = _norm_opt_str(self.scope)
        self.node_kind = _normalize_node_kind(self.node_kind)

        self.own_element_ids = _normalize_unique_string_list(
            self.own_element_ids,
            "ClauseNode.own_element_ids",
        )
        self.subtree_element_ids = _normalize_unique_string_list(
            self.subtree_element_ids,
            "ClauseNode.subtree_element_ids",
        )
        self.own_text = _norm_opt_str(self.own_text)
        self.subtree_text = _norm_opt_str(self.subtree_text)

        self.start_page = _normalize_positive_int(self.start_page, "ClauseNode.start_page")
        self.end_page = _normalize_positive_int(self.end_page, "ClauseNode.end_page")
        self.children = _ensure_clause_nodes(self.children, "ClauseNode.children")

        self.range_end_reason = _normalize_range_end_reason(self.range_end_reason)
        self.diagnostics = _ensure_dict(self.diagnostics, "ClauseNode.diagnostics")

        # Валидация typed metadata
        if self.semantic_node_type is not None:
            normalized_snt = _norm_str(self.semantic_node_type).lower()
            if normalized_snt not in VALID_SEMANTIC_ELEMENT_TYPES:
                raise ValueError(
                    f"ClauseNode.semantic_node_type={self.semantic_node_type!r} is not valid. "
                    f"Expected one of {sorted(VALID_SEMANTIC_ELEMENT_TYPES)} or None"
                )
            self.semantic_node_type = normalized_snt

        if self.parse_confidence is not None:
            self.parse_confidence = _normalize_probability(
                self.parse_confidence,
                "ClauseNode.parse_confidence",
            )

        _VALID_CITABILITY_HINTS: frozenset[str] = frozenset({"high", "medium", "low"})
        if self.citability_hint is not None:
            normalized_ch = _norm_str(self.citability_hint).lower()
            if normalized_ch not in _VALID_CITABILITY_HINTS:
                raise ValueError(
                    f"ClauseNode.citability_hint={self.citability_hint!r} is not valid. "
                    f"Expected one of {sorted(_VALID_CITABILITY_HINTS)} or None"
                )
            self.citability_hint = normalized_ch

        self.recovered_via_best_effort = _norm_bool(self.recovered_via_best_effort)
        self.fallback_reason = _norm_opt_str(self.fallback_reason)

        if self.end_page < self.start_page:
            raise ValueError("ClauseNode.end_page must be >= ClauseNode.start_page")

        inferred_scope, inferred_raw_uid = split_effective_uid(self.effective_uid)
        self.effective_uid = make_effective_uid(inferred_scope, inferred_raw_uid)

        if self.scope is None:
            self.scope = inferred_scope
        else:
            self.scope = _validate_scope_name(self.scope)

        if self.raw_uid is None:
            self.raw_uid = inferred_raw_uid
        else:
            self.raw_uid = _norm_str(self.raw_uid)

        if not self.raw_uid:
            raise ValueError("ClauseNode.raw_uid must be non-empty")

        if self.scope != inferred_scope:
            raise ValueError(
                f"ClauseNode scope mismatch: scope={self.scope!r}, "
                f"effective_uid implies {inferred_scope!r}"
            )

        if self.raw_uid != inferred_raw_uid:
            raise ValueError(
                f"ClauseNode raw_uid mismatch: raw_uid={self.raw_uid!r}, "
                f"effective_uid implies {inferred_raw_uid!r}"
            )

        if self.node_kind == NODE_KIND_LEAF and self.children:
            raise ValueError("ClauseNode with node_kind='leaf' must not have children")

        if self.node_kind == NODE_KIND_SECTION and not self.children:
            raise ValueError("ClauseNode with node_kind='section' must have children")

        own_set = set(self.own_element_ids)
        subtree_set = set(self.subtree_element_ids)
        if own_set and not own_set.issubset(subtree_set):
            raise ValueError(
                "ClauseNode.own_element_ids must be a subset of ClauseNode.subtree_element_ids"
            )

        for child in self.children:
            if child.level <= self.level:
                raise ValueError(
                    f"ClauseNode child level must be greater than parent level: "
                    f"parent={self.effective_uid!r} level={self.level}, "
                    f"child={child.effective_uid!r} level={child.level}"
                )
            if child.scope != self.scope:
                raise ValueError(
                    f"ClauseNode child scope mismatch: parent.scope={self.scope!r}, "
                    f"child.scope={child.scope!r}, child={child.effective_uid!r}"
                )
            if child.start_page < self.start_page or child.end_page > self.end_page:
                raise ValueError(
                    f"ClauseNode child page range must be within parent range: "
                    f"parent={self.effective_uid!r} [{self.start_page}, {self.end_page}], "
                    f"child={child.effective_uid!r} [{child.start_page}, {child.end_page}]"
                )

    def to_dict(self) -> dict[str, Any]:
        """Сериализовать в dict для JSON."""
        return {
            "effective_uid": self.effective_uid,
            "raw_uid": self.raw_uid,
            "scope": self.scope,
            "title": self.title,
            "level": self.level,
            "node_kind": self.node_kind,
            "own_element_ids": list(self.own_element_ids),
            "subtree_element_ids": list(self.subtree_element_ids),
            "own_text": self.own_text,
            "subtree_text": self.subtree_text,
            "start_page": self.start_page,
            "end_page": self.end_page,
            "range_end_reason": self.range_end_reason,
            "diagnostics": dict(self.diagnostics),
            "children": [child.to_dict() for child in self.children],
            "semantic_node_type": self.semantic_node_type,
            "parse_confidence": self.parse_confidence,
            "citability_hint": self.citability_hint,
            "recovered_via_best_effort": self.recovered_via_best_effort,
            "fallback_reason": self.fallback_reason,
        }


@dataclass
class CrossReference:
    """
    Ссылка между двумя узлами внутри одного ClauseTree.

    Canonical identity: (source_effective_uid, target_effective_uid).
    """

    source_effective_uid: str
    target_effective_uid: str
    reference_text: str
    source_raw_uid: str | None = None
    target_raw_uid: str | None = None
    source_scope: str | None = None
    target_scope: str | None = None
    resolution_mode: str = "resolved"

    def __post_init__(self) -> None:
        self.source_effective_uid = _norm_str(self.source_effective_uid)
        self.target_effective_uid = _norm_str(self.target_effective_uid)
        self.reference_text = _norm_str(self.reference_text)
        self.source_raw_uid = _norm_opt_str(self.source_raw_uid)
        self.target_raw_uid = _norm_opt_str(self.target_raw_uid)
        self.source_scope = _norm_opt_str(self.source_scope)
        self.target_scope = _norm_opt_str(self.target_scope)
        self.resolution_mode = _norm_str(self.resolution_mode) or "resolved"

        if not self.source_effective_uid:
            raise ValueError("CrossReference.source_effective_uid must be non-empty")
        if not self.target_effective_uid:
            raise ValueError("CrossReference.target_effective_uid must be non-empty")
        if not self.reference_text:
            raise ValueError("CrossReference.reference_text must be non-empty")

        source_scope, source_raw_uid = split_effective_uid(self.source_effective_uid)
        target_scope, target_raw_uid = split_effective_uid(self.target_effective_uid)

        self.source_effective_uid = make_effective_uid(source_scope, source_raw_uid)
        self.target_effective_uid = make_effective_uid(target_scope, target_raw_uid)

        if self.source_scope is None:
            self.source_scope = source_scope
        else:
            self.source_scope = _validate_scope_name(self.source_scope)
            if self.source_scope != source_scope:
                raise ValueError(
                    f"CrossReference source_scope mismatch: source_scope={self.source_scope!r}, "
                    f"source_effective_uid implies {source_scope!r}"
                )

        if self.target_scope is None:
            self.target_scope = target_scope
        else:
            self.target_scope = _validate_scope_name(self.target_scope)
            if self.target_scope != target_scope:
                raise ValueError(
                    f"CrossReference target_scope mismatch: target_scope={self.target_scope!r}, "
                    f"target_effective_uid implies {target_scope!r}"
                )

        if self.source_raw_uid is None:
            self.source_raw_uid = source_raw_uid
        elif _norm_str(self.source_raw_uid) != source_raw_uid:
            raise ValueError(
                f"CrossReference source_raw_uid mismatch: source_raw_uid={self.source_raw_uid!r}, "
                f"source_effective_uid implies {source_raw_uid!r}"
            )

        if self.target_raw_uid is None:
            self.target_raw_uid = target_raw_uid
        elif _norm_str(self.target_raw_uid) != target_raw_uid:
            raise ValueError(
                f"CrossReference target_raw_uid mismatch: target_raw_uid={self.target_raw_uid!r}, "
                f"target_effective_uid implies {target_raw_uid!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Сериализовать в dict для JSON."""
        return {
            "source_effective_uid": self.source_effective_uid,
            "target_effective_uid": self.target_effective_uid,
            "source_raw_uid": self.source_raw_uid,
            "target_raw_uid": self.target_raw_uid,
            "source_scope": self.source_scope,
            "target_scope": self.target_scope,
            "reference_text": self.reference_text,
            "resolution_mode": self.resolution_mode,
        }


@dataclass
class CrossSegmentRef:
    """
    Ссылка из узла одного segment tree на узел в другом segment tree.

    Может быть resolved (target_effective_uid заполнен) или unresolved.
    """

    source_effective_uid: str
    target_raw_uid: str | None = None
    target_scope_hint: str | None = None
    target_effective_uid: str | None = None
    resolution_confidence: float = 0.0
    resolution_method: str = "unresolved"
    reference_text: str | None = None

    def __post_init__(self) -> None:
        self.source_effective_uid = _norm_str(self.source_effective_uid)
        self.target_raw_uid = _norm_opt_str(self.target_raw_uid)
        self.target_scope_hint = _norm_opt_str(self.target_scope_hint)
        self.target_effective_uid = _norm_opt_str(self.target_effective_uid)
        self.reference_text = _norm_opt_str(self.reference_text)
        self.resolution_method = _norm_str(self.resolution_method) or "unresolved"
        self.resolution_confidence = _normalize_probability(
            self.resolution_confidence,
            "CrossSegmentRef.resolution_confidence",
        )

        if not self.source_effective_uid:
            raise ValueError("CrossSegmentRef.source_effective_uid must be non-empty")

        source_scope, source_raw_uid = split_effective_uid(self.source_effective_uid)
        self.source_effective_uid = make_effective_uid(source_scope, source_raw_uid)

        if self.target_scope_hint is not None:
            self.target_scope_hint = _validate_scope_name(self.target_scope_hint)

        if self.target_effective_uid is not None:
            target_scope, target_raw_uid = split_effective_uid(self.target_effective_uid)
            self.target_effective_uid = make_effective_uid(target_scope, target_raw_uid)

            if self.target_scope_hint is not None and self.target_scope_hint != target_scope:
                raise ValueError(
                    f"CrossSegmentRef target_scope_hint mismatch: "
                    f"target_scope_hint={self.target_scope_hint!r}, "
                    f"target_effective_uid implies {target_scope!r}"
                )

            if self.target_raw_uid is not None and _norm_str(self.target_raw_uid) != target_raw_uid:
                raise ValueError(
                    f"CrossSegmentRef target_raw_uid mismatch: "
                    f"target_raw_uid={self.target_raw_uid!r}, "
                    f"target_effective_uid implies {target_raw_uid!r}"
                )

    def to_dict(self) -> dict[str, Any]:
        """Сериализовать в dict для JSON."""
        return {
            "source_effective_uid": self.source_effective_uid,
            "target_raw_uid": self.target_raw_uid,
            "target_scope_hint": self.target_scope_hint,
            "target_effective_uid": self.target_effective_uid,
            "resolution_confidence": self.resolution_confidence,
            "resolution_method": self.resolution_method,
            "reference_text": self.reference_text,
        }
    

    