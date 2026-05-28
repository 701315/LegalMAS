# src/services/structure/hierarchy_builder.py

"""
Сборка иерархии ClauseTree из уже отфильтрованных heading candidates.
Публичный фасад.
"""

from __future__ import annotations

from ._hierarchy_builder._core import build_clause_hierarchy
from ._hierarchy_builder._traversal import populate_subtree_element_ids
from ._hierarchy_builder._types import HeadingCandidate
from ._hierarchy_builder._utils import find_parent_raw_uid_within_scope, level_from_uid

__all__ = [
    "HeadingCandidate",
    "build_clause_hierarchy",
    "populate_subtree_element_ids",
    "level_from_uid",
    "find_parent_raw_uid_within_scope",
]
