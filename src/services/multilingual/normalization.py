# src/services/multilingual/normalization.py

"""
Layer 1: Normalization.

Задача:
- анализировать raw_layout elements и производить NormalizationHints для каждого;
- обнаруживать три типа split signals: script boundary, explicit separator,
  digit-letter boundary;
- помечать элементы находящиеся в ячейках таблиц через bbox intersection.

НЕ делает:
- не изменяет исходный элемент;
- не разбивает text (это задача Layer 2);
- не определяет язык (это задача Layer 3).

Что производит:
- cleaned_text — версия текста после zero-width cleanup (для Layer 3 detection)
- позиции всех обнаруженных boundaries — используются Layer 2 для split

Примеры реальных паттернов (из документа Simonova SPA):

    Паттерн 1 — script boundary без разделителя (90% случаев):
        "This Real Estate Sale and Purchase Agreement has Настоящий договор..."
        script_boundary_detected=True, positions=(49,)
        (переход "s " → "Н")

    Паттерн 2 — explicit separator "/":
        "APPENDICES / ПРИЛОЖЕНИЯ"
        explicit_separator_detected="/", positions=(10,)
        (позиция самого символа "/")
        Плюс: script_boundary_detected=True, positions=(12,)

    Паттерн 3 — digit-letter boundary:
        "1. DEFINITIONS 1 ОПРЕДЕЛЕНИЯ"
        digit_letter_boundary_detected=True, positions=(15,)
        (после "DEFINITIONS " перед "1")
        Плюс: script_boundary_detected=True, positions=(17,)

    Паттерн 4 — separator "\\" в table cells:
        "Земельный участок ... \\ Land plot with the area 21,041 sq.m."
        explicit_separator_detected="\\", positions=(20,)

Все hints — advisory для Layer 2. Layer 2 сам решает какие использовать
и в каком порядке применять при multi-split.
"""

from __future__ import annotations

import re
import time
from typing import Any

from core.logging import get_logger

