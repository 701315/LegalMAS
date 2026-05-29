# src/services/structure/heading_patterns.py

"""
Паттерны и базовый парсер заголовков (heading-строк).

Задача этого модуля:
- держать ВСЕ regex-паттерны заголовков в одном месте;
- уметь аккуратно распарсить строку в (uid, title);
- НЕ принимать финальное решение о том, хороший это заголовок или нет —
  это делает отдельный слой валидации/скоринга.
"""

from __future__ import annotations

import re

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

_MAX_TITLE_LEN = max(160, int(settings.STRUCTURE_MAX_CLAUSE_TITLE_LEN or 160))


# --- Паттерны uid / заголовков ---


# Явные sectional-заголовки:
# "Section 2 Payment terms", "Article 3. Liability", "Clause 4: ..."
_SECTIONAL = re.compile(
    r"""
    ^\s*
    (?:section|sec\.?|article|art\.?|clause)
    \s+
    (?P<uid>\d+(?:\.\d+)*)
    (?:[\.\:\-\)]\s*|\s+)
    (?P<title>.{1,320}?)
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


# Appendix / Приложение:
# "APPENDIX No. 4 Real estate ...",
# "Appendix 4 - Property",
# "ПРИЛОЖЕНИЕ № 4 ОПИСАНИЕ ОБЪЕКТА"
_APPENDIX_HEADING = re.compile(
    r"""
    ^\s*
    (?P<prefix>
        appendix
        |
        app\.
        |
        приложение
        |
        прил\.
    )
    \s*
    (?:no\.?|№)?
    \s*
    (?P<num>\d+(?:\.\d+)*)
    (?:[\.\:\-\)]\s*|\s+)
    (?P<title>.{1,320}?)
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


# Основной numeric-паттерн:
# "3.1 Продавец обязан", "2.2.4 Наименование ..."
# Требуем нормальный textual tail после uid.
_NUMERIC_MAIN = re.compile(
    r"""
    ^\s*
    (?P<uid>\d+(?:\.\d+)*)
    (?:[\.\)]\s+|\s+)
    (?P<title>.+?)
    \s*$
    """,
    re.VERBOSE,
)


# Более осторожный fallback для OCR/плотной вёрстки:
# "3.1.Обязанности сторон" или "2.2)Порядок расчетов"
# Используем только если после uid сразу идёт буква/кавычка/скобка,
# а не цифра и не типичный мусор.
_NUMERIC_TIGHT = re.compile(
    r"""
    ^\s*
    (?P<uid>\d+(?:\.\d+)*)
    (?P<sep>[\.\)])                     # separator обязателен
    (?=\S)                              # сразу что-то есть
    (?P<title>[A-Za-zА-Яа-яЁё«"(\[].+?)
    \s*$
    """,
    re.VERBOSE,
)


# Legacy numeric-формы
_NUMERIC_FULL = re.compile(
    r"""
    ^\s*
    (?P<uid>\d+(?:\.\d+)*)
    [\.\)]
    \s+
    (?P<title>.{1,320}?)
    \s*$
    """,
    re.VERBOSE,
)


_NUMERIC_NO_DOT = re.compile(
    r"""
    ^\s*
    (?P<uid>\d+(?:\.\d+)+)
    \s{1,3}
    (?P<title>[A-ZА-ЯЁ«"\(].{1,320}?)
    \s*$
    """,
    re.VERBOSE,
)


# Roman / Alpha оставляем только как fallback
_ROMAN_L1 = re.compile(
    r"""
    ^\s*
    (?P<uid>I{1,3}|IV|V?I{0,3}|IX|X{1,3}(?:IX|IV|V?I{0,3})?)
    [\.\)]
    \s+
    (?P<title>.{1,320}?)
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


_ALPHA = re.compile(
    r"""
    ^\s*
    (?P<uid>[A-Za-zА-Яа-яЁё])
    [\.\)]
    \s+
    (?P<title>.{1,320}?)
    \s*$
    """,
    re.VERBOSE,
)


# Защита от строк вида "1 что-то" без явного разделителя "1." / "1)"
_SIMPLE_BAD = re.compile(r"^(\d+)\s+\S")


# Внутренние list-маркеры в title
_INNER_LIST_MARKER = re.compile(
    r"^(?:[\u2022\u2023\u25E6\u2043\u2219\uf0b7•\-–—]|\d+|[A-Za-zА-Яа-яЁё])[\.\)]?\s+(.+)$",
    re.IGNORECASE,
)


_HAS_LETTERS = re.compile(r"[A-Za-zА-Яа-яЁё]")


# TOC/pagination-like noise в хвосте строки
_TOC_DOTS_TAIL = re.compile(r"\s?(?:\.{3,}|·{3,}|•{3,})\s*\d{1,4}\s*$")
_PAGINATION_TAIL = re.compile(
    r"""
    \s*
    (?:
        (?:стр\.?|с\.|page|p\.)\s*\d{1,4}
        (?:\s*(?:из|of)\s*\d{1,4})?
        |
        \d{1,4}\s*/\s*\d{1,4}
    )
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


