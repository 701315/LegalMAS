# src/services/structure/element_classifier/_detectors.py

"""Детекторы для различных типов элементов документа.

Содержит специализированные функции для определения:
- Page artifacts (номера страниц, колонтитулы)
- Блоков подписей
- Блоков реквизитов
- Табличного контента
- Элементов списков
- Заголовков
- TOC строк
- False positive TOC кандидатов
- Шумовых/неизвестных элементов
"""

from __future__ import annotations

import re

from ._config import (
    BOUNDARY_KEYWORDS_RU,
    DOT_LEADER_RE,
    LIST_ITEM_RE,
    PAGE_ARTIFACT_PATTERNS,
    REQUISITES_KEYWORDS_RU,
    ROMAN_HEADING_RE,
    ROMAN_LIST_ITEM_RE,
    ROOT_HEADING_NO_DOT_RE,
    SIGNATURE_KEYWORDS_RU,
    TOC_HEADER_PATTERNS,
    TOC_LINE_UID_PREFIX,
    TOC_SCORE_STRONG,
    TOC_SCORE_WEAK,
    UID_HEADING_RE,
)
from ._text_utils import _normalize_for_match, _normalize_text


def _is_toc_header(text: str) -> bool:
    """Проверяет, является ли текст заголовком оглавления.

    Args:
        text: Текст элемента

    Returns:
        True если текст соответствует паттернам TOC заголовка
    """
    normalized = _normalize_for_match(text)
    return any(re.fullmatch(pattern, normalized) for pattern in TOC_HEADER_PATTERNS)


