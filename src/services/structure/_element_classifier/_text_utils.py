# src/services/structure/element_classifier/_text_utils.py

"""Утилиты для нормализации текста и безопасного приведения типов.

Содержит вспомогательные функции для:
- Нормализации текста (удаление лишних пробелов, приведение регистра)
- Безопасного преобразования в int/float
- Извлечения bbox из элемента
"""

from __future__ import annotations

from typing import Any

from ._config import NORMALIZE_NUM_SIGN_RE, PUNCT_SPACES_RE, WHITESPACE_RE


def _normalize_text(text: str) -> str:
    """Нормализует текст для последующего анализа.

    Выполняет:
    - Замену неразрывных пробелов на обычные
    - Нормализацию буквы 'ё' в 'е'
    - Нормализацию знаков номера (№, N, No) в "№ "
    - Корректировку пробелов вокруг пунктуации
    - Схлопывание множественных пробелов

    Args:
        text: Исходный текст

    Returns:
        Нормализованный текст
    """
    text = text.replace("\u00a0", " ")
    text = text.replace("ё", "е").replace("Ё", "Е")
    text = NORMALIZE_NUM_SIGN_RE.sub("№ ", text)
    text = PUNCT_SPACES_RE.sub(r"\1 ", text)
    text = WHITESPACE_RE.sub(" ", text)
    return text.strip()


def _normalize_for_match(text: str) -> str:
    """Нормализует текст для сопоставления с паттернами (нижний регистр).

    Args:
        text: Исходный текст

    Returns:
        Нормализованный текст в нижнем регистре
    """
    return _normalize_text(text).lower()


def _safe_int(value: Any, default: int) -> int:
    """Безопасно преобразует значение в int.

    Args:
        value: Преобразуемое значение
        default: Значение по умолчанию при ошибке

    Returns:
        Целое число или default при ошибке
    """
    try:
        return int(value)
    except Exception:
        return default


def _safe_bbox(bbox: Any) -> list[float]:
    """Безопасно извлекает bounding box из элемента.

    Args:
        bbox: Bounding box в любом формате (list, tuple, None)

    Returns:
        Список из 4 float значений [x0, y0, x1, y1]
    """
    if not isinstance(bbox, list | tuple):
        return [0.0, 0.0, 0.0, 0.0]
    values = list(bbox[:4])
    while len(values) < 4:
        values.append(0.0)
    out: list[float] = []
    for v in values:
        try:
            out.append(float(v))
        except Exception:
            out.append(0.0)
    return out
