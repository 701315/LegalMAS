# src/services/structure/_models/_nodes.py

"""
Модели узлов иерархии документа.

MutableHierarchyNode  — mutable узел во время FSM assembly
FrozenHierarchyNode   — immutable узел после freeze(), используется downstream
freeze()              — явная точка перехода mutable → frozen
freeze_forest()       — freeze для набора корневых узлов (forest)
CrossReference        — внутрисегментная ссылка между узлами
CrossSegmentRef       — межсегментная ссылка
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from ._constants import NODE_KIND_LEAF, NODE_KIND_SECTION
from ._identity import make_effective_uid, split_effective_uid
from ._normalization import (
    _ensure_dict,
    _norm_opt_str,
    _norm_str,
    _normalize_node_kind,
    _normalize_positive_int,
    _normalize_probability,
    _normalize_range_end_reason,
    _normalize_unique_string_list,
    _normalize_unique_string_tuple,
    _validate_scope_name,
)
from ._structural_hash import compute_structural_hash


_ALLOWED_NODE_ORIGINS = {
    "semantic_heading",
    "toc_rebuild",
    "appendix_recovery",
    "technical_fallback",
    "synthetic_preamble",
    "unknown",
}

_ALLOWED_CONTENT_MODES = {
    "full_text",
    "heading_only",
    "skeleton",
    "technical_fragment",
}

_ALLOWED_CITABILITY = {
    "high",
    "medium",
    "low",
    "technical",
}


def _normalize_node_origin(value: Any) -> str:
    normalized = (_norm_opt_str(value) or "unknown").lower()
    if normalized not in _ALLOWED_NODE_ORIGINS:
        raise ValueError(f"Unsupported node_origin: {value!r}")
    return normalized


def _normalize_content_mode(value: Any) -> str:
    normalized = (_norm_opt_str(value) or "full_text").lower()
    if normalized not in _ALLOWED_CONTENT_MODES:
        raise ValueError(f"Unsupported content_mode: {value!r}")
    return normalized


def _normalize_citability(value: Any) -> str:
    normalized = (_norm_opt_str(value) or "low").lower()
    if normalized not in _ALLOWED_CITABILITY:
        raise ValueError(f"Unsupported citability: {value!r}")
    return normalized


def _ensure_mutable_nodes(values: Any, field_name: str) -> list["MutableHierarchyNode"]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError(f"{field_name} must be a list[MutableHierarchyNode]")
    for idx, value in enumerate(values):
        if not isinstance(value, MutableHierarchyNode):
            raise ValueError(f"{field_name}[{idx}] must be MutableHierarchyNode")
    return list(values)


def _ensure_frozen_nodes(values: Any, field_name: str) -> tuple["FrozenHierarchyNode", ...]:
    if values is None:
        return ()
    if not isinstance(values, (list, tuple)):
        raise ValueError(f"{field_name} must be list|tuple[FrozenHierarchyNode]")
    normalized: list[FrozenHierarchyNode] = []
    for idx, value in enumerate(values):
        if not isinstance(value, FrozenHierarchyNode):
            raise ValueError(f"{field_name}[{idx}] must be FrozenHierarchyNode")
        normalized.append(value)
    return tuple(normalized)


def _ensure_cross_segment_refs(values: Any, field_name: str) -> list["CrossSegmentRef"]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError(f"{field_name} must be a list[CrossSegmentRef]")
    for idx, value in enumerate(values):
        if not isinstance(value, CrossSegmentRef):
            raise ValueError(f"{field_name}[{idx}] must be CrossSegmentRef")
    return list(values)


def _validate_child_invariants(
    parent_uid: str,
    parent_level: int,
    parent_scope: str,
    parent_start_page: int,
    parent_end_page: int,
    children: list["MutableHierarchyNode"],
) -> None:
    for child in children:
        if child.level <= parent_level:
            raise ValueError(
                f"Child level must be > parent level: "
                f"parent={parent_uid!r} level={parent_level}, "
                f"child={child.effective_uid!r} level={child.level}"
            )
        if child.scope != parent_scope:
            raise ValueError(
                f"Child scope mismatch: parent.scope={parent_scope!r}, "
                f"child.scope={child.scope!r}, child={child.effective_uid!r}"
            )
        if child.start_page < parent_start_page or child.end_page > parent_end_page:
            raise ValueError(
                f"Child page range must be within parent range: "
                f"parent={parent_uid!r} [{parent_start_page}, {parent_end_page}], "
                f"child={child.effective_uid!r} [{child.start_page}, {child.end_page}]"
            )


def _validate_frozen_child_invariants(
    parent_uid: str,
    parent_level: int,
    parent_scope: str,
    parent_start_page: int,
    parent_end_page: int,
    children: tuple["FrozenHierarchyNode", ...],
) -> None:
    for child in children:
        if child.level <= parent_level:
            raise ValueError(
                f"Child level must be > parent level: "
                f"parent={parent_uid!r} level={parent_level}, "
                f"child={child.effective_uid!r} level={child.level}"
            )
        if child.scope != parent_scope:
            raise ValueError(
                f"Child scope mismatch: parent.scope={parent_scope!r}, "
                f"child.scope={child.scope!r}, child={child.effective_uid!r}"
            )
        if child.start_page < parent_start_page or child.end_page > parent_end_page:
            raise ValueError(
                f"Child page range must be within parent range: "
                f"parent={parent_uid!r} [{parent_start_page}, {parent_end_page}], "
                f"child={child.effective_uid!r} [{child.start_page}, {child.end_page}]"
            )


def _validate_mutable_child_invariants_soft(
    parent_uid: str,
    parent_level: int,
    parent_scope: str,
    children: list["MutableHierarchyNode"],
) -> None:
    """
    Soft validation for assembly-time mutable trees.

    Здесь проверяем только то, что точно нельзя допускать уже на mutable стадии:
    - child.level должен быть строго больше parent.level;
    - child.scope должен совпадать со scope parent.

    Page ranges намеренно НЕ валидируются жёстко на mutable стадии:
    они могут быть стабилизированы позднее.
    """
    for child in children:
        if child.level <= parent_level:
            raise ValueError(
                f"Child level must be > parent level: "
                f"parent={parent_uid!r} level={parent_level}, "
                f"child={child.effective_uid!r} level={child.level}"
            )
        if child.scope != parent_scope:
            raise ValueError(
                f"Child scope mismatch: parent.scope={parent_scope!r}, "
                f"child.scope={child.scope!r}, child={child.effective_uid!r}"
            )


@dataclass
class MutableHierarchyNode:
    effective_uid: str
    title: str
    level: int

    raw_uid: str | None = None
    scope: str | None = None
    node_kind: str = NODE_KIND_LEAF

    node_origin: str = "unknown"
    content_mode: str = "full_text"
    citability: str = "low"

    # B3.5/Gap3: semantic_node_type как явное поле модели (не только в diagnostics).
    # До этого fix значение хранилось только в diagnostics dict и не доходило
    # до legal_unit_builder.
    semantic_node_type: str | None = None

    own_element_ids: list[str] = field(default_factory=list)
    subtree_element_ids: list[str] = field(default_factory=list)
    own_text: str | None = None
    subtree_text: str | None = None

    start_page: int = 1
    end_page: int = 1

    children: list["MutableHierarchyNode"] = field(default_factory=list)
    range_end_reason: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    structural_hash: str | None = None

    def __post_init__(self) -> None:
        self.effective_uid = _norm_str(self.effective_uid)
        self.title = _norm_str(self.title)
        self.level = _normalize_positive_int(self.level, "MutableHierarchyNode.level")
        self.raw_uid = _norm_opt_str(self.raw_uid)
        self.scope = _norm_opt_str(self.scope)
        self.node_kind = _normalize_node_kind(self.node_kind)

        self.node_origin = _normalize_node_origin(self.node_origin)
        self.content_mode = _normalize_content_mode(self.content_mode)
        self.citability = _normalize_citability(self.citability)

        self.own_element_ids = _normalize_unique_string_list(
            self.own_element_ids, "MutableHierarchyNode.own_element_ids"
        )
        self.subtree_element_ids = _normalize_unique_string_list(
            self.subtree_element_ids, "MutableHierarchyNode.subtree_element_ids"
        )
        self.own_text = _norm_opt_str(self.own_text)
        self.subtree_text = _norm_opt_str(self.subtree_text)

        self.start_page = _normalize_positive_int(self.start_page, "MutableHierarchyNode.start_page")
        self.end_page = _normalize_positive_int(self.end_page, "MutableHierarchyNode.end_page")

        self.children = _ensure_mutable_nodes(self.children, "MutableHierarchyNode.children")
        self.range_end_reason = _normalize_range_end_reason(self.range_end_reason)
        self.semantic_node_type = _norm_opt_str(self.semantic_node_type)
        self.diagnostics = _ensure_dict(self.diagnostics, "MutableHierarchyNode.diagnostics")

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
            raise ValueError("MutableHierarchyNode.raw_uid must be non-empty")

        if self.scope != inferred_scope:
            raise ValueError(
                f"MutableHierarchyNode scope mismatch: scope={self.scope!r}, "
                f"effective_uid implies {inferred_scope!r}"
            )
        if self.raw_uid != inferred_raw_uid:
            raise ValueError(
                f"MutableHierarchyNode raw_uid mismatch: raw_uid={self.raw_uid!r}, "
                f"effective_uid implies {inferred_raw_uid!r}"
            )

        if self.end_page < self.start_page:
            raise ValueError("MutableHierarchyNode.end_page must be >= start_page")

        if self.content_mode == "technical_fragment":
            self.node_origin = "technical_fallback"
            self.citability = "technical"

        # Mutable stage: children => section.
        # But section without children is allowed temporarily during assembly.
        if self.children and self.node_kind == NODE_KIND_LEAF:
            self.node_kind = NODE_KIND_SECTION

        own_set = set(self.own_element_ids)
        subtree_set = set(self.subtree_element_ids)
        if own_set and not own_set.issubset(subtree_set):
            raise ValueError(
                "MutableHierarchyNode.own_element_ids must be a subset of subtree_element_ids"
            )

        if self.children:
            _validate_mutable_child_invariants_soft(
                self.effective_uid,
                self.level,
                self.scope,
                self.children,
            )

    def compute_and_set_structural_hash(
        self,
        *,
        normalized_path: str,
        sibling_index: int,
    ) -> str:
        h = compute_structural_hash(
            normalized_path=normalized_path,
            stable_level=self.level,
            sibling_index=sibling_index,
            scope_id=self.scope or "main_contract",
        )
        if self.structural_hash is None:
            self.structural_hash = h
            return h
        if self.structural_hash != h:
            raise ValueError(
                f"Conflicting structural_hash recomputation for {self.effective_uid!r}: "
                f"existing={self.structural_hash!r}, new={h!r}"
            )
        return self.structural_hash


@dataclass(frozen=True)
class FrozenHierarchyNode:
    effective_uid: str
    title: str
    level: int
    raw_uid: str
    scope: str
    node_kind: str
    structural_hash: str

    node_origin: str = "unknown"
    content_mode: str = "full_text"
    citability: str = "low"

    # B3.5/Gap3: см. комментарий в MutableHierarchyNode.semantic_node_type.
    semantic_node_type: str | None = None

    own_element_ids: tuple[str, ...] = ()
    subtree_element_ids: tuple[str, ...] = ()
    own_text: str | None = None
    subtree_text: str | None = None

    start_page: int = 1
    end_page: int = 1

    children: tuple["FrozenHierarchyNode", ...] = ()
    range_end_reason: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        effective_uid = _norm_str(self.effective_uid)
        title = _norm_str(self.title)
        level = _normalize_positive_int(self.level, "FrozenHierarchyNode.level")
        raw_uid = _norm_str(self.raw_uid)
        scope = _validate_scope_name(self.scope)
        node_kind = _normalize_node_kind(self.node_kind)
        structural_hash = _norm_str(self.structural_hash)

        node_origin = _normalize_node_origin(self.node_origin)
        content_mode = _normalize_content_mode(self.content_mode)
        citability = _normalize_citability(self.citability)

        own_element_ids = _normalize_unique_string_tuple(
            self.own_element_ids, "FrozenHierarchyNode.own_element_ids"
        )
        subtree_element_ids = _normalize_unique_string_tuple(
            self.subtree_element_ids, "FrozenHierarchyNode.subtree_element_ids"
        )
        own_text = _norm_opt_str(self.own_text)
        subtree_text = _norm_opt_str(self.subtree_text)
        start_page = _normalize_positive_int(self.start_page, "FrozenHierarchyNode.start_page")
        end_page = _normalize_positive_int(self.end_page, "FrozenHierarchyNode.end_page")
        children = _ensure_frozen_nodes(self.children, "FrozenHierarchyNode.children")
        range_end_reason = _normalize_range_end_reason(self.range_end_reason)
        semantic_node_type = _norm_opt_str(self.semantic_node_type)
        diagnostics_dict = _ensure_dict(self.diagnostics, "FrozenHierarchyNode.diagnostics")

        inferred_scope, inferred_raw_uid = split_effective_uid(effective_uid)
        effective_uid = make_effective_uid(inferred_scope, inferred_raw_uid)

        if scope != inferred_scope:
            raise ValueError(
                f"FrozenHierarchyNode scope mismatch: scope={scope!r}, "
                f"effective_uid implies {inferred_scope!r}"
            )
        if raw_uid != inferred_raw_uid:
            raise ValueError(
                f"FrozenHierarchyNode raw_uid mismatch: raw_uid={raw_uid!r}, "
                f"effective_uid implies {inferred_raw_uid!r}"
            )
        if end_page < start_page:
            raise ValueError("FrozenHierarchyNode.end_page must be >= start_page")
        if not structural_hash:
            raise ValueError("FrozenHierarchyNode.structural_hash must be non-empty")

        if content_mode == "technical_fragment":
            node_origin = "technical_fallback"
            citability = "technical"

        if node_kind == NODE_KIND_LEAF and children:
            raise ValueError("FrozenHierarchyNode with node_kind='leaf' must not have children")
        if node_kind == NODE_KIND_SECTION and not children:
            raise ValueError("FrozenHierarchyNode with node_kind='section' must have children")

        own_set = set(own_element_ids)
        subtree_set = set(subtree_element_ids)
        if own_set and not own_set.issubset(subtree_set):
            raise ValueError(
                "FrozenHierarchyNode.own_element_ids must be a subset of subtree_element_ids"
            )

        if children:
            _validate_frozen_child_invariants(
                effective_uid,
                level,
                scope,
                start_page,
                end_page,
                children,
            )

        object.__setattr__(self, "effective_uid", effective_uid)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "level", level)
        object.__setattr__(self, "raw_uid", raw_uid)
        object.__setattr__(self, "scope", scope)
        object.__setattr__(self, "node_kind", node_kind)
        object.__setattr__(self, "structural_hash", structural_hash)
        object.__setattr__(self, "node_origin", node_origin)
        object.__setattr__(self, "content_mode", content_mode)
        object.__setattr__(self, "citability", citability)
        object.__setattr__(self, "own_element_ids", own_element_ids)
        object.__setattr__(self, "subtree_element_ids", subtree_element_ids)
        object.__setattr__(self, "own_text", own_text)
        object.__setattr__(self, "subtree_text", subtree_text)
        object.__setattr__(self, "start_page", start_page)
        object.__setattr__(self, "end_page", end_page)
        object.__setattr__(self, "children", children)
        object.__setattr__(self, "range_end_reason", range_end_reason)
        object.__setattr__(self, "semantic_node_type", semantic_node_type)
        object.__setattr__(self, "diagnostics", MappingProxyType(dict(diagnostics_dict)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "effective_uid": self.effective_uid,
            "raw_uid": self.raw_uid,
            "scope": self.scope,
            "title": self.title,
            "level": self.level,
            "node_kind": self.node_kind,
            "structural_hash": self.structural_hash,
            "node_origin": self.node_origin,
            "content_mode": self.content_mode,
            "citability": self.citability,
            "own_element_ids": list(self.own_element_ids),
            "subtree_element_ids": list(self.subtree_element_ids),
            "own_text": self.own_text,
            "subtree_text": self.subtree_text,
            "start_page": self.start_page,
            "end_page": self.end_page,
            "range_end_reason": self.range_end_reason,
            "semantic_node_type": self.semantic_node_type,
            "diagnostics": dict(self.diagnostics),
            "children": [child.to_dict() for child in self.children],
        }


def freeze(node: MutableHierarchyNode) -> FrozenHierarchyNode:
    return _freeze_node(
        node,
        seen_node_ids=set(),
        seen_effective_uids=set(),
    )


def freeze_forest(nodes: list[MutableHierarchyNode]) -> tuple[FrozenHierarchyNode, ...]:
    if nodes is None:
        return ()
    if not isinstance(nodes, list):
        raise ValueError("freeze_forest(nodes): nodes must be list[MutableHierarchyNode]")

    seen_node_ids: set[int] = set()
    seen_effective_uids: set[str] = set()
    frozen: list[FrozenHierarchyNode] = []

    for idx, node in enumerate(nodes):
        if not isinstance(node, MutableHierarchyNode):
            raise ValueError(f"freeze_forest(nodes)[{idx}] must be MutableHierarchyNode")
        frozen.append(
            _freeze_node(
                node,
                seen_node_ids=seen_node_ids,
                seen_effective_uids=seen_effective_uids,
            )
        )
    return tuple(frozen)


def _freeze_node(
    node: MutableHierarchyNode,
    *,
    seen_node_ids: set[int],
    seen_effective_uids: set[str],
) -> FrozenHierarchyNode:
    if not isinstance(node, MutableHierarchyNode):
        raise ValueError("_freeze_node(node): node must be MutableHierarchyNode")

    node_id = id(node)
    if node_id in seen_node_ids:
        raise ValueError(
            f"Cannot freeze hierarchy: cycle or shared mutable node detected for "
            f"{node.effective_uid!r}"
        )

    if node.effective_uid in seen_effective_uids:
        raise ValueError(
            f"Cannot freeze hierarchy: duplicate effective_uid encountered during freeze: "
            f"{node.effective_uid!r}"
        )

    if node.structural_hash is None:
        raise ValueError(
            f"Cannot freeze MutableHierarchyNode {node.effective_uid!r}: "
            f"structural_hash not computed. "
            f"Call node.compute_and_set_structural_hash() before freeze()."
        )

    seen_node_ids.add(node_id)
    seen_effective_uids.add(node.effective_uid)
    try:
        frozen_children = tuple(
            _freeze_node(
                child,
                seen_node_ids=seen_node_ids,
                seen_effective_uids=seen_effective_uids,
            )
            for child in node.children
        )

        node_kind = node.node_kind
        if frozen_children and node_kind == NODE_KIND_LEAF:
            node_kind = NODE_KIND_SECTION

        return FrozenHierarchyNode(
            effective_uid=node.effective_uid,
            title=node.title,
            level=node.level,
            raw_uid=node.raw_uid or "",
            scope=node.scope or "main_contract",
            node_kind=node_kind,
            structural_hash=node.structural_hash,
            node_origin=node.node_origin,
            content_mode=node.content_mode,
            citability=node.citability,
            semantic_node_type=node.semantic_node_type,
            own_element_ids=tuple(node.own_element_ids),
            subtree_element_ids=tuple(node.subtree_element_ids),
            own_text=node.own_text,
            subtree_text=node.subtree_text,
            start_page=node.start_page,
            end_page=node.end_page,
            children=frozen_children,
            range_end_reason=node.range_end_reason,
            diagnostics=dict(node.diagnostics),
        )
    finally:
        seen_node_ids.remove(node_id)

def unfreeze_node(node: FrozenHierarchyNode) -> MutableHierarchyNode:
    """
    Рекурсивно клонировать FrozenHierarchyNode → MutableHierarchyNode.

    Сохраняет structural_hash оригинала — он будет пересчитан
    только при явном вызове compute_and_set_structural_hash()
    или через refreeze_forest().

    Универсален: не зависит от причины заморозки или источника узла.
    """
    if not isinstance(node, FrozenHierarchyNode):
        raise ValueError(f"unfreeze_node: expected FrozenHierarchyNode, got {type(node).__name__}")

    mutable_children = [unfreeze_node(child) for child in node.children]

    mutable = MutableHierarchyNode(
        effective_uid=node.effective_uid,
        title=node.title,
        level=node.level,
        raw_uid=node.raw_uid,
        scope=node.scope,
        node_kind=node.node_kind,
        node_origin=node.node_origin,
        content_mode=node.content_mode,
        citability=node.citability,
        own_element_ids=list(node.own_element_ids),
        subtree_element_ids=list(node.subtree_element_ids),
        own_text=node.own_text,
        subtree_text=node.subtree_text,
        start_page=node.start_page,
        end_page=node.end_page,
        children=mutable_children,
        range_end_reason=node.range_end_reason,
        diagnostics=dict(node.diagnostics),
    )
    # Сохраняем оригинальный хэш; пересчёт — ответственность вызывающего кода
    mutable.structural_hash = node.structural_hash
    return mutable


def unfreeze_forest(
    nodes: tuple[FrozenHierarchyNode, ...] | list[FrozenHierarchyNode],
) -> list[MutableHierarchyNode]:
    """
    Клонировать лес frozen-узлов в mutable-узлы.
    Симметричная операция к freeze_forest().
    """
    if not nodes:
        return []
    return [unfreeze_node(n) for n in nodes]


def _ensure_structural_hashes(
    node: MutableHierarchyNode,
    parent_path: str = "",
    sibling_index: int = 0,
) -> None:
    """
    Рекурсивно пересчитать structural_hash для узлов, у которых он отсутствует.
    Узлы с уже установленным хэшем не пересчитываются (инвариант compute_and_set).
    """
    if node.structural_hash is None:
        normalized_path = (
            f"{parent_path}/{node.raw_uid}" if parent_path else (node.raw_uid or "")
        )
        node.compute_and_set_structural_hash(
            normalized_path=normalized_path,
            sibling_index=sibling_index,
        )
    for idx, child in enumerate(node.children):
        _ensure_structural_hashes(child, node.raw_uid or "", idx)


def refreeze_forest(
    nodes: list[MutableHierarchyNode],
) -> tuple[FrozenHierarchyNode, ...]:
    """
    Пересчитать хэши (где нужно) и заморозить лес mutable-узлов.
    Симметричная операция к unfreeze_forest().

    Гарантирует, что все узлы имеют structural_hash перед freeze.
    """
    if not nodes:
        return ()
    for idx, node in enumerate(nodes):
        _ensure_structural_hashes(node, "", idx)
    return freeze_forest(nodes)


@dataclass(frozen=True)
class CrossReference:
    source_effective_uid: str
    target_effective_uid: str
    reference_text: str
    source_raw_uid: str | None = None
    target_raw_uid: str | None = None
    source_scope: str | None = None
    target_scope: str | None = None
    resolution_mode: str = "resolved"
    reference_kind: str = "clause"
    match_start: int | None = None
    match_end: int | None = None
    pattern_family: str | None = None

    def __post_init__(self) -> None:
        source_effective_uid = _norm_str(self.source_effective_uid)
        target_effective_uid = _norm_str(self.target_effective_uid)
        reference_text = _norm_str(self.reference_text)
        source_raw_uid = _norm_opt_str(self.source_raw_uid)
        target_raw_uid = _norm_opt_str(self.target_raw_uid)
        source_scope = _norm_opt_str(self.source_scope)
        target_scope = _norm_opt_str(self.target_scope)
        resolution_mode = _norm_str(self.resolution_mode) or "resolved"
        reference_kind = _norm_str(self.reference_kind).lower() or "clause"
        pattern_family = _norm_opt_str(self.pattern_family)

        match_start = self.match_start
        match_end = self.match_end

        if not source_effective_uid:
            raise ValueError("CrossReference.source_effective_uid must be non-empty")
        if not target_effective_uid:
            raise ValueError("CrossReference.target_effective_uid must be non-empty")
        if not reference_text:
            raise ValueError("CrossReference.reference_text must be non-empty")

        if match_start is not None:
            if not isinstance(match_start, int):
                raise ValueError("CrossReference.match_start must be int | None")
            if match_start < 0:
                raise ValueError("CrossReference.match_start must be >= 0")

        if match_end is not None:
            if not isinstance(match_end, int):
                raise ValueError("CrossReference.match_end must be int | None")
            if match_end < 0:
                raise ValueError("CrossReference.match_end must be >= 0")

        if match_start is not None and match_end is not None and match_end < match_start:
            raise ValueError("CrossReference.match_end must be >= match_start")

        normalized_source_scope, normalized_source_raw_uid = split_effective_uid(source_effective_uid)
        normalized_target_scope, normalized_target_raw_uid = split_effective_uid(target_effective_uid)

        source_effective_uid = make_effective_uid(normalized_source_scope, normalized_source_raw_uid)
        target_effective_uid = make_effective_uid(normalized_target_scope, normalized_target_raw_uid)

        if source_scope is None:
            source_scope = normalized_source_scope
        else:
            source_scope = _validate_scope_name(source_scope)
            if source_scope != normalized_source_scope:
                raise ValueError(
                    f"CrossReference source_scope mismatch: "
                    f"source_scope={source_scope!r}, "
                    f"source_effective_uid implies {normalized_source_scope!r}"
                )

        if target_scope is None:
            target_scope = normalized_target_scope
        else:
            target_scope = _validate_scope_name(target_scope)
            if target_scope != normalized_target_scope:
                raise ValueError(
                    f"CrossReference target_scope mismatch: "
                    f"target_scope={target_scope!r}, "
                    f"target_effective_uid implies {normalized_target_scope!r}"
                )

        if source_raw_uid is None:
            source_raw_uid = normalized_source_raw_uid
        elif _norm_str(source_raw_uid) != normalized_source_raw_uid:
            raise ValueError(
                f"CrossReference source_raw_uid mismatch: "
                f"source_raw_uid={source_raw_uid!r}, "
                f"source_effective_uid implies {normalized_source_raw_uid!r}"
            )

        if target_raw_uid is None:
            target_raw_uid = normalized_target_raw_uid
        elif _norm_str(target_raw_uid) != normalized_target_raw_uid:
            raise ValueError(
                f"CrossReference target_raw_uid mismatch: "
                f"target_raw_uid={target_raw_uid!r}, "
                f"target_effective_uid implies {normalized_target_raw_uid!r}"
            )

        object.__setattr__(self, "source_effective_uid", source_effective_uid)
        object.__setattr__(self, "target_effective_uid", target_effective_uid)
        object.__setattr__(self, "reference_text", reference_text)
        object.__setattr__(self, "source_raw_uid", source_raw_uid)
        object.__setattr__(self, "target_raw_uid", target_raw_uid)
        object.__setattr__(self, "source_scope", source_scope)
        object.__setattr__(self, "target_scope", target_scope)
        object.__setattr__(self, "resolution_mode", resolution_mode)
        object.__setattr__(self, "reference_kind", reference_kind)
        object.__setattr__(self, "match_start", match_start)
        object.__setattr__(self, "match_end", match_end)
        object.__setattr__(self, "pattern_family", pattern_family)

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
            "reference_kind": self.reference_kind,
            "match_start": self.match_start,
            "match_end": self.match_end,
            "pattern_family": self.pattern_family,
        }


@dataclass(frozen=True)
class CrossSegmentRef:
    source_effective_uid: str
    target_raw_uid: str | None = None
    target_scope_hint: str | None = None
    target_effective_uid: str | None = None
    resolution_confidence: float = 0.0
    resolution_method: str = "unresolved"
    reference_text: str | None = None

    def __post_init__(self) -> None:
        source_effective_uid = _norm_str(self.source_effective_uid)
        target_raw_uid = _norm_opt_str(self.target_raw_uid)
        target_scope_hint = _norm_opt_str(self.target_scope_hint)
        target_effective_uid = _norm_opt_str(self.target_effective_uid)
        reference_text = _norm_opt_str(self.reference_text)
        resolution_method = _norm_str(self.resolution_method) or "unresolved"
        resolution_confidence = _normalize_probability(
            self.resolution_confidence,
            "CrossSegmentRef.resolution_confidence",
        )

        if not source_effective_uid:
            raise ValueError("CrossSegmentRef.source_effective_uid must be non-empty")

        source_scope, source_raw_uid = split_effective_uid(source_effective_uid)
        source_effective_uid = make_effective_uid(source_scope, source_raw_uid)

        if target_scope_hint is not None:
            target_scope_hint = _validate_scope_name(target_scope_hint)

        if target_effective_uid is not None:
            target_scope, target_raw_uid_from_effective = split_effective_uid(target_effective_uid)
            target_effective_uid = make_effective_uid(target_scope, target_raw_uid_from_effective)

            if target_scope_hint is not None and target_scope_hint != target_scope:
                raise ValueError(
                    f"CrossSegmentRef target_scope_hint mismatch: "
                    f"target_scope_hint={target_scope_hint!r}, "
                    f"target_effective_uid implies {target_scope!r}"
                )
            if target_raw_uid is not None and _norm_str(target_raw_uid) != target_raw_uid_from_effective:
                raise ValueError(
                    f"CrossSegmentRef target_raw_uid mismatch: "
                    f"target_raw_uid={target_raw_uid!r}, "
                    f"target_effective_uid implies {target_raw_uid_from_effective!r}"
                )

        object.__setattr__(self, "source_effective_uid", source_effective_uid)
        object.__setattr__(self, "target_raw_uid", target_raw_uid)
        object.__setattr__(self, "target_scope_hint", target_scope_hint)
        object.__setattr__(self, "target_effective_uid", target_effective_uid)
        object.__setattr__(self, "resolution_confidence", resolution_confidence)
        object.__setattr__(self, "resolution_method", resolution_method)
        object.__setattr__(self, "reference_text", reference_text)

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
    
    
