# src/services/structure/_hierarchy_builder/_types.py

"""Определения структур данных для процесса сборки иерархии."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class HeadingCandidate:
    """
    Минимальный входной тип для сборки иерархии.

    Поля должны соответствовать контракту, ожидаемому от heading_builder.

    Примечание:
    дополнительные поля ниже вводятся как forward-compatible contract
    для TOC-aware scoring, appendix detection и richer structural evidence.
    Они не обязательны для всех call sites, но позволяют постепенно
    усиливать pipeline без ломающих изменений интерфейса.
    """

    elem_i: int
    uid: str
    title: str
    page: int
    scope: str | None = None
    raw_uid: str | None = None
    effective_uid: str | None = None
    metadata: dict[str, Any] | None = None

    # Forward-compatible optional evidence fields
    normalized_title: str | None = None
    toc_entry: bool = False
    toc_match_type: str | None = None
    toc_match_score: float | None = None
    is_appendix: bool = False
    is_toc_like: bool = False


@dataclass(slots=True)
class OwnRangeComputation:
    """Результат вычисления физического диапазона элементов, которыми владеет узел."""

    start_elem_i: int
    end_elem_i: int  # Гарантированный int (индекс конца или длина списка)
    range_end_reason: str

    