from services.multilingual.models import (
    BBox,
    NormalizationHints,
    ProcessingWarning,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Константы cleanup
# ---------------------------------------------------------------------------

# Zero-width символы, которые невидимы но занимают позицию в тексте.
# Их нужно удалить перед language detection.
_ZERO_WIDTH_CHARS = frozenset({
    "\u200b",   # ZERO WIDTH SPACE
    "\u200c",   # ZERO WIDTH NON-JOINER
    "\u200d",   # ZERO WIDTH JOINER
    "\ufeff",   # ZERO WIDTH NO-BREAK SPACE (BOM)
    "\u2060",   # WORD JOINER
})

# Мусор-символы от деградации PDF/OCR.
# Не zero-width, но не несут информации.
_DEGRADATION_CHARS = frozenset({
    "\ufffd",   # REPLACEMENT CHARACTER (?)
    "\u25a0",   # BLACK SQUARE (■)
    "\u25a1",   # WHITE SQUARE (□)
    "\u25aa",   # BLACK SMALL SQUARE (▪)
    "\u25ab",   # WHITE SMALL SQUARE (▫)
})

# ---------------------------------------------------------------------------
# Script ranges — переиспользуем из существующего LanguageDetector
# ---------------------------------------------------------------------------

# Импортируем через прямой доступ к внутренней константе language_detector.
# Это единственный источник истины по Unicode ranges в проекте.
# Если понадобится расширить (например, добавить греческий) — меняется там,
# и multilingual pipeline получает это автоматически.
from services.language_detector import _SCRIPT_RANGES

# Строим быстрый lookup: code_point → script_name
# Использование tuple lookup вместо lambda для производительности.
# 90000+ code points, поэтому важно чтобы проверка была O(len(ranges)) не O(N).


def _script_of_char(ch: str) -> str:
    """
    Определить script одного символа.

    Возвращает script name из _SCRIPT_RANGES или "other".

    "other" присваивается:
    - цифрам (нейтральны, не привязаны к языку)
    - пунктуации
    - пробелам
    - символам вне известных диапазонов

    Для непрофессионального программиста:
    - "А" (кириллица) → "cyrillic"
    - "A" (латиница) → "latin"
    - "1" → "other" (цифра, нейтральна)
    - " " → "other" (пробел)
    - "." → "other" (пунктуация)
    """
    if not ch:
        return "other"
    code = ord(ch)
    for script_name, ranges in _SCRIPT_RANGES:
        for start, end in ranges:
            if start <= code <= end:
                return script_name
    return "other"


# ---------------------------------------------------------------------------
# Константы для separator detection
# ---------------------------------------------------------------------------

# Символы-разделители языков.
# Важно: обязательно должны быть окружены пробелами (иначе это часть URL, даты и т.д.).
_SEPARATOR_CHARS = frozenset({"/", "\\", "|", "\t"})

# ---------------------------------------------------------------------------
# Regex для digit-letter boundary
# ---------------------------------------------------------------------------

# Паттерны цифра-буква без пробела.
# Пример: "1.DEFINITIONS" — цифра с точкой прилипла к букве.
# Пример: "DEFINITIONS1" — буква прилипла к цифре без пробела.
# ВАЖНО: обычные "1st", "2nd" (ordinals) не считаем boundary,
# потому что здесь цифра и буква — часть одного слова.
_DIGIT_LETTER_PATTERN = re.compile(
    r"(?:"
    r"(?<=\d)(?=[A-Za-zА-Яа-яЁё])"          # цифра → буква без пробела
    r"|(?<=\d[.\)])(?=[A-Za-zА-Яа-яЁё])"    # цифра с точкой/скобкой → буква
    r"|(?<=[A-Za-zА-Яа-яЁё])\s+(?=\d[.\s])" # буква + пробел + цифра с точкой/пробелом (новая клауза)
    r")"
)

# ---------------------------------------------------------------------------
# Константы для table cell detection
# ---------------------------------------------------------------------------

# Толерантность при проверке "содержит ли ячейка таблицы элемент".
# Используется для нечёткого сравнения bbox: element inside cell if
# element_center is inside cell_bbox +/- этот tolerance в pt.
_TABLE_CELL_BBOX_TOLERANCE = 2.0

# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------


def normalize_elements(
    elements: list[dict[str, Any]],
    tables: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, NormalizationHints], list[ProcessingWarning]]:
    """
    Layer 1 entry point.

    Проанализировать все elements и вернуть hints для каждого.

    Аргументы:
        elements: raw_layout["elements"] — список dict с полями
                  element_id, text, page, bbox
        tables:   raw_layout.get("tables") или None — для table cell detection

    Возвращает:
        (hints_by_id, warnings):
        - hints_by_id: dict {element_id → NormalizationHints}
        - warnings: список ProcessingWarning для audit

    Гарантии:
    - никогда не бросает исключений;
    - элементы с невалидным text (None, non-str) получают минимальные hints;
    - элементы без element_id пропускаются с warning.

    Для непрофессионального программиста:
    Функция принимает список PDF элементов и возвращает подсказки для каждого:
    "здесь надо разбивать на позиции 15", "здесь есть табличная ячейка",
    "здесь была zero-width пунктуация — вот cleaned версия текста".
    """
    if not elements:
        return {}, []

    # Строим индекс table cells для быстрого lookup
    table_cell_index = _build_table_cell_index(tables) if tables else {}

    hints_by_id: dict[str, NormalizationHints] = {}
    warnings: list[ProcessingWarning] = []

    for element in elements:
        if not isinstance(element, dict):
            continue

        element_id = element.get("element_id")
        if not element_id:
            # Элементы без ID нельзя корректно связать с hints.
            # Логируем warning но не падаем.
            warnings.append(
                ProcessingWarning(
                    warning_type="missing_element_id",
                    page=_safe_page(element),
                    details={"reason": "element skipped in Layer 1 normalization"},
                )
            )
            continue

        element_id_str = str(element_id)

        try:
            hints = _normalize_single_element(
                element=element,
                table_cell_index=table_cell_index,
            )
            hints_by_id[element_id_str] = hints

            # Собираем warnings для этого элемента
            element_warnings = _collect_element_warnings(element_id_str, element, hints)
            warnings.extend(element_warnings)

        except Exception as exc:
            # Ошибка обработки одного элемента не должна ломать весь pipeline.
            # Логируем и создаём минимальные hints.
            logger.warning(
                "Layer 1 normalization failed for element",
                element_id=element_id_str,
                error=str(exc),
            )
            warnings.append(
                ProcessingWarning(
                    warning_type="normalization_error",
                    element_id=element_id_str,
                    page=_safe_page(element),
                    details={"error": str(exc)},
                )
            )
            hints_by_id[element_id_str] = _make_minimal_hints(element_id_str, element)

    return hints_by_id, warnings


