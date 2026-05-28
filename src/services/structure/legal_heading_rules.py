# src/services/structure/legal_heading_rules.py

"""
Юридические эвристики для structural heading pipeline.

Зачем нужен этот файл:
- не смешивать "общие heading features" с юридическими правилами;
- централизовать legal-specific признаки для element_classifier и heading_scoring;
- дать переиспользуемые helpers для:
  1) definition item detection,
  2) appendix heading detection,
  3) signature / requisites negative rules,
  4) continuity / monotonic-series helpers.

Для непрофессионального программиста:
- heading_patterns.py отвечает за формальный парсинг строки как (uid, title)
- heading_features.py отвечает за общие признаки строки
- legal_heading_rules.py отвечает за юридические признаки строки
- heading_scoring.py потом решает: accepted / rejected / ambiguous
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from services.structure.heading_patterns import normalize_spaces
from services.structure.models import (
    BODY_SEMANTIC_TYPES,
)
from services.structure.models import (
    HEADING_SEMANTIC_TYPES as HEADING_LIKE_SEMANTIC_TYPES,
)

# ============================================================================
# Semantic type constants — импортируем из models.py как canonical source
# ============================================================================
# Локальные алиасы для удобного использования внутри модуля.
# Не дублируем значения — только переименовываем для краткости.

# BODY_LIKE_SEMANTIC_TYPES включает также table_content,
# которого нет в models.py (это element_type, не semantic_type).
# Держим расширенный вариант локально.
BODY_LIKE_SEMANTIC_TYPES: frozenset[str] = frozenset(BODY_SEMANTIC_TYPES | {"table_content"})


# ============================================================================
# Regex / паттерны
# ============================================================================

_NUMERIC_UID_RE = re.compile(r"^\d+(?:\.\d+)*$")
_OPTIONAL_NUMERIC_PREFIX_RE = re.compile(
    r"""
    ^\s*
    (?:
        \d+(?:\.\d+)*   # 1 / 1.1 / 2.3.4
        [\.\)]?         # optional trailing separator
        \s+
    )?
    (?P<body>.+?)\s*$
    """,
    re.VERBOSE,
)

_HAS_LETTERS_RE = re.compile(r"[A-Za-zА-Яа-яЁё]")
_STARTS_WITH_LOWER_RE = re.compile(r"^\s*[a-zа-яё]")
_SENTENCE_END_RE = re.compile(r"[.!?…;:]$")
_QUOTED_TERM_START_RE = re.compile(
    r'^\s*(?:"[^"]{1,120}"|«[^»]{1,120}»|„[^“]{1,120}“|“[^”]{1,120}”)'
)

_DEFINITION_VERB_RE = re.compile(
    r"""
    \b(
        означает(?:ся|ют|ет)?
        |понимается
        |именуется
        |подразумевает(?:ся)?
        |shall\s+mean
        |means
        |shall\s+have\s+the\s+meaning
        |has\s+the\s+meaning
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_DEFINITION_LEAD_RE = re.compile(
    r"""
    ^\s*
    (?:
        (?:"[^"]{1,120}")
        |
        (?:«[^»]{1,120}»)
        |
        (?:[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё0-9/&\-\(\)\.]{1,80})
    )
    \s+
    (?:
        означает(?:ся|ют|ет)?
        |понимается
        |именуется
        |подразумевает(?:ся)?
        |shall\s+mean
        |means
        |shall\s+have\s+the\s+meaning
        |has\s+the\s+meaning
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_DEFINITION_COLON_RE = re.compile(
    r"""
    ^\s*
    (?:
        (?:"[^"]{1,120}")
        |
        (?:«[^»]{1,120}»)
        |
        (?:[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё0-9/&\-\(\)\.]{1,80})
    )
    \s*[:—-]\s+
    .+
    $
    """,
    re.IGNORECASE | re.VERBOSE,
)

_APPENDIX_START_RE = re.compile(
    r"""
    ^\s*
    (?:
        приложение
        |appendix
        |annex
        |schedule
        |exhibit
    )
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_APPENDIX_HEADING_RE = re.compile(
    r"""
    ^\s*
    (?:
        приложение
        |appendix
        |annex
        |schedule
        |exhibit
    )
    \b
    \s*
    (?:
        №|n|no\.?
    )?
    \s*
    (?:
        [A-ZА-ЯЁ]
        |
        \d{1,3}
        |
        [IVXLCM]{1,8}
    )?
    (?:\s*[-–—:]\s*.+)?                 # optional short title
    (?:\s+(?:к|to)\s+(?:договору|контракту|agreement|contract).+)?  # optional tail
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

_SIGNATURE_KEYWORDS_RE = re.compile(
    r"""
    \b(
        подписи\s+сторон
        |подписи
        |подпись
        |стороны\s+подписали
        |от\s+заказчика
        |от\s+исполнителя
        |от\s+поставщика
        |от\s+покупателя
        |от\s+арендатора
        |от\s+арендодателя
        |от\s+подрядчика
        |генеральный\s+директор
        |директор
        |уполномоченный\s+представитель
        |signature
        |signatures
        |for\s+the\s+buyer
        |for\s+the\s+seller
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_SEAL_RE = re.compile(r"\bм\.?\s*п\.?\b", re.IGNORECASE)

_REQUISITES_KEYWORDS_RE = re.compile(
    r"""
    \b(
        реквизиты
        |реквизиты\s+сторон
        |юридический\s+адрес
        |почтовый\s+адрес
        |адрес\s+местонахождения
        |адрес\s+для\s+корреспонденции
        |инн
        |кпп
        |огрн
        |окпо
        |оквэд
        |банк
        |бик
        |корреспондентский\s+счет
        |корреспондентский\s+сч[её]т
        |корр\.\s*счет
        |кор\s*счет
        |расчетный\s+счет
        |расч[её]тный\s+сч[её]т
        |iban
        |swift
        |e-mail
        |email
        |телефон
        |тел\.
        |факс
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_SUBSTANTIVE_VERBS_RE = re.compile(
    r"""
    \b(
        обязуется|обязан|обязаны|вправе|имеет\s+право|должен|должны|
        гарантирует|гарантируют|заверяет|заверяют|
        подлежит|подлежат|уплачивает|уплачивают|
        выплачивает|выплачивают|компенсирует|компенсируют|
        несет|несут|осуществляет|осуществляют|
        agrees|shall|must|may|undertakes|warrants|represents|covenants|pays|payable
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_SUBSTANTIVE_CONNECTORS_RE = re.compile(
    r"""
    \b(
        если|если\s+иное|в\s+случае|при\s+условии|при\s+этом|за\s+исключением|
        в\s+течение|не\s+позднее|после\s+того\s+как|
        provided\s+that|except\s+that|subject\s+to|unless|in\s+the\s+event
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


# ============================================================================
# Базовые helpers
# ============================================================================


def _normalized_text(text: str) -> str:
    return normalize_spaces(text or "")


def _has_letters(text: str) -> bool:
    return bool(_HAS_LETTERS_RE.search(text or ""))


def _strip_optional_numeric_prefix(text: str) -> str:
    """
    Убирает ведущий numeric uid, если он есть.

    Примеры:
    - '1.1 Definitions' -> 'Definitions'
    - '2.3 "Term" means ...' -> '"Term" means ...'
    """
    t = _normalized_text(text)
    if not t:
        return ""

    m = _OPTIONAL_NUMERIC_PREFIX_RE.match(t)
    if not m:
        return t

    body = _normalized_text(m.group("body"))
    return body or t


def _normalize_semantic_type(value: Any) -> str:
    return _normalized_text(str(value or "")).lower()


def get_semantic_element_type(element: Mapping[str, Any] | None) -> str | None:
    """
    Безопасно вытаскивает semantic_element_type из element metadata.

    Если semantic_element_type ещё не проставлен,
    используем fallback на обычный element_type.
    """
    if not isinstance(element, Mapping):
        return None

    metadata = element.get("metadata")
    if isinstance(metadata, Mapping):
        semantic = _normalize_semantic_type(metadata.get("semantic_element_type"))
        if semantic:
            return semantic

    fallback = _normalize_semantic_type(element.get("element_type"))
    return fallback or None


# ============================================================================
# Definition item detection
# ============================================================================


def looks_like_definition_item(text: str) -> bool:
    """
    Определяет, похожа ли строка на definition item, а не на section heading.

    Ловит типичные случаи:
    - "Термин" означает ...
    - «Термин» означает ...
    - Purchase Price means ...
    - Goods: ...
    - 1.1 "Seller" means ...

    Функция специально более строгая, чем общий heading parser:
    она ищет именно юридическую формулу определения.
    """
    t = _normalized_text(text)
    if not t:
        return False

    body = _strip_optional_numeric_prefix(t)
    if not body or not _has_letters(body):
        return False

    # Appendix / signature / requisites не считаем определением
    if looks_like_appendix_heading(body):
        return False
    if looks_like_signature_heading(body):
        return False
    if looks_like_requisites_heading(body):
        return False

    words = body.split()
    if len(words) < 2:
        return False

    # Самый сильный сигнал: явный definition lead
    if _DEFINITION_LEAD_RE.search(body):
        return True

    # Частый legal-шаблон: "Term": ...
    if _DEFINITION_COLON_RE.search(body):
        return True

    # Более мягкий случай:
    # quoted term + definition verb дальше по строке
    if _QUOTED_TERM_START_RE.search(body) and _DEFINITION_VERB_RE.search(body):
        return True

    # Ещё один полезный случай:
    # строка начинается с TitleCase-термина и дальше идёт means/означает
    first_chunk = body[:120]
    if _DEFINITION_VERB_RE.search(first_chunk):
        lead = body.split(maxsplit=1)[0]
        if lead and lead[0].isupper():
            return True

    return False


def looks_like_definition_series(
    lines: Sequence[str],
    *,
    min_hits: int = 2,
    min_ratio: float = 0.6,
) -> bool:
    # Нормализуем min_ratio в допустимый диапазон [0.0, 1.0].
    # Это защита от случайных ошибок вызывающего кода:
    # например если передали 60 вместо 0.6.
    min_ratio = max(0.0, min(1.0, float(min_ratio)))

    non_empty = [_normalized_text(line) for line in lines if _normalized_text(line)]
    if len(non_empty) < min_hits:
        return False

    hits = sum(1 for line in non_empty if looks_like_definition_item(line))
    if hits < min_hits:
        return False

    ratio = hits / len(non_empty)
    return ratio >= min_ratio


# ============================================================================
# Appendix detection
# ============================================================================


def looks_like_appendix_heading(text: str) -> bool:
    """
    Проверяет, похожа ли строка на заголовок приложения.

    Примеры:
    - Приложение №1
    - Appendix 2
    - Annex A
    - Schedule I
    """
    t = _normalized_text(text)
    if not t:
        return False

    if not _APPENDIX_START_RE.search(t):
        return False

    # Слишком длинные substantive строки не считаем appendix heading
    if len(t) > 220 or len(t.split()) > 18:
        return False

    if _SUBSTANTIVE_VERBS_RE.search(t):
        return False

    if _APPENDIX_HEADING_RE.search(t):
        return True

    return False


# ============================================================================
# Signature / requisites negative rules
# ============================================================================


def looks_like_signature_heading(text: str) -> bool:
    """
    Похоже ли на блок подписей.

    Такие строки не должны получать приоритет как normal section headings.
    """
    t = _normalized_text(text)
    if not t:
        return False

    if _SIGNATURE_KEYWORDS_RE.search(t):
        return True

    if _SEAL_RE.search(t):
        return True

    if "________" in t or "________________" in t:
        return True

    return False


def looks_like_requisites_heading(text: str) -> bool:
    """
    Похоже ли на реквизиты / банковский блок / адресный блок.
    """
    t = _normalized_text(text)
    if not t:
        return False

    keyword_hits = len(_REQUISITES_KEYWORDS_RE.findall(t))
    if keyword_hits >= 2:
        return True

    if keyword_hits >= 1 and t.count(":") >= 2:
        return True

    return False


def looks_like_signature_or_requisites_heading(text: str) -> bool:
    """
    Объединённый negative rule для scorer-а и classifier-а.
    """
    return looks_like_signature_heading(text) or looks_like_requisites_heading(text)


# ============================================================================
# Continuity helpers
# ============================================================================


def is_heading_like_semantic_type(value: Any) -> bool:
    return _normalize_semantic_type(value) in HEADING_LIKE_SEMANTIC_TYPES


def is_body_like_semantic_type(value: Any) -> bool:
    return _normalize_semantic_type(value) in BODY_LIKE_SEMANTIC_TYPES


def compute_heading_continuity_signals(
    *,
    prev_element: Mapping[str, Any] | None = None,
    next_element: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Возвращает простые continuity-сигналы вокруг кандидата.

    Зачем это нужно:
    - если после heading идёт обычный body -> это хороший знак;
    - если после heading сразу идёт другой heading -> это слабый знак;
    - если next line похожа на definition/body sentence -> штрафной сигнал.

    Функция ничего не "решает" сама.
    Она только возвращает признаки для scorer-а / builder-а.
    """
    prev_type = get_semantic_element_type(prev_element)
    next_type = get_semantic_element_type(next_element)

    next_text = _normalized_text(str((next_element or {}).get("text") or ""))

    next_is_definition_like = looks_like_definition_item(next_text)
    next_is_appendix_heading = looks_like_appendix_heading(next_text)
    next_is_signature_or_requisites = looks_like_signature_or_requisites_heading(next_text)

    signals = {
        "prev_semantic_type": prev_type,
        "next_semantic_type": next_type,
        "prev_is_heading_like": is_heading_like_semantic_type(prev_type),
        "prev_is_body_like": is_body_like_semantic_type(prev_type),
        "next_is_heading_like": is_heading_like_semantic_type(next_type),
        "next_is_body_like": is_body_like_semantic_type(next_type),
        "next_is_definition_like": next_is_definition_like,
        "next_is_appendix_heading": next_is_appendix_heading,
        "next_is_signature_or_requisites": next_is_signature_or_requisites,
        "next_starts_with_lowercase": bool(_STARTS_WITH_LOWER_RE.search(next_text))
        if next_text
        else False,
        "next_ends_like_sentence": bool(_SENTENCE_END_RE.search(next_text)) if next_text else False,
        "next_has_substantive_verb": bool(_SUBSTANTIVE_VERBS_RE.search(next_text))
        if next_text
        else False,
        "next_has_substantive_connector": bool(_SUBSTANTIVE_CONNECTORS_RE.search(next_text))
        if next_text
        else False,
        "continuity_body_positive": False,
        "continuity_heading_negative": False,
        "continuity_definition_negative": False,
    }

    # Позитивный continuity:
    # после заголовка идёт body/list/enumerated clause/table-like line
    if signals["next_is_body_like"] and not next_is_definition_like:
        signals["continuity_body_positive"] = True

    # Негативный continuity:
    # после заголовка сразу идёт ещё один heading
    if signals["next_is_heading_like"] or next_is_appendix_heading:
        signals["continuity_heading_negative"] = True

    # Отдельный негатив для definition-like continuation
    if next_is_definition_like or next_is_signature_or_requisites:
        signals["continuity_definition_negative"] = True

    return signals


# ============================================================================
# Numeric UID / monotonic-series helpers
# ============================================================================


def parse_numeric_uid_parts(uid: str) -> tuple[int, ...] | None:
    """
    Превращает numeric uid в tuple[int].

    Примеры:
    - "1" -> (1,)
    - "2.3" -> (2, 3)
    - "4.1.5" -> (4, 1, 5)
    """
    normalized = _normalized_text(uid)
    if not normalized or not _NUMERIC_UID_RE.fullmatch(normalized):
        return None

    try:
        parts = tuple(int(part) for part in normalized.split("."))
    except Exception:
        return None

    if not parts or any(part <= 0 for part in parts):
        return None

    return parts


def numeric_uid_depth(uid: str) -> int:
    parts = parse_numeric_uid_parts(uid)
    if not parts:
        return 1
    return len(parts)


def is_direct_child_uid(parent_uid: str, candidate_uid: str) -> bool:
    """
    Проверяет отношение parent -> direct child.

    Примеры:
    - 1 -> 1.1  = True
    - 1.1 -> 1.1.1 = True
    - 1 -> 1.2.1 = False
    """
    parent_parts = parse_numeric_uid_parts(parent_uid)
    candidate_parts = parse_numeric_uid_parts(candidate_uid)

    if not parent_parts or not candidate_parts:
        return False

    if len(candidate_parts) != len(parent_parts) + 1:
        return False

    return candidate_parts[: len(parent_parts)] == parent_parts


def is_next_peer_uid(prev_uid: str, candidate_uid: str) -> bool:
    """
    Проверяет, является ли candidate_uid следующим peer-узлом
    относительно prev_uid.

    Примеры:
    - 1 -> 2 = True
    - 1.1 -> 1.2 = True
    - 1.1 -> 2.1 = False
    """
    prev_parts = parse_numeric_uid_parts(prev_uid)
    candidate_parts = parse_numeric_uid_parts(candidate_uid)

    if not prev_parts or not candidate_parts:
        return False

    if len(prev_parts) != len(candidate_parts):
        return False

    if len(prev_parts) == 1:
        return candidate_parts[0] == prev_parts[0] + 1

    if candidate_parts[:-1] != prev_parts[:-1]:
        return False

    return candidate_parts[-1] == prev_parts[-1] + 1


def build_numeric_uid_continuity(
    *,
    prev_uid: str | None = None,
    current_uid: str | None = None,
    next_uid: str | None = None,
) -> dict[str, bool]:
    """
    Возвращает простые monotonic-series сигналы для numeric uid.

    Это пригодится:
    - в heading scoring,
    - в hierarchy state machine,
    - в diagnostics.
    """
    prev_uid = _normalized_text(prev_uid or "")
    current_uid = _normalized_text(current_uid or "")
    next_uid = _normalized_text(next_uid or "")

    return {
        "has_prev_uid": bool(prev_uid),
        "has_next_uid": bool(next_uid),
        "prev_is_next_peer": bool(
            prev_uid and current_uid and is_next_peer_uid(prev_uid, current_uid)
        ),
        "next_is_next_peer": bool(
            current_uid and next_uid and is_next_peer_uid(current_uid, next_uid)
        ),
        "current_is_child_of_prev": bool(
            prev_uid and current_uid and is_direct_child_uid(prev_uid, current_uid)
        ),
        "next_is_child_of_current": bool(
            current_uid and next_uid and is_direct_child_uid(current_uid, next_uid)
        ),
    }
