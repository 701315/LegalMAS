# src/services/structure/models.py

"""
Data models for document structure tree and file-level graph.

Описывает результирующую структуру, которую строит Structure Builder
по layout документа и которую далее используют API, viewer и downstream pipeline.

Canonical model:
- canonical identity узла = effective_uid
- raw_uid = номер пункта внутри своего scope
- scope = пространство нумерации сегмента, например "main_contract", "appendix_1"

Structure confidence:
- HIGH
- MEDIUM
- LOW
- FAILED

Segmentation confidence:
- HIGH
- MEDIUM
- LOW

Multi-document архитектура:
- ClauseTree — дерево одного логического сегмента
- SegmentDocument — один логический документ внутри файла
- FileGraph — файловый контейнер: список сегментов + межсегментные связи + diagnostics
- FileStructureResult — итог build_file_structure()
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Общие константы
# ---------------------------------------------------------------------------

DEFAULT_SCOPE = "main_contract"
SCOPE_NAME_RE = re.compile(r"^[a-z0-9_]+$")


STRUCTURE_CONFIDENCE_HIGH = "HIGH"
STRUCTURE_CONFIDENCE_MEDIUM = "MEDIUM"
STRUCTURE_CONFIDENCE_LOW = "LOW"
STRUCTURE_CONFIDENCE_FAILED = "FAILED"

VALID_STRUCTURE_CONFIDENCE: frozenset[str] = frozenset(
    {
        STRUCTURE_CONFIDENCE_HIGH,
        STRUCTURE_CONFIDENCE_MEDIUM,
        STRUCTURE_CONFIDENCE_LOW,
        STRUCTURE_CONFIDENCE_FAILED,
    }
)


SEGMENT_CONFIDENCE_HIGH = "HIGH"
SEGMENT_CONFIDENCE_MEDIUM = "MEDIUM"
SEGMENT_CONFIDENCE_LOW = "LOW"

VALID_SEGMENT_CONFIDENCE: frozenset[str] = frozenset(
    {
        SEGMENT_CONFIDENCE_HIGH,
        SEGMENT_CONFIDENCE_MEDIUM,
        SEGMENT_CONFIDENCE_LOW,
    }
)


SEGMENT_TYPE_CONTRACT = "contract"
SEGMENT_TYPE_APPENDIX = "appendix"
SEGMENT_TYPE_AMENDMENT = "amendment"
SEGMENT_TYPE_ACT = "act"
SEGMENT_TYPE_INVOICE = "invoice"
SEGMENT_TYPE_SCHEDULE = "schedule"
SEGMENT_TYPE_PROTOCOL = "protocol"
SEGMENT_TYPE_OTHER = "other"
SEGMENT_TYPE_UNKNOWN = "unknown"

VALID_SEGMENT_TYPES: frozenset[str] = frozenset(
    {
        SEGMENT_TYPE_CONTRACT,
        SEGMENT_TYPE_APPENDIX,
        SEGMENT_TYPE_AMENDMENT,
        SEGMENT_TYPE_ACT,
        SEGMENT_TYPE_INVOICE,
        SEGMENT_TYPE_SCHEDULE,
        SEGMENT_TYPE_PROTOCOL,
        SEGMENT_TYPE_OTHER,
        SEGMENT_TYPE_UNKNOWN,
    }
)


NODE_KIND_LEAF = "leaf"
NODE_KIND_SECTION = "section"

VALID_NODE_KINDS: frozenset[str] = frozenset(
    {
        NODE_KIND_LEAF,
        NODE_KIND_SECTION,
    }
)


VALID_RANGE_END_REASONS: frozenset[str] = frozenset(
    {
        "first_child",
        "next_same_or_higher",
        "segment_end",
        "fallback_boundary",
        "unbounded_error",
    }
)


# ---------------------------------------------------------------------------
# Вспомогательные функции нормализации
# ---------------------------------------------------------------------------

def _norm_str(value: Any) -> str:
    return str(value or "").strip()


def _norm_opt_str(value: Any) -> str | None:
    normalized = _norm_str(value)
    return normalized or None


def _norm_bool(value: Any) -> bool:
    return bool(value)


def _norm_scope(value: Any) -> str:
    scope = _norm_opt_str(value)
    return scope or DEFAULT_SCOPE


def _normalize_structure_confidence(value: Any) -> str:
    confidence = _norm_str(value).upper() or STRUCTURE_CONFIDENCE_MEDIUM
    if confidence not in VALID_STRUCTURE_CONFIDENCE:
        raise ValueError(
            f"Invalid structure_confidence={confidence!r}. "
            f"Expected one of {sorted(VALID_STRUCTURE_CONFIDENCE)}"
        )
    return confidence


def _normalize_segment_confidence(value: Any) -> str:
    confidence = _norm_str(value).upper() or SEGMENT_CONFIDENCE_MEDIUM
    if confidence not in VALID_SEGMENT_CONFIDENCE:
        raise ValueError(
            f"Invalid segment confidence={confidence!r}. "
            f"Expected one of {sorted(VALID_SEGMENT_CONFIDENCE)}"
        )
    return confidence


def _normalize_segment_type(value: Any) -> str:
    segment_type = _norm_str(value).lower() or SEGMENT_TYPE_UNKNOWN
    if segment_type not in VALID_SEGMENT_TYPES:
        raise ValueError(
            f"Invalid segment_type={segment_type!r}. "
            f"Expected one of {sorted(VALID_SEGMENT_TYPES)}"
        )
    return segment_type


def _validate_scope_name(scope_name: str) -> str:
    normalized = _norm_scope(scope_name)
    if not SCOPE_NAME_RE.fullmatch(normalized):
        raise ValueError(
            f"Invalid scope_name={normalized!r}. "
            f"Expected ASCII snake_case matching [a-z0-9_]+"
        )
    return normalized


def _normalize_range_end_reason(value: Any) -> str | None:
    reason = _norm_opt_str(value)
    if reason is None:
        return None
    if reason not in VALID_RANGE_END_REASONS:
        raise ValueError(
            f"Invalid range_end_reason={reason!r}. "
            f"Expected one of {sorted(VALID_RANGE_END_REASONS)}"
        )
    return reason


def _normalize_node_kind(value: Any) -> str:
    node_kind = _norm_str(value).lower() or NODE_KIND_LEAF
    if node_kind not in VALID_NODE_KINDS:
        raise ValueError(
            f"Invalid node_kind={node_kind!r}. "
            f"Expected one of {sorted(VALID_NODE_KINDS)}"
        )
    return node_kind


def _normalize_non_negative_int(value: Any, field_name: str) -> int:
    normalized = int(value)
    if normalized < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return normalized


def _normalize_positive_int(value: Any, field_name: str) -> int:
    normalized = int(value)
    if normalized < 1:
        raise ValueError(f"{field_name} must be >= 1")
    return normalized


def _normalize_probability(value: Any, field_name: str) -> float:
    normalized = float(value)
    if not (0.0 <= normalized <= 1.0):
        raise ValueError(f"{field_name} must be in [0.0, 1.0]")
    return normalized


def _normalize_string_list(values: Any, field_name: str) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError(f"{field_name} must be a list")
    normalized: list[str] = []
    for idx, value in enumerate(values):
        item = _norm_str(value)
        if not item:
            raise ValueError(f"{field_name}[{idx}] must be non-empty")
        normalized.append(item)
    return normalized


def _normalize_unique_string_list(values: Any, field_name: str) -> list[str]:
    normalized = _normalize_string_list(values, field_name)
    seen: set[str] = set()
    unique: list[str] = []
    for item in normalized:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def _ensure_dict(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a dict")
    return dict(value)


def _ensure_clause_nodes(values: Any, field_name: str) -> list["ClauseNode"]:
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


def _ensure_segments(values: Any, field_name: str) -> list["SegmentDocument"]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError(f"{field_name} must be a list[SegmentDocument]")
    normalized: list[SegmentDocument] = []
    for idx, value in enumerate(values):
        if not isinstance(value, SegmentDocument):
            raise ValueError(f"{field_name}[{idx}] must be SegmentDocument")
        normalized.append(value)
    return normalized


def _ensure_cross_links(values: Any, field_name: str) -> list["CrossDocumentLink"]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError(f"{field_name} must be a list[CrossDocumentLink]")
    normalized: list[CrossDocumentLink] = []
    for idx, value in enumerate(values):
        if not isinstance(value, CrossDocumentLink):
            raise ValueError(f"{field_name}[{idx}] must be CrossDocumentLink")
        normalized.append(value)
    return normalized


def make_effective_uid(scope: str, raw_uid: str) -> str:
    normalized_scope = _validate_scope_name(scope)
    normalized_raw_uid = _norm_str(raw_uid)
    if not normalized_raw_uid:
        raise ValueError("raw_uid must be non-empty to build effective_uid")
    return f"{normalized_scope}::{normalized_raw_uid}"


def split_effective_uid(effective_uid: str) -> tuple[str, str]:
    normalized = _norm_str(effective_uid)
    if not normalized:
        raise ValueError("effective_uid must be non-empty")

    if "::" not in normalized:
        raise ValueError(
            f"Invalid effective_uid={normalized!r}. "
            "Expected canonical '<scope>::<raw_uid>' format"
        )

    scope, raw_uid = normalized.split("::", 1)
    scope = _validate_scope_name(scope)
    raw_uid = _norm_str(raw_uid)

    if not raw_uid:
        raise ValueError("effective_uid must contain non-empty raw uid")

    return scope, raw_uid


def generate_scope_name(segment_type: str, segment_order: int) -> str:
    normalized_type = _normalize_segment_type(segment_type)
    normalized_order = _normalize_non_negative_int(segment_order, "segment_order")

    if normalized_type == SEGMENT_TYPE_CONTRACT and normalized_order == 0:
        return DEFAULT_SCOPE

    return f"{normalized_type}_{normalized_order + 1}"


def make_segment_id(document_id: str, segment_order: int) -> str:
    normalized_document_id = _norm_str(document_id)
    if not normalized_document_id:
        raise ValueError("document_id must be non-empty to build segment_id")

    normalized_order = _normalize_non_negative_int(segment_order, "segment_order")
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{normalized_document_id}::segment::{normalized_order}",
        )
    )


# ---------------------------------------------------------------------------
# Узлы дерева и ссылки
# ---------------------------------------------------------------------------

@dataclass
class ClauseNode:
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
        }


@dataclass
class CrossReference:
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
        return {
            "source_effective_uid": self.source_effective_uid,
            "target_raw_uid": self.target_raw_uid,
            "target_scope_hint": self.target_scope_hint,
            "target_effective_uid": self.target_effective_uid,
            "resolution_confidence": self.resolution_confidence,
            "resolution_method": self.resolution_method,
            "reference_text": self.reference_text,
        }


# ---------------------------------------------------------------------------
# Дерево одного сегмента
# ---------------------------------------------------------------------------

@dataclass
class ClauseTree:
    document_id: str
    root: list[ClauseNode]
    references_index: list[CrossReference]
    structure_confidence: str
    degraded: bool = False
    structure_diagnostics: dict[str, Any] = field(default_factory=dict)
    cross_segment_refs: list[CrossSegmentRef] = field(default_factory=list)

    nodes_index: dict[str, ClauseNode] = field(default_factory=dict)

    segment_id: str | None = None
    segment_type: str | None = None
    segment_title: str | None = None
    segment_page_range: tuple[int, int] | None = None
    segment_order: int | None = None
    scope_name: str | None = None
    is_primary_segment: bool = False
    schema_version: str = "3.0"

    def __post_init__(self) -> None:
        self.document_id = _norm_str(self.document_id)
        self.root = _ensure_clause_nodes(self.root, "ClauseTree.root")
        self.references_index = _ensure_cross_refs(
            self.references_index,
            "ClauseTree.references_index",
        )
        self.structure_confidence = _normalize_structure_confidence(self.structure_confidence)
        self.degraded = _norm_bool(self.degraded)
        self.structure_diagnostics = _ensure_dict(
            self.structure_diagnostics,
            "ClauseTree.structure_diagnostics",
        )
        self.cross_segment_refs = _ensure_cross_segment_refs(
            self.cross_segment_refs,
            "ClauseTree.cross_segment_refs",
        )
        self.nodes_index = _ensure_dict(self.nodes_index, "ClauseTree.nodes_index")

        self.segment_id = _norm_opt_str(self.segment_id)
        self.segment_title = _norm_opt_str(self.segment_title)

        if self.segment_type is not None:
            self.segment_type = _normalize_segment_type(self.segment_type)

        if self.scope_name is not None:
            self.scope_name = _validate_scope_name(self.scope_name)

        if self.segment_page_range is not None:
            if not isinstance(self.segment_page_range, tuple | list) or len(self.segment_page_range) != 2:
                raise ValueError("ClauseTree.segment_page_range must be a 2-item tuple/list")
            start_page, end_page = self.segment_page_range
            start_page = _normalize_positive_int(start_page, "ClauseTree.segment_page_range[0]")
            end_page = _normalize_positive_int(end_page, "ClauseTree.segment_page_range[1]")
            if end_page < start_page:
                raise ValueError(
                    "ClauseTree.segment_page_range must be valid inclusive pages: "
                    "(start >= 1, end >= start)"
                )
            self.segment_page_range = (start_page, end_page)

        if self.segment_order is not None:
            self.segment_order = _normalize_non_negative_int(
                self.segment_order,
                "ClauseTree.segment_order",
            )

        if not self.document_id:
            raise ValueError("ClauseTree.document_id must be non-empty")

        normalized_index: dict[str, ClauseNode] = {}
        for key, node in self.nodes_index.items():
            normalized_key = _norm_str(key)
            if not normalized_key:
                raise ValueError("ClauseTree.nodes_index keys must be non-empty")
            if not isinstance(node, ClauseNode):
                raise ValueError(f"ClauseTree.nodes_index[{normalized_key!r}] must be ClauseNode")
            if normalized_key != node.effective_uid:
                raise ValueError(
                    f"ClauseTree.nodes_index key mismatch: key={normalized_key!r}, "
                    f"node.effective_uid={node.effective_uid!r}"
                )
            normalized_index[normalized_key] = node
        self.nodes_index = normalized_index

        root_index = self._build_nodes_index_from_root(self.root)

        if self.nodes_index:
            if set(self.nodes_index.keys()) != set(root_index.keys()):
                missing_in_nodes_index = sorted(set(root_index.keys()) - set(self.nodes_index.keys()))
                extra_in_nodes_index = sorted(set(self.nodes_index.keys()) - set(root_index.keys()))
                raise ValueError(
                    "ClauseTree.nodes_index must match tree root traversal exactly: "
                    f"missing_in_nodes_index={missing_in_nodes_index}, "
                    f"extra_in_nodes_index={extra_in_nodes_index}"
                )
        else:
            self.nodes_index = root_index

        if self.scope_name is None and self.nodes_index:
            scopes = {node.scope for node in self.nodes_index.values()}
            if len(scopes) == 1:
                self.scope_name = next(iter(scopes))

        if self.scope_name is not None:
            for node in self.nodes_index.values():
                if node.scope != self.scope_name:
                    raise ValueError(
                        f"ClauseTree scope mismatch: tree.scope_name={self.scope_name!r}, "
                        f"node.scope={node.scope!r}, effective_uid={node.effective_uid!r}"
                    )

        if self.segment_page_range is not None:
            tree_start, tree_end = self.segment_page_range
            for node in self.nodes_index.values():
                if node.start_page < tree_start or node.end_page > tree_end:
                    raise ValueError(
                        f"ClauseTree segment_page_range does not cover node range: "
                        f"segment_page_range={self.segment_page_range}, "
                        f"node={node.effective_uid!r} [{node.start_page}, {node.end_page}]"
                    )

        for ref in self.references_index:
            if ref.source_effective_uid not in self.nodes_index:
                raise ValueError(
                    f"ClauseTree.references_index contains unknown source_effective_uid="
                    f"{ref.source_effective_uid!r}"
                )
            if ref.target_effective_uid not in self.nodes_index:
                raise ValueError(
                    f"ClauseTree.references_index contains unknown target_effective_uid="
                    f"{ref.target_effective_uid!r}"
                )

    @staticmethod
    def _build_nodes_index_from_root(root: list[ClauseNode]) -> dict[str, ClauseNode]:
        index: dict[str, ClauseNode] = {}

        def _walk(node: ClauseNode) -> None:
            if node.effective_uid in index:
                raise ValueError(
                    f"ClauseTree contains duplicate effective_uid={node.effective_uid!r}"
                )
            index[node.effective_uid] = node
            for child in node.children:
                _walk(child)

        for node in root:
            _walk(node)

        return index

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "document_id": self.document_id,
            "root": [node.to_dict() for node in self.root],
            "references_index": [ref.to_dict() for ref in self.references_index],
            "cross_segment_refs": [ref.to_dict() for ref in self.cross_segment_refs],
            "structure_confidence": self.structure_confidence,
            "structure_diagnostics": self.structure_diagnostics,
            "degraded": self.degraded,
            "schema_version": self.schema_version,
        }

        if self.segment_id is not None:
            result["segment_id"] = self.segment_id
        if self.segment_type is not None:
            result["segment_type"] = self.segment_type
        if self.segment_title is not None:
            result["segment_title"] = self.segment_title
        if self.segment_page_range is not None:
            result["segment_page_range"] = list(self.segment_page_range)
        if self.segment_order is not None:
            result["segment_order"] = self.segment_order
        if self.scope_name is not None:
            result["scope_name"] = self.scope_name

        result["is_primary_segment"] = self.is_primary_segment
        return result


# ---------------------------------------------------------------------------
# Segment / FileGraph
# ---------------------------------------------------------------------------

@dataclass
class SegmentDocument:
    segment_id: str
    document_id: str
    segment_order: int
    segment_type: str
    page_start: int
    page_end: int
    element_start: int
    element_end: int
    document_version_id: str | None = None
    segment_title: str | None = None
    scope_name: str | None = None
    confidence: str = SEGMENT_CONFIDENCE_MEDIUM
    segmentation_confidence_score: float = 0.0
    segmentation_reasons: list[str] = field(default_factory=list)
    is_primary: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.segment_id = _norm_str(self.segment_id)
        self.document_id = _norm_str(self.document_id)
        self.document_version_id = _norm_opt_str(self.document_version_id)
        self.segment_title = _norm_opt_str(self.segment_title)
        self.segment_type = _normalize_segment_type(self.segment_type)
        self.segment_order = _normalize_non_negative_int(
            self.segment_order,
            "SegmentDocument.segment_order",
        )
        self.page_start = _normalize_positive_int(self.page_start, "SegmentDocument.page_start")
        self.page_end = _normalize_positive_int(self.page_end, "SegmentDocument.page_end")
        self.element_start = _normalize_non_negative_int(
            self.element_start,
            "SegmentDocument.element_start",
        )
        self.element_end = _normalize_non_negative_int(
            self.element_end,
            "SegmentDocument.element_end",
        )
        self.confidence = _normalize_segment_confidence(self.confidence)
        self.segmentation_confidence_score = _normalize_probability(
            self.segmentation_confidence_score,
            "SegmentDocument.segmentation_confidence_score",
        )
        self.segmentation_reasons = _normalize_string_list(
            self.segmentation_reasons,
            "SegmentDocument.segmentation_reasons",
        )
        self.is_primary = _norm_bool(self.is_primary)
        self.diagnostics = _ensure_dict(self.diagnostics, "SegmentDocument.diagnostics")

        if not self.segment_id:
            raise ValueError("SegmentDocument.segment_id must be non-empty")
        if not self.document_id:
            raise ValueError("SegmentDocument.document_id must be non-empty")
        if self.page_end < self.page_start:
            raise ValueError("SegmentDocument page range must satisfy 1 <= page_start <= page_end")
        if self.element_end < self.element_start:
            raise ValueError(
                "SegmentDocument element range must satisfy 0 <= element_start <= element_end"
            )

        if self.scope_name is None:
            self.scope_name = generate_scope_name(self.segment_type, self.segment_order)
        else:
            self.scope_name = _validate_scope_name(self.scope_name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "document_id": self.document_id,
            "document_version_id": self.document_version_id,
            "segment_order": self.segment_order,
            "segment_type": self.segment_type,
            "segment_title": self.segment_title,
            "scope_name": self.scope_name,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "element_start": self.element_start,
            "element_end": self.element_end,
            "confidence": self.confidence,
            "segmentation_confidence_score": self.segmentation_confidence_score,
            "segmentation_reasons": list(self.segmentation_reasons),
            "is_primary": self.is_primary,
            "diagnostics": dict(self.diagnostics),
        }


@dataclass
class CrossDocumentLink:
    source_segment_id: str
    target_segment_id: str
    link_type: str
    reference_text: str | None = None
    confidence: float = 0.5

    def __post_init__(self) -> None:
        self.source_segment_id = _norm_str(self.source_segment_id)
        self.target_segment_id = _norm_str(self.target_segment_id)
        self.link_type = _norm_str(self.link_type)
        self.reference_text = _norm_opt_str(self.reference_text)
        self.confidence = _normalize_probability(
            self.confidence,
            "CrossDocumentLink.confidence",
        )

        if not self.source_segment_id or not self.target_segment_id:
            raise ValueError(
                "CrossDocumentLink source_segment_id and target_segment_id must be non-empty"
            )
        if not self.link_type:
            raise ValueError("CrossDocumentLink.link_type must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_segment_id": self.source_segment_id,
            "target_segment_id": self.target_segment_id,
            "link_type": self.link_type,
            "reference_text": self.reference_text,
            "confidence": self.confidence,
        }


@dataclass
class FileGraph:
    document_id: str
    segments: list[SegmentDocument]
    cross_links: list[CrossDocumentLink]
    primary_segment_id: str | None
    document_version_id: str | None = None
    degraded: bool = False
    structural_confidence: str = STRUCTURE_CONFIDENCE_MEDIUM
    diagnostics: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "3.0"

    def __post_init__(self) -> None:
        self.document_id = _norm_str(self.document_id)
        self.segments = _ensure_segments(self.segments, "FileGraph.segments")
        self.cross_links = _ensure_cross_links(self.cross_links, "FileGraph.cross_links")
        self.primary_segment_id = _norm_opt_str(self.primary_segment_id)
        self.document_version_id = _norm_opt_str(self.document_version_id)
        self.degraded = _norm_bool(self.degraded)
        self.structural_confidence = _normalize_structure_confidence(self.structural_confidence)
        self.diagnostics = _ensure_dict(self.diagnostics, "FileGraph.diagnostics")

        if not self.document_id:
            raise ValueError("FileGraph.document_id must be non-empty")

        segment_ids = [segment.segment_id for segment in self.segments]
        if len(segment_ids) != len(set(segment_ids)):
            raise ValueError(f"FileGraph contains duplicate segment_ids: {segment_ids}")

        segment_orders = [segment.segment_order for segment in self.segments]
        if len(segment_orders) != len(set(segment_orders)):
            raise ValueError(f"FileGraph contains duplicate segment_order values: {segment_orders}")

        for segment in self.segments:
            if segment.document_id != self.document_id:
                raise ValueError(
                    f"FileGraph segment document_id mismatch: "
                    f"graph.document_id={self.document_id!r}, "
                    f"segment.document_id={segment.document_id!r}, "
                    f"segment_id={segment.segment_id!r}"
                )
            if self.document_version_id is not None:
                if segment.document_version_id is not None and segment.document_version_id != self.document_version_id:
                    raise ValueError(
                        f"FileGraph segment document_version_id mismatch: "
                        f"graph.document_version_id={self.document_version_id!r}, "
                        f"segment.document_version_id={segment.document_version_id!r}, "
                        f"segment_id={segment.segment_id!r}"
                    )

        if self.primary_segment_id:
            if self.primary_segment_id not in set(segment_ids):
                raise ValueError(
                    f"FileGraph.primary_segment_id={self.primary_segment_id!r} "
                    f"is not present in segments"
                )

        primary_marked = [segment.segment_id for segment in self.segments if segment.is_primary]

        if len(primary_marked) > 1:
            raise ValueError(
                f"FileGraph invariant violated: multiple primary segments marked: {primary_marked}"
            )

        if self.primary_segment_id:
            if primary_marked and primary_marked[0] != self.primary_segment_id:
                raise ValueError(
                    f"FileGraph invariant violated: primary_segment_id={self.primary_segment_id!r} "
                    f"does not match segment marked is_primary=True ({primary_marked[0]!r})"
                )
        elif primary_marked:
            self.primary_segment_id = primary_marked[0]

        for link in self.cross_links:
            if link.source_segment_id not in set(segment_ids):
                raise ValueError(
                    f"FileGraph.cross_links contains unknown source_segment_id="
                    f"{link.source_segment_id!r}"
                )
            if link.target_segment_id not in set(segment_ids):
                raise ValueError(
                    f"FileGraph.cross_links contains unknown target_segment_id="
                    f"{link.target_segment_id!r}"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "document_id": self.document_id,
            "document_version_id": self.document_version_id,
            "primary_segment_id": self.primary_segment_id,
            "degraded": self.degraded,
            "structural_confidence": self.structural_confidence,
            "diagnostics": self.diagnostics,
            "segments": [segment.to_dict() for segment in self.segments],
            "cross_links": [link.to_dict() for link in self.cross_links],
        }

    @property
    def primary_segment(self) -> SegmentDocument | None:
        if not self.primary_segment_id:
            return None
        return next(
            (segment for segment in self.segments if segment.segment_id == self.primary_segment_id),
            None,
        )

    @property
    def segment_count(self) -> int:
        return len(self.segments)

    def get_segment(self, segment_id: str) -> SegmentDocument | None:
        normalized_segment_id = _norm_str(segment_id)
        if not normalized_segment_id:
            return None
        return next(
            (segment for segment in self.segments if segment.segment_id == normalized_segment_id),
            None,
        )


# ---------------------------------------------------------------------------
# Итог build_file_structure()
# ---------------------------------------------------------------------------

@dataclass
class FileStructureResult:
    primary_tree: ClauseTree
    segment_trees: list[ClauseTree]
    file_graph: FileGraph

    def __post_init__(self) -> None:
        if not isinstance(self.primary_tree, ClauseTree):
            raise ValueError("FileStructureResult.primary_tree must be ClauseTree")
        if not isinstance(self.file_graph, FileGraph):
            raise ValueError("FileStructureResult.file_graph must be FileGraph")
        if not isinstance(self.segment_trees, list):
            raise ValueError("FileStructureResult.segment_trees must be list[ClauseTree]")
        for idx, tree in enumerate(self.segment_trees):
            if not isinstance(tree, ClauseTree):
                raise ValueError(f"FileStructureResult.segment_trees[{idx}] must be ClauseTree")

        graph_segments = self.file_graph.segments or []

        if len(self.segment_trees) != len(graph_segments):
            raise ValueError(
                f"FileStructureResult invariant violated: "
                f"segment_trees count ({len(self.segment_trees)}) != "
                f"file_graph.segments count ({len(graph_segments)})"
            )

        graph_ids = {str(getattr(segment, "segment_id", "") or "") for segment in graph_segments}
        tree_ids = {str(tree.segment_id or "") for tree in self.segment_trees}

        missing_in_trees = graph_ids - tree_ids
        extra_in_trees = tree_ids - graph_ids

        if missing_in_trees or extra_in_trees:
            raise ValueError(
                f"FileStructureResult invariant violated: "
                f"segment_ids mismatch between file_graph.segments and segment_trees. "
                f"missing_in_trees={missing_in_trees}, "
                f"extra_in_trees={extra_in_trees}"
            )

        if self.file_graph.primary_segment_id:
            if self.primary_tree.segment_id != self.file_graph.primary_segment_id:
                raise ValueError(
                    "FileStructureResult invariant violated: "
                    "primary_tree.segment_id must match file_graph.primary_segment_id"
                )

        for tree in self.segment_trees:
            if tree.document_id != self.file_graph.document_id:
                raise ValueError(
                    f"FileStructureResult invariant violated: "
                    f"tree.document_id={tree.document_id!r} != "
                    f"file_graph.document_id={self.file_graph.document_id!r}"
                )

    @property
    def primary_segment_id(self) -> str | None:
        return self.file_graph.primary_segment_id

    @property
    def segment_count(self) -> int:
        return len(self.segment_trees)

    def get_tree_for_segment(self, segment_id: str) -> ClauseTree | None:
        normalized_segment_id = _norm_str(segment_id)
        if not normalized_segment_id:
            return None
        return next(
            (tree for tree in self.segment_trees if tree.segment_id == normalized_segment_id),
            None,
        )
    
    