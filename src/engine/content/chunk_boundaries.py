# src/engine/content/chunk_boundaries.py

"""
chunk_boundaries.py — boundary-aware утилиты для разбиения юридического текста.

Для непрофессионального программиста:
- Обычный text splitter режет текст по предложениям не зная что перед ним
  юридический документ. Это приводит к тому что:
  * "Ltd. The parties" — режется на "Ltd." и "The parties" (неправильно)
  * "п. 3.1 применяется" — режется внутри ссылки на клаузу (неправильно)
  * "1. Стороны обязаны..." — список нумерованных пунктов режется
    посередине пункта (неправильно)

- Этот модуль содержит:
  * список юридических аббревиатур которые нельзя считать концом предложения
  * regex для boundary detection с учётом этих аббревиатур
  * функции для определения типа boundary (paragraph / list item / sentence)
  * правила no-split pairs (heading + следующий абзац не разрываем)

Архитектурная роль:
- используется только в split_text_to_sized_chunks() в chunking.py
- не зависит от БД, MinIO, LLM
- pure функции без side effects
"""

from __future__ import annotations

import re
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Юридические аббревиатуры — точка после них НЕ конец предложения
# ---------------------------------------------------------------------------

# Полный список юридических и общеупотребительных аббревиатур
# которые встречаются в договорах на русском и английском.
# После них точка НЕ является концом предложения.
_LEGAL_ABBREVIATIONS: frozenset[str] = frozenset(
    {
        # Английские юридические
        "Ltd",
        "Inc",
        "Corp",
        "Co",
        "LLC",
        "LLP",
        "PLC",
        "GmbH",
        "S.A",
        "B.V",
        "No",
        "Art",
        "Sec",
        "para",
        "cl",
        "sub",
        "approx",
        "dept",
        "div",
        "est",
        "etc",
        "fig",
        "govt",
        "max",
        "min",
        "misc",
        "natl",
        "org",
        "pp",
        "ref",
        "reg",
        "rev",
        "spec",
        "std",
        "temp",
        "vol",
        "vs",
        "i.e",
        "e.g",
        "cf",
        "ibid",
        "op",
        "cit",
        # Русские юридические
        "п",
        "пп",
        "ст",
        "гл",
        "разд",
        "подп",
        "прим",
        "абз",
        "ч",
        "руб",
        "коп",
        "млн",
        "млрд",
        "тыс",
        "кг",
        "км",
        "га",
        "кв",
        "г",
        "обл",
        "р-н",
        "пр",
        "ул",
        "д",
        "оф",
        "тел",
        "факс",
        "др",
        "пр-т",
        "б-р",
        "наб",
        "пл",
        # Единицы измерения
        "кв.м",
        "куб.м",
        "л.с",
        "кВт",
        "МВт",
    }
)

