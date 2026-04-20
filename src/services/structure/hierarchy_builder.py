# src/services/structure/hierarchy_builder.py

"""
Сборка иерархии clause tree из уже отфильтрованных heading candidates.

Задача этого модуля:
- не парсить заголовки;
- не принимать решения accepted/rejected;
- не искать TOC;
- только собирать ClauseNode-дерево из heading candidates и layout elements.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple

from core.logging import get_logger
from services.structure.models import ClauseNode

logger = get_logger(__name__)

# ── Вспомогательные функции ──────────────────────────────────────────────────

_NUMERIC_UID_RE = re.compile(r"^\d+(?:\.\d+)*$")
_DEFAULT_SCOPE = "main_contract"


def _is_strict_numeric_uid(uid: str) -> bool:
    """
    Надёжная проверка числового uid: "1", "1.2", "3.1.4".

    Используем везде вместо uid.replace(".", "").isdigit(),
    которая давала ложные срабатывания на "1.2.".
    """
    return bool(_NUMERIC_UID_RE.fullmatch((uid or "").strip()))


def _normalize_scope(value: Any) -> str:
    """
    Универсальная нормализация scope.

    Backward-compatible:
    - если scope не задан → main_contract;
    - пустые/битые значения тоже приводим к main_contract.
    """
    if value is None:
        return _DEFAULT_SCOPE
    scope = str(value).strip()
    return scope or _DEFAULT_SCOPE


def _normalize_uid(value: Any) -> str:
    return str(value or "").strip()


def _effective_uid_from_scope(scope: str, raw_uid: str) -> str:
    """
    Вычислить effective_uid:
    - main_contract → raw_uid без префикса;
    - appendix_* / другие scope → "<scope>::<raw_uid>".
    """
    scope = _normalize_scope(scope)
    raw_uid = _normalize_uid(raw_uid)

    if not raw_uid:
        return raw_uid

    if scope == _DEFAULT_SCOPE:
        return raw_uid

    return f"{scope}::{raw_uid}"


@dataclass(slots=True)
class HeadingCandidate:
    """
    Минимальный входной тип для hierarchy assembly.

    Сюда попадают уже принятые кандидаты после parsing/scoring/filtering.

    Поля:
    - uid: legacy/raw uid для обратной совместимости;
    - raw_uid: исходный юридический uid внутри scope;
    - effective_uid: диагностический uid с учётом scope.
    """

    elem_i: int
    uid: str
    title: str
    page: int
    scope: str | None = None
    raw_uid: str | None = None
    effective_uid: str | None = None


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
        return explicit
    return _effective_uid_from_scope(_heading_scope(heading), _heading_raw_uid(heading))


def level_from_uid(uid: str) -> int:
    """
    Глубина numeric uid по количеству точек:
    "1" → 1, "1.2" → 2, "1.2.3" → 3.

    Для non-numeric uid вызывающий код обычно использует level=1.
    """
    return uid.count(".") + 1


def find_parent_uid(raw_uid: str, nodes: Dict[str, ClauseNode]) -> str | None:
    """
    Ищет ближайшего существующего родителя по raw uid-цепочке:
    "1.2.3" → пробуем "1.2" → "1".

    ВАЖНО:
    parent ищем по raw_uid внутри текущего scope-контекста обхода.
    Scope-изоляция достигается тем, что вызывающий код передаёт сюда
    scope-local словарь nodes.
    """
    raw_uid = _normalize_uid(raw_uid)
    if not raw_uid or "." not in raw_uid:
        return None

    parts = raw_uid.split(".")
    for i in range(len(parts) - 1, 0, -1):
        candidate = ".".join(parts[:i])
        if candidate in nodes:
            return candidate

    return None


def _collect_own_text(
    elements: List[dict[str, Any]],
    elem_i: int,
    next_elem_i: int,
) -> str:
    """
    Собирает текст элементов layout, принадлежащих только этому узлу.

    ВАЖНО:
    - сюда должен попадать только диапазон самого узла;
    - если у узла есть дети, диапазон own заканчивается на первом
      дочернем заголовке;
    - если детей нет, диапазон own заканчивается на следующем заголовке.

    Каждый элемент разделяется пробелом — итоговая строка нормализована.
    Пустые элементы пропускаются.
    """
    parts: List[str] = []
    for j in range(elem_i, next_elem_i):
        text = (elements[j].get("text") or "").strip()
        if text:
            parts.append(text)
    return " ".join(parts)


def _build_heading_positions(
    headings: List[HeadingCandidate],
) -> Tuple[Dict[Tuple[str, str], int], Dict[Tuple[str, str], int]]:
    """
    Строит две служебные карты по ключу (scope, raw_uid):

    1. key_to_elem_i:
       Позиция заголовка в layout-элементах для каждого (scope, raw_uid).

    2. key_to_heading_index:
       Порядковый индекс заголовка в списке headings.

    Предполагается, что после heading_builder/filter_heading_sequence
    (scope, raw_uid) уже уникальны в пределах документа.
    """
    key_to_elem_i: Dict[Tuple[str, str], int] = {}
    key_to_heading_index: Dict[Tuple[str, str], int] = {}

    for idx, heading in enumerate(headings):
        raw_uid = _heading_raw_uid(heading)
        if not raw_uid:
            continue

        scope = _heading_scope(heading)
        key = (scope, raw_uid)

        if key not in key_to_elem_i:
            key_to_elem_i[key] = heading.elem_i
            key_to_heading_index[key] = idx

    return key_to_elem_i, key_to_heading_index


def _find_first_child_elem_i(
    node: ClauseNode,
    key_to_elem_i: Dict[Tuple[str, str], int],
    scope: str,
) -> int | None:
    """
    Найти позицию первого дочернего заголовка этого узла в том же scope.

    Если детей нет — возвращаем None.
    Если дети есть — берём минимальный elem_i среди всех прямых детей.
    """
    first_child_elem_i: int | None = None

    for child in node.children:
        child_key = (scope, _normalize_uid(child.clause_uid))
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
    headings: List[HeadingCandidate],
    key_to_heading_index: Dict[Tuple[str, str], int],
) -> int | None:
    """
    Найти elem_i следующего заголовка того же или более высокого уровня
    в пределах того же scope.

    Используется как верхняя граница own-диапазона: текст, который
    относится к соседнему разделу/подразделу, не должен попадать в own.
    """
    key = (scope, raw_uid)
    idx = key_to_heading_index.get(key)
    if idx is None:
        return None

    for h in headings[idx + 1 :]:
        h_scope = _heading_scope(h)
        if h_scope != scope:
            continue

        h_raw_uid = _heading_raw_uid(h)
        if not h_raw_uid:
            continue

        if _is_strict_numeric_uid(h_raw_uid):
            h_level = level_from_uid(h_raw_uid)
        else:
            h_level = 1

        if h_level <= node_level:
            return h.elem_i

    return None


def _compute_own_range_end(
    *,
    raw_uid: str,
    node: ClauseNode,
    headings: List[HeadingCandidate],
    elements: List[dict[str, Any]],
    key_to_elem_i: Dict[Tuple[str, str], int],
    key_to_heading_index: Dict[Tuple[str, str], int],
    scope: str,
) -> int | None:
    """
    Вычислить конец own-диапазона для узла в пределах того же scope.

    Правильное правило:
    - own начинается с elem_i текущего заголовка;
    - own заканчивается на первом из событий:
      1) первый дочерний заголовок (в том же scope);
      2) следующий заголовок того же или более высокого уровня (в том же scope);
      3) конец документа.
    """
    key = (scope, raw_uid)
    heading_elem_i = key_to_elem_i.get(key)
    heading_idx = key_to_heading_index.get(key)

    if heading_elem_i is None or heading_idx is None:
        return None

    next_same_or_higher = _find_next_same_or_higher_level_elem_i(
        raw_uid=raw_uid,
        node_level=node.level,
        scope=scope,
        headings=headings,
        key_to_heading_index=key_to_heading_index,
    )

    first_child_elem_i = _find_first_child_elem_i(node, key_to_elem_i, scope)

    end_candidates: List[int] = [len(elements)]
    if next_same_or_higher is not None:
        end_candidates.append(next_same_or_higher)
    if first_child_elem_i is not None:
        end_candidates.append(first_child_elem_i)

    return min(end_candidates)


# ── Основная функция построения дерева ──────────────────────────────────────


def build_clause_hierarchy(
    headings: List[HeadingCandidate],
    elements: List[dict[str, Any]],
    *,
    document_id: str,
    stable_element_id_resolver: Callable[[dict[str, Any], int], str],
) -> tuple[list[ClauseNode], dict[str, ClauseNode], dict[str, str], bool]:
    """
    Построить ClauseNode-дерево и индекс element_id → clause_uid.

    Возвращает:
    - root_nodes:      корневые узлы дерева;
    - nodes:           плоский словарь raw_uid → ClauseNode;
    - element_to_uid:  словарь element_id → raw_uid (для crossrefs);
    - structure_degraded: True, если own-range деградировал (node_own_range_invalid).
    """
    nodes: Dict[str, ClauseNode] = {}
    root: List[ClauseNode] = []
    element_to_uid: Dict[str, str] = {}

    if not headings:
        return root, nodes, element_to_uid, False

    scope_stats: Dict[str, int] = {}
    own_range_invalid_count = 0
    own_range_missing_count = 0
    duplicate_uid_skipped_count = 0

    for h in headings:
        s = _heading_scope(h)
        scope_stats[s] = scope_stats.get(s, 0) + 1

    logger.debug(
        "STRUCTURE hierarchy_build_scopes",
        extra={
            "document_id": document_id,
            "scope_stats": scope_stats,
        },
    )

    key_to_elem_i, key_to_heading_index = _build_heading_positions(headings)

    # scope-local registry для parent lookup:
    # scope -> raw_uid -> ClauseNode
    nodes_by_scope: Dict[str, Dict[str, ClauseNode]] = {}

    # ── Первый проход: создаём все узлы и связываем parent/children ─────────
    for h_idx, heading in enumerate(headings):
        elem_i = heading.elem_i
        raw_uid = _heading_raw_uid(heading)
        effective_uid = _heading_effective_uid(heading)
        title = heading.title
        page = heading.page
        scope = _heading_scope(heading)

        if not raw_uid:
            logger.warning(
                "STRUCTURE node_empty_uid_skipped",
                extra={
                    "document_id": document_id,
                    "scope": scope,
                    "page": page,
                    "elem_i": elem_i,
                },
            )
            continue

        next_elem_i = (
            headings[h_idx + 1].elem_i
            if h_idx + 1 < len(headings)
            else len(elements)
        )

        end_page = (
            elements[next_elem_i - 1].get("page", page)
            if next_elem_i > elem_i
            else page
        )

        numeric_uid = _is_strict_numeric_uid(raw_uid)
        level = level_from_uid(raw_uid) if numeric_uid else 1

        # Глобальный nodes остаётся legacy-совместимым по raw_uid.
        # Если сюда всё же доехал конфликт raw_uid между scope,
        # это означает, что downstream с raw_uid-only индексом не сможет
        # различить узлы корректно. В таком случае безопаснее пропустить
        # второй узел и оставить подробный warning.
        if raw_uid in nodes:
            duplicate_uid_skipped_count += 1
            logger.warning(
                "STRUCTURE node_duplicate_uid_skipped",
                extra={
                    "document_id": document_id,
                    "clause_uid": raw_uid,
                    "raw_uid": raw_uid,
                    "effective_uid": effective_uid,
                    "title": title,
                    "page": page,
                    "elem_i": elem_i,
                    "scope": scope,
                    "reason": "global_raw_uid_conflict",
                },
            )
            continue

        node = ClauseNode(
            clause_uid=raw_uid,
            title=title,
            level=level,
            node_kind="leaf",
            own_element_ids=[],
            own_text=None,
            start_page=page,
            end_page=end_page,
        )

        # Мягко добавляем новые диагностические атрибуты, если модель разрешает.
        for attr_name, attr_value in (
            ("scope", scope),
            ("raw_uid", raw_uid),
            ("effective_uid", effective_uid),
        ):
            try:
                setattr(node, attr_name, attr_value)
            except Exception:
                pass

        nodes[raw_uid] = node
        nodes_by_scope.setdefault(scope, {})[raw_uid] = node

        logger.debug(
            "structure.node.created",
            extra={
                "document_id": document_id,
                "clause_uid": node.clause_uid,
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

        scope_nodes = nodes_by_scope.get(scope, {})
        parent_uid = find_parent_uid(raw_uid, scope_nodes)

        if parent_uid and parent_uid in scope_nodes:
            scope_nodes[parent_uid].children.append(node)
            logger.debug(
                "structure.node.parenting",
                extra={
                    "document_id": document_id,
                    "clause_uid": node.clause_uid,
                    "raw_uid": raw_uid,
                    "effective_uid": effective_uid,
                    "parent_uid": parent_uid,
                    "level": node.level,
                    "attached_to_root": False,
                    "scope": scope,
                },
            )
        else:
            root.append(node)
            logger.debug(
                "structure.node.parenting",
                extra={
                    "document_id": document_id,
                    "clause_uid": node.clause_uid,
                    "raw_uid": raw_uid,
                    "effective_uid": effective_uid,
                    "parent_uid": None,
                    "level": node.level,
                    "attached_to_root": True,
                    "scope": scope,
                },
            )

    # ── Второй проход: заполняем own_element_ids и own_text ─────────────────
    for heading in headings:
        raw_uid = _heading_raw_uid(heading)
        if not raw_uid:
            continue

        scope = _heading_scope(heading)
        effective_uid = _heading_effective_uid(heading)

        node = nodes.get(raw_uid)
        if node is None:
            continue

        key = (scope, raw_uid)
        heading_elem_i = key_to_elem_i.get(key)
        if heading_elem_i is None:
            own_range_missing_count += 1
            logger.warning(
                "STRUCTURE node_heading_position_missing",
                extra={
                    "document_id": document_id,
                    "clause_uid": raw_uid,
                    "raw_uid": raw_uid,
                    "effective_uid": effective_uid,
                    "scope": scope,
                },
            )
            continue

        own_end = _compute_own_range_end(
            raw_uid=raw_uid,
            node=node,
            headings=headings,
            elements=elements,
            key_to_elem_i=key_to_elem_i,
            key_to_heading_index=key_to_heading_index,
            scope=scope,
        )

        if own_end is None:
            own_range_missing_count += 1
            logger.warning(
                "STRUCTURE node_own_range_missing",
                extra={
                    "document_id": document_id,
                    "clause_uid": raw_uid,
                    "raw_uid": raw_uid,
                    "effective_uid": effective_uid,
                    "scope": scope,
                    "heading_elem_i": heading_elem_i,
                },
            )
            continue

        # Этап 2: own_end <= heading_elem_i — это уже деградация структуры,
        # а не просто косметический warning.
        if own_end <= heading_elem_i:
            own_range_invalid_count += 1
            logger.warning(
                "STRUCTURE node_own_range_invalid",
                extra={
                    "document_id": document_id,
                    "clause_uid": raw_uid,
                    "raw_uid": raw_uid,
                    "effective_uid": effective_uid,
                    "scope": scope,
                    "heading_elem_i": heading_elem_i,
                    "own_end": own_end,
                    "structure_degraded": True,
                },
            )
            continue

        own_element_ids: List[str] = []
        for j in range(heading_elem_i, own_end):
            stable_id = stable_element_id_resolver(elements[j], j)
            own_element_ids.append(stable_id)
            element_to_uid.setdefault(stable_id, raw_uid)

        own_text = _collect_own_text(elements, heading_elem_i, own_end)

        node.own_element_ids = own_element_ids
        node.own_text = own_text if own_text else None

        logger.debug(
            "structure.node.own_scope_built",
            extra={
                "document_id": document_id,
                "clause_uid": raw_uid,
                "raw_uid": raw_uid,
                "effective_uid": effective_uid,
                "scope": scope,
                "heading_elem_i": heading_elem_i,
                "own_end": own_end,
                "own_count": len(own_element_ids),
                "own_text_len": len(own_text),
                "children_count": len(node.children),
                "first_child_elem_i": _find_first_child_elem_i(node, key_to_elem_i, scope),
            },
        )

    structure_degraded = own_range_invalid_count > 0

    logger.info(
        "STRUCTURE hierarchy_build_diagnostics",
        extra={
            "document_id": document_id,
            "headings_count": len(headings),
            "nodes_count": len(nodes),
            "root_count": len(root),
            "scope_stats": scope_stats,
            "own_range_invalid_count": own_range_invalid_count,
            "own_range_missing_count": own_range_missing_count,
            "duplicate_uid_skipped_count": duplicate_uid_skipped_count,
            "structure_degraded": structure_degraded,
        },
    )

    # Bottom-up проход: subtree_element_ids, subtree_text, node_kind
    populate_subtree_element_ids(nodes, document_id=document_id)

    return root, nodes, element_to_uid, structure_degraded


# ── Bottom-up сборка subtree полей ──────────────────────────────────────────


def populate_subtree_element_ids(
    nodes: Dict[str, ClauseNode],
    *,
    document_id: str,
) -> None:
    """
    Bottom-up проход по дереву (от листьев к корню).

    Для каждого узла заполняем:
    - subtree_element_ids: own + все потомки, без дубликатов, порядок сохранён;
    - subtree_text:       own_text + тексты всех потомков через пробел;
    - node_kind:          "leaf" если нет детей, "section" если есть.

    Почему bottom-up: когда обрабатываем узел, его дети уже обработаны
    и имеют заполненные subtree_element_ids и subtree_text.
    """
    if not nodes:
        return

    sorted_uids = sorted(
        nodes.keys(),
        key=lambda u: level_from_uid(u) if _is_strict_numeric_uid(u) else 1,
        reverse=True,
    )

    for uid in sorted_uids:
        node = nodes[uid]

        node.node_kind = "section" if node.children else "leaf"

        subtree_ids: List[str] = list(node.own_element_ids or [])
        for child in node.children:
            subtree_ids.extend(child.subtree_element_ids or [])
        node.subtree_element_ids = list(dict.fromkeys(subtree_ids))

        text_parts: List[str] = []
        if node.own_text:
            text_parts.append(node.own_text)
        for child in node.children:
            if child.subtree_text:
                text_parts.append(child.subtree_text)
        node.subtree_text = " ".join(text_parts) if text_parts else None

        own_count = len(node.own_element_ids or [])
        subtree_count = len(node.subtree_element_ids)
        logger.debug(
            "structure.node.subtree_built",
            extra={
                "document_id": document_id,
              

                "clause_uid": node.clause_uid,
                "raw_uid": getattr(node, "raw_uid", node.clause_uid),
                "effective_uid": getattr(node, "effective_uid", node.clause_uid),
                "scope": getattr(node, "scope", None),
                "level": node.level,
                "node_kind": node.node_kind,
                "own_count": own_count,
                "subtree_count": subtree_count,
                "own_text_len": len(node.own_text or ""),
                "subtree_text_len": len(node.subtree_text or ""),
                "children_count": len(node.children),
                "suspicious_own_scope": (
                    bool(node.children)
                    and own_count >= 0.8 * subtree_count
                    and subtree_count > 0
                ),
            },
        )

        
        
        
        