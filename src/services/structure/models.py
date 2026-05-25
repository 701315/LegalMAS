# src/services/structure/models.py

"""
Data models for document structure tree and file-level graph.

Описывает результирующую структуру, которую строит Structure Builder
по layout документа и которую далее используют API, viewer и downstream pipeline.

Canonical model:
- canonical identity узла = effective_uid
- raw_uid = номер пункта внутри своего scope
- scope = пространство нумерации сегмента, например "main_contract", "appendix_1"
- clause_uid сохранён как legacy alias на переходный период

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

VALID_STRUCTURE_CONFIDENCE: frozenset[str] = frozenset({
    STRUCTURE_CONFIDENCE_HIGH,
    STRUCTURE_CONFIDENCE_MEDIUM,
    STRUCTURE_CONFIDENCE_LOW,
    STRUCTURE_CONFIDENCE_FAILED,
})

SEGMENT_CONFIDENCE_HIGH = "HIGH"
SEGMENT_CONFIDENCE_MEDIUM = "MEDIUM"
SEGMENT_CONFIDENCE_LOW = "LOW"

VALID_SEGMENT_CONFIDENCE: frozenset[str] = frozenset({
    SEGMENT_CONFIDENCE_HIGH,
    SEGMENT_CONFIDENCE_MEDIUM,
    SEGMENT_CONFIDENCE_LOW,
})

SEGMENT_TYPE_CONTRACT = "contract"
SEGMENT_TYPE_APPENDIX = "appendix"
SEGMENT_TYPE_AMENDMENT = "amendment"
SEGMENT_TYPE_ACT = "act"
SEGMENT_TYPE_INVOICE = "invoice"
SEGMENT_TYPE_SCHEDULE = "schedule"
SEGMENT_TYPE_PROTOCOL = "protocol"
SEGMENT_TYPE_OTHER = "other"
SEGMENT_TYPE_UNKNOWN = "unknown"

VALID_SEGMENT_TYPES: frozenset[str] = frozenset({
    SEGMENT_TYPE_CONTRACT,
    SEGMENT_TYPE_APPENDIX,
    SEGMENT_TYPE_AMENDMENT,
    SEGMENT_TYPE_ACT,
    SEGMENT_TYPE_INVOICE,
    SEGMENT_TYPE_SCHEDULE,
    SEGMENT_TYPE_PROTOCOL,
    SEGMENT_TYPE_OTHER,
    SEGMENT_TYPE_UNKNOWN,
})

NODE_KIND_LEAF = "leaf"
NODE_KIND_SECTION = "section"

VALID_NODE_KINDS: frozenset[str] = frozenset({
    NODE_KIND_LEAF,
    NODE_KIND_SECTION,
})

VALID_RANGE_END_REASONS: frozenset[str] = frozenset({
    "first_child",
    "next_same_or_higher",
    "segment_end",
    "fallback_boundary",
    "unbounded_error",
})


# ---------------------------------------------------------------------------
# Вспомогательные функции нормализации
# ---------------------------------------------------------------------------

def _norm_str(value: Any) -> str:
    return str(value or "").strip()


def _norm_opt_str(value: Any) -> str | None:
    normalized = _norm_str(value)
    return normalized or None


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


def make_effective_uid(scope: str, raw_uid: str) -> str:
    normalized_scope = _validate_scope_name(scope)
    normalized_raw_uid = _norm_str(raw_uid)
    if not normalized_raw_uid:
        raise ValueError("raw_uid must be non-empty to build effective_uid")
    return f"{normalized_scope}::{normalized_raw_uid}"


def generate_scope_name(segment_type: str, segment_order: int) -> str:
    normalized_type = _normalize_segment_type(segment_type)
    if segment_order < 0:
        raise ValueError("segment_order must be >= 0")

    if normalized_type == SEGMENT_TYPE_CONTRACT and segment_order == 0:
        return DEFAULT_SCOPE

    return f"{normalized_type}_{segment_order + 1}"


def make_segment_id(document_id: str, segment_order: int) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{document_id}::segment::{segment_order}",
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
    clause_uid: str | None = None

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
    clause_uid_alias_mode: bool = True

    def __post_init__(self) -> None:
        self.effective_uid = _norm_str(self.effective_uid)
        self.title = _norm_str(self.title)
        self.level = int(self.level)
        self.raw_uid = _norm_opt_str(self.raw_uid)
        self.scope = _norm_opt_str(self.scope)
        self.clause_uid = _norm_opt_str(self.clause_uid)
        self.node_kind = _normalize_node_kind(self.node_kind)
        self.start_page = int(self.start_page)
        self.end_page = int(self.end_page)
        self.range_end_reason = _normalize_range_end_reason(self.range_end_reason)
        self.clause_uid_alias_mode = bool(self.clause_uid_alias_mode)

        if not self.effective_uid:
            raise ValueError("ClauseNode.effective_uid must be non-empty")
        if self.level < 1:
            raise ValueError("ClauseNode.level must be >= 1")
        if self.start_page < 1 or self.end_page < 1:
            raise ValueError("ClauseNode start_page/end_page must be >= 1")
        if self.end_page < self.start_page:
            raise ValueError("ClauseNode.end_page must be >= start_page")

        if "::" in self.effective_uid:
            inferred_scope, inferred_raw_uid = self.effective_uid.split("::", 1)
        else:
            inferred_scope = DEFAULT_SCOPE
            inferred_raw_uid = self.effective_uid
            self.effective_uid = make_effective_uid(inferred_scope, inferred_raw_uid)

        inferred_scope = _validate_scope_name(inferred_scope)
        inferred_raw_uid = _norm_str(inferred_raw_uid)

        if not inferred_raw_uid:
            raise ValueError("ClauseNode.effective_uid must contain non-empty raw uid")

        if self.scope is None:
            self.scope = inferred_scope
        else:
            self.scope = _validate_scope_name(self.scope)

        if self.raw_uid is None:
            self.raw_uid = inferred_raw_uid

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

        if self.clause_uid is None:
            self.clause_uid = self.raw_uid
        elif self.clause_uid != self.raw_uid:
            raise ValueError(
                f"ClauseNode clause_uid mismatch: clause_uid={self.clause_uid!r}, "
                f"raw_uid={self.raw_uid!r}"
            )

    @property
    def element_ids(self) -> list[str]:
        return self.own_element_ids

    @element_ids.setter
    def element_ids(self, value: list[str]) -> None:
        self.own_element_ids = list(value or [])


@dataclass
class CrossReference:
    source_clause_uid: str
    target_clause_uid: str
    reference_text: str

    def __post_init__(self) -> None:
        self.source_clause_uid = _norm_str(self.source_clause_uid)
        self.target_clause_uid = _norm_str(self.target_clause_uid)
        self.reference_text = _norm_str(self.reference_text)


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
        self.resolution_confidence = float(self.resolution_confidence)

        if not self.source_effective_uid:
            raise ValueError("CrossSegmentRef.source_effective_uid must be non-empty")
        if not (0.0 <= self.resolution_confidence <= 1.0):
            raise ValueError("CrossSegmentRef.resolution_confidence must be in [0.0, 1.0]")

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
    clause_uid_alias_mode: bool = True
    cross_segment_refs: list[CrossSegmentRef] = field(default_factory=list)

    nodes_index: dict[str, ClauseNode] = field(default_factory=dict)

    segment_id: str | None = None
    segment_type: str | None = None
    segment_title: str | None = None
    segment_page_range: tuple[int, int] | None = None
    segment_order: int | None = None
    scope_name: str | None = None
    is_primary_segment: bool = False
    schema_version: str = "2.0"

    def __post_init__(self) -> None:
        self.document_id = _norm_str(self.document_id)
        self.structure_confidence = _normalize_structure_confidence(self.structure_confidence)
        self.segment_id = _norm_opt_str(self.segment_id)
        self.segment_title = _norm_opt_str(self.segment_title)

        if self.segment_type is not None:
            self.segment_type = _normalize_segment_type(self.segment_type)

        if self.scope_name is not None:
            self.scope_name = _validate_scope_name(self.scope_name)

        if self.segment_page_range is not None:
            start_page, end_page = self.segment_page_range
            start_page = int(start_page)
            end_page = int(end_page)
            if start_page < 1 or end_page < 1 or end_page < start_page:
                raise ValueError(
                    "ClauseTree.segment_page_range must be valid inclusive pages: (start >= 1, end >= start)"
                )
            self.segment_page_range = (start_page, end_page)

        if self.segment_order is not None and int(self.segment_order) < 0:
            raise ValueError("ClauseTree.segment_order must be >= 0")

        if self.nodes_index:
            for key, node in self.nodes_index.items():
                if key != node.effective_uid:
                    raise ValueError(
                        f"ClauseTree.nodes_index key mismatch: key={key!r}, "
                        f"node.effective_uid={node.effective_uid!r}"
                    )

        if self.scope_name is not None:
            for node in self.nodes_index.values():
                if node.scope != self.scope_name:
                    raise ValueError(
                        f"ClauseTree scope mismatch: tree.scope_name={self.scope_name!r}, "
                        f"node.scope={node.scope!r}, effective_uid={node.effective_uid!r}"
                    )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "document_id": self.document_id,
            "root": [self._node_to_dict(n) for n in self.root],
            "references_index": [
                {
                    "source": r.source_clause_uid,
                    "target": r.target_clause_uid,
                    "text": r.reference_text,
                }
                for r in self.references_index
            ],
            "cross_segment_refs": [r.to_dict() for r in self.cross_segment_refs],
            "structure_confidence": self.structure_confidence,
            "structure_diagnostics": self.structure_diagnostics,
            "clause_uid_alias_mode": self.clause_uid_alias_mode,
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

    def _node_to_dict(self, node: ClauseNode) -> dict[str, Any]:
        return {
            "effective_uid": node.effective_uid,
            "raw_uid": node.raw_uid,
            "scope": node.scope,
            "clause_uid": node.clause_uid,
            "title": node.title,
            "level": node.level,
            "node_kind": node.node_kind,
            "own_element_ids": node.own_element_ids,
            "subtree_element_ids": node.subtree_element_ids,
            "own_text": node.own_text,
            "subtree_text": node.subtree_text,
            "element_ids": node.element_ids,
            "start_page": node.start_page,
            "end_page": node.end_page,
            "range_end_reason": node.range_end_reason,
            "diagnostics": node.diagnostics,
            "clause_uid_alias_mode": node.clause_uid_alias_mode,
            "children": [self._node_to_dict(c) for c in node.children],
        }


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
        self.segment_order = int(self.segment_order)
        self.page_start = int(self.page_start)
        self.page_end = int(self.page_end)
        self.element_start = int(self.element_start)
        self.element_end = int(self.element_end)
        self.confidence = _normalize_segment_confidence(self.confidence)
        self.segmentation_confidence_score = float(self.segmentation_confidence_score)

        if not self.segment_id:
            raise ValueError("SegmentDocument.segment_id must be non-empty")
        if not self.document_id:
            raise ValueError("SegmentDocument.document_id must be non-empty")
        if self.segment_order < 0:
            raise ValueError("SegmentDocument.segment_order must be >= 0")
        if self.page_start < 1 or self.page_end < 1 or self.page_end < self.page_start:
            raise ValueError("SegmentDocument page range must satisfy 1 <= page_start <= page_end")
        if self.element_start < 0 or self.element_end < self.element_start:
            raise ValueError("SegmentDocument element range must satisfy 0 <= element_start <= element_end")
        if not (0.0 <= self.segmentation_confidence_score <= 1.0):
            raise ValueError("SegmentDocument.segmentation_confidence_score must be in [0.0, 1.0]")

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
            "segmentation_reasons": self.segmentation_reasons,
            "is_primary": self.is_primary,
            "diagnostics": self.diagnostics,
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
        self.confidence = float(self.confidence)

        if not self.source_segment_id or not self.target_segment_id:
            raise ValueError("CrossDocumentLink source_segment_id and target_segment_id must be non-empty")
        if not self.link_type:
            raise ValueError("CrossDocumentLink.link_type must be non-empty")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("CrossDocumentLink.confidence must be in [0.0, 1.0]")

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
    schema_version: str = "2.0"

    def __post_init__(self) -> None:
        self.document_id = _norm_str(self.document_id)
        self.document_version_id = _norm_opt_str(self.document_version_id)
        self.primary_segment_id = _norm_opt_str(self.primary_segment_id)
        self.structural_confidence = _normalize_structure_confidence(self.structural_confidence)

        if not self.document_id:
            raise ValueError("FileGraph.document_id must be non-empty")

        if self.primary_segment_id:
            segment_ids = {segment.segment_id for segment in self.segments}
            if self.primary_segment_id not in segment_ids:
                raise ValueError(
                    f"FileGraph.primary_segment_id={self.primary_segment_id!r} "
                    f"is not present in segments"
                )

        primary_marked = [s.segment_id for s in self.segments if s.is_primary]

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "document_id": self.document_id,
            "document_version_id": self.document_version_id,
            "primary_segment_id": self.primary_segment_id,
            "degraded": self.degraded,
            "structural_confidence": self.structural_confidence,
            "diagnostics": self.diagnostics,
            "segments": [s.to_dict() for s in self.segments],
            "cross_links": [lnk.to_dict() for lnk in self.cross_links],
        }

    @property
    def primary_segment(self) -> SegmentDocument | None:
        if not self.primary_segment_id:
            return None
        return next(
            (s for s in self.segments if s.segment_id == self.primary_segment_id),
            None,
        )

    @property
    def segment_count(self) -> int:
        return len(self.segments)

    def get_segment(self, segment_id: str) -> SegmentDocument | None:
        return next(
            (s for s in self.segments if s.segment_id == segment_id),
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
        graph_segments = self.file_graph.segments or []

        if len(self.segment_trees) != len(graph_segments):
            raise ValueError(
                f"FileStructureResult invariant violated: "
                f"segment_trees count ({len(self.segment_trees)}) != "
                f"file_graph.segments count ({len(graph_segments)})"
            )

        graph_ids = {
            str(getattr(seg, "segment_id", "") or "")
            for seg in graph_segments
        }
        tree_ids = {
            str(t.segment_id or "")
            for t in self.segment_trees
        }

        missing_in_trees = graph_ids - tree_ids
        extra_in_trees = tree_ids - graph_ids

        if missing_in_trees or extra_in_trees:
            raise ValueError(
                f"FileStructureResult invariant violated: "
                f"segment_ids mismatch between file_graph.segments and segment_trees. "
                f"missing_in_trees={missing_in_trees}, "
                f"extra_in_trees={extra_in_trees}"
            )

        if self.file_graph.primary_segment_id and self.primary_tree.segment_id != self.file_graph.primary_segment_id:
            raise ValueError(
                "FileStructureResult invariant violated: "
                "primary_tree.segment_id must match file_graph.primary_segment_id"
            )

    @property
    def primary_segment_id(self) -> str | None:
        return self.file_graph.primary_segment_id

    @property
    def segment_count(self) -> int:
        return len(self.segment_trees)

    def get_tree_for_segment(self, segment_id: str) -> ClauseTree | None:
        return next(
            (t for t in self.segment_trees if t.segment_id == segment_id),
            None,
        )
    
    