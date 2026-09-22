"""
Citation normalization helpers for B2 Citation Resolver.

Назначение:
- Привести текст и цитату к единому виду для поиска совпадений.
- Предоставить карту индексов, чтобы span, найденный в нормализованном
  тексте, можно было корректно вернуть в оригинальный текст.

Контракт:
- normalize_text(text) -> str
    Агрессивная нормализация: NFC-совместимые замены, NBSP, ё→е,
    кавычки/тире → ASCII, сжатие whitespace, strip.
    Используется для проверки совпадения цитаты с текстом.

- normalize_with_index_map(text) -> (str, list[int])
    Та же логика, что normalize_text, но дополнительно возвращает
    позиционную карту: idx_map[i] = индекс начала i-го символа
    нормализованного текста в ОРИГИНАЛЬНОМ тексте.
    Инвариант: len(normalized) == len(idx_map).

Домен:
- Русский + английский юридический текст.
- Замены 1:1 (ё→е, кавычки, тире) — карта тривиальна.
- Сжатие пробелов (NBSP, \n, \t, повтор) — карта сдвигает индексы.
"""

from __future__ import annotations

# Кавычки: двойные → " ; одинарные → ' .
_QUOTE_MAP: dict[str, str] = {
    "«": '"',
    "»": '"',
    "„": '"',
    "“": '"',
    "”": '"',
    "‟": '"',
    "❝": '"',
    "❞": '"',
    "‘": "'",
    "’": "'",
    "‚": "'",
    "‛": "'",
    "`": "'",
    "´": "'",
}

# Тире и дефисы: всё → ASCII hyphen-minus '-' .
_DASH_MAP: dict[str, str] = {
    "—": "-",   # em dash
    "–": "-",   # en dash
    "−": "-",   # minus sign
    "‐": "-",   # hyphen
    "‑": "-",   # non-breaking hyphen
    "‒": "-",   # figure dash
}

# Пробельные символы (все → обычный пробел ' ').
_WHITESPACE: frozenset[str] = frozenset(
    " \t\n\r\f\v"
    "\u00a0"    # NBSP
    "\u202f"    # narrow NBSP
    "\u2009"    # thin space
    "\u200a"    # hair space
)


def _normalize_char(ch: str) -> str:
    """
    Нормализовать один символ 1:1 (без изменения длины строки).

    Все преобразования — точечные, заменяют один символ на один.
    Сжатие пробелов происходит не здесь, а в normalize_with_index_map
    (там это часть управления позиционной картой).
    """
    if ch in _WHITESPACE:
        return " "
    if ch in ("Ё", "ё"):
        return "Е" if ch == "Ё" else "е"
    if ch in _QUOTE_MAP:
        return _QUOTE_MAP[ch]
    if ch in _DASH_MAP:
        return _DASH_MAP[ch]
    return ch


def normalize_with_index_map(text: str) -> tuple[str, list[int]]:
    """
    Агрессивная нормализация + позиционная карта в оригинальный текст.

    Возвращает:
    - normalized: нормализованный текст;
    - idx_map:    список, где idx_map[i] — индекс начала i-го символа
      normalized в оригинальном text.

    Гарантия:
    - len(normalized) == len(idx_map);
    - normalized[i] == _normalize_char(text[idx_map[i]])
      для всех i (см. unit-тесты).

    Правила нормализации:
    - пробельные символы (space, \t, \n, \r, \f, \v, NBSP, ...) → ' ';
    - последовательность пробельных символов сжимается в один ' ';
    - ведущие и замыкающие пробелы удаляются (strip);
    - ё → е, Ё → Е;
    - кавычки → " или ';
    - тире → -.
    """
    if not text:
        return "", []

    out_chars: list[str] = []
    out_map: list[int] = []
    prev_was_space = True  # эмулирует strip в начале

    for i, ch in enumerate(text):
        norm_ch = _normalize_char(ch)

        if norm_ch == " ":
            if prev_was_space:
                continue
            out_chars.append(" ")
            out_map.append(i)
            prev_was_space = True
            continue

        out_chars.append(norm_ch)
        out_map.append(i)
        prev_was_space = False

    # strip trailing (последний символ может быть ' ', если текст заканчивался
    # пробелом, а перед ним был непробел)
    while out_chars and out_chars[-1] == " ":
        out_chars.pop()
        out_map.pop()

    return "".join(out_chars), out_map


def normalize_text(text: str) -> str:
    """
    Нормализовать текст для поиска цитаты.

    Тонкая обёртка над normalize_with_index_map: та же логика,
    но без позиционной карты.
    """
    normalized, _ = normalize_with_index_map(text)
    return normalized
