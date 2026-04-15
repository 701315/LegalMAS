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
from typing import Any, Callable


from core.logging import get_logger
from services.structure.models import ClauseNode


logger = get_logger(__name__)


# ── Вспомогательные функции ──────────────────────────────────────────────────


_NUMERIC_UID_RE = re.compile(r"^\d+(?:\.\d+)*$")


def _is_strict_numeric_uid(uid: str) -> bool:
    """
    Надёжная проверка числового uid: "1", "1.2", "3.1.4".

    Используем везде вместо uid.replace(".", "").isdigit(),
    которая давала ложные срабатывания на "1.2." (точка в конце).
    """
    return bool(_NUMERIC_UID_RE.fullmatch((uid or "").strip()))


@dataclass(slots=True)
class HeadingCandidate:
    """
    Минимальный входной тип для hierarchy assembly.

    Сюда попадают уже принятые кандидаты после parsing/scoring/filtering.
    """
    elem_i: int
    uid: str
    title: str
    page: int


def level_from_uid(uid: str) -> int:
    """
    Глубина numeric uid по количеству точек:
    "1" → 1, "1.2" → 2, "1.2.3" → 3.

    Для non-numeric uid вызывающий код обычно использует level=1.
    """
    return uid.count(".") + 1


def find_parent_uid(uid: str, nodes: dict[str, ClauseNode]) -> str | None:
    """
    Ищет ближайшего существующего родителя по uid-цепочке:
    "1.2.3" → пробуем "1.2" → "1".
    """
    if not uid or "." not in uid:
        return None

    parts = uid.split(".")
    for i in range(len(parts) - 1, 0, -1):
        candidate = ".".join(parts[:i])
        if candidate in nodes:
            return candidate

    return None


