# src/services/structure/_clause_detector/routing.py

"""
Global Routing Pass — универсальная пост-обработка ClauseTree.

Решает фундаментальную проблему span-based extraction в документах
с многоколоночной версткой (bilingual, RTL, mixed-layout):
пункты физически попадают в спан соседней главы, но их логический
адрес (UID-префикс) однозначно определяет принадлежность.

Агностичность и надежность:
    • Язык: RU, EN, DE, FR, bilingual, multilingual
    • Нумерация: 1.1, I.a, § 4.2, Статья 1, (a), Article 3
    • Пространственные границы (Spatial Envelope): строгая проверка физического
      вхождения страницы узла в диапазон страниц целевой главы [start_page, end_page].
    • Изоляция Scope (Scope Boundary Shield): запрет переноса между основным договором
      и приложениями.
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from services.structure._models._constants import NODE_KIND_LEAF, NODE_KIND_SECTION
from services.structure._models._identity import make_effective_uid
from services.structure._models._nodes import MutableHierarchyNode

logger = structlog.get_logger(__name__)

_SEPARATORS = frozenset(". )(\t-")


def _get_raw_uid(node: MutableHierarchyNode) -> str:
    return (node.raw_uid or "").strip()


def _is_valid_separator(char: str) -> bool:
    return char in _SEPARATORS


def _is_chapter_node(node: MutableHierarchyNode) -> bool:
    uid = _get_raw_uid(node)
    if not uid or uid.startswith("__"):
        return False
    return True


# ──────────────────────────────────────────────
# Longest-prefix matching + Spatial Envelope
# ──────────────────────────────────────────────

def _find_owning_chapter(
    node: MutableHierarchyNode,
    chapters: dict[str, MutableHierarchyNode],
    page_tolerance: int = 1,
) -> MutableHierarchyNode | None:
    """
    Longest prefix match с ДВОЙНОЙ ЗАЩИТОЙ:
    1. Проверка совпадения UID-префиксов.
    2. Spatial Page Envelope: страница узла ДОЛЖНА входить в физический диапазон
       страниц главы [start_page - tolerance, end_page + tolerance].
       Это предотвращает улет элементов со стр. 21 в главу на стр. 13.
    3. Scope Boundary Shield: запрет переноса между несовместимыми scope.
    """
    node_uid = _get_raw_uid(node)
    if not node_uid or node_uid.startswith("__"):
        return None

    node_start = getattr(node, "start_page", 0)
    node_end = getattr(node, "end_page", node_start)

    best: MutableHierarchyNode | None = None
    best_len: int = 0

    for ch_node in chapters.values():
        # 1. 🛡️ Scope Boundary Shield (договор vs приложения)
        if node.scope and ch_node.scope and node.scope != ch_node.scope:
            continue

        # 2. 🗺️ Spatial Page Envelope Check
        ch_start = getattr(ch_node, "start_page", 0) - page_tolerance
        ch_end = getattr(ch_node, "end_page", ch_start) + page_tolerance

        # Если узел физически находится вне допустимых страниц главы — перенос ЗАПРЕЩЕН
        if node_start < ch_start or node_end > ch_end:
            continue

        # 3. Проверка префикса UID
        ch_raw = _get_raw_uid(ch_node)
        if not node_uid.startswith(ch_raw):
            continue

        rest = node_uid[len(ch_raw):]
        if not rest:
            continue

        if _is_valid_separator(rest[0]):
            if len(ch_raw) > best_len:
                best_len = len(ch_raw)
                best = ch_node

    return best


def _find_root_of(
    node: MutableHierarchyNode,
    roots: list[MutableHierarchyNode],
) -> MutableHierarchyNode | None:
    for root in roots:
        if _contains(root, node):
            return root
    return None


def _contains(parent: MutableHierarchyNode, target: MutableHierarchyNode) -> bool:
    if parent is target:
        return True
    for child in parent.children:
        if _contains(child, target):
            return True
    return False


def _detach_subtree(
    node: MutableHierarchyNode,
    roots: list[MutableHierarchyNode],
) -> bool:
    def _walk(parent: MutableHierarchyNode) -> bool:
        new_children = [c for c in parent.children if c is not node]
        if len(new_children) != len(parent.children):
            parent.children = new_children
            return True
        for c in list(parent.children):
            if _walk(c):
                return True
        return False

    for root in roots:
        if _walk(root):
            return True
    return False


def _find_by_uid_in_subtree(
    root: MutableHierarchyNode,
    target_uid: str,
) -> MutableHierarchyNode | None:
    if _get_raw_uid(root) == target_uid:
        return root
    for child in root.children:
        found = _find_by_uid_in_subtree(child, target_uid)
        if found is not None:
            return found
    return None


def _compute_parent_uid(node_uid: str) -> str | None:
    if not node_uid:
        return None

    last_sep_idx = -1
    for i, ch in enumerate(node_uid):
        if ch in ".)":
            last_sep_idx = i

    if last_sep_idx <= 0:
        return None

    parent_uid = node_uid[:last_sep_idx].strip()
    return parent_uid if parent_uid else None


def _create_placeholder(
    parent_uid: str,
    chapter: MutableHierarchyNode,
    parent_level: int,
) -> MutableHierarchyNode:
    scope = chapter.scope or "main_contract"
    eff_uid = make_effective_uid(scope, parent_uid)

    return MutableHierarchyNode(
        effective_uid=eff_uid,
        title="",
        level=parent_level + 1,
        raw_uid=parent_uid,
        scope=scope,
        node_kind=NODE_KIND_SECTION,
        node_origin="technical_fallback",
        content_mode="skeleton",
        citability="technical",
        own_element_ids=[],
        subtree_element_ids=[],
        start_page=chapter.start_page,
        end_page=chapter.end_page,
        children=[],
    )


def _find_or_create_parent(
    node: MutableHierarchyNode,
    target_chapter: MutableHierarchyNode,
) -> MutableHierarchyNode:
    node_uid = _get_raw_uid(node)
    parent_uid = _compute_parent_uid(node_uid)

    if parent_uid is None or parent_uid == _get_raw_uid(target_chapter):
        return target_chapter

    existing = _find_by_uid_in_subtree(target_chapter, parent_uid)
    if existing is not None:
        return existing

    placeholder = _create_placeholder(
        parent_uid, target_chapter, target_chapter.level
    )

    grandparent = _find_or_create_parent(placeholder, target_chapter)
    grandparent.children = list(grandparent.children) + [placeholder]
    _update_node_page_envelope(placeholder, grandparent)

    return placeholder


def _update_node_page_envelope(
    node: MutableHierarchyNode,
    parent: MutableHierarchyNode,
) -> None:
    """Расширяет физический конверт страниц родителя при добавлении ребенка."""
    parent.start_page = min(parent.start_page, node.start_page)
    parent.end_page = max(parent.end_page, node.end_page)


def _update_levels_recursive(node: MutableHierarchyNode, parent_level: int) -> None:
    node.level = parent_level + 1
    for child in node.children:
        _update_levels_recursive(child, node.level)


def _reset_hashes_recursive(node: MutableHierarchyNode) -> None:
    node.structural_hash = None
    for child in node.children:
        _reset_hashes_recursive(child)


def _cleanup_empty_sections(node: MutableHierarchyNode) -> int:
    removed = 0
    new_children: list[MutableHierarchyNode] = []

    for child in node.children:
        removed += _cleanup_empty_sections(child)
        if child.node_kind == NODE_KIND_SECTION and not child.children:
            removed += 1
            continue
        new_children.append(child)

    node.children = new_children

    # Гарантия Pydantic-валидации: секция без детей трансформируется в leaf
    if node.node_kind == NODE_KIND_SECTION and not node.children:
        node.node_kind = NODE_KIND_LEAF

    return removed


def _deduplicate_subtree(node: MutableHierarchyNode) -> int:
    removed = 0
    seen: dict[str, MutableHierarchyNode] = {}
    unique: list[MutableHierarchyNode] = []

    for child in node.children:
        uid = _get_raw_uid(child)
        if not uid:
            unique.append(child)
            removed += _deduplicate_subtree(child)
            continue

        if uid in seen:
            existing = seen[uid]
            if len(child.own_element_ids) > len(existing.own_element_ids):
                unique = [c if c is not existing else child for c in unique]
                seen[uid] = child
            removed += 1
        else:
            seen[uid] = child
            unique.append(child)

        removed += _deduplicate_subtree(child)

    node.children = unique
    return removed


def _natural_sort_key(uid: str) -> tuple[tuple[int, Any], ...]:
    """Безопасный ключ сортировки (исключает TypeError между str и int)."""
    parts = re.split(r"[.\s)]+", uid.strip())
    result: list[tuple[int, Any]] = []
    for part in parts:
        if not part:
            continue
        try:
            result.append((0, int(part)))
        except ValueError:
            result.append((1, part.lower()))
    return tuple(result)


def _sort_children_recursive(node: MutableHierarchyNode) -> None:
    node.children.sort(key=lambda c: _natural_sort_key(_get_raw_uid(c)))
    for child in node.children:
        _sort_children_recursive(child)


def global_routing_pass(
    mutable_roots: list[MutableHierarchyNode],
) -> dict[str, int]:
    stats = {"moved": 0, "synthetic_parents": 0, "deduplicated": 0, "empty_cleaned": 0}

    chapters: dict[str, MutableHierarchyNode] = {}
    for root in mutable_roots:
        if _is_chapter_node(root):
            chapters[_get_raw_uid(root)] = root

    if not chapters:
        return stats

    misplaced: list[tuple[MutableHierarchyNode, MutableHierarchyNode]] = []

    # Собираем порядок следования глав по страницам
    ch_list = sorted(chapters.values(), key=lambda c: getattr(c, "start_page", 0))
    next_ch_start = {}
    for i, ch in enumerate(ch_list):
        ch_uid = _get_raw_uid(ch)
        next_p = ch_list[i+1].start_page if i + 1 < len(ch_list) else 999
        next_ch_start[ch_uid] = next_p

    invalid_nodes = []

    def _scan(node: MutableHierarchyNode, current_root: MutableHierarchyNode) -> None:
        for child in list(node.children):
            target = _find_owning_chapter(child, chapters)

            if target is not None and target is not current_root:
                misplaced.append((child, target))
            else:
                # 🛡️ ПРОВЕРКА НА ВЫХОД ЗА ГРАНИЦЫ СЛЕДУЮЩЕЙ ГЛАВЫ
                cur_uid = _get_raw_uid(current_root)
                max_allowed_page = next_ch_start.get(cur_uid, 999) + 1
                child_page = getattr(child, "start_page", 0)

                if child_page > max_allowed_page:
                    # Узел (например, 7.5 на стр. 21) находится ПОСЛЕ начала следующей главы (стр. 15)
                    invalid_nodes.append(child)
                else:
                    effective_root = target if target is not None else current_root
                    _scan(child, effective_root)

    for root in mutable_roots:
        _scan(root, root)

    if not misplaced:
        for root in mutable_roots:
            stats["deduplicated"] += _deduplicate_subtree(root)
            stats["empty_cleaned"] += _cleanup_empty_sections(root)
            _sort_children_recursive(root)
        return stats

    # Удаляем фантомные узлы, выходящие за пределы следующих глав (7.5, 7.7 со стр. 21)
    for inv in invalid_nodes:
        _detach_subtree(inv, mutable_roots)
        stats["empty_cleaned"] += 1

    for node, target_chapter in misplaced:
        node_uid = _get_raw_uid(node)

        if not _detach_subtree(node, mutable_roots):
            continue

        parent = _find_or_create_parent(node, target_chapter)
        if _get_raw_uid(parent) != _get_raw_uid(target_chapter):
            stats["synthetic_parents"] += 1

        parent.children = list(parent.children) + [node]

        _update_levels_recursive(node, parent.level)
        _update_node_page_envelope(node, parent)
        _reset_hashes_recursive(node)
        parent.structural_hash = None

        stats["moved"] += 1

    for root in mutable_roots:
        stats["empty_cleaned"] += _cleanup_empty_sections(root)
        stats["deduplicated"] += _deduplicate_subtree(root)
        _sort_children_recursive(root)

    return stats
