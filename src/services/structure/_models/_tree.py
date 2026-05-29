# src/services/structure/_models/_tree.py

"""
Модель дерева структуры одного логического документа (segment).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ._crossref_graph import CrossReferenceGraph
from ._diagnostics import ParseQualityDiagnostics, TOCDiagnostics
from ._nodes import (
    CrossSegmentRef,
    FrozenHierarchyNode,
    _ensure_cross_segment_refs,
)
from ._normalization import (
    _ensure_dict,
    _norm_bool,
    _norm_opt_str,
    _norm_str,
    _normalize_non_negative_int,
    _normalize_positive_int,
    _normalize_segment_type,
    _normalize_structure_confidence,
    _validate_scope_name,
)


def _ensure_frozen_root(values: Any, field_name: str) -> list[FrozenHierarchyNode]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError(f"{field_name} must be a list[FrozenHierarchyNode]")
    normalized: list[FrozenHierarchyNode] = []
    for idx, value in enumerate(values):
        if not isinstance(value, FrozenHierarchyNode):
            raise ValueError(f"{field_name}[{idx}] must be FrozenHierarchyNode")
        normalized.append(value)
    return normalized


@dataclass
class ClauseTree:
    document_id: str
    root: list[FrozenHierarchyNode]
    cross_reference_graph: CrossReferenceGraph
    structure_confidence: str

    degraded: bool = False
    structure_diagnostics: dict[str, Any] = field(default_factory=dict)
    cross_segment_refs: list[CrossSegmentRef] = field(default_factory=list)
    nodes_index: dict[str, FrozenHierarchyNode] = field(default_factory=dict)

    segment_id: str | None = None
    segment_type: str | None = None
    segment_title: str | None = None
    segment_page_range: tuple[int, int] | None = None
    segment_order: int | None = None
    scope_name: str | None = None
    is_primary_segment: bool = False
    schema_version: str = "4.0"

    def __post_init__(self) -> None:
        self.document_id = _norm_str(self.document_id)
        self.root = _ensure_frozen_root(self.root, "ClauseTree.root")
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

        if not isinstance(self.cross_reference_graph, CrossReferenceGraph):
            raise ValueError("ClauseTree.cross_reference_graph must be CrossReferenceGraph")

        if self.segment_type is not None:
            self.segment_type = _normalize_segment_type(self.segment_type)

        if self.scope_name is not None:
            self.scope_name = _validate_scope_name(self.scope_name)

        if self.segment_page_range is not None:
            if (
                not isinstance(self.segment_page_range, tuple | list)
                or len(self.segment_page_range) != 2
            ):
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
        if self.cross_reference_graph.document_id != self.document_id:
            raise ValueError(
                "ClauseTree.cross_reference_graph.document_id mismatch: "
                f"tree={self.document_id!r}, graph={self.cross_reference_graph.document_id!r}"
            )

        normalized_index: dict[str, FrozenHierarchyNode] = {}
        for key, node in self.nodes_index.items():
            normalized_key = _norm_str(key)
            if not normalized_key:
                raise ValueError("ClauseTree.nodes_index keys must be non-empty")
            if not isinstance(node, FrozenHierarchyNode):
                raise ValueError(
                    f"ClauseTree.nodes_index[{normalized_key!r}] must be FrozenHierarchyNode"
                )
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
                missing_in_nodes_index = sorted(
                    set(root_index.keys()) - set(self.nodes_index.keys())
                )
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

        for ref in self.cross_reference_graph.references:
            if ref.source_effective_uid not in self.nodes_index:
                raise ValueError(
                    f"ClauseTree.cross_reference_graph contains unknown source_effective_uid="
                    f"{ref.source_effective_uid!r}"
                )
            if ref.target_effective_uid not in self.nodes_index:
                raise ValueError(
                    f"ClauseTree.cross_reference_graph contains unknown target_effective_uid="
                    f"{ref.target_effective_uid!r}"
                )

    @staticmethod
    def _build_nodes_index_from_root(root: list[FrozenHierarchyNode]) -> dict[str, FrozenHierarchyNode]:
        index: dict[str, FrozenHierarchyNode] = {}

        def _walk(node: FrozenHierarchyNode) -> None:
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

    @property
    def toc_diagnostics(self) -> TOCDiagnostics | None:
        raw = self.structure_diagnostics.get("toc_diagnostics")
        if raw is None:
            return None
        if isinstance(raw, TOCDiagnostics):
            return raw
        if not isinstance(raw, dict):
            raise ValueError(
                "ClauseTree.structure_diagnostics['toc_diagnostics'] must be dict | TOCDiagnostics | None"
            )
        return TOCDiagnostics(**raw)

    @property
    def parse_quality(self) -> ParseQualityDiagnostics | None:
        raw = self.structure_diagnostics.get("parse_quality")
        if raw is None:
            return None
        if isinstance(raw, ParseQualityDiagnostics):
            return raw
        if not isinstance(raw, dict):
            raise ValueError(
                "ClauseTree.structure_diagnostics['parse_quality'] must be dict | ParseQualityDiagnostics | None"
            )
        toc_raw = raw.get("toc_diagnostics")
        toc_obj = None
        if toc_raw is not None:
            if isinstance(toc_raw, TOCDiagnostics):
                toc_obj = toc_raw
            elif isinstance(toc_raw, dict):
                toc_obj = TOCDiagnostics(**toc_raw)
            else:
                raise ValueError(
                    "ParseQualityDiagnostics.toc_diagnostics must be dict | TOCDiagnostics | None"
                )

        normalized = dict(raw)
        normalized["toc_diagnostics"] = toc_obj
        return ParseQualityDiagnostics(**normalized)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "document_id": self.document_id,
            "root": [node.to_dict() for node in self.root],
            "cross_reference_graph": self.cross_reference_graph.to_dict(),
            "cross_segment_refs": [ref.to_dict() for ref in self.cross_segment_refs],
            "structure_confidence": self.structure_confidence,
            "structure_diagnostics": self.structure_diagnostics,
            "degraded": self.degraded,
            "schema_version": self.schema_version,
            "is_primary_segment": self.is_primary_segment,
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

        return result
    
