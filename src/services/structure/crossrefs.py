# src/services/structure/crossrefs.py

"""
Извлечение перекрёстных ссылок между пунктами документа.

Задача этого модуля:
- не строить дерево;
- не парсить заголовки;
- а только искать в тексте ссылки вида "см. п. 3.2", "ст. 5", "Clause 7" и т.п.,
  а затем разрешать их на существующие узлы дерева.

Production notes:
- модуль backward-compatible с legacy nodes_index/raw uid;
- если у ClauseNode уже есть scope/raw_uid/effective_uid, резолвинг становится
  scope-aware;
- если таких полей ещё нет, используется legacy fallback по raw uid.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from core.logging import get_logger
from services.structure.models import ClauseNode, CrossReference

logger = get_logger(__name__)

_DEFAULT_SCOPE = "main_contract"
_UID_RE = r"\d+(?:\.\d+)*"

# Более аккуратный и расширяемый regex:
# - поддерживает RU/EN базовые формы;
# - выделяет target uid в именованную группу;
# - сохраняет matched text для explainability.
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
        return _DEFAULT_SCOPE
    scope = str(value).strip()
    return scope or _DEFAULT_SCOPE


def _normalize_uid(value: Any) -> str:
    return str(value or "").strip()


def _node_scope(node: ClauseNode) -> str:
    return _normalize_scope(getattr(node, "scope", None))


def _node_raw_uid(node: ClauseNode) -> str:
    raw_uid = _normalize_uid(getattr(node, "raw_uid", None))
    if raw_uid:
        return raw_uid
    return _normalize_uid(getattr(node, "clause_uid", None))


def _node_effective_uid(node: ClauseNode) -> str:
    effective_uid = _normalize_uid(getattr(node, "effective_uid", None))
    if effective_uid:
        return effective_uid

    scope = _node_scope(node)
    raw_uid = _node_raw_uid(node)

    if not raw_uid:
        return raw_uid
    if scope == _DEFAULT_SCOPE:
        return raw_uid
    return f"{scope}::{raw_uid}"


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
    dict[str, ClauseNode],
    dict[tuple[str, str], ClauseNode],
    dict[str, ClauseNode],
]:
    """
    Возвращает:
    - raw_uid_index: legacy raw_uid -> node
    - scoped_raw_index: (scope, raw_uid) -> node
    - effective_uid_index: effective_uid -> node
    """
    raw_uid_index: dict[str, ClauseNode] = {}
    scoped_raw_index: dict[tuple[str, str], ClauseNode] = {}
    effective_uid_index: dict[str, ClauseNode] = {}

    for legacy_key, node in nodes.items():
        raw_uid = _node_raw_uid(node) or _normalize_uid(legacy_key)
        scope = _node_scope(node)
        effective_uid = _node_effective_uid(node)

        if raw_uid and raw_uid not in raw_uid_index:
            raw_uid_index[raw_uid] = node

        if raw_uid:
            scoped_raw_index.setdefault((scope, raw_uid), node)

        if effective_uid:
            effective_uid_index.setdefault(effective_uid, node)

    return raw_uid_index, scoped_raw_index, effective_uid_index


def _resolve_target_node(
    *,
    source_node: ClauseNode,
    target_raw_uid: str,
    raw_uid_index: dict[str, ClauseNode],
    scoped_raw_index: dict[tuple[str, str], ClauseNode],
    effective_uid_index: dict[str, ClauseNode],
) -> tuple[ClauseNode | None, str]:
    """
    Разрешает target в порядке приоритета:

    1. exact same-scope raw uid
    2. exact effective uid for source scope
    3. legacy global raw uid fallback

    Возвращает:
    - target node или None
    - resolution_mode
    """
    source_scope = _node_scope(source_node)
    target_raw_uid = _normalize_uid(target_raw_uid)
    if not target_raw_uid:
        return None, "empty_target"

    same_scope = scoped_raw_index.get((source_scope, target_raw_uid))
    if same_scope is not None:
        return same_scope, "same_scope_raw_uid"

    if source_scope != _DEFAULT_SCOPE:
        effective_candidate = f"{source_scope}::{target_raw_uid}"
        by_effective = effective_uid_index.get(effective_candidate)
        if by_effective is not None:
            return by_effective, "same_scope_effective_uid"

    global_fallback = raw_uid_index.get(target_raw_uid)
    if global_fallback is not None:
        return global_fallback, "global_raw_uid_fallback"

    return None, "not_found"


def extract_references(
    elements: list[dict],
    element_to_uid: dict[str, str],
    nodes: dict[str, ClauseNode],
    *,
    document_id: str,
    stable_element_id_resolver: Callable[[dict[str, Any], int], str],
) -> list[CrossReference]:
    """
    Найти перекрёстные ссылки между клаузами.

    elements:
        layout-элементы (text_layout_raw.elements)
    element_to_uid:
        mapping element_id -> clause_uid, построенный при сборке дерева
    nodes:
        индекс ClauseNode по uid
    stable_element_id_resolver:
        функция/метод, превращающая элемент + индекс в стабильный element_id
        (обычно StructureBuilder._stable_element_id)

    Возвращает список CrossReference.

    Backward-compatible поведение:
    - если nodes содержат только legacy clause_uid без scope-атрибутов,
      работаем как раньше;
    - если node имеет scope/raw_uid/effective_uid, используем scope-aware resolution.
    """
    references: list[CrossReference] = []
    seen_refs: set[tuple[str, str, str]] = set()

    raw_uid_index, scoped_raw_index, effective_uid_index = _build_scope_indexes(nodes)

    logger.debug(
        "STRUCTURE crossrefs_index_built",
        extra={
            "document_id": document_id,
            "nodes_count": len(nodes),
            "raw_uid_index_count": len(raw_uid_index),
            "scoped_raw_index_count": len(scoped_raw_index),
            "effective_uid_index_count": len(effective_uid_index),
        },
    )

    for idx, el in enumerate(elements):
        try:
            text = str(el.get("text", "") or "")
            if not text.strip():
                continue

            stable_el_id = stable_element_id_resolver(el, idx)
            source_uid = _normalize_uid(element_to_uid.get(stable_el_id))
            if not source_uid:
                continue

            source_node = nodes.get(source_uid)
            if source_node is None:
                logger.debug(
                    "STRUCTURE crossref_source_node_missing",
                    extra={
                        "document_id": document_id,
                        "element_index": idx,
                        "stable_element_id": stable_el_id,
                        "source_uid": source_uid,
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
                    logger.debug(
                        "STRUCTURE crossref_target_not_resolved",
                        extra={
                            "document_id": document_id,
                            "element_index": idx,
                            "source_uid": source_uid,
                            "source_scope": source_scope,
                            "target_raw_uid": target_raw_uid,
                            "reference_text": match.group(),
                            "resolution_mode": resolution_mode,
                        },
                    )
                    continue

                target_uid = _normalize_uid(getattr(target_node, "clause_uid", None))
                target_scope = _node_scope(target_node)
                target_effective_uid = _node_effective_uid(target_node)

                if not target_uid or target_uid == source_uid:
                    continue

                key = (source_uid, target_uid, match.group())
                if key in seen_refs:
                    continue

                seen_refs.add(key)
                references.append(
                    CrossReference(
                        source_clause_uid=source_uid,
                        target_clause_uid=target_uid,
                        reference_text=match.group(),
                    )
                )

                logger.debug(
                    "STRUCTURE crossref_extracted",
                    extra={
                        "document_id": document_id,
                        "element_index": idx,
                        "stable_element_id": stable_el_id,
                        "source_uid": source_uid,
                        "source_raw_uid": source_raw_uid,
                        "source_effective_uid": source_effective_uid,
                        "source_scope": source_scope,
                        "target_uid": target_uid,
                        "target_raw_uid": _node_raw_uid(target_node),
                        "target_effective_uid": target_effective_uid,
                        "target_scope": target_scope,
                        "reference_text": match.group(),
                        "match_kind": _match_kind(match),
                        "resolution_mode": resolution_mode,
                    },
                )

        except Exception as e:
            logger.error(
                "STRUCTURE cross-ref unexpected error",
                extra={
                    "document_id": document_id,
                    "element_index": idx,
                    "error": str(e),
                },
            )
            continue

    logger.info(
        "STRUCTURE crossrefs_extraction_completed",
        extra={
            "document_id": document_id,
            "references_count": len(references),
            "elements_count": len(elements),
        },
    )

    return references

    

