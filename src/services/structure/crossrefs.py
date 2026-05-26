# src/services/structure/crossrefs.py

"""
Извлечение перекрёстных ссылок между пунктами документа.

Задача этого модуля:
- не строить дерево;
- не парсить заголовки;
- а только искать в тексте ссылки вида "см. п. 3.2", "ст. 5", "Clause 7" и т.п.,
  а затем разрешать их на существующие узлы дерева.

Sprint 3 contract:
- canonical identity узла = effective_uid;
- raw_uid используется только как номер внутри scope и для explainability;
- резолвинг выполняется scope-aware;
- CrossReference всегда возвращается в canonical effective_uid space.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from core.logging import get_logger
from services.structure.models import (
    ClauseNode,
    CrossReference,
    DEFAULT_SCOPE,
    make_effective_uid,
    split_effective_uid,
)

logger = get_logger(__name__)


_UID_RE = r"\d+(?:\.\d+)*"

_CROSS_REF = re.compile(
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
            Art(?:icle)?\.?|
            Sec(?:tion)?\.?|
            Clause|Cl\.?
        )
        \s+
        (?P<en_target>{_UID_RE})
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _normalize_scope(value: Any) -> str:
    if value is None:
        return DEFAULT_SCOPE
    scope = str(value).strip()
    return scope or DEFAULT_SCOPE


def _normalize_uid(value: Any) -> str:
    return str(value or "").strip()


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _node_scope(node: ClauseNode) -> str:
    return _normalize_scope(getattr(node, "scope", None))


def _node_raw_uid(node: ClauseNode) -> str:
    return _normalize_uid(getattr(node, "raw_uid", None))


def _node_effective_uid(node: ClauseNode) -> str:
    effective_uid = _normalize_uid(getattr(node, "effective_uid", None))
    if not effective_uid:
        raw_uid = _node_raw_uid(node)
        if not raw_uid:
            raise ValueError("ClauseNode must have non-empty effective_uid or raw_uid")
        return make_effective_uid(_node_scope(node), raw_uid)

    scope, raw_uid = split_effective_uid(effective_uid)
    return make_effective_uid(scope, raw_uid)


def _extract_target_uid(match: re.Match[str]) -> str:
    return _normalize_uid(
        match.group("ru_target")
        or match.group("en_target")
    )


def _match_kind(match: re.Match[str]) -> str:
    prefix = _normalize_uid(match.group("ru_prefix") or match.group("en_prefix")).lower()

    if any(token in prefix for token in ("ст", "art", "article")):
        return "article"
    if any(token in prefix for token in ("sec", "section", "раздел")):
        return "section"
    if any(token in prefix for token in ("подп",)):
        return "subpoint"
    return "clause"


def _build_scope_indexes(
    nodes: dict[str, ClauseNode],
) -> tuple[
    dict[str, list[ClauseNode]],
    dict[tuple[str, str], ClauseNode],
    dict[str, ClauseNode],
]:
    """
    Возвращает:
    - raw_uid_index: raw_uid -> list[ClauseNode]
    - scoped_raw_index: (scope, raw_uid) -> node
    - effective_uid_index: effective_uid -> node

    Важная деталь:
    raw_uid больше не считается глобально уникальным, поэтому в global index
    храним список кандидатов.
    """
    raw_uid_index: dict[str, list[ClauseNode]] = {}
    scoped_raw_index: dict[tuple[str, str], ClauseNode] = {}
    effective_uid_index: dict[str, ClauseNode] = {}

    for key, node in nodes.items():
        try:
            effective_uid = _node_effective_uid(node)
            raw_uid = _node_raw_uid(node)
            scope = _node_scope(node)

            if _normalize_uid(key) and _normalize_uid(key) != effective_uid:
                raise ValueError(
                    f"nodes index key mismatch: key={key!r}, node.effective_uid={effective_uid!r}"
                )

            if not raw_uid:
                raise ValueError(f"node raw_uid is empty for effective_uid={effective_uid!r}")

            effective_uid_index.setdefault(effective_uid, node)
            raw_uid_index.setdefault(raw_uid, []).append(node)
            scoped_raw_index.setdefault((scope, raw_uid), node)

        except Exception as exc:
            logger.warning(
                "STRUCTURE crossrefs_index_node_skipped",
                extra={
                    "node_key": _normalize_uid(key),
                    "error": str(exc),
                },
            )
            continue

    return raw_uid_index, scoped_raw_index, effective_uid_index


def _resolve_target_node(
    *,
    source_node: ClauseNode,
    target_raw_uid: str,
    raw_uid_index: dict[str, list[ClauseNode]],
    scoped_raw_index: dict[tuple[str, str], ClauseNode],
    effective_uid_index: dict[str, ClauseNode],
) -> tuple[ClauseNode | None, str]:
    """
    Разрешает target в порядке приоритета:

    1. exact same-scope raw uid
    2. exact effective uid for source scope
    3. global raw uid fallback, только если кандидат ровно один
    4. иначе unresolved / ambiguous

    Возвращает:
    - target node или None
    - resolution_mode
    """
    source_scope = _node_scope(source_node)
    normalized_target_raw_uid = _normalize_uid(target_raw_uid)
    if not normalized_target_raw_uid:
        return None, "empty_target"

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


def extract_references(
    elements: list[dict],
    element_to_effective_uid: dict[str, str],
    nodes: dict[str, ClauseNode],
    *,
    document_id: str,
    stable_element_id_resolver: Callable[[dict[str, Any], int], str],
) -> list[CrossReference]:
    """
    Найти перекрёстные ссылки между клаузами.

    elements:
        layout-элементы (text_layout_raw.elements)
    element_to_effective_uid:
        mapping stable_element_id -> source effective_uid
    nodes:
        индекс ClauseNode по effective_uid
    stable_element_id_resolver:
        функция/метод, превращающая элемент + индекс в стабильный element_id
        (обычно StructureBuilder._stable_element_id)

    Возвращает список CrossReference в canonical effective_uid contract.
    """
    normalized_document_id = _normalize_text(document_id)

    references: list[CrossReference] = []
    seen_refs: set[tuple[str, str, str]] = set()

    unresolved_count = 0
    ambiguous_count = 0
    invalid_source_mapping_count = 0
    malformed_stable_element_id_count = 0

    raw_uid_index, scoped_raw_index, effective_uid_index = _build_scope_indexes(nodes)

    logger.debug(
        "STRUCTURE crossrefs_index_built",
        extra={
            "document_id": normalized_document_id,
            "nodes_count": len(nodes),
            "raw_uid_index_count": len(raw_uid_index),
            "scoped_raw_index_count": len(scoped_raw_index),
            "effective_uid_index_count": len(effective_uid_index),
        },
    )

    for idx, el in enumerate(elements):
        try:
            text = _normalize_text(el.get("text", ""))
            if not text:
                continue

            stable_el_id = _normalize_text(stable_element_id_resolver(el, idx))
            if not stable_el_id:
                malformed_stable_element_id_count += 1
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
                invalid_source_mapping_count += 1
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

            for match in _CROSS_REF.finditer(text):
                target_raw_uid = _extract_target_uid(match)
                if not target_raw_uid:
                    continue

                if target_raw_uid == source_raw_uid:
                    continue

                target_node, resolution_mode = _resolve_target_node(
                    source_node=source_node,
                    target_raw_uid=target_raw_uid,
                    raw_uid_index=raw_uid_index,
                    scoped_raw_index=scoped_raw_index,
                    effective_uid_index=effective_uid_index,
                )

                if target_node is None:
                    if resolution_mode == "ambiguous_global_raw_uid":
                        ambiguous_count += 1
                    else:
                        unresolved_count += 1

                    logger.debug(
                        "STRUCTURE crossref_target_not_resolved",
                        extra={
                            "document_id": normalized_document_id,
                            "element_index": idx,
                            "source_effective_uid": source_effective_uid,
                            "source_scope": source_scope,
                            "target_raw_uid": target_raw_uid,
                            "reference_text": match.group(),
                            "resolution_mode": resolution_mode,
                        },
                    )
                    continue

                target_scope = _node_scope(target_node)
                target_effective_uid = _node_effective_uid(target_node)
                target_raw_uid_resolved = _node_raw_uid(target_node)

                if not target_effective_uid or target_effective_uid == source_effective_uid:
                    continue

                reference_text = _normalize_text(match.group())
                key = (source_effective_uid, target_effective_uid, reference_text)
                if key in seen_refs:
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
                        "match_kind": _match_kind(match),
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

    logger.info(
        "STRUCTURE crossrefs_extraction_completed",
        extra={
            "document_id": normalized_document_id,
            "references_count": len(references),
            "elements_count": len(elements),
            "unresolved_count": unresolved_count,
            "ambiguous_count": ambiguous_count,
            "invalid_source_mapping_count": invalid_source_mapping_count,
            "malformed_stable_element_id_count": malformed_stable_element_id_count,
        },
    )

    return references

    

