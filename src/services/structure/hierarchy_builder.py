# src/services/structure/hierarchy_builder.py

"""
Сборка иерархии ClauseTree из уже отфильтрованных heading candidates.

Архитектурная роль модуля:
- не парсить заголовки;
- не принимать accepted/rejected решения;
- не искать TOC;
- не выполнять LLM-refinement;
- только собирать scope-aware дерево ClauseNode из уже принятых heading candidates
  и layout elements.

Контракт входных heading candidates:
- сюда попадают только уже accepted headings;
- каждый heading обязан иметь:
  - elem_i
  - page
  - title
  - scope
  - raw_uid или uid
  - effective_uid желательно уже готовый, но при отсутствии будет вычислен.

Контракт возврата build_clause_hierarchy():
- root_nodes: список корневых узлов дерева;
- nodes: глобальный индекс effective_uid -> ClauseNode;
- element_to_effective_uid: stable_element_id -> effective_uid;
- structure_degraded: bool, true если обнаружены опасные structural anomalies.

Clean-break contract:
- canonical identity узла = effective_uid в формате "<scope>::<raw_uid>";
- parent lookup выполняется только внутри того же scope;
- глобальный индекс nodes хранится как effective_uid -> ClauseNode;
- никакого legacy fallback на raw-only canonical ids;
- invalid/incomplete heading candidates не "лечатся", а честно пропускаются с diagnostics/logs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from core.logging import get_logger
from services.structure.models import (
    ClauseNode,
    DEFAULT_SCOPE,
    make_effective_uid,
    split_effective_uid,
)

logger = get_logger(__name__)

_NUMERIC_UID_RE = re.compile(r"^\d+(?:\.\d+)*$")

_SUSPICIOUS_LEAF_RANGE_SPAN_THRESHOLD = 200
_SUSPICIOUS_OWN_SHARE_RATIO = 0.8

# Этап 1: recoverable hierarchy
_RECOVERABLE_INVALID_HEADING_RATIO = 0.35
_RECOVERABLE_OWN_RANGE_ANOMALY_RATIO = 0.35
_FATAL_ROOTLESS_WITH_NODES = True


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def _is_strict_numeric_uid(uid: str) -> bool:
    """
    Надёжная проверка числового uid.

    Поддерживаемые примеры:
    - "1"
    - "1.2"
    - "3.1.4"

    Не считаются валидными:
    - "1."
    - ".2"
    - "1..2"
    - "A.1"
    """
    return bool(_NUMERIC_UID_RE.fullmatch((uid or "").strip()))


def _normalize_scope(value: Any) -> str:
    if value is None:
        return DEFAULT_SCOPE
    scope = str(value).strip()
    return scope or DEFAULT_SCOPE


def _normalize_uid(value: Any) -> str:
    return str(value or "").strip()


def _normalize_title(value: Any) -> str:
    return str(value or "").strip()


def _effective_uid_from_scope(scope: str, raw_uid: str) -> str:
    scope = _normalize_scope(scope)
    raw_uid = _normalize_uid(raw_uid)
    if not raw_uid:
        raise ValueError("raw_uid must be non-empty to build effective_uid")
    return make_effective_uid(scope, raw_uid)


@dataclass(slots=True)
class HeadingCandidate:
    """
    Минимальный входной тип для hierarchy assembly.
    """

    elem_i: int
    uid: str
    title: str
    page: int
    scope: str | None = None
    raw_uid: str | None = None
    effective_uid: str | None = None


@dataclass(slots=True)
class OwnRangeComputation:
    """
    Результат вычисления own-диапазона узла.
    """

    start_elem_i: int
    end_elem_i: int | None
    range_end_reason: str


def _heading_scope(heading: HeadingCandidate) -> str:
    return _normalize_scope(getattr(heading, "scope", None))


def _heading_raw_uid(heading: HeadingCandidate) -> str:
    raw_uid = _normalize_uid(getattr(heading, "raw_uid", None))
    if raw_uid:
        return raw_uid
    return _normalize_uid(getattr(heading, "uid", None))


def _heading_effective_uid(heading: HeadingCandidate) -> str:
    explicit = _normalize_uid(getattr(heading, "effective_uid", None))
    if explicit:
        scope, raw_uid = split_effective_uid(explicit)
        return make_effective_uid(scope, raw_uid)
    return _effective_uid_from_scope(_heading_scope(heading), _heading_raw_uid(heading))


def level_from_uid(uid: str) -> int:
    """
    Глубина numeric uid по количеству уровней.
    """
    normalized = _normalize_uid(uid)
    if not _is_strict_numeric_uid(normalized):
        raise ValueError(f"level_from_uid expects strict numeric uid, got {uid!r}")
    return normalized.count(".") + 1


def find_parent_raw_uid_within_scope(
    raw_uid: str,
    nodes_by_raw_uid: dict[str, ClauseNode],
) -> str | None:
    """
    Ищет ближайшего существующего родителя по raw uid-цепочке
    только внутри одного scope.

    Пример:
    - "1.2.3" -> пробуем "1.2", затем "1"
    """
    raw_uid = _normalize_uid(raw_uid)
    if not raw_uid or "." not in raw_uid:
        return None

    parts = raw_uid.split(".")
    for i in range(len(parts) - 1, 0, -1):
        candidate = ".".join(parts[:i])
        if candidate in nodes_by_raw_uid:
            return candidate

    return None


def _collect_own_text(
    elements: list[dict[str, Any]],
    start_elem_i: int,
    end_elem_i: int,
) -> str:
    """
    Собирает нормализованный текст элементов layout, принадлежащих только этому узлу.
    """
    parts: list[str] = []
    upper_bound = min(end_elem_i, len(elements))
    for j in range(max(start_elem_i, 0), upper_bound):
        text = (elements[j].get("text") or "").strip()
        if text:
            parts.append(text)
    return " ".join(parts)


def _group_headings_by_scope(
    headings: list[HeadingCandidate],
) -> dict[str, list[HeadingCandidate]]:
    """
    Группирует headings по scope и сортирует внутри scope по elem_i.
    """
    grouped: dict[str, list[HeadingCandidate]] = {}
    for heading in headings:
        scope = _heading_scope(heading)
        grouped.setdefault(scope, []).append(heading)

    for scope in grouped:
        grouped[scope].sort(key=lambda h: (int(h.elem_i), int(h.page)))

    return grouped


def _build_scope_boundaries(
    elements: list[dict[str, Any]],
) -> dict[str, tuple[int, int]]:
    """
    Возвращает для каждого scope диапазон элементов [start, end),
    в котором живёт этот scope.

    Если scope встречается несколькими непрерывными кусками, берём
    минимальный start и максимальный end. Для текущего контракта это safe bound.
    """
    bounds: dict[str, list[int]] = {}

    for idx, element in enumerate(elements):
        scope = _normalize_scope(element.get("scope"))
        if scope not in bounds:
            bounds[scope] = [idx, idx + 1]
        else:
            bounds[scope][1] = idx + 1

    return {scope: (start, end) for scope, (start, end) in bounds.items()}


def _build_heading_positions(
    headings: list[HeadingCandidate],
) -> tuple[dict[tuple[str, str], int], dict[tuple[str, str], int]]:
    """
    Строит две служебные карты по ключу (scope, raw_uid):
    1. key_to_elem_i
    2. key_to_heading_index

    duplicate keys не допускаются на этом уровне silently:
    сохраняем первое вхождение, остальное будет диагностироваться выше.
    """
    key_to_elem_i: dict[tuple[str, str], int] = {}
    key_to_heading_index: dict[tuple[str, str], int] = {}

    for idx, heading in enumerate(headings):
        raw_uid = _heading_raw_uid(heading)
        if not raw_uid:
            continue

        scope = _heading_scope(heading)
        key = (scope, raw_uid)

        if key not in key_to_elem_i:
            key_to_elem_i[key] = int(heading.elem_i)
            key_to_heading_index[key] = idx

    return key_to_elem_i, key_to_heading_index


def _find_first_child_elem_i(
    node: ClauseNode,
    key_to_elem_i: dict[tuple[str, str], int],
    scope: str,
) -> int | None:
    """
    Найти позицию первого прямого дочернего заголовка этого узла в том же scope.
    """
    first_child_elem_i: int | None = None

    for child in node.children:
        child_raw_uid = _normalize_uid(child.raw_uid)
        if not child_raw_uid:
            continue

        child_key = (scope, child_raw_uid)
        child_elem_i = key_to_elem_i.get(child_key)
        if child_elem_i is None:
            continue

        if first_child_elem_i is None or child_elem_i < first_child_elem_i:
            first_child_elem_i = child_elem_i

    return first_child_elem_i


def _find_next_same_or_higher_level_elem_i(
    *,
    raw_uid: str,
    node_level: int,
    scope: str,
    headings: list[HeadingCandidate],
    key_to_heading_index: dict[tuple[str, str], int],
) -> int | None:
    """
    Найти elem_i следующего заголовка того же или более высокого уровня
    в пределах того же scope.
    """
    key = (scope, raw_uid)
    idx = key_to_heading_index.get(key)
    if idx is None:
        return None

    for heading in headings[idx + 1:]:
        if _heading_scope(heading) != scope:
            continue

        heading_raw_uid = _heading_raw_uid(heading)
        if not heading_raw_uid:
            continue

        heading_level = level_from_uid(heading_raw_uid) if _is_strict_numeric_uid(heading_raw_uid) else 1
        if heading_level <= node_level:
            return int(heading.elem_i)

    return None


def _compute_own_range(
    *,
    raw_uid: str,
    node: ClauseNode,
    headings: list[HeadingCandidate],
    elements: list[dict[str, Any]],
    key_to_elem_i: dict[tuple[str, str], int],
    key_to_heading_index: dict[tuple[str, str], int],
    scope: str,
    scope_boundaries: dict[str, tuple[int, int]],
) -> OwnRangeComputation:
    """
    Вычислить own-диапазон для узла в пределах того же scope.

    Правильное правило:
    - own начинается с elem_i текущего заголовка;
    - own заканчивается на первом из событий:
      1) первый дочерний заголовок;
      2) следующий заголовок того же или более высокого уровня;
      3) конец текущего scope/сегмента;
      4) fallback_boundary, если scope boundary неизвестен.
    """
    key = (scope, raw_uid)
    heading_elem_i = key_to_elem_i.get(key)

    if heading_elem_i is None:
        return OwnRangeComputation(
            start_elem_i=-1,
            end_elem_i=None,
            range_end_reason="unbounded_error",
        )

    next_same_or_higher = _find_next_same_or_higher_level_elem_i(
        raw_uid=raw_uid,
        node_level=node.level,
        scope=scope,
        headings=headings,
        key_to_heading_index=key_to_heading_index,
    )

    first_child_elem_i = _find_first_child_elem_i(node, key_to_elem_i, scope)

    candidates: list[tuple[int, str]] = []
    if first_child_elem_i is not None and first_child_elem_i > heading_elem_i:
        candidates.append((first_child_elem_i, "first_child"))
    if next_same_or_higher is not None and next_same_or_higher > heading_elem_i:
        candidates.append((next_same_or_higher, "next_same_or_higher"))

    scope_boundary = scope_boundaries.get(scope)
    if scope_boundary is not None and scope_boundary[1] > heading_elem_i:
        candidates.append((scope_boundary[1], "segment_end"))
    elif len(elements) > heading_elem_i:
        candidates.append((len(elements), "fallback_boundary"))

    if not candidates:
        scope_boundary = scope_boundaries.get(scope)
        if scope_boundary is not None and scope_boundary[1] > heading_elem_i:
            return OwnRangeComputation(
                start_elem_i=heading_elem_i,
                end_elem_i=scope_boundary[1],
                range_end_reason="segment_end",
            )

        if len(elements) > heading_elem_i:
            return OwnRangeComputation(
                start_elem_i=heading_elem_i,
                end_elem_i=len(elements),
                range_end_reason="fallback_boundary",
            )

        return OwnRangeComputation(
            start_elem_i=heading_elem_i,
            end_elem_i=None,
            range_end_reason="unbounded_error",
        )

    end_elem_i, reason = min(candidates, key=lambda item: item[0])

    return OwnRangeComputation(
        start_elem_i=heading_elem_i,
        end_elem_i=end_elem_i,
        range_end_reason=reason,
    )


def _walk_postorder(node: ClauseNode):
    """
    Реальный bottom-up обход дерева.
    """
    for child in node.children:
        yield from _walk_postorder(child)
    yield node


def build_clause_hierarchy(
    headings: list[HeadingCandidate],
    elements: list[dict[str, Any]],
    *,
    document_id: str,
    stable_element_id_resolver: Callable[[dict[str, Any], int], str],
) -> tuple[list[ClauseNode], dict[str, ClauseNode], dict[str, str], bool]:
    """
    Построить scope-aware ClauseNode-дерево и индекс element_id -> effective_uid.

    Возвращает:
    - root_nodes
    - nodes
    - element_to_effective_uid
    - structure_degraded
    """
    normalized_document_id = str(document_id or "").strip()

    nodes: dict[str, ClauseNode] = {}
    root_nodes: list[ClauseNode] = []
    element_to_effective_uid: dict[str, str] = {}

    if not headings:
        return root_nodes, nodes, element_to_effective_uid, False

    scope_stats: dict[str, int] = {}
    own_range_invalid_count = 0
    own_range_missing_count = 0
    duplicate_effective_uid_skipped_count = 0
    duplicate_scope_raw_uid_skipped_count = 0
    suspicious_leaf_nodes_count = 0
    element_ownership_conflicts = 0
    invalid_heading_candidates_count = 0
    parent_attach_rejected_count = 0

    headings_by_scope = _group_headings_by_scope(headings)
    scope_boundaries = _build_scope_boundaries(elements)

    for scope, scope_headings in headings_by_scope.items():
        scope_stats[scope] = len(scope_headings)

    logger.debug(
        "STRUCTURE hierarchy_build_scopes",
        extra={
            "document_id": normalized_document_id,
            "scope_stats": scope_stats,
            "scope_boundaries": scope_boundaries,
        },
    )

    key_to_elem_i, key_to_heading_index = _build_heading_positions(headings)

    nodes_by_scope: dict[str, dict[str, ClauseNode]] = {}

    for scope, scope_headings in headings_by_scope.items():
        scope_nodes = nodes_by_scope.setdefault(scope, {})

        for local_idx, heading in enumerate(scope_headings):
            try:
                elem_i = int(heading.elem_i)
                raw_uid = _heading_raw_uid(heading)
                effective_uid = _heading_effective_uid(heading)
                title = _normalize_title(heading.title)
                page = int(heading.page)

                if elem_i < 0:
                    raise ValueError("elem_i must be >= 0")
                if page < 1:
                    raise ValueError("page must be >= 1")
                if not raw_uid:
                    raise ValueError("raw_uid must be non-empty")
                if not effective_uid:
                    raise ValueError("effective_uid must be non-empty")

                inferred_scope, inferred_raw_uid = split_effective_uid(effective_uid)
                if inferred_scope != scope:
                    raise ValueError(
                        f"heading scope mismatch: heading.scope={scope!r}, "
                        f"effective_uid implies {inferred_scope!r}"
                    )
                if inferred_raw_uid != raw_uid:
                    raise ValueError(
                        f"heading raw_uid mismatch: raw_uid={raw_uid!r}, "
                        f"effective_uid implies {inferred_raw_uid!r}"
                    )

                if raw_uid in scope_nodes:
                    duplicate_scope_raw_uid_skipped_count += 1
                    logger.warning(
                        "STRUCTURE node_duplicate_scope_raw_uid_skipped",
                        extra={
                            "document_id": normalized_document_id,
                            "raw_uid": raw_uid,
                            "effective_uid": effective_uid,
                            "title": title,
                            "page": page,
                            "elem_i": elem_i,
                            "scope": scope,
                            "reason": "duplicate_raw_uid_within_same_scope",
                        },
                    )
                    continue

                if effective_uid in nodes:
                    duplicate_effective_uid_skipped_count += 1
                    logger.warning(
                        "STRUCTURE node_duplicate_effective_uid_skipped",
                        extra={
                            "document_id": normalized_document_id,
                            "raw_uid": raw_uid,
                            "effective_uid": effective_uid,
                            "title": title,
                            "page": page,
                            "elem_i": elem_i,
                            "scope": scope,
                            "reason": "duplicate_canonical_id",
                        },
                    )
                    continue

                next_elem_i = (
                    int(scope_headings[local_idx + 1].elem_i)
                    if local_idx + 1 < len(scope_headings)
                    else scope_boundaries.get(scope, (0, len(elements)))[1]
                )

                if next_elem_i > elem_i and next_elem_i - 1 < len(elements):
                    end_page = int(elements[next_elem_i - 1].get("page", page) or page)
                else:
                    end_page = page

                numeric_uid = _is_strict_numeric_uid(raw_uid)
                level = level_from_uid(raw_uid) if numeric_uid else 1

                node = ClauseNode(
                    effective_uid=effective_uid,
                    raw_uid=raw_uid,
                    scope=scope,
                    title=title,
                    level=level,
                    node_kind="leaf",
                    own_element_ids=[],
                    subtree_element_ids=[],
                    own_text=None,
                    subtree_text=None,
                    start_page=page,
                    end_page=end_page,
                    children=[],
                    range_end_reason=None,
                    diagnostics={},
                )

                nodes[effective_uid] = node
                scope_nodes[raw_uid] = node

                logger.debug(
                    "structure.node.created",
                    extra={
                        "document_id": normalized_document_id,
                        "raw_uid": raw_uid,
                        "effective_uid": effective_uid,
                        "title": node.title,
                        "level": node.level,
                        "own_count": 0,
                        "own_text_len": 0,
                        "start_page": node.start_page,
                        "end_page": node.end_page,
                        "heading_elem_i": elem_i,
                        "next_heading_elem_i": next_elem_i,
                        "numeric_uid": numeric_uid,
                        "scope": scope,
                    },
                )

                parent_uid = find_parent_raw_uid_within_scope(raw_uid, scope_nodes)

                if parent_uid and parent_uid in scope_nodes:
                    parent_node = scope_nodes[parent_uid]

                    if parent_node.level >= node.level:
                        parent_attach_rejected_count += 1
                        node.diagnostics["parent_attach_status"] = "rejected_invalid_parent_level"
                        node.diagnostics["requested_parent_raw_uid"] = parent_uid
                        root_nodes.append(node)

                        logger.warning(
                            "STRUCTURE node_parent_attach_rejected",
                            extra={
                                "document_id": normalized_document_id,
                                "raw_uid": raw_uid,
                                "effective_uid": effective_uid,
                                "parent_uid": parent_uid,
                                "parent_effective_uid": parent_node.effective_uid,
                                "parent_level": parent_node.level,
                                "child_level": node.level,
                                "scope": scope,
                                "reason": "invalid_parent_level",
                            },
                        )
                    else:
                        parent_node.children.append(node)
                        node.diagnostics["parent_attach_status"] = "attached"

                        logger.debug(
                            "structure.node.parenting",
                            extra={
                                "document_id": normalized_document_id,
                                "raw_uid": raw_uid,
                                "effective_uid": effective_uid,
                                "parent_uid": parent_uid,
                                "parent_effective_uid": parent_node.effective_uid,
                                "level": node.level,
                                "attached_to_root": False,
                                "scope": scope,
                            },
                        )
                else:
                    node.diagnostics["parent_attach_status"] = "root"
                    root_nodes.append(node)

                    logger.debug(
                        "structure.node.parenting",
                        extra={
                            "document_id": normalized_document_id,
                            "raw_uid": raw_uid,
                            "effective_uid": effective_uid,
                            "parent_uid": None,
                            "parent_effective_uid": None,
                            "level": node.level,
                            "attached_to_root": True,
                            "scope": scope,
                        },
                    )

            except Exception as exc:
                invalid_heading_candidates_count += 1
                logger.warning(
                    "STRUCTURE invalid_heading_candidate_skipped",
                    extra={
                        "document_id": normalized_document_id,
                        "scope": scope,
                        "elem_i": getattr(heading, "elem_i", None),
                        "page": getattr(heading, "page", None),
                        "raw_uid": getattr(heading, "raw_uid", None),
                        "uid": getattr(heading, "uid", None),
                        "effective_uid": getattr(heading, "effective_uid", None),
                        "title": getattr(heading, "title", None),
                        "error": str(exc),
                    },
                )
                continue

    for heading in headings:
        try:
            raw_uid = _heading_raw_uid(heading)
            if not raw_uid:
                continue

            scope = _heading_scope(heading)
            effective_uid = _heading_effective_uid(heading)

            node = nodes.get(effective_uid)
            if node is None:
                continue

            scope_headings = headings_by_scope.get(scope, [])

            range_info = _compute_own_range(
                raw_uid=raw_uid,
                node=node,
                headings=scope_headings,
                elements=elements,
                key_to_elem_i=key_to_elem_i,
                key_to_heading_index=key_to_heading_index,
                scope=scope,
                scope_boundaries=scope_boundaries,
            )

            node.range_end_reason = range_info.range_end_reason

            if range_info.start_elem_i < 0 or range_info.end_elem_i is None:
                own_range_missing_count += 1
                node.range_end_reason = "unbounded_error"
                node.diagnostics["own_range_status"] = "missing"
                node.diagnostics["own_range_unbounded"] = True

                logger.warning(
                    "STRUCTURE node_own_range_missing",
                    extra={
                        "document_id": normalized_document_id,
                        "raw_uid": raw_uid,
                        "effective_uid": effective_uid,
                        "scope": scope,
                        "structure_degraded": True,
                    },
                )
                continue

            if range_info.end_elem_i <= range_info.start_elem_i:
                recovered_end = None
                scope_boundary = scope_boundaries.get(scope)
                if scope_boundary is not None and scope_boundary[1] > range_info.start_elem_i:
                    recovered_end = scope_boundary[1]
                    recovered_reason = "segment_end_recovered"
                elif len(elements) > range_info.start_elem_i:
                    recovered_end = len(elements)
                    recovered_reason = "fallback_boundary_recovered"
                else:
                    recovered_reason = "unbounded_error"

                if recovered_end is None or recovered_end <= range_info.start_elem_i:
                    own_range_invalid_count += 1
                    node.range_end_reason = "unbounded_error"
                    node.diagnostics["own_range_status"] = "invalid"
                    node.diagnostics["own_range_unbounded"] = True

                    logger.warning(
                        "STRUCTURE node_own_range_invalid",
                        extra={
                            "document_id": normalized_document_id,
                            "raw_uid": raw_uid,
                            "effective_uid": effective_uid,
                            "scope": scope,
                            "heading_elem_i": range_info.start_elem_i,
                            "own_end": range_info.end_elem_i,
                            "range_end_reason": "unbounded_error",
                            "structure_degraded": True,
                        },
                    )
                    continue

                range_info = OwnRangeComputation(
                    start_elem_i=range_info.start_elem_i,
                    end_elem_i=recovered_end,
                    range_end_reason=recovered_reason,
                )
                node.range_end_reason = recovered_reason
                node.diagnostics["own_range_status"] = "recovered"
                node.diagnostics["own_range_unbounded"] = False
                node.diagnostics["own_range_recovered"] = True

                logger.warning(
                    "STRUCTURE node_own_range_recovered",
                    extra={
                        "document_id": normalized_document_id,
                        "raw_uid": raw_uid,
                        "effective_uid": effective_uid,
                        "scope": scope,
                        "heading_elem_i": range_info.start_elem_i,
                        "own_end": recovered_end,
                        "range_end_reason": recovered_reason,
                    },
                )

            own_element_ids: list[str] = []
            upper_bound = min(range_info.end_elem_i, len(elements))

            for j in range(max(range_info.start_elem_i, 0), upper_bound):
                stable_id = stable_element_id_resolver(elements[j], j)
                stable_id = str(stable_id or "").strip()
                if not stable_id:
                    continue

                own_element_ids.append(stable_id)

                if stable_id in element_to_effective_uid:
                    existing_uid = element_to_effective_uid[stable_id]
                    if existing_uid != effective_uid:
                        element_ownership_conflicts += 1
                        logger.warning(
                            "STRUCTURE element_ownership_conflict",
                            extra={
                                "document_id": normalized_document_id,
                                "stable_id": stable_id,
                                "existing_uid": existing_uid,
                                "conflicting_uid": effective_uid,
                                "scope": scope,
                                "elem_i": j,
                            },
                        )
                else:
                    element_to_effective_uid[stable_id] = effective_uid

            own_element_ids = list(dict.fromkeys(own_element_ids))
            own_text = _collect_own_text(elements, range_info.start_elem_i, range_info.end_elem_i)

            node.own_element_ids = own_element_ids
            node.own_text = own_text if own_text else None
            if node.diagnostics.get("own_range_status") != "recovered":
                node.diagnostics["own_range_status"] = "ok"
            node.diagnostics["own_range_unbounded"] = False
            node.diagnostics.setdefault("own_range_recovered", False)
            node.diagnostics["own_range_span"] = max(0, range_info.end_elem_i - range_info.start_elem_i)

            if (
                not node.children
                and node.diagnostics["own_range_span"] >= _SUSPICIOUS_LEAF_RANGE_SPAN_THRESHOLD
            ):
                suspicious_leaf_nodes_count += 1
                node.diagnostics["suspicious_leaf_range"] = True

                logger.warning(
                    "STRUCTURE node_suspicious_leaf_range",
                    extra={
                        "document_id": normalized_document_id,
                        "raw_uid": raw_uid,
                        "effective_uid": effective_uid,
                        "scope": scope,
                        "own_range_span": node.diagnostics["own_range_span"],
                        "threshold": _SUSPICIOUS_LEAF_RANGE_SPAN_THRESHOLD,
                    },
                )
            else:
                node.diagnostics["suspicious_leaf_range"] = False

            logger.debug(
                "structure.node.own_scope_built",
                extra={
                    "document_id": normalized_document_id,
                    "raw_uid": raw_uid,
                    "effective_uid": effective_uid,
                    "scope": scope,
                    "heading_elem_i": range_info.start_elem_i,
                    "own_end": range_info.end_elem_i,
                    "range_end_reason": range_info.range_end_reason,
                    "own_count": len(own_element_ids),
                    "own_text_len": len(own_text),
                    "children_count": len(node.children),
                    "first_child_elem_i": _find_first_child_elem_i(node, key_to_elem_i, scope),
                },
            )

        except Exception as exc:
            own_range_missing_count += 1
            logger.warning(
                "STRUCTURE node_own_range_build_failed",
                extra={
                    "document_id": normalized_document_id,
                    "scope": getattr(heading, "scope", None),
                    "raw_uid": getattr(heading, "raw_uid", None),
                    "uid": getattr(heading, "uid", None),
                    "effective_uid": getattr(heading, "effective_uid", None),
                    "error": str(exc),
                    "structure_degraded": True,
                },
            )
            continue

    populate_subtree_element_ids(
        root_nodes,
        document_id=normalized_document_id,
    )

    for node in nodes.values():
        own_count = len(node.own_element_ids or [])
        subtree_count = len(node.subtree_element_ids or [])
        suspicious_own_scope = bool(
            node.children
            and subtree_count > 0
            and own_count >= _SUSPICIOUS_OWN_SHARE_RATIO * subtree_count
        )
        node.diagnostics["suspicious_own_scope"] = suspicious_own_scope

    total_nodes = len(nodes)
    total_headings = len(headings)

    invalid_heading_ratio = _safe_ratio(invalid_heading_candidates_count, total_headings)
    own_range_anomaly_count = own_range_invalid_count + own_range_missing_count
    own_range_anomaly_ratio = _safe_ratio(own_range_anomaly_count, max(total_nodes, 1))

    fatal_hierarchy_failure = bool(
        (total_headings > 0 and total_nodes == 0)
        or (total_nodes > 0 and not root_nodes and _FATAL_ROOTLESS_WITH_NODES)
    )

    heavy_candidate_loss = invalid_heading_ratio >= _RECOVERABLE_INVALID_HEADING_RATIO
    heavy_range_damage = own_range_anomaly_ratio >= _RECOVERABLE_OWN_RANGE_ANOMALY_RATIO

    structure_degraded = bool(
        fatal_hierarchy_failure
        or heavy_candidate_loss
        or heavy_range_damage
    )

    hierarchy_quality = "good"
    if total_nodes == 0:
        hierarchy_quality = "failed"
    elif structure_degraded:
        hierarchy_quality = "partial"

    for node in nodes.values():
        node.diagnostics.setdefault("hierarchy_quality", hierarchy_quality)

    logger.info(
        "STRUCTURE hierarchy_build_diagnostics",
        extra={
            "document_id": normalized_document_id,
            "headings_count": len(headings),
            "nodes_count": len(nodes),
            "root_count": len(root_nodes),
            "scope_stats": scope_stats,
            "scope_boundaries": scope_boundaries,
            "own_range_invalid_count": own_range_invalid_count,
            "own_range_missing_count": own_range_missing_count,
            "duplicate_effective_uid_skipped_count": duplicate_effective_uid_skipped_count,
            "duplicate_scope_raw_uid_skipped_count": duplicate_scope_raw_uid_skipped_count,
            "invalid_heading_candidates_count": invalid_heading_candidates_count,
            "suspicious_leaf_nodes_count": suspicious_leaf_nodes_count,
            "element_ownership_conflicts": element_ownership_conflicts,
            "parent_attach_rejected_count": parent_attach_rejected_count,
            "structure_degraded": structure_degraded,
            "total_nodes": total_nodes,
            "total_headings": total_headings,
            "invalid_heading_ratio": invalid_heading_ratio,
            "own_range_anomaly_count": own_range_anomaly_count,
            "own_range_anomaly_ratio": own_range_anomaly_ratio,
            "fatal_hierarchy_failure": fatal_hierarchy_failure,
            "heavy_candidate_loss": heavy_candidate_loss,
            "heavy_range_damage": heavy_range_damage,
            "hierarchy_quality": hierarchy_quality,
        },
    )

    return root_nodes, nodes, element_to_effective_uid, structure_degraded


def populate_subtree_element_ids(
    root_nodes: list[ClauseNode],
    *,
    document_id: str,
) -> None:
    """
    Bottom-up проход по дереву.

    Для каждого узла заполняем:
    - subtree_element_ids: own + все потомки, без дубликатов, порядок сохранён;
    - subtree_text: own_text + тексты всех потомков через пробел;
    - node_kind: "leaf" если детей нет, "section" если есть.
    """
    normalized_document_id = str(document_id or "").strip()
    if not root_nodes:
        return

    for root_node in root_nodes:
        for node in _walk_postorder(root_node):
            node.node_kind = "section" if node.children else "leaf"

            subtree_ids: list[str] = list(node.own_element_ids or [])
            for child in node.children:
                subtree_ids.extend(child.subtree_element_ids or [])
            node.subtree_element_ids = list(dict.fromkeys(subtree_ids))

            text_parts: list[str] = []
            if node.own_text:
                text_parts.append(node.own_text)
            for child in node.children:
                if child.subtree_text:
                    text_parts.append(child.subtree_text)
            node.subtree_text = " ".join(text_parts) if text_parts else None

            own_count = len(node.own_element_ids or [])
            subtree_count = len(node.subtree_element_ids or [])

            logger.debug(
                "structure.node.subtree_built",
                extra={
                    "document_id": normalized_document_id,
                    "raw_uid": node.raw_uid,
                    "effective_uid": node.effective_uid,
                    "scope": node.scope,
                    "level": node.level,
                    "node_kind": node.node_kind,
                    "own_count": own_count,
                    "subtree_count": subtree_count,
                    "own_text_len": len(node.own_text or ""),
                    "subtree_text_len": len(node.subtree_text or ""),
                    "children_count": len(node.children),
                    "suspicious_own_scope": (
                        bool(node.children)
                        and subtree_count > 0
                        and own_count >= _SUSPICIOUS_OWN_SHARE_RATIO * subtree_count
                    ),
                },
            )
        
        
        
        