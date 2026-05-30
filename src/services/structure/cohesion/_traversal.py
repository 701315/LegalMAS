# src/services/structure/cohesion/_traversal.py

"""
Traversal утилиты для Phase 8 — Semantic Cohesion Analysis.

Работает исключительно с FrozenHierarchyNode (immutable tree).

Контракт:
- все функции pure (нет side effects);
- порядок обхода deterministic;
- complexity O(N) для всех traversal операций.

Важно:
- НЕ дублирует _hierarchy_builder/_traversal.py;
- тот модуль работает с MutableHierarchyNode на стадии assembly;
- этот модуль работает с FrozenHierarchyNode после freeze().
"""

from __future__ import annotations

from collections.abc import Generator

from services.structure.models import FrozenHierarchyNode


# ============================================================================
# Базовый traversal
# ============================================================================

def walk_preorder(
    node: FrozenHierarchyNode,
) -> Generator[FrozenHierarchyNode, None, None]:
    """
    Preorder DFS обход поддерева.

    Порядок: parent → children слева направо.
    Используется для построения ordered sequence узлов
    в том порядке как они встречаются в документе.

    Complexity: O(N) где N = узлы в поддереве.
    """
    yield node
    for child in node.children:
        yield from walk_preorder(child)


def walk_preorder_forest(
    root_nodes: list[FrozenHierarchyNode],
) -> Generator[FrozenHierarchyNode, None, None]:
    """
    Preorder DFS обход всего forest (списка root nodes).

    Возвращает узлы в document order.
    Complexity: O(N) где N = все узлы дерева.
    """
    for root in root_nodes:
        yield from walk_preorder(root)


# ============================================================================
# Sibling extraction — основа для sliding window
# ============================================================================

def extract_siblings_per_parent(
    root_nodes: list[FrozenHierarchyNode],
) -> list[list[FrozenHierarchyNode]]:
    """
    Извлекает списки siblings для каждого parent узла.

    Возвращает список групп. Каждая группа — direct children одного parent.
    Root nodes трактуются как siblings между собой (их parent = document root).

    Пример для дерева:
        1
        ├── 1.1
        ├── 1.2
        └── 1.3
        2
        └── 2.1

    Результат:
        [[1, 2],          ← root level siblings
         [1.1, 1.2, 1.3], ← children of 1
         [2.1]]           ← children of 2

    Complexity: O(N).
    """
    if not root_nodes:
        return []

    groups: list[list[FrozenHierarchyNode]] = []

    # Root nodes — первая группа siblings
    if root_nodes:
        groups.append(list(root_nodes))

    # Для каждого узла — его children как отдельная группа siblings
    for node in walk_preorder_forest(root_nodes):
        if node.children:
            groups.append(list(node.children))

    return groups


# ============================================================================
# Parent lookup index — для within_section edges
# ============================================================================

def build_parent_index(
    root_nodes: list[FrozenHierarchyNode],
) -> dict[str, FrozenHierarchyNode | None]:
    """
    Строит индекс effective_uid → parent node.

    Root nodes маппируются на None (нет parent).

    Используется для:
    - within_section edge построения (parent → child);
    - определения глубины контекста при cohesion scoring.

    Complexity: O(N).
    """
    parent_index: dict[str, FrozenHierarchyNode | None] = {}

    for root in root_nodes:
        parent_index[root.effective_uid] = None

    for node in walk_preorder_forest(root_nodes):
        for child in node.children:
            parent_index[child.effective_uid] = node

    return parent_index


# ============================================================================
# Document order sequence — основа для sliding window по всему дереву
# ============================================================================

def build_document_order_sequence(
    root_nodes: list[FrozenHierarchyNode],
) -> list[FrozenHierarchyNode]:
    """
    Строит список всех узлов в document order (preorder DFS).

    Используется для глобального sliding window если нужно
    анализировать cohesion across section boundaries.

    Порядок стабильный и deterministic для одного и того же дерева.

    Complexity: O(N).
    """
    return list(walk_preorder_forest(root_nodes))


# ============================================================================
# Numbering continuity helper
# ============================================================================

def _extract_numeric_parts(raw_uid: str) -> list[int] | None:
    """
    Парсит numeric uid в список int компонентов.

    "1.2.3" → [1, 2, 3]
    "appendix-A" → None (не numeric)
    "" → None

    Возвращает None если uid не является strict numeric.
    """
    if not raw_uid:
        return None
    parts = raw_uid.strip().split(".")
    try:
        return [int(p) for p in parts]
    except ValueError:
        return None


def are_numbering_continuous(
    left: FrozenHierarchyNode,
    right: FrozenHierarchyNode,
) -> bool:
    """
    Проверяет является ли нумерация между двумя узлами непрерывной.

    Непрерывность означает:
    - оба узла имеют strict numeric uid;
    - они на одном уровне (одинаковая глубина uid);
    - right следует сразу за left по последнему компоненту.

    Примеры:
        "1.1" → "1.2" : True  (последний компонент: 1 → 2)
        "1.1" → "1.3" : False (gap: пропущена 1.2)
        "1"   → "2"   : True
        "1"   → "appendix-A" : False (разные типы)

    Complexity: O(depth) где depth ≤ max_uid_depth.
    """
    left_parts = _extract_numeric_parts(left.raw_uid)
    right_parts = _extract_numeric_parts(right.raw_uid)

    # Оба должны быть numeric
    if left_parts is None or right_parts is None:
        return False

    # Одинаковая глубина
    if len(left_parts) != len(right_parts):
        return False

    # Префикс одинаковый, последний компонент отличается на 1
    if len(left_parts) == 0:
        return False

    prefix_len = len(left_parts) - 1
    if left_parts[:prefix_len] != right_parts[:prefix_len]:
        return False

    return right_parts[-1] == left_parts[-1] + 1


def is_appendix_boundary(
    left: FrozenHierarchyNode,
    right: FrozenHierarchyNode,
) -> bool:
    """
    Проверяет является ли граница между узлами appendix boundary.

    Appendix boundary = один из узлов является appendix root
    (scope содержит "appendix" или raw_uid начинается с "appendix-").

    Используется как strong cohesion break сигнал.
    """
    def _is_appendix(node: FrozenHierarchyNode) -> bool:
        scope = (node.scope or "").lower()
        raw_uid = (node.raw_uid or "").lower()
        return (
            scope.startswith("appendix")
            or scope.startswith("приложение")
            or scope.startswith("annex")
            or scope.startswith("schedule")
            or scope.startswith("exhibit")
            or raw_uid.startswith("appendix-")
            or raw_uid.startswith("annex-")
        )

    return _is_appendix(left) or _is_appendix(right)