# Шумовые хвосты / висячая пунктуация
_TRAILING_PUNCT_NOISE = re.compile(r"[\s,;:\-–—]+$")


# Полезное начало title: буква, кавычка, скобка, цифра в особых legal-formulations
_TITLE_START_OK = re.compile(r'^[A-Za-zА-Яа-яЁё«"\(\[]')
_TITLE_HAS_MEANING = re.compile(r"[A-Za-zА-Яа-яЁё]")


def normalize_spaces(text: str) -> str:
    """
    Привести пробелы к аккуратному виду:
    - убрать пробелы в начале/конце;
    - заменить несколько пробелов одним.
    """
    return re.sub(r"\s+", " ", (text or "").strip())


def _has_letters(text: str) -> bool:
    return bool(_HAS_LETTERS.search(text or ""))


def _is_strict_numeric_uid(uid: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.\d+)*", (uid or "").strip()))


def _normalize_uid(uid: str) -> str:
    """
    Каноническая нормализация uid:
    - trim;
    - убрать хвостовую точку, если она случайно попала;
    - не менять семантику.
    """
    u = normalize_spaces(uid)
    u = u.rstrip(".")
    return u


def _uid_depth(uid: str) -> int:
    """
    Глубина numeric uid: "1" -> 1, "1.2" -> 2, "1.2.3" -> 3.
    Для нечисловых uid возвращаем 1.
    """
    u = _normalize_uid(uid)
    if not _is_strict_numeric_uid(u):
        return 1
    return u.count(".") + 1


def _strip_toc_dots_tail(title: str) -> str:
    t = normalize_spaces(title)
    if not t:
        return t
    return normalize_spaces(_TOC_DOTS_TAIL.sub("", t))


def _strip_pagination_tail(title: str) -> str:
    t = normalize_spaces(title)
    if not t:
        return t
    return normalize_spaces(_PAGINATION_TAIL.sub("", t))


def _strip_trailing_punctuation_noise(title: str) -> str:
    t = normalize_spaces(title)
    if not t:
        return t
    return normalize_spaces(_TRAILING_PUNCT_NOISE.sub("", t))


def _postprocess_heading_title(uid: str, title: str) -> str:
    """
    Универсальный пост‑процессинг заголовка:
    - убираем TOC-like хвосты и pagination noise;
    - убираем висящую пунктуацию;
    - нормализуем пробелы.
    """
    t = normalize_spaces(title)
    t = _strip_toc_dots_tail(t)
    t = _strip_pagination_tail(t)
    t = _strip_trailing_punctuation_noise(t)
    return normalize_spaces(t)


def _normalize_title(title: str, *, uid_depth: int) -> str:
    """
    Нормализуем заголовок:
    - приводим пробелы к аккуратному виду;
    - ограничиваем максимальную длину.

    Для корневых разделов (uid_depth == 1) стараемся резать по границе
    предложения/фразы, чтобы оставить компактный заголовок.

    Для вложенных пунктов (uid_depth > 1) избегаем агрессивного реза по
    первой точке/точке с запятой/двоеточию, так как там часто вся
    существенная формулировка в одном длинном предложении —
    используем только мягкий hard-cut по длине.
    """
    t = normalize_spaces(title)

    if len(t) <= _MAX_TITLE_LEN:
        return t

    if uid_depth == 1:
        cut_zone = t[: _MAX_TITLE_LEN + 50]
        for sep in [". ", "; ", ": "]:
            idx = cut_zone.find(sep)
            if 0 < idx <= _MAX_TITLE_LEN:
                return cut_zone[: idx + len(sep.strip())].rstrip(" ;,:-–—")

    return t[:_MAX_TITLE_LEN].rstrip(" ;,:-–—")


def _strip_inner_list_marker(title: str) -> str:
    """
    Убирает внутренний маркер списка из начала title:
    - "1 В течение ..." -> "В течение ..."
    - "4 Наименование ..." -> "Наименование ..."
    - "а) Покупатель ..." -> "Покупатель ..."
    - "• текст" -> "текст"

    ВАЖНО: если после удаления маркера в строке не остаётся буквенного текста,
    оставляем исходный title как есть.
    """
    t = normalize_spaces(title)
    if not t:
        return t

    m = _INNER_LIST_MARKER.match(t)
    if not m:
        return t

    candidate = normalize_spaces(m.group(1))
    if not candidate or not _has_letters(candidate):
        return t

    return candidate


def _looks_like_minimally_valid_title(title: str) -> bool:
    """
    Минимальный parser-level sanity check для title.

    Это НЕ бизнес-решение accept/reject, а защита от явно плохого slicing.
    """
    t = normalize_spaces(title)
    if not t:
        return False

    if len(t) < 2:
        return False

    if not _TITLE_HAS_MEANING.search(t):
        return False

    # Слишком цифровой хвост без буквенного содержания
    letters = sum(ch.isalpha() for ch in t)
    digits = sum(ch.isdigit() for ch in t)
    if letters == 0:
        return False
    if digits > letters * 3 and len(t) < 20:
        return False

    return True


