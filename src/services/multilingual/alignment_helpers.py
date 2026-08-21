# src/services/multilingual/alignment_helpers.py

"""
Alignment helpers для Layer 4.

Три компонента:

1. cross_language_anchor_key(anchor_uid) - приведение anchor к language-agnostic
   ключу для cross-language matching. Решает проблему что existing
   parse_raw_heading возвращает "appendix-1" для EN и "приложение-1" для RU
   как разные uid.

2. ScopeTracker - state machine для scope tracking по reading order.
   Отслеживает "текущий scope" (empty=основной договор, "appendix::N", ...).
   Используется Layer 4 для scope-aware matching (например, чтобы клауза
   "1.1" в основном договоре не смэтчилась с клаузой "1.1" в Appendix 3).

3. normalize_number_representation - универсальная нормализация числовых
   представлений: "1." -> "1", "1)" -> "1", "1.1." -> "1.1".

Архитектурное решение:
Этот модуль не трогает existing _normalize_appendix_uid в heading_patterns.py.
Existing функция корректно работает для structure pipeline (там RU и EN
appendices - разные SegmentDocument scopes). Наша cross_language_anchor_key -
специфический helper только для Layer 4 alignment.

Примеры:
    parse_raw_heading("APPENDIX No. 1 FORM") -> uid="appendix-1"
    parse_raw_heading("ПРИЛОЖЕНИЕ № 1 ФОРМА") -> uid="приложение-1"

    cross_language_anchor_key("appendix-1") -> ("appendix", "1")
    cross_language_anchor_key("приложение-1") -> ("appendix", "1")
    cross_language_anchor_key("annexe-1") -> ("appendix", "1")  # FR
    cross_language_anchor_key("anhang-1") -> ("appendix", "1")  # DE

    # Оба ключа одинаковы -> Layer 4 сматчит их в ParallelGroup
"""

from __future__ import annotations

import re

from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Cross-language keyword mapping
# ---------------------------------------------------------------------------

# Мапинг language-specific prefix -> canonical category.
# Расширяется добавлением новых языков без изменения кода Layer 4.
# Порядок ключей не важен: matching через set membership.
_APPENDIX_PREFIXES: frozenset[str] = frozenset({
    # English
    "appendix", "annex", "schedule", "exhibit", "attachment",
    # Russian
    "приложение", "прил",
    # French
    "annexe", "appendice",
    # German
    "anhang", "anlage",
    # Turkish
    "ek",
    # Spanish
    "anexo", "apéndice", "apendice",
    # Italian
    "allegato", "appendice",
    # Portuguese
    "anexo", "apêndice", "apendice",
    # Kazakh
    "қосымша",
    # Ukrainian
    "додаток",
    # Belarusian
    "дадатак",
})

_AMENDMENT_PREFIXES: frozenset[str] = frozenset({
    "amendment", "addendum",
    "дополнение", "дополнительное",
    "avenant", "modification",
    "änderung", "nachtrag",
    "değişiklik", "ek anlaşma",
})

# ---------------------------------------------------------------------------
# Regex для нормализации
# ---------------------------------------------------------------------------

# Trailing punctuation в номерах: "1." -> "1", "1)" -> "1", "1;" -> "1"
_TRAILING_PUNCT_RE = re.compile(r"[.,;:)\]]+$")

# Leading punctuation: "(1)" -> "1"
_LEADING_PUNCT_RE = re.compile(r"^[.,;:(\[]+")

# Категории anchor
AnchorCategory = str  # "clause" | "appendix" | "amendment" | "roman" | "letter" | "list_marker" | "unknown"


# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------


