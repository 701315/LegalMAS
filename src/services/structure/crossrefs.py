# src/services/structure/crossrefs.py

"""
Извлечение перекрёстных ссылок между пунктами документа.

Phase 7 contract:
- canonical identity узла = effective_uid;
- source/target space = FrozenHierarchyNode.effective_uid;
- raw_uid используется только как номер внутри scope и для explainability;
- резолвинг выполняется scope-aware;
- output фазы = CrossReferenceGraph.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from core.logging import get_logger
from services.structure.models import (
    DEFAULT_SCOPE,
    CrossReference,
    CrossReferenceGraph,
    CrossReferenceStats,
    FrozenHierarchyNode,
    make_effective_uid,
    split_effective_uid,
)

logger = get_logger(__name__)

_UID_RE = r"\d+(?:\.\d+)*"
_APPENDIX_NO_RE = r"(?:appendix|annex|schedule|exhibit|attachment|appendices|приложение)\s*(?:no\.?|№)?\s*(\d+)"

_CROSS_REF_SIMPLE = re.compile(
    rf"""
    (?:
        (?P<ru_prefix>
            см\.\s*
            (?:
                п\.?|пункт(?:а|е|ом)?|пп\.?|подп\.?|подпункт(?:а|е|ом)?|
                ст\.?|стать(?:я|и|е|ёй|ею)?|раздел(?:а|е|ом)?
            )
            \s*
        )
        (?P<ru_target>{_UID_RE})
    )
    |
    (?:
        (?P<en_prefix>
            Item|Clause|Cl\.?|Sec(?:tion)?\.?|Art(?:icle)?\.?
        )
        \s+
        (?P<en_target>{_UID_RE})
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

_CROSS_REF_APPENDIX_SCOPED = re.compile(
    rf"""
    (?:
        (?P<item_prefix>item|clause|section|sec\.?|п\.?|пункт(?:а|е|ом)?|подп\.?|подпункт(?:а|е|ом)?)
        \s+
        (?P<item_uid>{_UID_RE})
        \s+
        (?:of|in|under|из|в|согласно|according\ to)\s+
        (?P<appendix_prefix>appendix|annex|schedule|exhibit|attachment|приложение)
        \s*
        (?:no\.?|№)?\s*
        (?P<appendix_no>\d+)
    )
    |
    (?:
        (?P<appendix_only_prefix>appendix|annex|schedule|exhibit|attachment|приложение)
        \s*
        (?:no\.?|№)?\s*
        (?P<appendix_only_no>\d+)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


@dataclass
class _ExtractionCounters:
    unresolved_count: int = 0
    ambiguous_count: int = 0
    invalid_source_mapping_count: int = 0
    malformed_stable_element_id_count: int = 0
    duplicate_reference_count: int = 0
    skipped_self_reference_count: int = 0
    index_node_skipped_count: int = 0
    duplicate_effective_uid_count: int = 0
    duplicate_scoped_raw_uid_count: int = 0
    appendix_scoped_resolved_count: int = 0
    appendix_scope_miss_count: int = 0
    toc_like_reference_skipped_count: int = 0


@dataclass(slots=True)
class _CrossRefStub:
    source_effective_uid: str
    source_scope: str
    source_raw_uid: str
    reference_text: str
    reference_kind: str
    target_number: str | None = None
    target_scope_hint: str | None = None
    target_appendix_no: str | None = None


def _normalize_scope(value: Any) -> str:
    if value is None:
        return DEFAULT_SCOPE
    scope = str(value).strip()
    return scope or DEFAULT_SCOPE


def _normalize_uid(value: Any) -> str:
    return str(value or "").strip()


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _node_scope(node: FrozenHierarchyNode) -> str:
    return _normalize_scope(getattr(node, "scope", None))


def _node_raw_uid(node: FrozenHierarchyNode) -> str:
    return _normalize_uid(getattr(node, "raw_uid", None))


def _node_effective_uid(node: FrozenHierarchyNode) -> str:
    effective_uid = _normalize_uid(getattr(node, "effective_uid", None))
    if not effective_uid:
        raw_uid = _node_raw_uid(node)
        if not raw_uid:
            raise ValueError("FrozenHierarchyNode must have non-empty effective_uid or raw_uid")
        return make_effective_uid(_node_scope(node), raw_uid)

    scope, raw_uid = split_effective_uid(effective_uid)
    return make_effective_uid(scope, raw_uid)


def _looks_like_appendix_scope(scope: str) -> bool:
    s = _normalize_scope(scope).lower()
    return s.startswith("appendix") or s.startswith("приложение")


def _looks_like_toc_element(el: dict[str, Any]) -> bool:
    element_type = str(el.get("element_type") or "").strip().lower()
    return element_type in {
        "toc_header",
        "toc_line",
        "possible_toc",
    }


def _match_kind_from_prefix(prefix: str) -> str:
    p = _normalize_text(prefix).lower()
    if any(token in p for token in ("ст", "art", "article")):
        return "article"
    if any(token in p for token in ("sec", "section", "раздел")):
        return "section"
    if any(token in p for token in ("подп",)):
        return "subpoint"
    if any(token in p for token in ("appendix", "annex", "schedule", "exhibit", "attachment", "приложение")):
        return "appendix"
    return "clause"


def _build_scope_indexes(
    nodes: dict[str, FrozenHierarchyNode],
    *,
    document_id: str,
    counters: _ExtractionCounters,
) -> tuple[
    dict[str, list[FrozenHierarchyNode]],
    dict[tuple[str, str], FrozenHierarchyNode],
    dict[str, FrozenHierarchyNode],
    dict[str, FrozenHierarchyNode],
]:
    raw_uid_index: dict[str, list[FrozenHierarchyNode]] = {}
    scoped_raw_index: dict[tuple[str, str], FrozenHierarchyNode] = {}
    effective_uid_index: dict[str, FrozenHierarchyNode] = {}
    appendix_scope_index: dict[str, FrozenHierarchyNode] = {}

    for key, node in nodes.items():
        try:
            effective_uid = _node_effective_uid(node)
            raw_uid = _node_raw_uid(node)
            scope = _node_scope(node)

            if _normalize_uid(key) != effective_uid:
                raise ValueError(
                    f"nodes index key mismatch: key={key!r}, node.effective_uid={effective_uid!r}"
                )

            if not raw_uid:
                raise ValueError(f"node raw_uid is empty for effective_uid={effective_uid!r}")

            existing_by_effective = effective_uid_index.get(effective_uid)
            if existing_by_effective is not None and existing_by_effective is not node:
                counters.duplicate_effective_uid_count += 1
                logger.warning(
                    "STRUCTURE crossrefs_duplicate_effective_uid",
                    extra={
                        "document_id": document_id,
                        "effective_uid": effective_uid,
                    },
                )
                continue

            scoped_key = (scope, raw_uid)
            existing_scoped = scoped_raw_index.get(scoped_key)
            if existing_scoped is not None and existing_scoped is not node:
                counters.duplicate_scoped_raw_uid_count += 1
                logger.warning(
                    "STRUCTURE crossrefs_duplicate_scoped_raw_uid",
                    extra={
                        "document_id": document_id,
                        "scope": scope,
                        "raw_uid": raw_uid,
                        "effective_uid": effective_uid,
                    },
                )
                continue

            effective_uid_index[effective_uid] = node
            raw_uid_index.setdefault(raw_uid, []).append(node)
            scoped_raw_index[scoped_key] = node

            if _looks_like_appendix_scope(scope) and raw_uid.isdigit():
                appendix_scope_index.setdefault(raw_uid, node)

        except Exception as exc:
            counters.index_node_skipped_count += 1
            logger.warning(
                "STRUCTURE crossrefs_index_node_skipped",
                extra={
                    "document_id": document_id,
                    "node_key": _normalize_uid(key),
                    "error": str(exc),
                },
            )
            continue

    return raw_uid_index, scoped_raw_index, effective_uid_index, appendix_scope_index


def _extract_crossref_stubs(
    *,
    text: str,
    source_effective_uid: str,
    source_scope: str,
    source_raw_uid: str,
) -> list[_CrossRefStub]:
    stubs: list[_CrossRefStub] = []

    for match in _CROSS_REF_APPENDIX_SCOPED.finditer(text):
        appendix_no = _normalize_uid(match.group("appendix_no") or match.group("appendix_only_no"))
        item_uid = _normalize_uid(match.group("item_uid"))
        prefix = _normalize_text(
            match.group("item_prefix")
            or match.group("appendix_prefix")
            or match.group("appendix_only_prefix")
        )
        ref_text = _normalize_text(match.group())
        kind = "appendix" if not item_uid else _match_kind_from_prefix(prefix)

        stubs.append(
            _CrossRefStub(
                source_effective_uid=source_effective_uid,
                source_scope=source_scope,
                source_raw_uid=source_raw_uid,
                reference_text=ref_text,
                reference_kind=kind,
                target_number=item_uid or appendix_no,
                target_scope_hint="appendix",
                target_appendix_no=appendix_no,
            )
        )

    for match in _CROSS_REF_SIMPLE.finditer(text):
        ref_text = _normalize_text(match.group())
        prefix = _normalize_text(match.group("ru_prefix") or match.group("en_prefix"))
        target_number = _normalize_uid(match.group("ru_target") or match.group("en_target"))

        stubs.append(
            _CrossRefStub(
                source_effective_uid=source_effective_uid,
                source_scope=source_scope,
                source_raw_uid=source_raw_uid,
                reference_text=ref_text,
                reference_kind=_match_kind_from_prefix(prefix),
                target_number=target_number,
                target_scope_hint=None,
                target_appendix_no=None,
            )
        )

    return stubs


def _resolve_target_node(
    *,
    source_node: FrozenHierarchyNode,
    stub: _CrossRefStub,
    raw_uid_index: dict[str, list[FrozenHierarchyNode]],
    scoped_raw_index: dict[tuple[str, str], FrozenHierarchyNode],
    effective_uid_index: dict[str, FrozenHierarchyNode],
    appendix_scope_index: dict[str, FrozenHierarchyNode],
) -> tuple[FrozenHierarchyNode | None, str]:
    source_scope = _node_scope(source_node)
    normalized_target_raw_uid = _normalize_uid(stub.target_number)
    if not normalized_target_raw_uid:
        return None, "empty_target"

    if stub.target_scope_hint == "appendix" and stub.target_appendix_no:
        appendix_node = appendix_scope_index.get(_normalize_uid(stub.target_appendix_no))
        if appendix_node is None:
            return None, "appendix_scope_not_found"

        appendix_scope = _node_scope(appendix_node)

        if stub.reference_kind == "appendix" and normalized_target_raw_uid == _normalize_uid(stub.target_appendix_no):
            return appendix_node, "appendix_scope_exact"

        scoped_candidate = scoped_raw_index.get((appendix_scope, normalized_target_raw_uid))
        if scoped_candidate is not None:
            return scoped_candidate, "appendix_scoped_raw_uid"

        effective_candidate = make_effective_uid(appendix_scope, normalized_target_raw_uid)
        by_effective = effective_uid_index.get(effective_candidate)
        if by_effective is not None:
            return by_effective, "appendix_scoped_effective_uid"

        return None, "appendix_scoped_target_not_found"

    same_scope = scoped_raw_index.get((source_scope, normalized_target_raw_uid))
    if same_scope is not None:
        return same_scope, "same_scope_raw_uid"

    effective_candidate = make_effective_uid(source_scope, normalized_target_raw_uid)
    by_effective = effective_uid_index.get(effective_candidate)
    if by_effective is not None:
        return by_effective, "same_scope_effective_uid"

    global_candidates = raw_uid_index.get(normalized_target_raw_uid, [])
    if len(global_candidates) == 1:
        return global_candidates[0], "global_unique_raw_uid_fallback"
    if len(global_candidates) > 1:
        return None, "ambiguous_global_raw_uid"

    return None, "not_found"


def _build_stats(
    *,
    references: list[CrossReference],
    counters: _ExtractionCounters,
) -> CrossReferenceStats:
    unique_sources = {ref.source_effective_uid for ref in references}
    unique_targets = {ref.target_effective_uid for ref in references}

    return CrossReferenceStats(
        references_count=len(references),
        unique_sources_count=len(unique_sources),
        unique_targets_count=len(unique_targets),
        unresolved_count=counters.unresolved_count,
        ambiguous_count=counters.ambiguous_count,
        invalid_source_mapping_count=counters.invalid_source_mapping_count,
        malformed_stable_element_id_count=counters.malformed_stable_element_id_count,
        duplicate_reference_count=counters.duplicate_reference_count,
        skipped_self_reference_count=counters.skipped_self_reference_count,
        index_node_skipped_count=counters.index_node_skipped_count,
        duplicate_effective_uid_count=counters.duplicate_effective_uid_count,
        duplicate_scoped_raw_uid_count=counters.duplicate_scoped_raw_uid_count,
    )


def build_cross_reference_graph(
    elements: list[dict[str, Any]],
    element_to_effective_uid: dict[str, str],
    nodes: dict[str, FrozenHierarchyNode],
    *,
    document_id: str,
    stable_element_id_resolver: Callable[[dict[str, Any], int], str],
) -> CrossReferenceGraph:
    normalized_document_id = _normalize_text(document_id)
    if not normalized_document_id:
        raise ValueError("document_id must be non-empty")

    references: list[CrossReference] = []
    seen_refs: set[tuple[str, str, str]] = set()
    counters = _ExtractionCounters()

    (
        raw_uid_index,
        scoped_raw_index,
        effective_uid_index,
        appendix_scope_index,
    ) = _build_scope_indexes(
        nodes,
        document_id=normalized_document_id,
        counters=counters,
    )

    logger.debug(
        "STRUCTURE crossrefs_index_built",
        extra={
            "document_id": normalized_document_id,
            "nodes_count": len(nodes),
            "raw_uid_index_count": len(raw_uid_index),
            "scoped_raw_index_count": len(scoped_raw_index),
            "effective_uid_index_count": len(effective_uid_index),
            "appendix_scope_index_count": len(appendix_scope_index),
        },
    )

    for idx, el in enumerate(elements):
        try:
            if _looks_like_toc_element(el):
                counters.toc_like_reference_skipped_count += 1
                continue

            text = _normalize_text(el.get("text", ""))
            if not text:
                continue

            stable_el_id = _normalize_text(stable_element_id_resolver(el, idx))
            if not stable_el_id:
                counters.malformed_stable_element_id_count += 1
                logger.debug(
                    "STRUCTURE crossref_stable_element_id_missing",
                    extra={
                        "document_id": normalized_document_id,
                        "element_index": idx,
                    },
                )
                continue

            source_effective_uid = _normalize_uid(element_to_effective_uid.get(stable_el_id))
            if not source_effective_uid:
                continue

            source_scope_check, source_raw_uid_check = split_effective_uid(source_effective_uid)
            source_effective_uid = make_effective_uid(source_scope_check, source_raw_uid_check)

            source_node = nodes.get(source_effective_uid)
            if source_node is None:
                counters.invalid_source_mapping_count += 1
                logger.debug(
                    "STRUCTURE crossref_source_node_missing",
                    extra={
                        "document_id": normalized_document_id,
                        "element_index": idx,
                        "stable_element_id": stable_el_id,
                        "source_effective_uid": source_effective_uid,
                    },
                )
                continue

            source_scope = _node_scope(source_node)
            source_raw_uid = _node_raw_uid(source_node)
            source_effective_uid = _node_effective_uid(source_node)

            stubs = _extract_crossref_stubs(
                text=text,
                source_effective_uid=source_effective_uid,
                source_scope=source_scope,
                source_raw_uid=source_raw_uid,
            )

            for stub in stubs:
                target_raw_uid = _normalize_uid(stub.target_number)
                if not target_raw_uid:
                    continue

                if (
                    stub.target_scope_hint != "appendix"
                    and target_raw_uid == source_raw_uid
                    and source_scope == stub.source_scope
                ):
                    counters.skipped_self_reference_count += 1
                    continue

                target_node, resolution_mode = _resolve_target_node(
                    source_node=source_node,
                    stub=stub,
                    raw_uid_index=raw_uid_index,
                    scoped_raw_index=scoped_raw_index,
                    effective_uid_index=effective_uid_index,
                    appendix_scope_index=appendix_scope_index,
                )

                if target_node is None:
                    if resolution_mode == "ambiguous_global_raw_uid":
                        counters.ambiguous_count += 1
                    else:
                        counters.unresolved_count += 1
                        if resolution_mode == "appendix_scope_not_found":
                            counters.appendix_scope_miss_count += 1

                    logger.debug(
                        "STRUCTURE crossref_target_not_resolved",
                        extra={
                            "document_id": normalized_document_id,
                            "element_index": idx,
                            "source_effective_uid": source_effective_uid,
                            "source_scope": source_scope,
                            "target_raw_uid": target_raw_uid,
                            "reference_text": stub.reference_text,
                            "reference_kind": stub.reference_kind,
                            "target_scope_hint": stub.target_scope_hint,
                            "target_appendix_no": stub.target_appendix_no,
                            "resolution_mode": resolution_mode,
                        },
                    )
                    continue

                target_scope = _node_scope(target_node)
                target_effective_uid = _node_effective_uid(target_node)
                target_raw_uid_resolved = _node_raw_uid(target_node)

                if not target_effective_uid or target_effective_uid == source_effective_uid:
                    counters.skipped_self_reference_count += 1
                    continue

                if resolution_mode.startswith("appendix_"):
                    counters.appendix_scoped_resolved_count += 1

                reference_text = stub.reference_text
                reference_kind = stub.reference_kind
                key = (source_effective_uid, target_effective_uid, reference_text)
                if key in seen_refs:
                    counters.duplicate_reference_count += 1
                    continue

                seen_refs.add(key)
                references.append(
                    CrossReference(
                        source_effective_uid=source_effective_uid,
                        target_effective_uid=target_effective_uid,
                        reference_text=reference_text,
                        source_raw_uid=source_raw_uid,
                        target_raw_uid=target_raw_uid_resolved,
                        source_scope=source_scope,
                        target_scope=target_scope,
                        resolution_mode=resolution_mode,
                        reference_kind=reference_kind,
                    )
                )

                logger.debug(
                    "STRUCTURE crossref_extracted",
                    extra={
                        "document_id": normalized_document_id,
                        "element_index": idx,
                        "stable_element_id": stable_el_id,
                        "source_raw_uid": source_raw_uid,
                        "source_effective_uid": source_effective_uid,
                        "source_scope": source_scope,
                        "target_raw_uid": target_raw_uid_resolved,
                        "target_effective_uid": target_effective_uid,
                        "target_scope": target_scope,
                        "reference_text": reference_text,
                        "match_kind": reference_kind,
                        "target_scope_hint": stub.target_scope_hint,
                        "target_appendix_no": stub.target_appendix_no,
                        "resolution_mode": resolution_mode,
                    },
                )

        except Exception as exc:
            logger.error(
                "STRUCTURE cross-ref unexpected error",
                extra={
                    "document_id": normalized_document_id,
                    "element_index": idx,
                    "error": str(exc),
                },
            )
            continue

    stats = _build_stats(references=references, counters=counters)
    graph = CrossReferenceGraph.from_references(
        document_id=normalized_document_id,
        references=references,
        stats=stats,
    )

    logger.info(
        "STRUCTURE crossrefs_extraction_completed",
        extra={
            "document_id": normalized_document_id,
            **graph.stats.to_dict(),
            "elements_count": len(elements),
            "appendix_scoped_resolved_count": counters.appendix_scoped_resolved_count,
            "appendix_scope_miss_count": counters.appendix_scope_miss_count,
            "toc_like_reference_skipped_count": counters.toc_like_reference_skipped_count,
        },
    )

    return graph



