# src/engine/extraction_normalization.py

from __future__ import annotations

from typing import Any, Sequence


NULL_LIKE_VALUES = frozenset(
    {
        "null",
        "none",
        # "not_found" НЕ считаем null-like:
        # это полезный бизнес-ответ, а не мусорный placeholder.
        "n/a",
        "na",
        "не найдено",
        "отсутствует",
        "нет данных",
        "",
        "unknown",
        "неизвестно",
        "-",
        "—",
    }
)


def is_null_like_value(raw: Any) -> bool:
    """
    True если значение выглядит как пустой/мусорный placeholder,
    который не должен считаться реальным business-value.
    """
    if raw is None:
        return True
    return str(raw).strip().lower() in NULL_LIKE_VALUES


def normalize_scalar_null_like_value(raw: Any) -> Any | None:
    """
    Нормализовать scalar null-like значение:
    - null-like -> None
    - иначе вернуть как есть
    """
    return None if is_null_like_value(raw) else raw


def find_allowed_candidate(
    allowed_values: Sequence[Any],
    expected_value: str,
) -> Any | None:
    """
    Найти канонический элемент из allowed_values по case-insensitive match.
    Возвращает именно значение из YAML (в исходном регистре/форме).
    """
    expected_norm = expected_value.strip().lower()
    for candidate in allowed_values or []:
        if str(candidate).strip().lower() == expected_norm:
            return candidate
    return None


def normalize_to_allowed_values(
    value: Any,
    allowed_values: Sequence[Any],
) -> Any | None:
    """
    Универсальная нормализация значения под allowed_values.

    Правила:
    - если allowed_values пустой -> вернуть value как есть;
    - если value null-like:
        * вернуть канонический 'not_found', если он разрешён;
        * иначе вернуть None;
    - если value совпадает с одним из allowed_values case-insensitive:
        * вернуть канонический вариант из YAML;
    - иначе вернуть None.
    """
    allowed = list(allowed_values or [])
    if not allowed:
        return value

    if is_null_like_value(value):
        return find_allowed_candidate(allowed, "not_found")

    value_norm = str(value).strip().lower()
    for candidate in allowed:
        if str(candidate).strip().lower() == value_norm:
            return candidate

    return None


