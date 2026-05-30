# src/services/structure/crossrefs.py

"""
Извлечение перекрёстных ссылок между пунктами документа.

Phase 7 contract:
- canonical identity узла = effective_uid;
- source/target space = FrozenHierarchyNode.effective_uid;
- raw_uid используется только как номер внутри scope и для explainability;
- резолвинг выполняется scope-aware;
- output фазы = CrossReferenceGraph.

Важно:
- текущий публичный contract CrossReference / CrossReferenceGraph хранит
  только resolved references;
- unresolved / ambiguous случаи отражаются в stats и structured logging;
- nondeterministic resolution запрещён.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
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
_APPENDIX_LABEL_RE = r"(?:\d+|[A-ZА-Я]|[IVXLCDM]+)"

_APPENDIX_LOCATOR_RE = re.compile(
    rf"""
    (?:appendix|annex|schedule|exhibit|attachment|appendices|приложение)
    \s*
    (?:no\.?|№)?
    \s*
    (?P<label>{_APPENDIX_LABEL_RE})
    """,
    re.IGNORECASE | re.VERBOSE,
)

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
        (?:of|in|under|из|в|согласно|according\ to)
        \s+
        (?P<appendix_prefix>appendix|annex|schedule|exhibit|attachment|приложение)
        \s*
        (?:no\.?|№)?
        \s*
        (?P<appendix_label>{_APPENDIX_LABEL_RE})
    )
    |
    (?:
        (?P<appendix_only_prefix>appendix|annex|schedule|exhibit|attachment|приложение)
        \s*
        (?:no\.?|№)?
        \s*
        (?P<appendix_only_label>{_APPENDIX_LABEL_RE})
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


@dataclass(slots=True)
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
    target_appendix_label: str | None = None
    match_start: int = 0
    match_end: int = 0
    pattern_family: str = "unknown"



# ============================================================================
# Phase 7 public result types
# ============================================================================

@dataclass(frozen=True)
class UnresolvedStubRecord:
    """
    Запись об одном unresolved или ambiguous stub.

    Хранит контекст который логировался в debug-лог, но не попадал
    ни в CrossReferenceStats (там только счётчики), ни в CrossReference
    (там только resolved references).

    Используется в CrossRefAudit для structured diagnostics — например,
    для Phase 8 анализа паттернов unresolved ссылок.

    Поля:
    - source_effective_uid: откуда ссылка
    - reference_text: исходный текст ссылки
    - reference_kind: тип ссылки (clause/appendix/article и т.д.)
    - target_number: целевой номер который не удалось разрезолвить
    - target_scope_hint: подсказка по scope (если была)
    - target_appendix_label: метка appendix (если была)
    - resolution_mode: причина failure (not_found / ambiguous_global_raw_uid и т.д.)
    - pattern_family: семейство паттерна (simple / appendix_scoped / appendix_only)
    - is_ambiguous: True если ambiguous, False если unresolved
    """

    source_effective_uid: str
    reference_text: str
    reference_kind: str
    target_number: str
    resolution_mode: str
    pattern_family: str
    target_scope_hint: str | None = None
    target_appendix_label: str | None = None
    is_ambiguous: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_effective_uid": self.source_effective_uid,
            "reference_text": self.reference_text,
            "reference_kind": self.reference_kind,
            "target_number": self.target_number,
            "resolution_mode": self.resolution_mode,
            "pattern_family": self.pattern_family,
            "target_scope_hint": self.target_scope_hint,
            "target_appendix_label": self.target_appendix_label,
            "is_ambiguous": self.is_ambiguous,
        }


@dataclass(frozen=True)
class CrossRefAudit:
    """
    Audit-артефакт Phase 7: детальные записи об unresolved и ambiguous ссылках.

    Дополняет CrossReferenceStats (счётчики) структурированными деталями
    о каждом конкретном случае который не удалось разрезолвить.

    CrossReferenceStats содержит: счётчики (unresolved_count, ambiguous_count и т.д.)
    CrossRefAudit содержит: конкретные записи с контекстом для diagnostics.

    Поля:
    - unresolved_records: записи об unresolved stubs (target не найден)
    - ambiguous_records: записи об ambiguous stubs (несколько кандидатов)
    - skipped_self_refs: количество пропущенных self-references
    - toc_like_skipped: количество пропущенных TOC-like элементов
    """

    unresolved_records: tuple[UnresolvedStubRecord, ...] = ()
    ambiguous_records: tuple[UnresolvedStubRecord, ...] = ()
    skipped_self_refs: int = 0
    toc_like_skipped: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "unresolved_count": len(self.unresolved_records),
            "ambiguous_count": len(self.ambiguous_records),
            "unresolved_records": [r.to_dict() for r in self.unresolved_records],
            "ambiguous_records": [r.to_dict() for r in self.ambiguous_records],
            "skipped_self_refs": self.skipped_self_refs,
            "toc_like_skipped": self.toc_like_skipped,
        }


@dataclass(frozen=True)
class CrossRefExtractionResult:
    """
    Typed результат Phase 7 — graph + audit.

    graph: CrossReferenceGraph — immutable resolved references graph со stats.
           Контракт graph не изменился — backward compatible.

    audit: CrossRefAudit — structured diagnostics по unresolved/ambiguous cases.
           Раньше эти данные были только в debug-логах.

    Используй build_cross_reference_graph_with_audit(...) чтобы получить этот тип.
    Используй build_cross_reference_graph(...) для backward compat (возвращает только graph).
    """

    graph: CrossReferenceGraph
    audit: CrossRefAudit

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph": self.graph.to_dict(),
            "audit": self.audit.to_dict(),
        }


def _normalize_scope(value: Any) -> str:
    if value is None:
        return DEFAULT_SCOPE
    scope = str(value).strip()
    return scope or DEFAULT_SCOPE


def _normalize_uid(value: Any) -> str:
    return str(value or "").strip()


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_appendix_label(value: Any) -> str:
    label = _normalize_text(value).upper()
    return label


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


def _node_title(node: FrozenHierarchyNode) -> str:
    return _normalize_text(getattr(node, "title", None))


def _looks_like_appendix_scope(scope: str) -> bool:
    s = _normalize_scope(scope).lower()
    return (
        s.startswith("appendix")
        or s.startswith("приложение")
        or s.startswith("annex")
        or s.startswith("schedule")
        or s.startswith("exhibit")
        or s.startswith("attachment")
    )


def _looks_like_toc_element(el: dict[str, Any]) -> bool:
    element_type = str(el.get("element_type") or "").strip().lower()
    return element_type in {
        "toc_header",
        "toc_line",
    }


def _looks_like_possible_toc_element(el: dict[str, Any]) -> bool:
    element_type = str(el.get("element_type") or "").strip().lower()
    return element_type == "possible_toc"


def _looks_like_noise_element(el: dict[str, Any]) -> bool:
    element_type = str(el.get("element_type") or "").strip().lower()
    return element_type in {
        "signature_block",
        "requisites_block",
        "page_artifact",
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


def _appendix_stub_priority(stub: _CrossRefStub) -> tuple[int, int, int]:
    family_rank = 0
    if stub.pattern_family == "appendix_scoped":
        family_rank = 3
    elif stub.pattern_family == "appendix_only":
        family_rank = 2
    elif stub.pattern_family == "simple":
        family_rank = 1

    span_len = max(0, stub.match_end - stub.match_start)
    return (stub.match_start, -family_rank, -span_len)


def _stubs_overlap(left: _CrossRefStub, right: _CrossRefStub) -> bool:
    return not (left.match_end <= right.match_start or right.match_end <= left.match_start)


def _select_non_overlapping_stubs(stubs: list[_CrossRefStub]) -> list[_CrossRefStub]:
    if not stubs:
        return []

    ordered = sorted(stubs, key=_appendix_stub_priority)
    selected: list[_CrossRefStub] = []

    for stub in ordered:
        overlaps = False
        for existing in selected:
            if _stubs_overlap(stub, existing):
                overlaps = True
                break
        if not overlaps:
            selected.append(stub)

    selected.sort(key=lambda item: (item.match_start, item.match_end))
    return selected


def _extract_appendix_locator_from_text(text: str) -> str | None:
    if not text:
        return None
    match = _APPENDIX_LOCATOR_RE.search(text)
    if not match:
        return None
    return _normalize_appendix_label(match.group("label")) or None


def _extract_appendix_locator_from_node(node: FrozenHierarchyNode) -> str | None:
    raw_uid = _node_raw_uid(node)
    if raw_uid:
        normalized_raw = _normalize_appendix_label(raw_uid)
        if normalized_raw:
            return normalized_raw

    effective_uid = _node_effective_uid(node)
    try:
        _, eff_raw = split_effective_uid(effective_uid)
        normalized_eff_raw = _normalize_appendix_label(eff_raw)
        if normalized_eff_raw:
            return normalized_eff_raw
    except Exception:
        pass

    title = _node_title(node)
    locator_from_title = _extract_appendix_locator_from_text(title)
    if locator_from_title:
        return locator_from_title

    scope = _node_scope(node)
    locator_from_scope = _extract_appendix_locator_from_text(scope)
    if locator_from_scope:
        return locator_from_scope

    tail_token = re.search(r"([A-Za-zА-Яа-я0-9IVXLCDM]+)$", scope, flags=re.IGNORECASE)
    if tail_token:
        normalized_tail = _normalize_appendix_label(tail_token.group(1))
        if normalized_tail:
            return normalized_tail

    return None


def _build_scope_indexes(
    nodes: dict[str, FrozenHierarchyNode],
    *,
    document_id: str,
    counters: _ExtractionCounters,
) -> tuple[
    dict[str, list[FrozenHierarchyNode]],
    dict[tuple[str, str], FrozenHierarchyNode],
    dict[str, FrozenHierarchyNode],
    dict[str, tuple[str, ...]],
]:
    raw_uid_index: dict[str, list[FrozenHierarchyNode]] = {}
    scoped_raw_index: dict[tuple[str, str], FrozenHierarchyNode] = {}
    effective_uid_index: dict[str, FrozenHierarchyNode] = {}
    appendix_scope_temp: dict[str, set[str]] = {}

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

            appendix_locator = _extract_appendix_locator_from_node(node)
            if appendix_locator and _looks_like_appendix_scope(scope):
                appendix_scope_temp.setdefault(appendix_locator, set()).add(scope)

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

    appendix_scope_index = {
        locator: tuple(sorted(scopes))
        for locator, scopes in sorted(appendix_scope_temp.items())
    }

    return raw_uid_index, scoped_raw_index, effective_uid_index, appendix_scope_index


def _extract_crossref_stubs(
    *,
    text: str,
    source_effective_uid: str,
    source_scope: str,
    source_raw_uid: str,
) -> list[_CrossRefStub]:
    raw_stubs: list[_CrossRefStub] = []

    for match in _CROSS_REF_APPENDIX_SCOPED.finditer(text):
        appendix_label = _normalize_appendix_label(
            match.group("appendix_label") or match.group("appendix_only_label")
        )
        item_uid = _normalize_uid(match.group("item_uid"))
        prefix = _normalize_text(
            match.group("item_prefix")
            or match.group("appendix_prefix")
            or match.group("appendix_only_prefix")
        )
        ref_text = _normalize_text(match.group())
        kind = "appendix" if not item_uid else _match_kind_from_prefix(prefix)
        pattern_family = "appendix_only" if not item_uid else "appendix_scoped"

        raw_stubs.append(
            _CrossRefStub(
                source_effective_uid=source_effective_uid,
                source_scope=source_scope,
                source_raw_uid=source_raw_uid,
                reference_text=ref_text,
                reference_kind=kind,
                target_number=item_uid or appendix_label,
                target_scope_hint="appendix",
                target_appendix_label=appendix_label,
                match_start=match.start(),
                match_end=match.end(),
                pattern_family=pattern_family,
            )
        )

    for match in _CROSS_REF_SIMPLE.finditer(text):
        ref_text = _normalize_text(match.group())
        prefix = _normalize_text(match.group("ru_prefix") or match.group("en_prefix"))
        target_number = _normalize_uid(match.group("ru_target") or match.group("en_target"))

        raw_stubs.append(
            _CrossRefStub(
                source_effective_uid=source_effective_uid,
                source_scope=source_scope,
                source_raw_uid=source_raw_uid,
                reference_text=ref_text,
                reference_kind=_match_kind_from_prefix(prefix),
                target_number=target_number,
                target_scope_hint=None,
                target_appendix_label=None,
                match_start=match.start(),
                match_end=match.end(),
                pattern_family="simple",
            )
        )

    return _select_non_overlapping_stubs(raw_stubs)


def _resolve_target_node(
    *,
    source_node: FrozenHierarchyNode,
    stub: _CrossRefStub,
    raw_uid_index: dict[str, list[FrozenHierarchyNode]],
    scoped_raw_index: dict[tuple[str, str], FrozenHierarchyNode],
    effective_uid_index: dict[str, FrozenHierarchyNode],
    appendix_scope_index: dict[str, tuple[str, ...]],
) -> tuple[FrozenHierarchyNode | None, str]:
    source_scope = _node_scope(source_node)
    normalized_target_raw_uid = _normalize_uid(stub.target_number)
    if not normalized_target_raw_uid:
        return None, "empty_target"

    if stub.target_scope_hint == "appendix" and stub.target_appendix_label:
        appendix_scopes = appendix_scope_index.get(_normalize_appendix_label(stub.target_appendix_label), ())
        if not appendix_scopes:
            return None, "appendix_scope_not_found"
        if len(appendix_scopes) > 1:
            return None, "appendix_scope_ambiguous"

        appendix_scope = appendix_scopes[0]

        if stub.reference_kind == "appendix" and normalized_target_raw_uid == _normalize_appendix_label(stub.target_appendix_label):
            appendix_scope_root = scoped_raw_index.get((appendix_scope, normalized_target_raw_uid))
            if appendix_scope_root is not None:
                return appendix_scope_root, "appendix_scope_exact_raw_uid"

            appendix_scope_effective = effective_uid_index.get(
                make_effective_uid(appendix_scope, normalized_target_raw_uid)
            )
            if appendix_scope_effective is not None:
                return appendix_scope_effective, "appendix_scope_exact_effective_uid"

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
        appendix_scoped_resolved_count=counters.appendix_scoped_resolved_count,
        appendix_scope_miss_count=counters.appendix_scope_miss_count,
        toc_like_reference_skipped_count=counters.toc_like_reference_skipped_count,
    )


def _sort_references_deterministically(
    references: list[CrossReference],
) -> list[CrossReference]:
    return sorted(
        references,
        key=lambda ref: (
            ref.source_effective_uid,
            ref.match_start if ref.match_start is not None else -1,
            ref.match_end if ref.match_end is not None else -1,
            ref.target_effective_uid,
            ref.reference_kind,
            ref.reference_text,
            ref.pattern_family or "",
        ),
    )


def build_cross_reference_graph_with_audit(
    elements: list[dict[str, Any]],
    element_to_effective_uid: dict[str, str],
    nodes: dict[str, FrozenHierarchyNode],
    *,
    document_id: str,
    stable_element_id_resolver: Callable[[dict[str, Any], int], str],
) -> CrossRefExtractionResult:
    """
    Расширенный Phase 7 entrypoint — возвращает graph + structured audit.

    Выполняет всю ту же логику что build_cross_reference_graph,
    дополнительно собирая UnresolvedStubRecord для каждого
    unresolved и ambiguous stub.

    Внутренняя логика (indexing, extraction, resolution) не изменена.
    Audit записи строятся из тех же данных что раньше шли только в debug-лог.

    Используй этот entrypoint в новом коде.
    Используй build_cross_reference_graph для backward compat.
    """
    normalized_document_id = _normalize_text(document_id)
    if not normalized_document_id:
        raise ValueError("document_id must be non-empty")

    references: list[CrossReference] = []
    seen_refs: set[tuple[str, str, str, str, int, int]] = set()
    counters = _ExtractionCounters()

    # Audit accumulators — собираем записи об unresolved/ambiguous
    unresolved_records: list[UnresolvedStubRecord] = []
    ambiguous_records: list[UnresolvedStubRecord] = []

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

            if _looks_like_noise_element(el):
                continue

            if _looks_like_possible_toc_element(el):
                text_probe = _normalize_text(el.get("text", ""))
                if _APPENDIX_LOCATOR_RE.search(text_probe) or re.search(rf"\b{_UID_RE}\b", text_probe):
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
                    is_ambiguous = resolution_mode in {
                        "ambiguous_global_raw_uid",
                        "appendix_scope_ambiguous",
                    }

                    if is_ambiguous:
                        counters.ambiguous_count += 1
                    else:
                        counters.unresolved_count += 1
                        if resolution_mode == "appendix_scope_not_found":
                            counters.appendix_scope_miss_count += 1

                    # Строим audit запись — тот же контекст что шёл в debug-лог,
                    # но теперь сохраняется как structured artifact.
                    record = UnresolvedStubRecord(
                        source_effective_uid=source_effective_uid,
                        reference_text=stub.reference_text,
                        reference_kind=stub.reference_kind,
                        target_number=target_raw_uid,
                        resolution_mode=resolution_mode,
                        pattern_family=stub.pattern_family,
                        target_scope_hint=stub.target_scope_hint,
                        target_appendix_label=stub.target_appendix_label,
                        is_ambiguous=is_ambiguous,
                    )

                    if is_ambiguous:
                        ambiguous_records.append(record)
                    else:
                        unresolved_records.append(record)

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
                            "target_appendix_label": stub.target_appendix_label,
                            "resolution_mode": resolution_mode,
                            "match_start": stub.match_start,
                            "match_end": stub.match_end,
                            "pattern_family": stub.pattern_family,
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
                key = (
                    source_effective_uid,
                    target_effective_uid,
                    reference_text,
                    stable_el_id,
                    stub.match_start,
                    stub.match_end,
                )
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
                        match_start=stub.match_start,
                        match_end=stub.match_end,
                        pattern_family=stub.pattern_family,
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
                        "target_appendix_label": stub.target_appendix_label,
                        "resolution_mode": resolution_mode,
                        "match_start": stub.match_start,
                        "match_end": stub.match_end,
                        "pattern_family": stub.pattern_family,
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

    references = _sort_references_deterministically(references)
    stats = _build_stats(references=references, counters=counters)
    graph = CrossReferenceGraph.from_references(
        document_id=normalized_document_id,
        references=references,
        stats=stats,
    )

    audit = CrossRefAudit(
        unresolved_records=tuple(unresolved_records),
        ambiguous_records=tuple(ambiguous_records),
        skipped_self_refs=counters.skipped_self_reference_count,
        toc_like_skipped=counters.toc_like_reference_skipped_count,
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

    return CrossRefExtractionResult(graph=graph, audit=audit)



def build_cross_reference_graph(
    elements: list[dict[str, Any]],
    element_to_effective_uid: dict[str, str],
    nodes: dict[str, FrozenHierarchyNode],
    *,
    document_id: str,
    stable_element_id_resolver: Callable[[dict[str, Any], int], str],
) -> CrossReferenceGraph:
    """
    Backward-compatible entrypoint Phase 7.

    Возвращает только CrossReferenceGraph без audit.
    Вся логика делегируется в build_cross_reference_graph_with_audit.

    Используй build_cross_reference_graph_with_audit если нужны
    structured diagnostics по unresolved/ambiguous cases.
    """
    result = build_cross_reference_graph_with_audit(
        elements,
        element_to_effective_uid,
        nodes,
        document_id=document_id,
        stable_element_id_resolver=stable_element_id_resolver,
    )
    return result.graph

