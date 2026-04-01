# src/services/layout_language_filter.py

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

import re
from typing import Any, Dict, List


# Разделители для разрезания "сомнительных" строк на сегменты
_SEGMENT_SPLIT_RE = re.compile(
    r"(\n|/|;|:|\s{3,}|\s[-–—]\s)"
)

# Паттерны нейтральных юридически значимых сущностей
_NEUTRAL_PATTERNS = [
    r"\b\d{10,20}\b",                   # длинные числовые идентификаторы (ИНН/ОГРН, счета и т.п.)
    r"\b\d{1,2}\.\d{1,2}\.\d{4}\b",     # даты формата 01.02.2024
    r"\b\d{1,2}\s+[а-яА-ЯёЁ]{3,}\s+\d{4}\b",  # даты с месяцами словами (12 марта 2024)
    r"\b7836\d{6}\b",                   # пример кадастровых/территориальных номеров (можно сузить/расширить)
]
_NEUTRAL_RES = [re.compile(p) for p in _NEUTRAL_PATTERNS]


def _is_neutral_legal_segment(text: str) -> bool:
    """Является ли сегмент нейтральной юридически значимой сущностью (числа/даты и т.п.)."""
    for rx in _NEUTRAL_RES:
        if rx.search(text):
            return True
    return False


def _script_ratio(text: str, target: str) -> float:
    """
    Доля символов целевого алфавита (cyrillic/latin) среди всех букв.
    target: "ru" или "en".
    """
    if not text:
        return 0.0

    cyr = 0
    lat = 0
    for ch in text:
        code = ord(ch)
        # Кириллица
        if 0x0400 <= code <= 0x04FF or 0x0500 <= code <= 0x052F:
            cyr += 1
        # Латиница
        elif (
            0x0041 <= code <= 0x005A
            or 0x0061 <= code <= 0x007A
            or 0x00C0 <= code <= 0x00FF
        ):
            lat += 1

    total = cyr + lat
    if total == 0:
        return 0.0

    if target == "ru":
        return cyr / total
    if target == "en":
        return lat / total
    return 0.0


def _detect_script(text: str) -> str:
    """
    Грубое определение доминирующего скрипта строки.

    Возвращает:
    - "ru"    — если доминирует кириллица;
    - "en"    — если доминирует латиница;
    - "other" — если ни то, ни другое (цифры, знаки).
    """
    cyr = 0
    lat = 0

    for ch in text:
        code = ord(ch)
        if 0x0400 <= code <= 0x04FF or 0x0500 <= code <= 0x052F:
            cyr += 1
        elif (
            0x0041 <= code <= 0x005A
            or 0x0061 <= code <= 0x007A
            or 0x00C0 <= code <= 0x00FF
        ):
            lat += 1

    total = cyr + lat
    if total == 0:
        return "other"

    cyr_ratio = cyr / total
    lat_ratio = lat / total

    if cyr_ratio >= 0.7 and cyr >= 3:
        return "ru"
    if lat_ratio >= 0.7 and lat >= 3:
        return "en"
    return "other"


def detect_languages_in_layout(layout: Dict[str, Any]) -> List[str]:
    """
    Определить, какие языки реально присутствуют в layout.

    - Берём все элементы layout["elements"].
    - Для каждого элемента смотрим текст и определяем скрипт.
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


def _filter_text_for_target(text: str, target: str) -> str | None:
    """
    Оставить в строке только сегменты целевого языка + нейтральные юр. сущности.

    Алгоритм:
    1) быстрый чек по всему тексту: если целевой алфавит доминирует ≥ 0.9 — вернуть текст как есть;
    2) иначе разрезать на сегменты и фильтровать по:
       - нейтральным сущностям,
       - порогу доли целевого алфавита.
    """
    text = (text or "").strip()
    if not text:
        return None

    # 1. Быстрая ветка: почти чистый целевой язык
    if _script_ratio(text, target) >= 0.9:
        return text

    # 2. Сегментация
    # split() с capturing-группой вернёт и разделители; для текста оставляем только части != разделители
    raw_parts = _SEGMENT_SPLIT_RE.split(text)
    segments: List[str] = []
    for part in raw_parts:
        if part is None:
            continue
        part = part.strip()
        if not part:
            continue
        # игнорируем сами разделители (\n, /, " - " и т.п.), они уже "съедены" split'ом
        if _SEGMENT_SPLIT_RE.fullmatch(part):
            continue
        segments.append(part)

    kept: List[str] = []
    for seg in segments:
        # Нейтральные юр. сущности сохраняем, независимо от алфавита
        if _is_neutral_legal_segment(seg):
            kept.append(seg)
            continue

        ratio = _script_ratio(seg, target)
        # Жёсткий порог для целевого языка
        if ratio >= 0.7:
            kept.append(seg)
            continue

        # Иначе сегмент отбрасываем как чужой язык/шум

    if not kept:
        return None

    # Осторожная склейка: через пробел, не добавляем искусственных \n
    return " ".join(kept)


def filter_layout_to_language(
    layout: Dict[str, Any],
    target_language: str,
) -> Dict[str, Any]:
    """
    Оставить в layout только элементы выбранного языка (ru/en),
    причём вырезать из строк куски на другом языке.

    Политика:
    - target_language == "ru":
        * элементы, где доминирует латиница, выкидываем;
        * смешанные строки режем, оставляя русские сегменты + нейтральные сущности.
    - target_language == "en":
        * аналогично, но для английского.
    - Любые другие коды языка → возвращаем layout без изменений.
    """
    target = (target_language or "").lower()
    if target not in ("ru", "en"):
        return layout

    elements: List[Dict[str, Any]] = layout.get("elements") or []
    filtered: List[Dict[str, Any]] = []

    for el in elements:
        raw_text = el.get("text") or ""
        cleaned = _filter_text_for_target(raw_text, target)
        if not cleaned:
            continue

        new_el = dict(el)
        new_el["text"] = cleaned
        filtered.append(new_el)

    tables = layout.get("tables") or []
    metadata = dict(layout.get("metadata") or {})
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
