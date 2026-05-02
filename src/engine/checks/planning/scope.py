# src/engine/checks/planning/scope.py

"""
Scope resolver: определяет, какие сегменты документа включать в анализ.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from core.logging import get_logger

logger = get_logger(__name__)


def _normalize_segment_types(raw: Any) -> set[str]:
    """
    Нормализовать include_segment_types в множество непустых lowercase-строк.

    Для непрофессионального программиста:
    - Если raw — список, tuple, set и т.п., превращаем значения в строки,
      чистим пробелы и приводим к lowercase.
    - Если raw — строка или неитерируемый объект, считаем конфигурацию некорректной
      и возвращаем пустое множество.
    """
    if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes)):
        return set()

    return {
        str(t).strip().lower()
        for t in raw
        if str(t).strip()
    }


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

        if not scope:
            return True, {"appendix"}

        include_primary = bool(scope.get("include_primary", True))
        include_types = _normalize_segment_types(
            scope.get("include_segment_types") or []
        )

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

        Важное правило для непрофессионального программиста:
        - Если у чанка вообще нет segment-aware metadata,
          считаем его primary-сегментом по умолчанию.
        - Это защита для legacy / transitional snapshot'ов,
          чтобы не потерять весь корпус из-за неполной metadata.
        """
        if not chunks:
            logger.debug("ScopeResolver: empty input chunks")
            return []

        try:
            if include_primary is None or include_types is None:
                resolved_primary, resolved_types = self.resolve_scope_flags()
                if include_primary is None:
                    include_primary = resolved_primary
                if include_types is None:
                    include_types = resolved_types

            include_types = _normalize_segment_types(include_types or set())

            filtered: list[dict] = []

            for ch in chunks:
                meta = ch.get("metadata")
                if not isinstance(meta, dict):
                    meta = {}

                seg_type = str(meta.get("segment_type") or "").strip().lower()

                has_primary_flag = (
                    "is_primary_segment" in meta or "is_primary" in meta
                )
                has_segment_type = bool(seg_type)

                if "is_primary_segment" in meta:
                    is_primary = bool(meta.get("is_primary_segment"))
                else:
                    is_primary = bool(meta.get("is_primary"))

                # Legacy-safe fallback:
                # если segment-aware metadata вообще отсутствует,
                # считаем такой чанк primary.
                if not has_primary_flag and not has_segment_type:
                    is_primary = True

                if is_primary and include_primary:
                    filtered.append(ch)
                    continue

                if seg_type and seg_type in include_types:
                    filtered.append(ch)
                    continue

            if not filtered:
                logger.warning(
                    "ScopeResolver: all chunks filtered out by scope",
                    extra={
                        "input_chunks": len(chunks),
                        "include_primary": include_primary,
                        "include_types": sorted(include_types),
                    },
                )
            else:
                logger.info(
                    "ScopeResolver: chunks filtered by scope",
                    extra={
                        "input_chunks": len(chunks),
                        "output_chunks": len(filtered),
                        "include_primary": include_primary,
                        "include_types": sorted(include_types),
                    },
                )

            return filtered

        except Exception as e:
            logger.exception(
                "ScopeResolver: failed to filter chunks by scope, returning input chunks",
                extra={
                    "input_chunks": len(chunks),
                    "error": str(e),
                },
            )
            return chunks
        

    
    