# ---------------------------------------------------------------------------
# Обработка одного элемента
# ---------------------------------------------------------------------------


def _normalize_single_element(
    element: dict[str, Any],
    table_cell_index: dict[int, list[dict[str, Any]]],
) -> NormalizationHints:
    """
    Обработать один element и построить NormalizationHints.

    Шаги:
    1. Cleanup: удалить zero-width и degradation символы
    2. Script boundary detection (primary signal)
    3. Explicit separator detection (secondary signal)
    4. Digit-letter boundary detection (tertiary signal)
    5. Table cell detection

    Все detection работают на ОРИГИНАЛЬНОМ тексте (не cleaned),
    потому что позиции должны совпадать с индексами оригинала для Layer 2.
    """
    element_id = str(element.get("element_id", ""))
    raw_text = element.get("text", "") or ""
    if not isinstance(raw_text, str):
        raw_text = str(raw_text)

    # Cleanup — производим отдельную "чистую" версию, но detect работаем
    # с оригиналом чтобы позиции совпадали.
    cleaned_text, has_zero_width = _clean_text(raw_text)

    # Script boundary detection на оригинальном тексте
    script_boundaries = _detect_script_boundaries(raw_text)

    # Explicit separator detection
    separator_char, separator_positions = _detect_explicit_separators(raw_text)

    # Digit-letter boundary detection
    digit_letter_positions = _detect_digit_letter_boundaries(raw_text)

    # Table cell detection
    page = _safe_page(element)
    bbox = BBox.from_list(element.get("bbox"))
    is_table_cell, cell_position = _detect_table_cell(
        page=page,
        bbox=bbox,
        table_cell_index=table_cell_index,
    )

    return NormalizationHints(
        source_element_id=element_id,
        script_boundary_detected=len(script_boundaries) > 0,
        script_boundary_positions=tuple(script_boundaries),
        explicit_separator_detected=separator_char,
        explicit_separator_positions=tuple(separator_positions),
        digit_letter_boundary_detected=len(digit_letter_positions) > 0,
        digit_letter_boundary_positions=tuple(digit_letter_positions),
        is_table_cell=is_table_cell,
        cell_position=cell_position,
        has_zero_width_chars=has_zero_width,
        cleaned_text=cleaned_text,
    )


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


def _clean_text(text: str) -> tuple[str, bool]:
    """
    Удалить zero-width и degradation символы.

    Возвращает:
        (cleaned_text, has_zero_width)

    Не изменяет пробелы, не нормализует случай, ничего не удаляет
    кроме символов из _ZERO_WIDTH_CHARS и _DEGRADATION_CHARS.
    """
    if not text:
        return "", False

    has_zw = False
    result_chars: list[str] = []

    for ch in text:
        if ch in _ZERO_WIDTH_CHARS:
            has_zw = True
            continue  # пропускаем
        if ch in _DEGRADATION_CHARS:
            continue  # пропускаем без флага (не zero-width, но мусор)
        result_chars.append(ch)

    return "".join(result_chars), has_zw


# ---------------------------------------------------------------------------
# Script boundary detection (PRIMARY signal)
# ---------------------------------------------------------------------------


