# src/services/layout_language_filter.py

"""
Layout language filter.

Назначение:
- взять text_layout_raw JSON (layout после извлечения),
- определить язык каждого текстового элемента по его содержимому,
- при необходимости оставить только элементы выбранного языка (ru/en),
- вернуть новый layout в том же формате.

Почему так:
- многие документы двуязычные (EN/RU, две колонки),
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

    Как это работает:
    - Берём все элементы layout["elements"].
    - Для каждого элемента смотрим текст и определяем "скрипт" (_detect_script).
    - Собираем коды языков 'ru' и 'en', если они реально встретились.

    Возвращает:
    - отсортированный список кодов языков, например ["ru"], ["en"], ["en", "ru"];
    - если вообще не нашли ни русских, ни английских символов, возвращаем ["ru"]
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
        # Ничего не нашли — считаем, что по умолчанию документ русский.
        return ["ru"]

    return sorted(langs)


def filter_layout_to_language(
    layout: Dict[str, Any],
    target_language: str,
) -> Dict[str, Any]:
    """
    Оставить в layout только элементы выбранного языка (ru/en).

    Простая версия:
    - Для каждого элемента считаем "скрипт" по тексту.
    - Если target_language == "ru":
        * удаляем явно английские элементы (script == "en"),
        * оставляем "ru" и "mixed".
    - Если target_language == "en":
        * удаляем явно русские элементы (script == "ru"),
        * оставляем "en" и "mixed".
    - Для любых других значений target_language (неожиданный код языка)
      фильтрацию не применяем и возвращаем layout как есть.

    Таблицы и метаданные не трогаем.
    """
    target = (target_language or "").lower()
    if target not in ("ru", "en"):
        # Неизвестный язык — безопаснее вернуть layout без изменений.
        return layout

    elements: List[Dict[str, Any]] = layout.get("elements") or []
    filtered: List[Dict[str, Any]] = []

    for el in elements:
        text = (el.get("text") or "").strip()
        if not text:
            # Пустые/почти пустые элементы пропускаем, но не добавляем
            # их в результирующий список, чтобы не плодить шум.
            continue

        script = _detect_script(text)

        if target == "ru":
            # Для русской дорожки отбрасываем чисто английские строки.
            if script == "en":
                continue
            # "ru", "mixed", "other" оставляем — в mixed часто цифры/сокращения.
            filtered.append(el)
        elif target == "en":
            # Для английской дорожки отбрасываем чисто русские строки.
            if script == "ru":
                continue
            # "en", "mixed", "other" оставляем.
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


def filter_layout_to_ru(layout: Dict[str, Any]) -> Dict[str, Any]:
    """
    Backwards‑compatible обёртка для старого кода.

    Исторически система умела фильтровать только до русского текста.
    Чтобы не ломать существующие вызовы, оставляем эту функцию,
    но внутри просто вызываем универсальный фильтр.
    """
    return filter_layout_to_language(layout, "ru")