def cross_language_anchor_key(anchor_uid: str | None) -> tuple[str, str] | None:
    """
    Привести anchor к language-agnostic ключу для cross-language matching.

    Argument:
        anchor_uid: результат existing parse_raw_heading или extract_appendix_number.
                    Примеры: "1", "1.1", "appendix-1", "приложение-1", "annexe-1"

    Возвращает:
        tuple (category, normalized_number) или None если anchor не парсится.

    Категории:
    - "clause"    - числовой номер клаузы: "1", "1.1", "1.1.1"
    - "appendix"  - номер приложения: "appendix", "annex", "прил", "annexe", etc.
    - "amendment" - номер дополнения: "amendment", "addendum", "дополнение", etc.
    - "roman"     - римская цифра: "I", "II", "IV"
    - "letter"    - буквенный маркер: "a", "b", "с"
    - "list_marker" - list marker "(1)", "(2)"

    Примеры:
    cross_language_anchor_key("1")            -> ("clause", "1")
    cross_language_anchor_key("1.1")          -> ("clause", "1.1")
    cross_language_anchor_key("appendix-1")   -> ("appendix", "1")
    cross_language_anchor_key("приложение-1") -> ("appendix", "1")
    cross_language_anchor_key("annexe-1")     -> ("appendix", "1")
    cross_language_anchor_key("I")            -> ("roman", "i")  # lowercased
    cross_language_anchor_key("a)")           -> ("letter", "a")
    cross_language_anchor_key(None)           -> None
    cross_language_anchor_key("")             -> None

    Для непрофессионального программиста:
    Функция берёт anchor "приложение-1" (русский) и "appendix-1" (английский)
    и превращает оба в один ключ ("appendix", "1"). Так Layer 4 alignment
    может сматчить их как перевод одной и той же вещи.
    """
    if not anchor_uid:
        return None

    normalized = str(anchor_uid).strip()
    if not normalized:
        return None

    # Проверка: содержит ли anchor prefix (appendix-1, приложение-1, ...)?
    if "-" in normalized:
        prefix, _, number = normalized.partition("-")
        prefix_lower = prefix.strip().lower()
        number_normalized = normalize_number_representation(number)

        if not number_normalized:
            return None

        # Проверяем к какой категории relateится prefix
        if prefix_lower in _APPENDIX_PREFIXES:
            return ("appendix", number_normalized)
        if prefix_lower in _AMENDMENT_PREFIXES:
            return ("amendment", number_normalized)

        # Неизвестный prefix - помечаем как unknown но сохраняем номер
        logger.debug(
            "cross_language_anchor_key: unknown prefix",
            prefix=prefix_lower,
            anchor_uid=anchor_uid,
        )
        return ("unknown", number_normalized)

    # Нет prefix - это clause number, roman, letter или list marker
    number_normalized = normalize_number_representation(normalized)

    if not number_normalized:
        return None

    # ВАЖНО: проверку list_marker делаем ПЕРВОЙ, на оригинальном anchor_uid
    # (со скобками). Иначе "(a)" после нормализации станет "a" и попадёт
    # в _is_single_letter → неправильная категория "letter" вместо "list_marker".
    if _is_list_marker(anchor_uid):
        # (1), (2), (a), (b) — list marker
        return ("list_marker", number_normalized)

    # Определяем категорию по формату нормализованного номера
    if _is_roman_numeral(number_normalized):
        return ("roman", number_normalized.lower())

    if _is_single_letter(number_normalized):
        return ("letter", number_normalized.lower())

    # Иначе - клауза (числовой номер типа "1", "1.1", "1.1.1")
    return ("clause", number_normalized)


def normalize_number_representation(raw: str) -> str:
    """
    Универсальная нормализация числового представления anchor.

    Удаляет trailing и leading пунктуацию, нормализует пробелы.

    Примеры:
    "1."      -> "1"
    "1)"      -> "1"
    "1.1"     -> "1.1"
    "1.1."    -> "1.1"
    "(1)"     -> "1"
    " 1 "     -> "1"
    "1. 1"    -> "1.1"     (внутренние пробелы схлопываются, но кроме перед .)
    ""        -> ""

    Note: внутренние пробелы в номерах вроде "1. 1. 2" (OCR artifacts)
    обрабатываются через existing normalize_spaces из heading_patterns.py.
    """
    if not raw:
        return ""

    text = str(raw).strip()
    if not text:
        return ""

    # Убираем leading и trailing пунктуацию
    text = _LEADING_PUNCT_RE.sub("", text)
    text = _TRAILING_PUNCT_RE.sub("", text)

    # Схлопываем пробелы внутри числового формата: "1. 1" -> "1.1"
    # Используем existing функцию для консистентности
    try:
        from services.structure.heading_patterns import normalize_spaces
        text = normalize_spaces(text)
    except Exception:
        # Fallback без существующей функции
        text = re.sub(r"\s+", "", text)

    return text.strip()


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def _is_roman_numeral(text: str) -> bool:
    """
    True если text это римская цифра (I, II, III, IV, V, VI, ..., MCMLXXXIV).

    Использует простой regex - не идеальная валидация всех римских цифр,
    но покрывает 99% реальных случаев в юридических документах.
    """
    if not text:
        return False
    # Roman numerals: I, V, X, L, C, D, M
    return bool(re.fullmatch(r"[IVXLCDMivxlcdm]+", text))