def _toc_line_score(text: str) -> tuple[float, list[str]]:
    """Вычисляет локальный score TOC-похожести строки.

    Args:
        text: Текст для анализа

    Returns:
        Кортеж (score, reasons) где score в диапазоне 0.0-1.0
    """
    normalized = _normalize_text(text)
    normalized_lc = normalized.lower()

    if not normalized:
        return 0.0, ["empty"]

    reasons: list[str] = []
    score = 0.0

    has_trailing_page = bool(re.search(r"\b\d{1,4}\s*$", normalized))
    has_dot_leader = bool(DOT_LEADER_RE.search(normalized))
    has_uid_heading = bool(UID_HEADING_RE.match(normalized))
    has_root_heading = bool(ROOT_HEADING_NO_DOT_RE.match(normalized))
    words = normalized.split()
    word_count = len(words)

    if has_trailing_page:
        score += 0.34
        reasons.append("trailing_page_number")

    if has_dot_leader and has_trailing_page:
        score += 0.38
        reasons.append("dot_leader_with_page")

    if has_uid_heading and has_trailing_page:
        score += 0.22
        reasons.append("uid_heading_with_page")

    if has_root_heading and has_trailing_page:
        score += 0.16
        reasons.append("root_heading_with_page")

    if (
        any(normalized_lc.startswith(prefix) for prefix in TOC_LINE_UID_PREFIX)
        and has_trailing_page
    ):
        score += 0.10
        reasons.append("toc_uid_prefix_with_page")

    if word_count <= 14:
        score += 0.08
        reasons.append("short_line")
    elif word_count >= 20:
        score -= 0.22
        reasons.append("too_long_for_toc")

    if len(normalized) >= 160:
        score -= 0.25
        reasons.append("line_too_long")

    if ":" in normalized and not has_dot_leader:
        score -= 0.08
        reasons.append("colon_without_dot_leader")

    if normalized.endswith((".", ";")):
        score -= 0.10
        reasons.append("body_like_terminal_punctuation")

    lower_hits = sum(1 for w in words[1:] if w and w[0].islower())
    if word_count >= 8 and lower_hits >= max(3, word_count // 2):
        score -= 0.14
        reasons.append("body_like_lowercase_flow")

    if has_trailing_page and not has_dot_leader and not has_uid_heading and word_count >= 10:
        score -= 0.18
        reasons.append("weak_page_tail_only")

    score = max(0.0, min(score, 1.0))
    return score, reasons


def _is_toc_line(text: str) -> bool:
    """Проверяет, является ли текст сильным TOC кандидатом.

    Args:
        text: Текст элемента

    Returns:
        True если TOC score >= 0.78
    """
    score, _ = _toc_line_score(text)
    return score >= TOC_SCORE_STRONG


def _looks_like_toc_false_positive(text: str) -> bool:
    """Локальный детектор false positive TOC-кандидатов (до guard).

    Args:
        text: Текст для анализа

    Returns:
        True если текст похож на TOC, но вероятно является substantive текстом
    """
    normalized = _normalize_text(text)
    if not normalized:
        return False

    words = normalized.split()
    word_count = len(words)

    if word_count >= 18:
        return True

    if ":" in normalized and not DOT_LEADER_RE.search(normalized):
        return True

    if normalized.endswith((".", ";")) and word_count >= 8:
        return True

    if re.search(r"[«\"'].+[»\"']", normalized) and word_count >= 6:
        return True

    return False


def _looks_like_signature_block(text: str) -> bool:
    """Проверяет, похож ли текст на блок подписей.

    Args:
        text: Текст элемента

    Returns:
        True при обнаружении признаков блока подписей
    """
    normalized = _normalize_for_match(text)

    if any(keyword in normalized for keyword in SIGNATURE_KEYWORDS_RU):
        return True
    if "________________" in text or "________" in text:
        return True
    if re.search(r"/\s*подпись\s*/", normalized):
        return True
    if re.search(r"\bм\.?\s*п\.?\b", normalized):
        return True

    return False


def _looks_like_requisites_block(text: str) -> bool:
    """Проверяет, похож ли текст на блок реквизитов.

    Args:
        text: Текст элемента

    Returns:
        True при обнаружении признаков блока реквизитов
    """
    normalized = _normalize_for_match(text)

    keyword_hits = sum(1 for kw in REQUISITES_KEYWORDS_RU if kw in normalized)
    if keyword_hits >= 2:
        return True

    colon_count = text.count(":")
    if colon_count >= 2 and keyword_hits >= 1:
        return True

    if re.search(r"\b(инн|кпп|огрн|бик|iban|swift)\b", normalized):
        return True

    return False


def _is_canonical_boundary_marker(text: str) -> bool:
    """Проверяет, является ли текст canonical boundary marker.

    Это защита от ложной demotion реальных appendix/amendment заголовков
    в page_artifact только из-за их позиции вверху/внизу страницы.
    """
    from services.structure._segmenter.patterns import (
        APPENDIX_RE,
        AMENDMENT_RE,
    )

    normalized = _normalize_for_match(text)
    if not normalized:
        return False

    return bool(APPENDIX_RE.match(normalized) or AMENDMENT_RE.match(normalized))


def _looks_like_page_artifact(text: str, top_ratio: float, bottom_ratio: float) -> bool:
    """Проверяет, является ли элемент page artifact (номер страницы, колонтитул).

    Args:
        text: Текст элемента
        top_ratio: Относительное расстояние от верхнего края (0-1)
        bottom_ratio: Относительное расстояние от нижнего края (0-1)

    Returns:
        True если элемент похож на page artifact
    """
    normalized = _normalize_for_match(text)

    if any(re.fullmatch(pattern, normalized) for pattern in PAGE_ARTIFACT_PATTERNS):
        return top_ratio <= 0.08 or bottom_ratio <= 0.08

    if len(normalized) <= 25 and (top_ratio <= 0.04 or bottom_ratio <= 0.04):
        if re.search(r"\b(договор|приложение|акт|страница|page)\b", normalized):
            # Реальный canonical boundary marker не должен демотиться в page_artifact.
            if _is_canonical_boundary_marker(text):
                return False
            return True

    return False


def _looks_like_table_content(text: str) -> bool:
    """Проверяет, похож ли текст на табличный контент.

    Args:
        text: Текст элемента

    Returns:
        True при обнаружении признаков таблицы
    """
    normalized = _normalize_text(text)

    if "|" in normalized and normalized.count("|") >= 2:
        return True
    if "\t" in text:
        return True
    if normalized.count(";") >= 3:
        return True

    tokens = normalized.split()
    numeric_tokens = sum(1 for t in tokens if re.fullmatch(r"[\d\.,/%()-]+", t))
    if len(tokens) >= 5 and numeric_tokens >= 3:
        return True

    return False


def _is_roman_heading(text: str) -> bool:
    """
    Проверяет, является ли текст заголовком раздела.

    КОНТРАКТ: принимает ОРИГИНАЛЬНЫЙ (не lowercased) текст элемента.
    Регистрозависимые проверки (ROMAN_HEADING_RE, isupper) выполняются
    на оригинальном тексте; нормализация используется только для длины.

    Критерии:
    1. Римская цифра + разделитель + заглавная буква (универсальный паттерн)
    2. Текст короткий, полностью заглавный, без терминальной пунктуации
       (признак heading для любого языка с uppercase/lowercase)
    """
    original = text.strip()
    if not original or len(original) > 120:
        return False

    # Критерий 1: Римская цифра + заглавная буква (на оригинальном тексте)
    if ROMAN_HEADING_RE.match(original):
        return True

    # Критерий 2: ALL-CAPS fallback (на оригинальном тексте).
    # Исключаем строки, начинающиеся с цифры: "1. ПРЕДМЕТ ДОГОВОРА" —
    # это нумерованный элемент, а не заголовок раздела. Числовые заголовки
    # обрабатываются через parse_raw_heading + numeric heading override.
    if (
        original.isupper()
        and len(original) <= 60
        and not original[0].isdigit()
        and not original.rstrip().endswith(('.', ',', ';', ':'))
    ):
        return True

    return False


def _looks_like_list_item(text: str) -> bool:
    """Проверяет, является ли текст элементом списка.

    КОНТРАКТ: принимает ОРИГИНАЛЬНЫЙ (не lowercased) текст.
    Регистрозависимый guard (_is_roman_heading) проверяется на оригинале,
    regex-матчинг — на нормализованном тексте.

    Args:
        text: Оригинальный текст элемента

    Returns:
        True если текст соответствует паттернам списка
    """
    original = text.strip()
    normalized = _normalize_text(text)

    # Guard: римский/ALL-CAPS заголовок не является list_item
    if _is_roman_heading(original):
        return False

    return bool(LIST_ITEM_RE.match(normalized) or ROMAN_LIST_ITEM_RE.match(normalized))


def _heading_candidate_confidence(*, text: str, raw_type: str | None) -> float:
    """Вычисляет уверенность в том, что текст является заголовком.

    КОНТРАКТ: принимает ОРИГИНАЛЬНЫЙ (не lowercased) текст.
    Регистрозависимые проверки выполняются на оригинале.

    Args:
        text: Оригинальный текст элемента
        raw_type: Сырой тип из экстрактора (если есть)

    Returns:
        Оценка уверенности 0.0-1.0
    """
    original = text.strip()
    normalized = _normalize_text(text)
    score = 0.0

    # Бонус за универсальные признаки заголовка (на оригинальном тексте)
    if _is_roman_heading(original):
        score += 0.50

    if raw_type == "heading":
        score += 0.45
    if UID_HEADING_RE.match(normalized):
        score += 0.35
    if ROOT_HEADING_NO_DOT_RE.match(normalized) and not _looks_like_list_item(original):
        score += 0.28
    if len(normalized) <= 80 and normalized.isupper() and len(normalized) >= 3:
        score += 0.18
    if any(keyword in _normalize_for_match(normalized) for keyword in BOUNDARY_KEYWORDS_RU):
        score += 0.08

    if _looks_like_signature_block(normalized) or _looks_like_requisites_block(normalized):
        score -= 0.35
    if _looks_like_list_item(original):
        score -= 0.30

    toc_score, _ = _toc_line_score(normalized)
    if toc_score >= TOC_SCORE_STRONG:
        score -= 0.40
    elif toc_score >= TOC_SCORE_WEAK:
        score -= 0.14

    return max(0.0, min(score, 0.99))


def _looks_like_unknown_layout(text: str) -> bool:
    """Проверяет, является ли текст шумовым/неизвестным элементом.

    Args:
        text: Текст элемента

    Returns:
        True если текст содержит много необычных символов или слишком мало алфавитных
    """
    normalized = _normalize_text(text)
    if not normalized:
        return True

    weird_ratio = sum(
        1 for ch in normalized if not (ch.isalnum() or ch.isspace() or ch in ".,:;!?()/-№\"'")
    ) / max(len(normalized), 1)
    if weird_ratio >= 0.25:
        return True

    if len(normalized) >= 12:
        alnum = sum(1 for ch in normalized if ch.isalnum())
        if alnum / len(normalized) < 0.35:
            return True

    return False
