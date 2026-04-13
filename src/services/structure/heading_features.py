# src/services/structure/heading_features.py

"""
Feature / predicate слой для heading detection.

Задача этого модуля:
- вычислять простые детерминированные признаки по uid/title/raw_text;
- НЕ строить ClauseTree;
- НЕ принимать финальное архитектурное решение о пайплайне;
- быть промежуточным слоем между parse_raw_heading(...) и scoring / validation.

Для непрофессионального программиста:
- heading_patterns.py отвечает на вопрос:
  "можно ли формально распарсить строку как заголовок?"
- heading_features.py отвечает на вопрос:
  "какими свойствами обладает этот кандидат?"
- heading_scoring.py позже будет отвечать:
  "принимаем, отвергаем или отправляем в ambiguous?"
"""

from __future__ import annotations

import re

from services.structure.heading_patterns import normalize_spaces


_MAX_HEADING_WORDS = 24
_MAX_HEADING_LEN = 220

# Эвристики для TOC / false positives
_TRAILING_TOC_DOTS = re.compile(r"\.{3,}\s*\d{1,4}\s*$")
_PAGE_END_NUMBER = re.compile(r"\s\d{1,4}\s*$")

# Эвристики текста / символов
_ONLY_PUNCT_OR_DIGITS = re.compile(r"^[\d\W_]+$")
_HAS_LETTERS = re.compile(r"[A-Za-zА-Яа-яЁё]")
_HAS_LOWER = re.compile(r"[a-zа-яё]")
_HAS_UPPER = re.compile(r"[A-ZА-ЯЁ]")
_BAD_HEADING_END = re.compile(r"[,;:]$")
_TOO_MUCH_PUNCT = re.compile(r"[,:;]\s+[,:;]")
_SENTENCE_END = re.compile(r"[.!?…]$")
_BODYISH_START = re.compile(
    r"^(?:в|во|на|по|при|если|после|до|согласно|в случае|в течение|для|при условии)\b",
    re.IGNORECASE,
)
_COLON_END = re.compile(r":$")

# Полезно для будущего scoring-слоя:
# заголовок вида ".", "-", "1 ,", "7 , ," и похожий мусор.
_GARBAGE_TITLE = re.compile(r"^[\s\d,.;:()\-–—]+$")

_NUMERIC_UID_STRICT_RE = re.compile(r"^\d+(?:\.\d+)*$")


def _is_strict_numeric_uid(uid: str) -> bool:
    return bool(_NUMERIC_UID_STRICT_RE.fullmatch((uid or "").strip()))


def _has_textual_content(title: str) -> bool:
    """
    Title с реальным текстовым содержимым:
    - есть буквы;
    - не целиком мусор по _GARBAGE_TITLE.
    """
    t = normalize_spaces(title)
    if not t:
        return False
    if not has_letters(t):
        return False
    if _GARBAGE_TITLE.fullmatch(t):
        return False
    return True


def digit_uid_without_textual_title(uid: str, title: str) -> bool:
    """
    Защита от заголовков вида:
    - uid: "1", "2.1", "3.2.4"
      title: пустой / пунктуация / почти только цифры.

    Если uid строго numeric, title обязан быть текстовым.
    """
    if not _is_strict_numeric_uid(uid):
        return False

    return not _has_textual_content(title)

def has_letters(text: str) -> bool:
    """
    Есть ли в строке хотя бы одна буква.
    """
    return bool(_HAS_LETTERS.search(text or ""))


def has_upper(text: str) -> bool:
    """
    Есть ли в строке заглавные буквы.
    """
    return bool(_HAS_UPPER.search(text or ""))


def has_lower(text: str) -> bool:
    """
    Есть ли в строке строчные буквы.
    """
    return bool(_HAS_LOWER.search(text or ""))


def level_from_uid(uid: str) -> int:
    """
    Определить глубину numeric uid:
    - "1" -> 1
    - "2.3" -> 2
    - "4.1.5" -> 3

    Для roman/alpha uid эта функция всё равно вернёт 1,
    потому что в них нет точки.
    """
    return uid.count(".") + 1


def looks_like_toc_line(text: str) -> bool:
    """
    Похожа ли строка на строку оглавления.

    Примеры:
    - "1. Definitions .......... 4"
    - "2. Scope 7"

    Это важно, потому что TOC-строки часто формально похожи на заголовки,
    но не должны попадать в реальное дерево документа.
    """
    t = normalize_spaces(text)
    if not t:
        return False

    if _TRAILING_TOC_DOTS.search(t):
        return True

    if len(t) <= 180 and _PAGE_END_NUMBER.search(t) and "." in t:
        return True

    return False