def cleanup_heading_title(uid: str, raw_title: str) -> str:
    """
    Аккуратно почистить заголовок.

    Правила:
    - для вложенных numeric uid (2.2, 3.1, 6.1.1 и т.п.) пробуем убрать
      внутренний маркер списка в начале;
    - корневые разделы 1 / 2 / 3 не трогаем агрессивно;
    - в конце всегда нормализуем пробелы, хвосты и длину.
    """
    title = normalize_spaces(raw_title)
    depth = _uid_depth(uid)

    if depth > 1:
        title = _strip_inner_list_marker(title)

    title = _postprocess_heading_title(uid, title)
    title = _normalize_title(title, uid_depth=depth)
    title = _postprocess_heading_title(uid, title)
    return title


def _normalize_appendix_uid(prefix: str, num: str) -> str:
    """
    Нормализация uid для appendix/приложение.

    Задача: получить стабильный uid, пригодный для построения
    appendix-scope и последующего резолва ссылок, не теряя номер.
    """
    p = normalize_spaces(prefix).lower()
    n = _normalize_uid(num)

    # Отдельно различаем en/ru только в префиксе, номер всегда числовой.
    if "app" in p:
        base = "appendix"
    else:
        base = "приложение"

    return f"{base}-{n}"


def _try_match(pattern: re.Pattern[str], stripped: str) -> tuple[str, str] | None:
    m = pattern.match(stripped)
    if not m:
        return None

    groupdict = m.groupdict()
    uid = groupdict.get("uid")
    title = groupdict.get("title")

    if uid is None or title is None:
        try:
            uid = m.group(1)
            title = m.group(2)
        except Exception:
            return None

    uid = _normalize_uid(str(uid or ""))
    title = cleanup_heading_title(uid, str(title or ""))

    if not uid or not title:
        return None

    if not _looks_like_minimally_valid_title(title):
        return None

    return uid, title


def parse_raw_heading(text: str) -> tuple[str, str] | None:
    """
    Попробовать распарсить строку как заголовок.

    Возвращает:
    - (uid, title) если строка похожа на заголовок;
    - None, если строка не подходит под известные паттерны.

    ВАЖНО:
    - эта функция НЕ решает, "хороший" это заголовок или нет;
      она только выделяет uid и title по формальным признакам;
    - бизнес-валидация (toc‑линии, numeric garbage и т.п.) делается
      на следующем слое.
    """
    stripped = normalize_spaces(text)
    if not stripped:
        return None

    logger.debug(
        "STRUCTURE parse_raw_heading",
        extra={"text_sample": stripped[:80]},
    )

    # 0. Ранний guard против "1 что-то" без "1." / "1)"
    #    Сейчас мы не отбрасываем такие строки на parser-слое,
    #    а только логируем потенциально шумный паттерн — финальное
    #    решение оставляем scorer'у.
    m_bad = _SIMPLE_BAD.match(stripped)
    if m_bad:
        n = m_bad.group(1)
        if not (stripped.startswith(f"{n}.") or stripped.startswith(f"{n})")):
            logger.debug(
                "STRUCTURE parse_raw_heading_simple_bad_guard_hit",
                extra={
                    "numeric_prefix": n,
                    "text_sample": stripped[:80],
                },
            )
            # не выходим, даём шанс нормальным паттернам ниже

    # 1. Основной numeric-паттерн
    result = _try_match(_NUMERIC_MAIN, stripped)
    if result is not None:
        return result

    # 2. Явные Section/Article/Clause-заголовки
    result = _try_match(_SECTIONAL, stripped)
    if result is not None:
        return result

    # 3. Appendix / Приложение
    m_app = _APPENDIX_HEADING.match(stripped)
    if m_app:
        prefix = m_app.group("prefix")
        num = m_app.group("num")
        title = m_app.group("title") or ""
        uid = _normalize_appendix_uid(prefix, num)
        cleaned_title = cleanup_heading_title(uid, title)

        if cleaned_title and _looks_like_minimally_valid_title(cleaned_title):
            return uid, cleaned_title

    # 4. Осторожный tight fallback
    result = _try_match(_NUMERIC_TIGHT, stripped)
    if result is not None:
        uid, title = result
        # Дополнительная защита: title должен начинаться “как заголовок”
        if _TITLE_START_OK.search(title):
            return uid, title

    # 5. Legacy numeric fallback-формы
    for pattern in (_NUMERIC_FULL, _NUMERIC_NO_DOT):
        result = _try_match(pattern, stripped)
        if result is not None:
            return result

    # 6. Roman / Alpha fallback — самые рискованные, держим в самом конце
    for pattern in (_ROMAN_L1, _ALPHA):
        result = _try_match(pattern, stripped)
        if result is not None:
            uid, title = result
            if len(title) >= 3 and _has_letters(title):
                return uid, title

    return None