def _is_single_letter(text: str) -> bool:
    """
    True если text это одна буква (a, b, c, а, б, в).
    """
    if not text or len(text) != 1:
        return False
    return text.isalpha()


def _is_list_marker(anchor_uid: str) -> bool:
    """
    True если оригинальный anchor выглядит как list marker: "(1)", "(a)".

    Проверяем оригинал (до нормализации), потому что normalize_number_representation
    удаляет скобки.
    """
    if not anchor_uid:
        return False
    return anchor_uid.startswith("(") and ")" in anchor_uid


# ---------------------------------------------------------------------------
# ScopeTracker: state machine для scope tracking
# ---------------------------------------------------------------------------


class ScopeTracker:
    """
    State machine для отслеживания scope по reading order.

    Использование Layer 4:
        tracker = ScopeTracker()
        for segment in segments_in_reading_order:
            scope = tracker.update(segment)
            # scope: "" (основной договор) | "appendix::1" | "amendment::2"

    Правила переходов:
    1. Начальный scope = "" (основной договор)
    2. Встреча appendix header (anchor="appendix-N") -> scope = "appendix::N"
    3. Встреча amendment header -> scope = "amendment::N"
    4. Возврат к основному тексту (следующий segment с anchor="1.1" типа clause
       после appendix) - НЕ переключает scope назад автоматически. Scope
       остаётся до следующего явного header'а.

    Это упрощённая модель. Реальная document structure может быть сложнее
    (nested appendices, amendments внутри appendices), но для типичных
    юридических документов работает надёжно.

    Для непрофессионального программиста:
    Класс запоминает "где мы сейчас читаем" в документе:
    - Обычный договор
    - Внутри Приложения 1
    - Внутри Приложения 2
    - Внутри Дополнения 1
    Layer 4 использует scope чтобы не смэтчить клаузу "1.1" из основного
    договора с клаузой "1.1" из Приложения 3 (они разные вещи).
    """

    def __init__(self) -> None:
        self._current_scope: str = ""
        self._scope_history: list[str] = []
        # История scope changes для audit

    @property
    def current_scope(self) -> str:
        """Текущий scope: "" или "appendix::N" или "amendment::N"."""
        return self._current_scope

    def update(self, anchor_uid: str | None) -> str:
        """
        Обновить scope на основе anchor текущего сегмента.

        Возвращает current_scope ПОСЛЕ update.

        Argument:
            anchor_uid: anchor_uid из LanguageSegment.anchor_uid.
                        Может быть None (сегмент без anchor).

        Правила:
        - Если anchor это appendix (например, "appendix-1", "приложение-1") ->
          scope = "appendix::<номер>"
        - Если anchor это amendment -> scope = "amendment::<номер>"
        - Если anchor это clause, roman, letter, list_marker -> scope не меняется
          (мы всё ещё в том же логическом разделе документа)
        - Если anchor is None -> scope не меняется
        """
        if not anchor_uid:
            return self._current_scope

        key = cross_language_anchor_key(anchor_uid)
        if not key:
            return self._current_scope

        category, number = key

        if category == "appendix":
            new_scope = f"appendix::{number}"
            if new_scope != self._current_scope:
                self._scope_history.append(new_scope)
                self._current_scope = new_scope
        elif category == "amendment":
            new_scope = f"amendment::{number}"
            if new_scope != self._current_scope:
                self._scope_history.append(new_scope)
                self._current_scope = new_scope
        # Для clause, roman, letter, list_marker - scope не меняется

        return self._current_scope

    def reset(self) -> None:
        """Сбросить scope к начальному (для тестов или reuse)."""
        self._current_scope = ""
        self._scope_history = []

    def history(self) -> list[str]:
        """Вернуть историю scope changes для audit."""
        return list(self._scope_history)



