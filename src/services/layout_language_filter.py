# src/workers/layout_language_filter.py

"""
Layout language filter.

Назначение:
- взять textlayoutraw JSON (layout после извлечения),
- определить язык каждого текстового элемента по его содержимому,
- оставить только элементы с русским текстом (кириллица),
- вернуть новый layout в том же формате.

Почему так:
- многие документы двуязычные (EN/RU, две колонки),
- для анализа и классификации мы хотим работать только с русской частью,
  чтобы упростить модели и правила.

Важно:
- Функции не зависят от БД и MinIO, работают только с dict/list.
- Формат входа/выхода совпадает со схемой build_text_layout_raw.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List


def _detect_script(text: str) -> str:
    """
    Грубое определение "скрипта" строки.

    Возвращает:
    - "ru"     — если заметная часть символов кириллическая;
    - "en"     — если заметная часть символов латинская;
    - "mixed"  — если и кириллицы, и латиницы много;
    - "other"  — если нет ни того, ни другого (цифры, знаки).

    Для наших целей (отделить RU от EN в договорах) этого достаточно.
    """
    cyr = lat = 0
    for ch in text:
        code = ord(ch)
        # Диапазоны Юникода для основной кириллицы и доп. блока
        if 0x0400 <= code <= 0x04FF or 0x0500 <= code <= 0x052F:
            cyr += 1
        # Базовая латиница + расширенная латиница
        elif 0x0041 <= code <= 0x005A or 0x0061 <= code <= 0x007A:
            lat += 1
        elif 0x00C0 <= code <= 0x00FF:
            lat += 1

    total = cyr + lat
    if total == 0:
        return "other"

    cyr_ratio = cyr / total
    lat_ratio = lat / total

    # Если кириллица явно доминирует
    if cyr_ratio >= 0.7 and cyr >= 3:
        return "ru"
    # Если латиница явно доминирует
    if lat_ratio >= 0.7 and lat >= 3:
        return "en"
    return "mixed"


def filter_layout_to_ru(layout: Dict[str, Any]) -> Dict[str, Any]:
    """
    Оставить в layout только элементы с русским текстом.

    Простая версия:
    - Для каждого элемента считаем "скрипт" по тексту.
    - Удаляем явно английские элементы (script == "en").
    - Элементы "ru" и "mixed" оставляем.
      (mixed часто встречается в строках с цифрами, сокращениями и т.п.)

    Более умный анализ колонок по bbox можно добавить позже,
    но даже эта фильтрация уже уберёт большую часть чисто английских строк.
    """
    elements: List[Dict[str, Any]] = layout.get("elements") or []
    filtered: List[Dict[str, Any]] = []

    for el in elements:
        text = (el.get("text") or "").strip()
        if not text:
            # Пустые/почти пустые элементы пропускаем как есть
            continue

        script = _detect_script(text)

        # Отбрасываем чисто английские строки.
        if script == "en":
            continue

        # Для русских и смешанных строк элемент оставляем как есть.
        filtered.append(el)

    # Таблицы и метаданные не трогаем.
    tables = layout.get("tables") or []
    metadata = layout.get("metadata") or {}

    # Обновим счётчик элементов в metadata, чтобы он соответствовал фильтру.
    metadata = dict(metadata)
    metadata["element_count"] = len(filtered)

    return {
        "document_version_id": layout.get("document_version_id"),
        "document_id": layout.get("document_id"),
        "elements": filtered,
        "tables": tables,
        "metadata": metadata,
    }