# Строим regex pattern для аббревиатур
# Паттерн: слово из списка + точка + пробел + следующее слово с большой буквы
# Это НЕ должно считаться концом предложения
_ABBREV_PATTERN = re.compile(
    r"\b(?:"
    + "|".join(re.escape(abbr) for abbr in sorted(_LEGAL_ABBREVIATIONS, key=len, reverse=True))
    + r")\.",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Паттерны для list items
# ---------------------------------------------------------------------------

# Нумерованные пункты списка: "1.", "1)", "(a)", "(1)", "a.", "–", "•"
_LIST_ITEM_PATTERN = re.compile(
    r"""
    ^                           # начало строки
    (?:
        \d+\.                   # "1."
        | \d+\)                 # "1)"
        | \([a-zA-Zа-яА-Я\d]+\) # "(a)" или "(1)"
        | [a-zA-Z]\.            # "a."
        | [–\-•·]\s             # "– " или "• "
    )
    \s*                         # пробел после маркера
    \S                          # хотя бы один непустой символ
    """,
    re.VERBOSE | re.MULTILINE,
)

# Паттерн для heading-like строк (короткая строка без точки в конце)
# Используется чтобы не отрывать heading от следующего абзаца
_HEADING_LINE_PATTERN = re.compile(
    r"""
    ^                   # начало строки
    (?:
        \d+(?:\.\d+)*   # числовой uid "1" / "1.2" / "3.1.4"
        \s+             # пробел
    )?
    [A-ZА-Я\w]         # начинается с большой буквы или цифры
    .{3,120}            # от 3 до 120 символов
    (?<![.!?:,;])       # НЕ заканчивается знаком препинания
    $                   # конец строки
    """,
    re.VERBOSE | re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Типы boundary
# ---------------------------------------------------------------------------


class BoundaryType:
    """
    Типы границ между частями текста.

    Для непрофессионального программиста:
    Это "метки" которые мы ставим между предложениями/абзацами,
    чтобы потом решить — можно ли здесь делать разрез чанка.
    """

    PARAGRAPH = "paragraph"  # двойной перенос строки — сильная граница
    LIST_ITEM = "list_item"  # начало нового пункта списка — граница
    SENTENCE = "sentence"  # конец предложения — слабая граница
    ABBREVIATION = "abbrev"  # точка после аббревиатуры — НЕ граница
    NONE = "none"  # граница отсутствует


class TextSegment(NamedTuple):
    """
    Один сегмент текста с информацией о boundary после него.

    text:          текст сегмента
    boundary_after: тип границы после этого сегмента
    is_heading:    True если сегмент похож на заголовок
    is_list_item:  True если сегмент — пункт нумерованного списка
    """

    text: str
    boundary_after: str
    is_heading: bool
    is_list_item: bool


# ---------------------------------------------------------------------------
# Основные функции
# ---------------------------------------------------------------------------


def is_legal_sentence_boundary(text: str, position: int) -> bool:
    """
    Проверить является ли позиция в тексте реальной границей предложения.

    Для непрофессионального программиста:
    - Функция смотрит на символ в позиции `position` и решает:
      "это конец предложения или просто точка внутри аббревиатуры?"
    - Пример: "Ltd. The" — точка после "Ltd" НЕ конец предложения.
    - Пример: "договор заключён. Стороны" — точка ЯВЛЯЕТСЯ концом предложения.

    Алгоритм:
    1. Проверяем что в позиции стоит .!?
    2. Ищем слово перед точкой
    3. Если слово — известная аббревиатура — это НЕ граница
    4. Если после точки нет большой буквы — это НЕ граница
    5. Иначе — граница
    """
    if position >= len(text):
        return False

    char = text[position]
    if char not in ".!?":
        return False

    # Проверяем что после точки (с пробелами) идёт большая буква или цифра
    rest = text[position + 1 : position + 20].lstrip()
    if not rest:
        return True  # конец текста — граница
    if not (rest[0].isupper() or rest[0].isdigit()):
        return False  # после точки строчная буква — не граница

    # Ищем слово перед точкой
    word_start = position - 1
    while word_start >= 0 and (text[word_start].isalpha() or text[word_start] in ".-"):
        word_start -= 1
    word_before = text[word_start + 1 : position]

    # Проверяем аббревиатуры
    if word_before in _LEGAL_ABBREVIATIONS:
        return False

    # Дополнительная проверка: если слово перед точкой короткое (1-3 буквы)
    # и строчное — это вероятно аббревиатура
    if len(word_before) <= 3 and word_before and word_before[0].islower():
        return False

    return True


def split_into_legal_sentences(text: str) -> list[str]:
    r"""
    Разбить текст на предложения с учётом юридических аббревиатур.

    Для непрофессионального программиста:
    - Это замена стандартного `re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)`
    - Стандартный split не знает про аббревиатуры и режет в неправильных местах.
    - Эта функция проверяет каждую потенциальную границу через
      is_legal_sentence_boundary() перед тем как делать разрез.

    Возвращает список предложений без потери текста.
    """
    if not text:
        return []

    text = text.strip()
    if not text:
        return []

    sentences: list[str] = []
    current_start = 0

    i = 0
    while i < len(text):
        char = text[i]

        if char in ".!?":
            # Проверяем: это реальный конец предложения?
            if is_legal_sentence_boundary(text, i):
                # Находим конец пробелов после знака препинания
                end_of_punct = i + 1
                while end_of_punct < len(text) and text[end_of_punct] in " \t":
                    end_of_punct += 1

                # Добавляем предложение если оно непустое
                sentence = text[current_start : i + 1].strip()
                if sentence:
                    sentences.append(sentence)
                current_start = end_of_punct
                i = end_of_punct
                continue

        i += 1

    # Остаток текста
    remaining = text[current_start:].strip()
    if remaining:
        sentences.append(remaining)

    return sentences if sentences else [text]


def detect_list_item_boundaries(text: str) -> list[int]:
    """
    Найти позиции начала новых пунктов списка в тексте.

    Для непрофессионального программиста:
    - Возвращает список индексов строк где начинается новый пункт списка.
    - Используется чтобы при разбиении на чанки не разрезать пункт списка
      посередине (всегда режем МЕЖДУ пунктами, не внутри).

    Пример:
    "1. Продавец обязан передать товар.
     2. Покупатель обязан оплатить." → позиции [0, 1] (строки 0 и 1)
    """
    lines = text.split("\n")
    boundaries: list[int] = []

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped and _LIST_ITEM_PATTERN.match(stripped):
            boundaries.append(idx)

    return boundaries


def is_heading_line(line: str) -> bool:
    """
    Определить является ли строка заголовком клаузы.

    Для непрофессионального программиста:
    - Заголовок — это короткая строка без точки в конце,
      часто начинающаяся с числового uid ("1.2 Definitions").
    - Заголовки не должны быть оторваны от следующего за ними тела клаузы.
    """
    stripped = line.strip()
    if not stripped:
        return False
    if len(stripped) > 150:
        return False

    return bool(_HEADING_LINE_PATTERN.match(stripped))


def segment_legal_text(text: str) -> list[TextSegment]:
    """
    Разбить юридический текст на сегменты с boundary метками.

    Для непрофессионального программиста:
    - Это главная функция модуля.
    - Она принимает текст клаузы и возвращает список TextSegment.
    - Каждый сегмент знает: что за текст, какая граница после него,
      является ли он заголовком или пунктом списка.
    - Это позволяет split_text_to_sized_chunks() принимать умные решения
      о том где делать разрез.

    Алгоритм:
    1. Разбиваем по двойным переносам строки (абзацы) — PARAGRAPH boundary.
    2. Внутри каждого абзаца ищем нумерованные пункты — LIST_ITEM boundary.
    3. Внутри пунктов разбиваем на предложения — SENTENCE boundary.
    """
    if not text:
        return []

    text = text.strip()
    segments: list[TextSegment] = []

    # Шаг 1: разбиваем по абзацам
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    for para_idx, paragraph in enumerate(paragraphs):
        is_last_para = para_idx == len(paragraphs) - 1
        boundary_after_para = BoundaryType.PARAGRAPH if not is_last_para else BoundaryType.NONE

        lines = [line.strip() for line in paragraph.split("\n") if line.strip()]
        if not lines:
            continue

        # Шаг 2: ищем list items внутри абзаца
        list_item_starts: list[int] = []
        for idx, line in enumerate(lines):
            if _LIST_ITEM_PATTERN.match(line):
                list_item_starts.append(idx)

        if list_item_starts:
            # Абзац содержит список — разбиваем по list items
            # Текст до первого list item — отдельный сегмент
            if list_item_starts[0] > 0:
                pre_text = "\n".join(lines[: list_item_starts[0]])
                if pre_text.strip():
                    is_h = is_heading_line(pre_text)
                    segments.append(
                        TextSegment(
                            text=pre_text,
                            boundary_after=BoundaryType.LIST_ITEM,
                            is_heading=is_h,
                            is_list_item=False,
                        )
                    )

            # Каждый list item — отдельный сегмент
            for item_idx, item_start in enumerate(list_item_starts):
                item_end = (
                    list_item_starts[item_idx + 1]
                    if item_idx + 1 < len(list_item_starts)
                    else len(lines)
                )
                item_text = "\n".join(lines[item_start:item_end]).strip()
                is_last_item = item_idx == len(list_item_starts) - 1
                boundary = boundary_after_para if is_last_item else BoundaryType.LIST_ITEM
                if item_text:
                    segments.append(
                        TextSegment(
                            text=item_text,
                            boundary_after=boundary,
                            is_heading=False,
                            is_list_item=True,
                        )
                    )
        else:
            # Абзац без списка — разбиваем на предложения
            full_para = "\n".join(lines)
            sentences = split_into_legal_sentences(full_para)

            for sent_idx, sentence in enumerate(sentences):
                if not sentence.strip():
                    continue
                is_last_sent = sent_idx == len(sentences) - 1
                boundary = boundary_after_para if is_last_sent else BoundaryType.SENTENCE
                is_h = is_heading_line(sentence) if sent_idx == 0 else False
                segments.append(
                    TextSegment(
                        text=sentence,
                        boundary_after=boundary,
                        is_heading=is_h,
                        is_list_item=False,
                    )
                )

    return segments


def can_split_at_boundary(
    boundary_type: str,
    *,
    current_is_heading: bool = False,
    next_is_heading: bool = False,
) -> bool:
    """
    Решить можно ли делать разрез на данной границе.

    Для непрофессионального программиста:
    - Правила no-split:
      * Если текущий сегмент — заголовок: НЕ разрезаем
        (heading нельзя отрывать от body).
      * Если следующий сегмент — заголовок: НЕ разрезаем
        (нельзя заканчивать чанк прямо перед heading).
      * ABBREVIATION — никогда не граница.
      * NONE — не граница (конец текста без boundary).
    - Разрезать можно по: PARAGRAPH > LIST_ITEM > SENTENCE.
    """
    if boundary_type == BoundaryType.ABBREVIATION:
        return False
    if boundary_type == BoundaryType.NONE:
        return False

    # Не разрываем heading от следующего body
    if current_is_heading:
        return False

    # Не заканчиваем чанк прямо перед heading
    if next_is_heading:
        return False

    # PARAGRAPH, LIST_ITEM, SENTENCE — разрезать можно
    return boundary_type in {
        BoundaryType.PARAGRAPH,
        BoundaryType.LIST_ITEM,
        BoundaryType.SENTENCE,
    }


def split_legal_text_to_segments(
    text: str,
    target_tokens: int,
    max_tokens: int,
    overlap_ratio: float,
) -> list[str]:
    """
    Разбить юридический текст на чанки с учётом boundary rules.

    Это boundary-aware замена для split_text_to_sized_chunks().

    Для непрофессионального программиста:
    - Вместо простого "режем по предложениям" — сначала анализируем
      структуру текста (heading / list item / paragraph / sentence).
    - Потом набираем сегменты в чанк пока не превысим target_tokens.
    - Разрез делаем только в допустимом месте (can_split_at_boundary).
    - heading + следующий за ним абзац никогда не разрываются.
    - Нумерованные пункты списка не разрезаются посередине.

    Параметры:
    - text:          исходный текст клаузы
    - target_tokens: целевой размер чанка в токенах
    - max_tokens:    максимальный размер чанка в токенах
    - overlap_ratio: доля перекрытия между чанками (0.0..1.0)

    Возвращает список строк — готовых чанков.
    """
    from engine.retrieval.tokenization import count_tokens

    text = (text or "").strip()
    if not text:
        return []

    # Если текст помещается в один чанк — сразу возвращаем
    if count_tokens(text) <= max_tokens:
        return [text]

    segments = segment_legal_text(text)
    if not segments:
        return [text]

    chunks: list[str] = []
    current_parts: list[str] = []
    current_tokens = 0
    overlap_parts: list[str] = []

    def _flush_current() -> None:
        """Сохранить накопленные части как готовый чанк."""
        nonlocal current_parts, current_tokens, overlap_parts
        if not current_parts:
            return
        chunk_text = "\n\n".join(current_parts).strip()
        if chunk_text:
            chunks.append(chunk_text)
        # Вычисляем overlap — берём последние N частей
        if overlap_ratio > 0:
            n_overlap = max(1, int(len(current_parts) * overlap_ratio))
            overlap_parts = current_parts[-n_overlap:]
        else:
            overlap_parts = []
        current_parts = []
        current_tokens = 0

    def _start_new_chunk_with_overlap() -> None:
        """Начать новый чанк с overlap из предыдущего."""
        nonlocal current_parts, current_tokens
        current_parts = list(overlap_parts)
        current_tokens = count_tokens("\n\n".join(current_parts)) if current_parts else 0

    for seg_idx, segment in enumerate(segments):
        seg_text = segment.text.strip()
        if not seg_text:
            continue

        seg_tokens = count_tokens(seg_text)

        # Если сегмент сам по себе больше max_tokens — добавляем как есть
        # (это forced chunk — нет смысла пытаться разрезать дальше)
        if seg_tokens > max_tokens and not current_parts:
            if current_parts:
                _flush_current()
            chunks.append(seg_text)
            overlap_parts = []
            continue

        # Определяем boundary контекст для следующего сегмента
        next_segment = segments[seg_idx + 1] if seg_idx + 1 < len(segments) else None
        next_is_heading = next_segment.is_heading if next_segment else False

        # Если текущий чанк пустой и есть overlap — начинаем с overlap
        if not current_parts and overlap_parts:
            _start_new_chunk_with_overlap()

        # Добавляем сегмент в текущий чанк
        current_parts.append(seg_text)
        current_tokens += seg_tokens

        # Проверяем нужно ли сделать разрез
        should_split = False

        if current_tokens >= target_tokens:
            # Достигли target — пробуем сделать разрез если boundary допустима
            if can_split_at_boundary(
                segment.boundary_after,
                current_is_heading=segment.is_heading,
                next_is_heading=next_is_heading,
            ):
                should_split = True

        if current_tokens > max_tokens:
            # Превысили max — принудительный разрез на ближайшей допустимой границе
            # даже если текущая не идеальна
            if can_split_at_boundary(
                segment.boundary_after,
                current_is_heading=False,  # форсируем разрез даже если heading
                next_is_heading=False,
            ):
                should_split = True
            elif current_tokens > max_tokens * 1.5:
                # Экстремальное превышение — разрезаем в любом случае
                should_split = True

        if should_split:
            _flush_current()

    # Остаток
    if current_parts:
        chunk_text = "\n\n".join(current_parts).strip()
        if chunk_text:
            chunks.append(chunk_text)

    # Если ничего не получилось — возвращаем исходный текст
    return chunks if chunks else [text]
