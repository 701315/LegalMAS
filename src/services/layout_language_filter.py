"""
Layout language filter.


Назначение:
- взять text_layout_raw JSON (layout после извлечения),
- определить язык каждого текстового элемента по его содержимому,
- при необходимости оставить только элементы выбранного языка (ru/en),
- вернуть новый layout в том же формате.


Почему так:
- многие документы двуязычные (EN/RU, две колонки или две строки подряд),
- для анализа и классификации мы хотим работать только с одной языковой
  дорожкой, чтобы упростить модели и правила.


Важно:
- Функции не зависят от БД и MinIO, работают только с dict/list.
- Формат входа/выхода совпадает со схемой build_text_layout_raw.
"""

from __future__ import annotations

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
    cyr = 0
    lat = 0

    for ch in text:
        code = ord(ch)

        # Диапазоны Юникода для основной кириллицы и доп. блока
        if 0x0400 <= code <= 0x04FF or 0x0500 <= code <= 0x052F:
            cyr += 1
        # Базовая латиница + немного расширенной латиницы
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


def detect_languages_in_layout(layout: Dict[str, Any]) -> List[str]:
    """
    Определить, какие языки реально присутствуют в layout.

    - Берём все элементы layout["elements"].
    - Для каждого элемента смотрим текст и определяем "скрипт".
    - Собираем коды языков 'ru' и 'en', если они реально встретились.

    Если вообще не нашли ни русских, ни английских символов, возвращаем ["ru"]
    как дефолт (система ориентирована на русские документы).
    """
    elements: List[Dict[str, Any]] = layout.get("elements") or []
    langs: set[str] = set()

    for el in elements:
        text = (el.get("text") or "").strip()
        if not text:
            continue

        script = _detect_script(text)
        if script in ("ru", "en"):
            langs.add(script)

    if not langs:
        return ["ru"]

    return sorted(langs)


def filter_layout_to_language(
    layout: Dict[str, Any],
    target_language: str,
) -> Dict[str, Any]:
    """
    Оставить в layout только элементы выбранного языка (ru/en).

    Жёсткая политика для реально одноязычных чанков:

    - Для каждого элемента считаем "скрипт" по тексту.
    - Если target_language == "ru":
        * оставляем только элементы со script == "ru";
        * выкидываем "en", "mixed", "other".
    - Если target_language == "en":
        * оставляем только элементы со script == "en";
        * выкидываем "ru", "mixed", "other".
    - Для любых других значений target_language (неожиданный код языка)
      фильтрацию не применяем и возвращаем layout как есть.

    Таблицы и метаданные не трогаем, но обновляем metadata["element_count"].
    """
    target = (target_language or "").lower()
    if target not in ("ru", "en"):
        return layout

    elements: List[Dict[str, Any]] = layout.get("elements") or []
    filtered: List[Dict[str, Any]] = []

    for el in elements:
        text = (el.get("text") or "").strip()
        if not text:
            continue

        script = _detect_script(text)

        if target == "ru":
            if script == "ru":
                filtered.append(el)
        elif target == "en":
            if script == "en":
                filtered.append(el)

    tables = layout.get("tables") or []
    metadata = layout.get("metadata") or {}

    metadata = dict(metadata)
    metadata["element_count"] = len(filtered)

    return {
        "document_version_id": layout.get("document_version_id"),
        "document_id": layout.get("document_id"),
        "elements": filtered,
        "tables": tables,
        "metadata": metadata,
    }


def filter_layout_to_ru(layout: Dict[str, Any]) -> Dict[str, Any]:
    """
    Backwards‑compatible обёртка для старого кода: фильтрация до русского.
    """
    return filter_layout_to_language(layout, "ru")