def is_bad_heading_title(title: str) -> bool:
    """
    Явно плохой заголовок.

    Сюда попадают случаи, когда title:
    - пустой;
    - слишком длинный;
    - состоит из слишком большого числа слов;
    - не содержит букв;
    - состоит только из цифр / пунктуации;
    - заканчивается на подозрительный символ;
    - содержит "ломаную" пунктуацию вида ", ,", ": ;" и т.п.
    """
    t = normalize_spaces(title)
    if not t:
        return True

    if len(t) > _MAX_HEADING_LEN:
        return True

    words = t.split()
    if len(words) > _MAX_HEADING_WORDS:
        return True

    if not has_letters(t):
        return True

    if _ONLY_PUNCT_OR_DIGITS.match(t):
        return True

    # Одно "слово", полностью из цифр — плохой заголовок
    if len(words) == 1 and words[0].isdigit():
        return True

    if _BAD_HEADING_END.search(t):
        return True

    if _TOO_MUCH_PUNCT.search(t):
        return True

    return False


_ONLY_DIGITS_AND_SEPARATORS = re.compile(r"^[\d\s,.;:()\-–—]+$")


def is_garbage_heading_title(title: str) -> bool:
    """
    Более узкая проверка на явно мусорный title.

    Примеры:
    - "."
    - "-"
    - "45 46"
    - "1 ,"
    - "7 , ,"
    - "1 11 334 700"
    """
    t = normalize_spaces(title)
    if not t:
        return True

    # Чистый пунктуационный/цифровой мусор
    if _GARBAGE_TITLE.fullmatch(t) and not has_letters(t):
        return True

    # Короткий заголовок, который почти целиком состоит из цифр и разделителей
    if not has_letters(t) and len(t.split()) <= 6 and _ONLY_DIGITS_AND_SEPARATORS.fullmatch(t):
        return True

    return False


def looks_like_body_sentence_title(uid: str, title: str) -> bool:
    """
    Похожа ли строка не на заголовок, а на обычное предложение текста.

    Сейчас эту эвристику применяем в основном к вложенным numeric uid.
    Это помогает отсекать строки, которые формально выглядят как "3.1 ..."
    но фактически являются частью тела документа после OCR/normalization.
    """
    t = normalize_spaces(title)
    if not t:
        return True

    # Только вложенные numeric uid
    if not ("." in uid and _is_strict_numeric_uid(uid)):
        return False

    # Заголовок с двоеточием — скорее валиден
    if _COLON_END.search(t):
        return False

    words = t.split()

    # Очень длинная фраза с типичным "телесным" началом и точкой в конце
    if _BODYISH_START.search(t) and len(words) >= 12 and _SENTENCE_END.search(t):
        return True

    return False


def uid_is_plausible(uid: str) -> bool:
    """
    Разумный ли numeric uid.

    Правила:
    - все части uid должны быть числами;
    - каждая часть > 0 и <= 999;
    - глубина не должна быть запредельной;
    - корневой uid не должен быть слишком большим для типичных договоров.
    """
    parts = uid.split(".")
    if not parts:
        return False

    for part in parts:
        if not part.isdigit():
            return False

        try:
            number = int(part)
        except ValueError:
            return False

        if number <= 0 or number > 999:
            return False

    if len(parts) > 8:
        return False

    # Новый грубый порог для корневого уровня:
    # uid вида "107" считаем маловероятным для договоров.
    if len(parts) == 1:
        root = int(parts[0])
        if root > 50:
            return False

    return True


def roman_uid_is_plausible(uid: str) -> bool:
    """
    Похожа ли строка на валидный roman uid.
    """
    return bool(re.fullmatch(r"[IVXLCM]+", uid.upper()))


def alpha_uid_is_plausible(uid: str) -> bool:
    """
    Похожа ли строка на валидный буквенный uid.
    """
    return len(uid) == 1 and has_letters(uid)


def classify_uid_kind(uid: str) -> str:
    """
    Определить тип uid.

    Возвращает одно из значений:
    - "numeric"
    - "roman"
    - "alpha"
    - "other"
    """
    normalized = normalize_spaces(uid)

    if _is_strict_numeric_uid(normalized):
        return "numeric"

    if roman_uid_is_plausible(normalized):
        return "roman"

    if alpha_uid_is_plausible(normalized):
        return "alpha"

    return "other"