def _detect_script_boundaries(text: str) -> list[int]:
    """
    Найти позиции переходов между скриптами внутри текста.

    Алгоритм:
    - Итерируемся по символам
    - Отслеживаем "текущий script" (не считая "other")
    - Когда встречаем новый script (не "other" и не равный текущему) —
      это boundary, регистрируем позицию

    Позиции = точка НАЧАЛА нового скрипта.
    То есть text[:pos] содержит один язык, text[pos:] — начинается с другого.

    Игнорирует "other" символы (цифры, пробелы, пунктуация) — они нейтральны
    и не сбрасывают "текущий script".

    Пример:
        "TABLE OF CONTENTS / СОДЕРЖАНИЕTABLE OF CONTENTS"
        Позиции: [18, 30]
        18 — начало "С" (после "/ ")
        30 — начало "T" (после "СОДЕРЖАНИЕ")

    Пример:
        "This Real Estate Sale and Purchase Agreement has Настоящий..."
        Позиция: [49]
        49 — начало "Н" (после "has ")

    Для непрофессионального программиста:
    Функция ищет места где кириллица меняется на латиницу или наоборот
    (или другие пары скриптов). Возвращает список позиций символов
    где происходит переход.
    """
    if not text or len(text) < 2:
        return []

    boundaries: list[int] = []
    current_script: str | None = None  # None означает "ещё не встретили значимый script"

    for i, ch in enumerate(text):
        script = _script_of_char(ch)

        if script == "other":
            # Цифра, пробел, пунктуация — не сбрасывает "текущий script",
            # но и не устанавливает его. Просто пропускаем.
            continue

        if current_script is None:
            # Первый значимый символ — устанавливаем текущий script
            current_script = script
            continue

        if script != current_script:
            # Boundary! Позиция = индекс этого символа (начало нового script)
            boundaries.append(i)
            current_script = script

    return boundaries


# ---------------------------------------------------------------------------
# Explicit separator detection (SECONDARY signal)
# ---------------------------------------------------------------------------


def _detect_explicit_separators(text: str) -> tuple[str | None, list[int]]:
    """
    Найти явные разделители языков: "/", "\\", "|", "\\t".

    Правила распознавания:
    1. Символ должен быть в _SEPARATOR_CHARS
    2. Слева и справа должны быть пробелы (или граница строки)
    3. Скрипты по бокам separator'а должны быть РАЗНЫЕ
       (иначе это например "A/B" в тексте, не разделитель)

    Возвращает:
        (separator_char, positions):
        - separator_char: сам символ ("/", "\\", "|", "\\t") или None если не найден
        - positions: список позиций символа-разделителя в тексте

    Если найдено несколько разных разделителей — возвращаем ПЕРВЫЙ по позиции.
    Позиции для этого разделителя.

    Пример:
        "APPENDICES / ПРИЛОЖЕНИЯ"
        → ("/", [10])
        (позиция символа "/")

    Пример:
        "Text A/B not separator"
        → (None, [])
        (нет пробелов вокруг "/", плюс скрипты одинаковые)

    Пример:
        "Земельный участок ... \\ Land plot ..."
        → ("\\", [20])

    Для непрофессионального программиста:
    Функция ищет символы "/", "\\", "|" которые окружены пробелами и
    разделяют текст на две языковые части. "A/B" не считается разделителем
    потому что нет пробелов и оба символа — латиница.
    """
    if not text:
        return None, []

    # Находим все кандидаты
    candidates: list[tuple[int, str]] = []  # [(position, separator_char)]

    for i, ch in enumerate(text):
        if ch not in _SEPARATOR_CHARS:
            continue

        # Проверяем контекст: пробелы вокруг (или границы строки)
        left_ok = i == 0 or text[i - 1].isspace()
        right_ok = i == len(text) - 1 or text[i + 1].isspace()

        if not (left_ok and right_ok):
            continue

        # Проверяем что скрипты по бокам разные
        left_script = _find_nearest_script_left(text, i)
        right_script = _find_nearest_script_right(text, i)

        if left_script == "other" or right_script == "other":
            # Не можем определить хотя бы одну сторону — не считаем разделителем
            continue

        if left_script == right_script:
            # Один и тот же язык — не разделитель
            continue

        candidates.append((i, ch))

    if not candidates:
        return None, []

    # Берём первый по позиции разделитель как "главный"
    candidates.sort(key=lambda x: x[0])
    primary_separator = candidates[0][1]

    # Возвращаем позиции только для primary_separator
    # (если есть смешанные разделители — оставляем один тип для simplicity)
    positions = [pos for pos, ch in candidates if ch == primary_separator]

    return primary_separator, positions


