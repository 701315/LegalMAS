# src/services/structure/hierarchy_builder.py

"""
Публичный фасад hierarchy builder.

Назначение модуля:
- дать стабильную точку входа для сборки иерархии ClauseTree;
- реэкспортировать только те типы и утилиты, которые допустимы как public API;
- скрыть внутреннюю структуру пакета services.structure._hierarchy_builder.

Важно:
- этот модуль не содержит бизнес-логики сборки иерархии;
- изменения алгоритмов должны происходить во внутренних модулях;
- внешний код должен импортировать hierarchy builder только через этот фасад.
"""

# src/services/structure/hierarchy_builder.py

from __future__ import annotations

from ._hierarchy_builder._core import (
    build_clause_hierarchy,
    DegradationInfo,
    HierarchyBuildResult,
    HierarchyResolutionAudit,   # ← обновлённое имя
    RecoveryAudit,
)
from ._hierarchy_builder._traversal import populate_subtree_element_ids
from ._hierarchy_builder._types import HeadingCandidate
from ._hierarchy_builder._utils import (
    find_parent_raw_uid_within_scope,
    level_from_uid,
)

__all__ = [
    # Canonical entry point
    "build_clause_hierarchy",
    # Typed result и вспомогательные типы
    "HierarchyBuildResult",
    "DegradationInfo",
    "RecoveryAudit",
    "HierarchyResolutionAudit",   # ← обновлённое имя
    # Входные типы
    "HeadingCandidate",
    # Утилиты
    "populate_subtree_element_ids",
    "level_from_uid",
    "find_parent_raw_uid_within_scope",
]