def _collect_own_text(
    elements: list[dict[str, Any]],
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
    parts: list[str] = []
    for j in range(elem_i, next_elem_i):
        text = (elements[j].get("text") or "").strip()
        if text:
            parts.append(text)
    return " ".join(parts)


def _build_heading_positions(
    headings: list[HeadingCandidate],
) -> tuple[dict[str, int], dict[str, int]]:
    """
    Строит две служебные карты:

    1. uid_to_elem_i:
       Позиция заголовка в layout-элементах для каждого uid.

    2. uid_to_heading_index:
       Порядковый индекс заголовка в списке headings.

    Предполагается, что после heading_builder/filter_heading_sequence
    uid уже уникальны в пределах текущего документа.
    """
    uid_to_elem_i: dict[str, int] = {}
    uid_to_heading_index: dict[str, int] = {}

    for idx, heading in enumerate(headings):
        uid = (heading.uid or "").strip()
        if not uid:
            continue
        if uid not in uid_to_elem_i:
            uid_to_elem_i[uid] = heading.elem_i
            uid_to_heading_index[uid] = idx

    return uid_to_elem_i, uid_to_heading_index


def _find_first_child_elem_i(
    node: ClauseNode,
    uid_to_elem_i: dict[str, int],
) -> int | None:
    """
    Найти позицию первого дочернего заголовка этого узла.

    Если детей нет — возвращаем None.
    Если дети есть — берём минимальный elem_i среди всех прямых детей.
    """
    first_child_elem_i: int | None = None

    for child in node.children:
        child_elem_i = uid_to_elem_i.get(child.clause_uid)
        if child_elem_i is None:
            continue

        if first_child_elem_i is None or child_elem_i < first_child_elem_i:
            first_child_elem_i = child_elem_i

    return first_child_elem_i


def _find_next_same_or_higher_level_elem_i(
    *,
    uid: str,
    node_level: int,
    headings: list[HeadingCandidate],
    uid_to_heading_index: dict[str, int],
) -> int | None:
    """
    Найти elem_i следующего заголовка того же или более высокого уровня.

    Используется как верхняя граница own-диапазона: текст, который
    относится к соседнему разделу/подразделу, не должен попадать в own.
    """
    idx = uid_to_heading_index.get(uid)
    if idx is None:
        return None

    for h in headings[idx + 1:]:
        h_uid = (h.uid or "").strip()
        if not h_uid:
            continue

        if _is_strict_numeric_uid(h_uid):
            h_level = level_from_uid(h_uid)
        else:
            # Для нечисловых uid считаем их корневыми, чтобы не захватывать
            # их текст в own дочерних numeric-разделов.
            h_level = 1

        if h_level <= node_level:
            return h.elem_i

    return None


def _compute_own_range_end(
    *,
    uid: str,
    node: ClauseNode,
    headings: list[HeadingCandidate],
    elements: list[dict[str, Any]],
    uid_to_elem_i: dict[str, int],
    uid_to_heading_index: dict[str, int],
) -> int | None:
    """
    Вычислить конец own-диапазона для узла.

    Правильное правило:
    - own начинается с elem_i текущего заголовка;
    - own заканчивается на первом из событий:
      1) первый дочерний заголовок;
      2) следующий заголовок того же или более высокого уровня;
      3) конец документа.
    """
    heading_elem_i = uid_to_elem_i.get(uid)
    heading_idx = uid_to_heading_index.get(uid)

    if heading_elem_i is None or heading_idx is None:
        return None

    # Следующий heading того же или более высокого уровня
    next_same_or_higher = _find_next_same_or_higher_level_elem_i(
        uid=uid,
        node_level=node.level,
        headings=headings,
        uid_to_heading_index=uid_to_heading_index,
    )

    # Первый дочерний heading
    first_child_elem_i = _find_first_child_elem_i(node, uid_to_elem_i)

    end_candidates: list[int] = [len(elements)]
    if next_same_or_higher is not None:
        end_candidates.append(next_same_or_higher)
    if first_child_elem_i is not None:
        end_candidates.append(first_child_elem_i)

    return min(end_candidates)


# ── Основная функция построения дерева ──────────────────────────────────────


def build_clause_hierarchy(
    headings: list[HeadingCandidate],
    elements: list[dict[str, Any]],
    *,
    document_id: str,
    stable_element_id_resolver: Callable[[dict[str, Any], int], str],
) -> tuple[list[ClauseNode], dict[str, ClauseNode], dict[str, str]]:
    """
    Построить ClauseNode-дерево и индекс element_id → clause_uid.

    Возвращает:
    - root_nodes:      корневые узлы дерева;
    - nodes:           плоский словарь uid → ClauseNode;
    - element_to_uid:  словарь element_id → uid (для crossrefs).

    ВАЖНО:
    - references здесь не строим — это отдельная ответственность crossrefs.py;
    - own_text собираем здесь при построении узла;
    - subtree_text и node_kind собираем bottom-up в populate_subtree_element_ids.
    """
    nodes: dict[str, ClauseNode] = {}
    root: list[ClauseNode] = []
    element_to_uid: dict[str, str] = {}

    if not headings:
        return root, nodes, element_to_uid

    uid_to_elem_i, uid_to_heading_index = _build_heading_positions(headings)

    # ── Первый проход: создаём все узлы и связываем parent/children ─────────
    for h_idx, heading in enumerate(headings):
        elem_i = heading.elem_i
        uid = heading.uid
        title = heading.title
        page = heading.page

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

        numeric_uid = _is_strict_numeric_uid(uid)
        level = level_from_uid(uid) if numeric_uid else 1

        if uid in nodes:
            logger.warning(
                "STRUCTURE node_duplicate_uid_skipped",
                extra={
                    "document_id": document_id,
                    "clause_uid": uid,
                    "title": title,
                    "page": page,
                    "elem_i": elem_i,
                },
            )
            continue

        node = ClauseNode(
            clause_uid=uid,
            title=title,
            level=level,
            node_kind="leaf",
            own_element_ids=[],
            own_text=None,
            start_page=page,
            end_page=end_page,
        )

        nodes[uid] = node

        logger.debug(
            "structure.node.created",
            extra={
                "document_id": document_id,
                "clause_uid": node.clause_uid,
                "title": node.title,
                "level": node.level,
                "own_count": 0,
                "own_text_len": 0,
                "start_page": node.start_page,
                "end_page": node.end_page,
                "heading_elem_i": elem_i,
                "next_heading_elem_i": next_elem_i,
                "numeric_uid": numeric_uid,
            },
        )

        parent_uid = find_parent_uid(uid, nodes)
        if parent_uid and parent_uid in nodes:
            nodes[parent_uid].children.append(node)
            logger.debug(
                "structure.node.parenting",
                extra={
                    "document_id": document_id,
                    "clause_uid": node.clause_uid,
                    "parent_uid": parent_uid,
                    "level": node.level,
                    "attached_to_root": False,
                },
            )
        else:
            root.append(node)
            logger.debug(
                "structure.node.parenting",
                extra={
                    "document_id": document_id,
                    "clause_uid": node.clause_uid,
                    "parent_uid": None,
                    "level": node.level,
                    "attached_to_root": True,
                },
            )

    # ── Второй проход: заполняем own_element_ids и own_text ─────────────────
    for uid, node in nodes.items():
        heading_elem_i = uid_to_elem_i.get(uid)
        if heading_elem_i is None:
            logger.warning(
                "STRUCTURE node_heading_position_missing",
                extra={
                    "document_id": document_id,
                    "clause_uid": uid,
                },
            )
            continue

        own_end = _compute_own_range_end(
            uid=uid,
            node=node,
            headings=headings,
            elements=elements,
            uid_to_elem_i=uid_to_elem_i,
            uid_to_heading_index=uid_to_heading_index,
        )

        if own_end is None:
            logger.warning(
                "STRUCTURE node_own_range_missing",
                extra={
                    "document_id": document_id,
                    "clause_uid": uid,
                    "heading_elem_i": heading_elem_i,
                },
            )
            continue

        if own_end < heading_elem_i:
            logger.warning(
                "STRUCTURE node_own_range_invalid",
                extra={
                    "document_id": document_id,
                    "clause_uid": uid,
                    "heading_elem_i": heading_elem_i,
                    "own_end": own_end,
                },
            )
            continue

        own_element_ids: list[str] = []
        for j in range(heading_elem_i, own_end):
            stable_id = stable_element_id_resolver(elements[j], j)
            own_element_ids.append(stable_id)
            element_to_uid.setdefault(stable_id, uid)

        own_text = _collect_own_text(elements, heading_elem_i, own_end)

        node.own_element_ids = own_element_ids
        node.own_text = own_text if own_text else None

        logger.debug(
            "structure.node.own_scope_built",
            extra={
                "document_id": document_id,
                "clause_uid": uid,
                "heading_elem_i": heading_elem_i,
                "own_end": own_end,
                "own_count": len(own_element_ids),
                "own_text_len": len(own_text),
                "children_count": len(node.children),
                "first_child_elem_i": _find_first_child_elem_i(node, uid_to_elem_i),
            },
        )

    # Bottom-up проход: subtree_element_ids, subtree_text, node_kind
    populate_subtree_element_ids(nodes, document_id=document_id)

    return root, nodes, element_to_uid


# ── Bottom-up сборка subtree полей ──────────────────────────────────────────


def populate_subtree_element_ids(
    nodes: dict[str, ClauseNode],
    *,
    document_id: str,
) -> None:
    """
    Bottom-up проход по дереву (от листьев к корню).

    Для каждого узла заполняем:
    - subtree_element_ids: own + все потомки, без дубликатов, порядок сохранён;
    - subtree_text:        own_text + тексты всех потомков через пробел;
    - node_kind:           "leaf" если нет детей, "section" если есть.

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
        subtree_count = len(node.subtree_element_ids)
        logger.debug(
            "structure.node.subtree_built",
            extra={
                "document_id": document_id,
                "clause_uid": node.clause_uid,
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
        
        
        