def _find_nearest_script_left(text: str, position: int) -> str:
    """
    Найти script ближайшего к позиции значимого символа слева.
    Пропускает "other" (цифры, пунктуацию, пробелы).
    Возвращает "other" если не найдено.
    """
    for i in range(position - 1, -1, -1):
        script = _script_of_char(text[i])
        if script != "other":
            return script
    return "other"


def _find_nearest_script_right(text: str, position: int) -> str:
    """
    Найти script ближайшего к позиции значимого символа справа.
    Пропускает "other".
    """
    for i in range(position + 1, len(text)):
        script = _script_of_char(text[i])
        if script != "other":
            return script
    return "other"


# ---------------------------------------------------------------------------
# Digit-letter boundary detection (TERTIARY signal)
# ---------------------------------------------------------------------------


def _detect_digit_letter_boundaries(text: str) -> list[int]:
    """
    Найти границы цифра-буква без пробела — потенциальные split points.

    Обнаруживаемые паттерны:
    - "1.DEFINITIONS" — цифра с точкой прилипла к букве без пробела
    - "1DEFINITIONS"  — цифра прилипла к букве без разделителя
    - "DEFINITIONS 1" (в контексте новой клаузы) — буква + пробел + новая номерная клауза

    Позиции — точка НАЧАЛА второй части.

    Пример:
        "1. DEFINITIONS 1 ОПРЕДЕЛЕНИЯ"
        Найдёт позицию 15 (перед "1" после "DEFINITIONS ")
        Это hint что здесь может быть переход к новой клаузе.

    Возвращает:
        Список позиций отсортированный по возрастанию.

    Для непрофессионального программиста:
    Функция ищет места где цифры и буквы стоят подозрительно близко —
    это может быть склеенный текст от неудачного PDF extraction.
    """
    if not text or len(text) < 2:
        return []

    positions: list[int] = []
    for match in _DIGIT_LETTER_PATTERN.finditer(text):
        # Позиция — начало правой части (после lookbehind)
        positions.append(match.start())

    return sorted(set(positions))


# ---------------------------------------------------------------------------
# Table cell detection
# ---------------------------------------------------------------------------


def _build_table_cell_index(
    tables: list[dict[str, Any]],
) -> dict[int, list[dict[str, Any]]]:
    """
    Построить индекс {page → list[cell_info]} для быстрого lookup.

    Формат cell_info:
        {
            "row": int,
            "col": int,
            "bbox": BBox,  # если у таблицы есть bbox per cell
        }

    ВАЖНО: в существующем raw_layout tables[] хранят только rows (list of list of str),
    без bbox каждой ячейки. То есть мы НЕ можем узнать точный bbox ячейки.

    В этом случае используется fallback:
    - если tables[i] есть на странице P, но нет bbox — считаем что все элементы
      на странице P могут быть внутри таблицы, но флаг is_table_cell не ставим
      (нельзя достоверно определить)

    Если у таблицы есть общий bbox (некоторые extraction ставят) — используем его
    для определения "элемент внутри таблицы".

    Для реального документа Simonova SPA этот индекс будет пустой,
    потому что tables[] содержат только rows без bbox.
    """
    index: dict[int, list[dict[str, Any]]] = {}

    for table in tables:
        if not isinstance(table, dict):
            continue

        page = _safe_page(table)
        if page <= 0:
            continue

        # Проверяем есть ли bbox у таблицы или ячеек.
        # В существующем формате обычно нет — table это просто {"page": N, "rows": [...]}
        table_bbox_raw = table.get("bbox")
        if table_bbox_raw:
            table_bbox = BBox.from_list(table_bbox_raw)
            if not table_bbox.is_zero:
                cell_info = {
                    "row": 0,
                    "col": 0,
                    "bbox": table_bbox,
                }
                index.setdefault(page, []).append(cell_info)

    return index


