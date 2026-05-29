# src/services/structure/_hierarchy_builder/_utils.py

"""Утилиты нормализации и логики UID с исправленной типизацией."""

from __future__ import annotations

import re
from typing import Any

from services.structure._models._constants import DEFAULT_SCOPE
from services.structure._models._identity import make_effective_uid, split_effective_uid

from ._types import HeadingCandidate

_NUMERIC_UID_RE = re.compile(r"^\d+(?:\.\d+)*$")


def _safe_ratio(numerator: int, denominator: int) -> float:
    """Безопасный расчёт пропорции."""
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def _is_strict_numeric_uid(uid: str | None) -> bool:
    """Проверка, является ли UID строго числовым (1.2.3)."""
    if not uid:
        return False
    return bool(_NUMERIC_UID_RE.fullmatch(uid.strip()))


def _normalize_scope(value: Any) -> str:
    """Приведение scope к каноничному виду str."""
    if value is None:
        return str(DEFAULT_SCOPE)
    return str(value).strip() or str(DEFAULT_SCOPE)


def _normalize_uid(value: Any) -> str:
    """Нормализация UID."""
    return str(value or "").strip()


def _normalize_title(value: Any) -> str:
    """Нормализация заголовка."""
    return str(value or "").strip()


def level_from_uid(uid: str) -> int:
    """Определение уровня вложенности (глубины) UID."""
    normalized = _normalize_uid(uid)
    if not _is_strict_numeric_uid(normalized):
        raise ValueError(f"level_from_uid expects strict numeric uid, got {uid!r}")
    return normalized.count(".") + 1


def _heading_scope(heading: HeadingCandidate) -> str:
    """Извлечение scope из кандидата."""
    return _normalize_scope(heading.scope)


def _heading_raw_uid(heading: HeadingCandidate) -> str:
    """Извлечение raw_uid из кандидата."""
    raw_uid = _normalize_uid(heading.raw_uid)
    if raw_uid:
        return raw_uid
    return _normalize_uid(heading.uid)


def _heading_effective_uid(heading: HeadingCandidate) -> str:
    """Получение канонического эффективного UID."""
    explicit = _normalize_uid(heading.effective_uid)
    if explicit:
        scope, raw_uid = split_effective_uid(explicit)
        return make_effective_uid(scope, raw_uid)
    return make_effective_uid(_heading_scope(heading), _heading_raw_uid(heading))


def find_parent_raw_uid_within_scope(
    raw_uid: str,
    nodes_by_raw_uid: dict[str, Any],  # ClauseNode заменяем на Any для избежания циклов
) -> str | None:
    """Поиск родительского raw_uid в цепочке (1.2.3 -> 1.2)."""
    uid = _normalize_uid(raw_uid)
    if not uid or "." not in uid:
        return None

    parts = uid.split(".")
    for i in range(len(parts) - 1, 0, -1):
        candidate = ".".join(parts[:i])
        if candidate in nodes_by_raw_uid:
            return candidate
    return None


