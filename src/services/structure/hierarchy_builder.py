# src/services/structure/hierarchy_builder.py

"""
Сборка иерархии clause tree из уже отфильтрованных heading candidates.

Задача этого модуля:
- не парсить заголовки;
- не принимать решения accepted/rejected;
- не искать TOC;
- а только собирать ClauseNode-дерево из heading candidates и layout elements.

На этом этапе модуль остаётся максимально совместимым с текущим builder.py:
- использует тот же HeadingCandidate shape;
- возвращает те же root nodes и references;
- subtree_element_ids собирает тем же bottom-up проходом.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from core.logging import get_logger
from services.structure.models import ClauseNode


logger = get_logger(__name__)


@dataclass(slots=True)
class HeadingCandidate:
    """
    Минимальный входной тип для hierarchy assembly.

    Важно:
    - это не raw candidate и не scored candidate;
    - сюда попадают уже принятые кандидаты после parsing/scoring/filtering.
    """

    elem_i: int
    uid: str
    title: str
    page: int


def level_from_uid(uid: str) -> int:
    """
    Глубина numeric uid:
    - "1" -> 1
    - "1.2" -> 2
    - "1.2.3" -> 3

    Для non-numeric uid вызывающий код обычно использует level=1.
    """
    return uid.count(".") + 1


def find_parent_uid(uid: str, nodes: dict[str, ClauseNode]) -> str | None:
    """
    Ищет ближайшего существующего родителя:
    1.2.3 -> 1.2 -> 1
    """
    if not uid or "." not in uid:
        return None

    parts = uid.split(".")
    for i in range(len(parts) - 1, 0, -1):
        candidate = ".".join(parts[:i])
        if candidate in nodes:
            return candidate

    return None


def build_clause_hierarchy(
    headings: list[HeadingCandidate],
    elements: list[dict[str, Any]],
    *,
    document_id: str,
    stable_element_id_resolver: Callable[[dict[str, Any], int], str],
) -> tuple[list[ClauseNode], dict[str, ClauseNode], dict[str, str]]:
    """
    Построить ClauseNode-дерево и индекс element_id -> clause_uid.

    Возвращает:
    - root nodes;
    - nodes index by uid;
    - element_to_uid mapping.

    ВАЖНО:
    - references здесь не строим; это отдельная ответственность;
    - subtree_element_ids собираем bottom-up после построения parent/child links.
    """
    nodes: dict[str, ClauseNode] = {}
    root: list[ClauseNode] = []
    element_to_uid: dict[str, str] = {}

    for h_idx, heading in enumerate(headings):
        elem_i = heading.elem_i
        uid = heading.uid
        title = heading.title
        page = heading.page

        next_elem_i = (
            headings[h_idx + 1].elem_i if h_idx + 1 < len(headings) else len(elements)
        )

        own_element_ids: list[str] = []
        for j in range(elem_i, next_elem_i):
            stable_id = stable_element_id_resolver(elements[j], j)
            own_element_ids.append(stable_id)
            element_to_uid.setdefault(stable_id, uid)

        end_page = (
            elements[next_elem_i - 1].get("page", page)
            if next_elem_i > elem_i
            else page
        )

        numeric_uid = uid.replace(".", "").isdigit()
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
            own_element_ids=own_element_ids,
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
                "own_count": len(node.own_element_ids or []),
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

    populate_subtree_element_ids(nodes, document_id=document_id)
    return root, nodes, element_to_uid


def populate_subtree_element_ids(
    nodes: dict[str, ClauseNode],
    *,
    document_id: str,
) -> None:
    """
    Снизу вверх собираем subtree_element_ids с сохранением порядка.
    """
    if not nodes:
        return

    sorted_uids = sorted(
        nodes.keys(),
        key=lambda u: level_from_uid(u) if u.replace(".", "").isdigit() else 1,
        reverse=True,
    )

    for uid in sorted_uids:
        node = nodes[uid]

        if not node.subtree_element_ids:
            node.subtree_element_ids = list(node.own_element_ids or [])

        for child in node.children:
            if child.subtree_element_ids:
                node.subtree_element_ids.extend(child.subtree_element_ids)

        node.subtree_element_ids = list(dict.fromkeys(node.subtree_element_ids))

        own_count = len(node.own_element_ids or [])
        subtree_count = len(node.subtree_element_ids or [])
        logger.debug(
            "structure.node.subtree_built",
            extra={
                "document_id": document_id,
                "clause_uid": node.clause_uid,
                "level": node.level,
                "own_count": own_count,
                "subtree_count": subtree_count,
                "children_count": len(node.children or []),
                "suspicious_parent_own_scope": bool(node.children)
                and own_count >= 0.8 * subtree_count
                and subtree_count > 0,
            },
        )

        