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
# Синхронизировано по смыслу с heading_patterns._TOC_DOTS_TAIL / _PAGINATION_TAIL
_TRAILING_TOC_DOTS = re.compile(r"\.{3,}\s*\d{1,4}\s*$")
_PAGE_END_NUMBER = re.compile(
    r"""
    \s*
    (?:
        (?:стр\.?|с\.|page|p\.)\s*\d{1,4}
        (?:\s*(?:из|of)\s*\d{1,4})?
        |
        \d{1,4}\s*/\s*\d{1,4}
        |
        \d{1,4}
    )
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

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

_QUOTED_TERM_START = re.compile(
    r'^\s*(?:"[^"]{1,120}"|«[^»]{1,120}»|„[^“]{1,120}“|“[^”]{1,120}”)'
)

_DEFINITION_TERM_START = re.compile(
    r"""
    ^\s*
    (?:
        (?:"[^"]{1,120}")
        |
        (?:«[^»]{1,120}»)
        |
        (?:[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё0-9\-/()]{1,80})
    )
    \s+
    (?:
        означает(?:ся|ют|ет)?
        |shall\s+mean
        |means
        |именуется
        |подразумевает(?:ся)?
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_LOWERCASE_CONTINUATION_START = re.compile(r"^\s*[a-zа-яё]")

_SUBSTANTIVE_CLAUSE_VERBS = re.compile(
    r"""
    \b(
        обязуется|обязан|вправе|имеет\s+право|должен|должны|осуществляет|осуществляют|
        гарантирует|гарантируют|заверяет|заверяют|подлежит|подлежат|уплачивает|уплачивают|
        выплачивает|выплачивают|компенсирует|компенсируют|несет|несут|
        agrees|shall|must|may|undertakes|warrants|represents|covenants|pays|payable
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_SUBSTANTIVE_CLAUSE_CONNECTORS = re.compile(
    r"""
    \b(
        если|если\s+иное|в\s+случае|при\s+условии|при\s+этом|за\s+исключением|
        если\s+только|при\s+наличии|в\s+течение|не\s+позднее|после\s+того\s+как|
        provided\s+that|except\s+that|subject\s+to|unless|in\s+the\s+event
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Полезно для будущего scoring-слоя:
# заголовок вида ".", "-", "1 ,", "7 , ," и похожий мусор.
_GARBAGE_TITLE = re.compile(r"^[\s\d,.;:()\-–—]+$")

_NUMERIC_UID_STRICT_RE = re.compile(r"^\d+(?:\.\d+)*$")


def _is_strict_numeric_uid(uid: str) -> bool:
    return bool(_NUMERIC_UID_STRICT_RE.fullmatch((uid or "").strip()))


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


def starts_with_quoted_term(text: str) -> bool:
    """
    Начинается ли строка с quoted term:
    - "Term"
    - «Термин»
    Это сильный сигнал definition-like строки.
    """
    t = normalize_spaces(text)
    if not t:
        return False
    return bool(_QUOTED_TERM_START.search(t))


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


def looks_like_definition_term_title(title: str) -> bool:
    """
    Похоже ли title на definition item, а не на section heading.

    Примеры:
    - "Актив" означает ...
    - «Объект» означает ...
    - Purchase Price means ...
    """
    t = normalize_spaces(title)
    if not t:
        return False

    if _DEFINITION_TERM_START.search(t):
        return True

    if starts_with_quoted_term(t) and len(t.split()) >= 3:
        lowered = t.lower()
        if any(marker in lowered for marker in [" означает", " means", " shall mean", " именуется", " подразумевает"]):
            return True

    return False


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

    # У нас уже есть cleanup-хвостов в heading_patterns, но здесь нам важно
    # отдельно подсветить TOC-подобное поведение для scoring.
    if _TRAILING_TOC_DOTS.search(t):
        return True

    # Короткие строки с номером страницы в конце
    if len(t) <= 180 and _PAGE_END_NUMBER.search(t) and "." in t:
        return True

    return False


def looks_like_lowercase_continuation(title: str) -> bool:
    """
    Начало со строчной буквы — сильный сигнал, что это continuation/body line,
    а не самостоятельный heading.
    """
    t = normalize_spaces(title)
    if not t:
        return False

    if not _LOWERCASE_CONTINUATION_START.search(t):
        return False

    # Короткие латинские/римские формы не режем здесь
    if len(t.split()) <= 2 and len(t) <= 16:
        return False

    return True


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

    if looks_like_substantive_clause_line(t) and len(words) >= 14:
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
    if (
        not has_letters(t)
        and len(t.split()) <= 6
        and _ONLY_DIGITS_AND_SEPARATORS.fullmatch(t)
    ):
        return True

    return False


def looks_like_substantive_clause_line(title: str) -> bool:
    """
    Похожа ли строка на substantive legal clause, а не на heading.

    Сигналы:
    - есть "оперативные" глаголы обязательства/права/гарантии;
    - есть clause connectors;
    - строка достаточно длинная;
    - часто есть запятая, но не обязательно есть sentence-ending punctuation.
    """
    t = normalize_spaces(title)
    if not t:
        return False

    words = t.split()
    if len(words) < 6:
        return False

    verb_hit = bool(_SUBSTANTIVE_CLAUSE_VERBS.search(t))
    connector_hit = bool(_SUBSTANTIVE_CLAUSE_CONNECTORS.search(t))
    longish = len(t) >= 60 or len(words) >= 10
    punctuated = "," in t or ";" in t

    if verb_hit and longish:
        return True

    if verb_hit and connector_hit:
        return True

    if connector_hit and punctuated and len(words) >= 10:
        return True

    return False


def looks_like_body_sentence_title(uid: str, title: str) -> bool:
    """
    Похожа ли строка не на заголовок, а на обычное предложение текста.

    Применяем в основном к вложенным numeric uid.
    Это помогает отсекать строки, которые формально выглядят как "3.1 ..."
    но фактически являются clause/body content.
    """
    t = normalize_spaces(title)
    if not t:
        return True

    if not ("." in uid and _is_strict_numeric_uid(uid)):
        return False

    if _COLON_END.search(t):
        return False

    words = t.split()

    if _BODYISH_START.search(t) and len(words) >= 10 and _SENTENCE_END.search(t):
        return True

    if looks_like_substantive_clause_line(t):
        return True

    if len(words) >= 16 and ("," in t or ";" in t):
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
    return bool(re.fullmatch(r"[IVXLCM]+", (uid or "").upper()))


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


