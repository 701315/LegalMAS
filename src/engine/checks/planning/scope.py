# src/engine/checks/planning/scope.py

"""
Scope resolver: определяет, какие сегменты документа включать в анализ.
"""

from __future__ import annotations

from typing import Any

from core.logging import get_logger

logger = get_logger(__name__)


class ScopeResolver:
    """
    Определяет, какие сегменты включать в corpus чанков,
    и фильтрует чанки по segment-aware metadata.
    """

    def __init__(self, checks_scope: dict[str, Any] | None = None):
        self.checks_scope = checks_scope or {}

    def resolve_scope_flags(self) -> tuple[bool, set[str]]:
        """
        Определить, какие сегменты включать в corpus чанков.

        Возвращает:
        - include_primary: включать ли primary-сегмент;
        - include_types: множество segment_type, которые надо включить.

        Поддерживаемые пресеты:
        - primary_only
        - appendices_only
        - primary_and_appendices

        Если scope не задан, по умолчанию включаем primary + appendix.
        """
        scope = self.checks_scope
        preset = str(scope.get("scope_preset") or "").strip().lower()

        if preset == "primary_only":
            return True, set()

        if preset == "appendices_only":
            return False, {"appendix"}

        if preset == "primary_and_appendices":
            return True, {"appendix"}

        include_primary = bool(scope.get("include_primary", True))
        include_types_raw = scope.get("include_segment_types") or []
        include_types = {
            str(t).strip().lower()
            for t in include_types_raw
            if str(t).strip()
        }

        if not scope:
            return True, {"appendix"}

        return include_primary, include_types

    def filter_chunks_by_scope(
        self,
        chunks: list[dict],
        *,
        include_primary: bool | None = None,
        include_types: set[str] | None = None,
    ) -> list[dict]:
        """
        Отфильтровать чанки по segment-aware metadata.

        Если include_primary / include_types не переданы,
        использует resolve_scope_flags() для определения.

        Ожидаемые поля в metadata:
        - segment_type
        - is_primary_segment (предпочтительно) или fallback: is_primary
        """
        if not chunks:
            return []

        if include_primary is None or include_types is None:
            resolved_primary, resolved_types = self.resolve_scope_flags()
            if include_primary is None:
                include_primary = resolved_primary
            if include_types is None:
                include_types = resolved_types

        filtered: list[dict] = []

        for ch in chunks:
            meta = ch.get("metadata") or {}

            seg_type = str(meta.get("segment_type") or "").strip().lower()

            if "is_primary_segment" in meta:
                is_primary = bool(meta.get("is_primary_segment"))
            else:
                is_primary = bool(meta.get("is_primary"))

            if is_primary and include_primary:
                filtered.append(ch)
                continue

            if seg_type and seg_type in include_types:
                filtered.append(ch)
                continue

        return filtered
    
    