def _detect_table_cell(
    page: int,
    bbox: BBox,
    table_cell_index: dict[int, list[dict[str, Any]]],
) -> tuple[bool, tuple[int, int] | None]:
    """
    Проверить находится ли элемент внутри ячейки таблицы.

    Возвращает:
        (is_table_cell, cell_position):
        - is_table_cell: True если bbox элемента находится внутри bbox какой-то ячейки
        - cell_position: (row, col) или None если не в таблице

    Если у таблицы нет bbox (типичный случай в existing raw_layout) —
    возвращает (False, None).
    """
    if page <= 0 or bbox.is_zero:
        return False, None

    cells = table_cell_index.get(page)
    if not cells:
        return False, None

    element_x_center = bbox.x_center
    element_y_center = bbox.y_center

    for cell in cells:
        cell_bbox: BBox = cell.get("bbox")
        if cell_bbox is None or cell_bbox.is_zero:
            continue

        # Element center должен быть внутри cell bbox +/- tolerance
        if (
            cell_bbox.x0 - _TABLE_CELL_BBOX_TOLERANCE <= element_x_center
            <= cell_bbox.x1 + _TABLE_CELL_BBOX_TOLERANCE
            and cell_bbox.top - _TABLE_CELL_BBOX_TOLERANCE <= element_y_center
            <= cell_bbox.bottom + _TABLE_CELL_BBOX_TOLERANCE
        ):
            return True, (cell.get("row", 0), cell.get("col", 0))

    return False, None


# ---------------------------------------------------------------------------
# Warning collection
# ---------------------------------------------------------------------------


def _collect_element_warnings(
    element_id: str,
    element: dict[str, Any],
    hints: NormalizationHints,
) -> list[ProcessingWarning]:
    """
    Собрать warnings для одного элемента после normalization.

    Warnings которые мы генерируем:
    - too_many_boundaries: >5 boundary positions в одном элементе (странно)
    - inconsistent_signals: script boundary + explicit separator на разных позициях
    - zero_width_cleanup: были удалены zero-width символы (info)
    """
    warnings: list[ProcessingWarning] = []
    page = _safe_page(element)

    total_positions = len(hints.all_split_positions)
    if total_positions > 5:
        warnings.append(
            ProcessingWarning(
                warning_type="too_many_boundaries",
                element_id=element_id,
                page=page,
                details={
                    "total_split_positions": total_positions,
                    "text_length": len(hints.cleaned_text),
                    "note": "unusually many boundaries in one element",
                },
            )
        )

    if hints.has_zero_width_chars:
        warnings.append(
            ProcessingWarning(
                warning_type="zero_width_cleanup",
                element_id=element_id,
                page=page,
                details={
                    "note": "zero-width characters removed in cleaned_text",
                },
            )
        )

    return warnings


# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------


def _safe_page(element: dict[str, Any]) -> int:
    """Безопасно извлечь page из элемента. Возвращает 0 если не удалось."""
    try:
        page_raw = element.get("page", 0)
        page = int(page_raw)
        return page if page > 0 else 0
    except (TypeError, ValueError):
        return 0


def _make_minimal_hints(element_id: str, element: dict[str, Any]) -> NormalizationHints:
    """
    Создать пустые hints для элемента при ошибке обработки.
    Layer 2 обработает как элемент без split.
    """
    raw_text = element.get("text", "") or ""
    if not isinstance(raw_text, str):
        raw_text = str(raw_text)

    return NormalizationHints(
        source_element_id=element_id,
        script_boundary_detected=False,
        script_boundary_positions=(),
        explicit_separator_detected=None,
        explicit_separator_positions=(),
        digit_letter_boundary_detected=False,
        digit_letter_boundary_positions=(),
        is_table_cell=False,
        cell_position=None,
        has_zero_width_chars=False,
        cleaned_text=raw_text,
    )


    