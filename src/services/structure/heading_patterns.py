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
from typing import Tuple, Optional


from core.config import settings
from core.logging import get_logger


logger = get_logger(__name__)


_MAX_TITLE_LEN = max(160, int(settings.STRUCTURE_MAX_CLAUSE_TITLE_LEN or 160))


# --- Паттерны uid / заголовков ---


_SECTIONAL = re.compile(
    r"^(?:section|sec\.?|article|art\.?|clause)\s+"
    r"(\d+(?:\.\d+)*)"
    r"(?:[\.\:\-\)]\s*|\s+)"
    r"(.{1,240})$",
    re.IGNORECASE,
)


# Универсальный numeric-паттерн: "3.1 Продавец обязан", "2.2.4 Наименование ..."
_NUMERIC_HEADING = re.compile(
    r"""
    ^\s*
    (?P<uid>\d+(?:\.\d+)*)
    [\.\)]?              # опциональная точка/скобка после uid
    \s+
    (?P<title>.+?)\s*$   # всё остальное — заголовок
    """,
    re.VERBOSE,
)


_NUMERIC_TIGHT = re.compile(
    r"""
    ^\s*
    (?P<uid>\d+(?:\.\d+)*)
    (?P<sep>[\.\)])?              # точка/скобка после uid (опционально)
    (?!\d)                        # НЕЛЬЗЯ сразу цифру после uid/sep
    \s*
    (?P<title>.+?)\s*$
    """,
    re.VERBOSE,
)


_NUMERIC_FULL = re.compile(
    r"""
    ^(?P<uid>\d+(?:\.\d+)*)
    [\.\)]
    \s+
    (?P<title>.{1,240})$
    """,
    re.VERBOSE,
)


_NUMERIC_NO_DOT = re.compile(
    r"^(\d+(?:\.\d+)+)\s{1,3}([A-ZА-ЯЁ\«\"\(].{1,240})$"
)


_ROMAN_L1 = re.compile(
    r"^(I{1,3}|IV|V?I{0,3}|IX|X{0,3}(?:IX|IV|V?I{0,3}))[\.\)]\s+(.{1,240})$",
    re.IGNORECASE,
)


_ALPHA = re.compile(
    r"^([A-Za-z\u0410-\u042f\u0430-\u044fЁё])[\.)]\s+(.{1,240})$"
)


_SIMPLE_BAD = re.compile(r"^(\d+)\s+\S")


_INNER_LIST_MARKER = re.compile(
    r"^(?:[\u2022\u2023\u25E6\u2043\u2219\uf0b7•\-–—]|\d+|[A-Za-zА-Яа-яЁё])[\.\)]?\s+(.+)$",
    re.IGNORECASE,
)


_HAS_LETTERS = re.compile(r"[A-Za-zА-Яа-яЁё]")


def normalize_spaces(text: str) -> str:
    """
    Привести пробелы к аккуратному виду:
    - убрать пробелы в начале/конце;
    - заменить несколько пробелов одним.
    """
    return re.sub(r"\s+", " ", (text or "").strip())


def _has_letters(text: str) -> bool:
    return bool(_HAS_LETTERS.search(text or ""))


def _uid_depth(uid: str) -> int:
    """
    Глубина numeric uid: "1" -> 1, "1.2" -> 2, "1.2.3" -> 3.
    Для нечисловых uid возвращаем 1.
    """
    u = (uid or "").strip()
    if not u or not u.replace(".", "").isdigit():
        return 1
    return u.count(".") + 1


def _postprocess_heading_title(uid: str, title: str) -> str:
    """
    Универсальный пост‑процессинг заголовка:
    - убираем висящие запятые/точки с запятой в конце;
    - оставляем как есть странные начала, но нормализуем пробелы.
    """
    t = normalize_spaces(title)

    # Убираем финальные разделители, если они одиночные
    t = t.rstrip(";, ")

    # Здесь можно добавлять более агрессивные эвристики позже;
    # сейчас — минимальный универсальный слой.
    return t


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

    # Корневые разделы: пытаемся аккуратно найти конец предложения до лимита
    if uid_depth == 1:
        cut_zone = t[: _MAX_TITLE_LEN + 50]  # небольшой запас после лимита
        for sep in [". ", "; ", ": "]:
            idx = cut_zone.find(sep)
            if 0 < idx <= _MAX_TITLE_LEN:
                return cut_zone[: idx + len(sep.strip())].rstrip(" ;,")

    # Для вложенных uid (uid_depth > 1) и fallback для корневых —
    # жёсткий cut по длине без попытки резать по первой точке.
    return t[:_MAX_TITLE_LEN].rstrip(" ;,")


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


def cleanup_heading_title(uid: str, raw_title: str) -> str:
    """
    Аккуратно почистить заголовок.

    Правила:
    - для вложенных numeric uid (2.2, 3.1, 6.1.1 и т.п.) пробуем убрать
      внутренний маркер списка в начале;
    - корневые разделы 1 / 2 / 3 не трогаем (оставляем как есть);
    - в конце всегда нормализуем пробелы и длину.
    """
    title = normalize_spaces(raw_title)
    depth = _uid_depth(uid)

    if depth > 1:
        # Вложенные numeric uid: пробуем отрезать внутренний маркер списка.
        title = _strip_inner_list_marker(title)

    title = _normalize_title(title, uid_depth=depth)
    title = _postprocess_heading_title(uid, title)
    return title


def parse_raw_heading(text: str) -> Optional[Tuple[str, str]]:
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

    # 1. Универсальный numeric-паттерн:
    #    "3.1 Продавец обязан:", "2.2.4 Наименование Банка-эмитента ..." и т.п.
    m = _NUMERIC_HEADING.match(stripped)
    if m:
        uid = m.group("uid").strip()
        title = cleanup_heading_title(uid, m.group("title"))
        return uid, title

    # 1а. Numeric-паттерн без обязательного пробела, но с запретом цифры после uid
    m = _NUMERIC_TIGHT.match(stripped)
    if m:
        uid = m.group("uid").strip()
        title = cleanup_heading_title(uid, m.group("title"))
        return uid, title

    # 2. Защита от строк вида "1 что‑то", которые не начинаются с "1." или "1)"
    m_bad = _SIMPLE_BAD.match(stripped)
    if m_bad:
        n = m_bad.group(1)
        if not (stripped.startswith(f"{n}.") or stripped.startswith(f"{n})")):
            return None

    # 3. Явные Section/Article/Clause‑заголовки
    m = _SECTIONAL.match(stripped)
    if m:
        uid = m.group(1).strip()
        title = cleanup_heading_title(uid, m.group(2))
        return uid, title

    # 4. Прочие Numeric, Roman, Alpha паттерны (legacy / спец‑кейсы)
    for pattern in (_NUMERIC_FULL, _NUMERIC_NO_DOT, _ROMAN_L1, _ALPHA):
        m = pattern.match(stripped)
        if m:
            uid = m.group(1).strip()
            title = cleanup_heading_title(uid, m.group(2))
            return uid, title

    return None


