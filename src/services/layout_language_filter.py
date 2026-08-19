# src/services/layout_language_filter.py

"""
Layout language filter.

Отвечает за приведение text_layout_raw к одноязычному layout_primary для
целевого языка (любой ISO 639-1 код), чтобы downstream‑стадии работали только
с одной языковой версией документа.

Два режима работы:
- Простой (монолингвальный или короткий документ): language detection через
  LanguageDetector, оставляются элементы целевого языка + короткие нейтральные
  блоки (цифры, подписи, номера пунктов) + структурированные данные (реквизиты).
- Структурный (multilingual, >= 10 элементов): _StructuralAnalyzer группирует
  параллельные блоки по странице и вертикальной позиции, выравнивает их по
  номерам пунктов и из каждой пары/группы выбирает представление на нужном
  языке, при этом может дополнительно проставить clause_uid/parent_clause_uid.

Контракты:
- Вход: text_layout_raw (document_id, document_version_id, elements, tables, metadata),
  где elements — плоский список блоков с element_id, text, type, page, bbox и
  опциональными clause_uid/parent_clause_uid.
- Выход: layout_primary с теми же elements/tables, но отфильтрованными по языку
  и дополненным блоком metadata.language_filter.
  Дополнительно: excluded_element_ids (список удалённых) и filter_decisions (audit trail).

LOSSLESS ИНВАРИАНТ:
- retained_element["text"] == raw_element["text"] БЕЗ ИСКЛЮЧЕНИЙ.
- _sanitize_text_to_script НЕ вызывается в canonical filter path.
- Mixed/unknown элементы — retained + flagged, текст не тронут.

MULTILINGUAL ПОДДЕРЖКА (Фаза 2A):
- Поддерживает любой язык через lingua-language-detector (75+ языков).
- target_language принимает любой ISO 639-1 код: "ru", "en", "ar", "fr", "kk"...
- filter_layout_to_language не ограничен списком поддерживаемых языков.
- detect_languages_in_layout возвращает реальные ISO коды всех найденных языков.
"""

from __future__ import annotations

import re
import traceback
from dataclasses import dataclass, field
from typing import Any

from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

# Нейтральный блок (цифры, пунктуация) включается только если короткий
_NEUTRAL_MAX_CHARS = 40

# Минимальная длина текста для структурного анализа
_STRUCT_MIN_TEXT_LEN = 5

# Y-допуск при группировке параллельных блоков (пиксели/pt PDF)
_Y_TOLERANCE = 20.0

# Минимальный размер документа для включения структурного анализа
_STRUCTURAL_MIN_ELEMENTS = 10

# Пороги degraded-оценки качества фильтрации
_MIN_ELEMENT_RETENTION_RATIO = 0.40
_MIN_CHAR_RETENTION_RATIO = 0.50

# Дополнительные эвристики очистки PDF артефактов
_MAX_REPEATED_SYMBOL_RUN = 6

# Максимальная доля букв естественного языка для признания элемента
# "pure structured data". Если буквы < 30% — элемент целиком из кодов/цифр.
_STRUCTURED_DATA_MAX_NATURAL_RATIO = 0.30

# Минимальная доля элементов одного языка для признания документа multilingual.
# Если второй язык занимает >= этой доли — документ считается multilingual.
_MULTILINGUAL_MIN_RATIO = 0.15

# ---------------------------------------------------------------------------
# Регулярное выражение для структурированных данных (реквизиты, коды, контакты)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Регулярные выражения для структурированных данных (реквизиты, коды, контакты)
#
# ВАЖНО: Разделены на case-sensitive и case-insensitive паттерны.
#
# Case-sensitive (без IGNORECASE):
# - SWIFT/BIC: строго заглавные буквы и цифры (SABRRUMM, DEUTDEDB001)
# - IBAN: страновой код заглавными + цифры (DE89370400440532013000)
#
# Case-insensitive (с IGNORECASE):
# - email, URL, телефоны, длинные числовые коды — регистр не важен
#
# Разделение необходимо потому что:
# - SWIFT паттерн [A-Z]{4}[A-Z]{2}[A-Z0-9]{2} с IGNORECASE матчит
#   любое слово из 8+ букв: "Agreement", "Покупатель" и т.д.
# - SWIFT реально никогда не содержит строчных букв — это стандарт ISO 9362
# ---------------------------------------------------------------------------

# Паттерны для fullmatch (весь элемент = один структурированный токен)
# Case-sensitive: регистр имеет значение

_SWIFT_BIC_FULLMATCH_RE = re.compile(
    r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?$"
    # SWIFT/BIC: 4 буквы банка + 2 буквы страны + 2 символа города + опц. 3 символа филиала
    # Примеры: SABRRUMM, CITIUSXX, DEUTDEDB001
    # Строго заглавные — это стандарт ISO 9362
)

_IBAN_FULLMATCH_RE = re.compile(
    r"^[A-Z]{2}\d{2}[A-Z0-9]{4,}\d{7,}$"
    # IBAN: 2 буквы страны (заглавные) + 2 контрольных цифры + BBAN
    # Примеры: DE89370400440532013000, GB29NWBK60161331926819
)

# Case-insensitive: регистр не важен для этих форматов

_EMAIL_FULLMATCH_RE = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$",
    re.IGNORECASE,
)

_URL_FULLMATCH_RE = re.compile(
    r"^https?://\S+$",
    re.IGNORECASE,
)

_PHONE_FULLMATCH_RE = re.compile(
    r"^\+?[\d][\d\s\-\(\)]{6,}$"
    # Телефон: начинается с цифры (или +цифра), содержит минимум 7 символов
    # Примеры: +7 495 123-45-67, 8 800 200-06-00
)

_LONG_CODE_FULLMATCH_RE = re.compile(
    r"^\d{6,}$"
    # Длинный числовой код: ИНН (10/12 цифр), ОГРН (13 цифр), БИК (9 цифр)
    # Примеры: 7707083893, 1027700132195
)

# Паттерны для search (структурированный токен внутри текста)
# Используются для определения "contains" — реквизит внутри естественного текста

_STRUCTURED_SEARCH_RE = re.compile(
    r"(?:"
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"   # email
    r"|https?://\S+"                                          # URL
    r"|\+?[\d][\d\s\-\(\)]{6,}"                              # телефон (начинается с цифры)
    r"|\d{6,}"                                                # длинный числовой код
    r"|[A-Z]{2}\d{2}[A-Z0-9]{4,}\d{7,}"                     # IBAN (case-sensitive через контекст)
    r"|[A-Z]{2,6}[\s\-]?\d{3,}"                              # BIC/KPP/прочие коды с цифрами
    r")",
    re.IGNORECASE,
)

# SWIFT search — отдельно, без IGNORECASE
_SWIFT_SEARCH_RE = re.compile(
    r"\b[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b"
    # SWIFT/BIC внутри текста — строго заглавные
)


def _classify_structured_data(text: str) -> str:
    """
    Классифицировать элемент по наличию структурированных данных.

    Структурированные данные — это технические коды и реквизиты:
    SWIFT/BIC, IBAN, email, URL, телефоны, длинные числовые коды (ИНН, ОГРН).

    Возвращает одну из трёх строк:

    "pure"
        Элемент целиком является структурированным токеном.
        Примеры: "SABRRUMM", "DE89370400440532013000",
                 "+7 495 123-45-67", "legal@company.ru"
        Такие элементы не являются "языком" — их всегда сохраняем,
        они не влияют на языковой баланс документа.

    "contains"
        Структурированный токен присутствует внутри естественного текста.
        Примеры: "Контакт: legal@company.ru",
                 "Перевод на счёт IBAN: DE89370400440532013000"
        Такие элементы классифицируются по языку текста, но всегда сохраняются.

    "none"
        Обычный текст без структурированных данных.
        Примеры: "Договор купли-продажи", "Agreement", "Покупатель обязуется"
        Классифицируется по языку и фильтруется по нему.

    Алгоритм (трёхуровневый):
    1. Fullmatch case-sensitive (SWIFT, IBAN) → "pure" мгновенно
    2. Fullmatch case-insensitive (email, URL, телефон, длинный код) → "pure" мгновенно
    3. Search токенов в тексте:
       - нет ни одного токена → "none"
       - есть токены → считаем долю оставшегося естественного текста
         после удаления всех найденных токенов:
         * мало естественного текста (< 30%) → "pure"
         * много естественного текста (>= 30%) → "contains"
    """
    stripped = (text or "").strip()
    if not stripped:
        return "none"

    # ── Уровень 1: Fullmatch case-sensitive ──────────────────────────────────
    # SWIFT/BIC и IBAN матчатся только если ВЕСЬ элемент = токен
    # и только в заглавном регистре (стандарт ISO)

    if _SWIFT_BIC_FULLMATCH_RE.match(stripped):
        return "pure"

    if _IBAN_FULLMATCH_RE.match(stripped):
        return "pure"

    # ── Уровень 2: Fullmatch case-insensitive ─────────────────────────────────
    # Форматы где регистр не важен: email, URL, телефон, длинный код

    if _EMAIL_FULLMATCH_RE.match(stripped):
        return "pure"

    if _URL_FULLMATCH_RE.match(stripped):
        return "pure"

    if _PHONE_FULLMATCH_RE.match(stripped):
        return "pure"

    if _LONG_CODE_FULLMATCH_RE.match(stripped):
        return "pure"

    # ── Уровень 3: Search токенов внутри текста ───────────────────────────────
    # Проверяем есть ли хотя бы один структурированный токен в тексте

    has_search_match = bool(
        _STRUCTURED_SEARCH_RE.search(stripped)
        or _SWIFT_SEARCH_RE.search(stripped)
    )

    if not has_search_match:
        return "none"

    # Есть токены внутри текста.
    # Считаем долю естественного языка ПОСЛЕ удаления всех токенов.
    # Если после удаления токенов почти ничего не осталось → "pure".
    # Если осталось много букв → "contains".

    # Удаляем все найденные структурированные токены из текста
    text_without_tokens = _STRUCTURED_SEARCH_RE.sub(" ", stripped)
    text_without_tokens = _SWIFT_SEARCH_RE.sub(" ", text_without_tokens)
    text_without_tokens = re.sub(r"\s+", " ", text_without_tokens).strip()

    # Считаем буквы естественного языка в остатке
    natural_chars_remaining = sum(
        1 for c in text_without_tokens
        if (0x0400 <= ord(c) <= 0x04FF)     # кириллица
        or (0x0041 <= ord(c) <= 0x005A)     # A-Z
        or (0x0061 <= ord(c) <= 0x007A)     # a-z
    )

    # Считаем буквы в оригинальном тексте для нормировки
    natural_chars_total = sum(
        1 for c in stripped
        if (0x0400 <= ord(c) <= 0x04FF)
        or (0x0041 <= ord(c) <= 0x005A)
        or (0x0061 <= ord(c) <= 0x007A)
    )

    if natural_chars_total == 0:
        # Весь текст — цифры и спецсимволы без букв → pure
        return "pure"

    # Доля букв, оставшихся ПОСЛЕ удаления токенов, от всех букв в оригинале
    remaining_ratio = natural_chars_remaining / natural_chars_total

    if remaining_ratio < _STRUCTURED_DATA_MAX_NATURAL_RATIO:
        # После удаления токенов букв почти не осталось → элемент = pure structured data
        return "pure"

    # Осталось много букв → реквизит внутри естественного текста
    return "contains"


# ---------------------------------------------------------------------------
# MULTILINGUAL: Language detection через LanguageDetector
# ---------------------------------------------------------------------------


def _get_element_language(text: str) -> tuple[str, str, float]:
    """
    Определить язык и скрипт текстового элемента.

    Возвращает кортеж (language_code, script_code, confidence):
    - language_code: ISO 639-1 код ("ru", "en", "ar", "fr", "kk", "unknown")
    - script_code:   письменность ("cyrillic", "latin", "arabic", "hebrew", "cjk", "other")
    - confidence:    уверенность 0.0 — 1.0

    Использует LanguageDetector из language_detector.py.
    """
    from services.language_detector import get_language_detector
    detector = get_language_detector()
    result = detector.detect_language(text)
    return result.language_code, result.script_code, result.confidence


def _get_script_for_element(text: str) -> str:
    """
    Быстро определить письменность текста (без полного language detection).
    Используется для структурного анализатора.
    """
    from services.language_detector import get_language_detector
    detector = get_language_detector()
    return detector.detect_script(text)


def classify_element_language(
    text: str,
    target_lang: str,
    structured_kind: str,
) -> str:
    """
    Определить доменный language label для элемента layout.

    MULTILINGUAL версия (Фаза 2A):
    - работает с любым ISO 639-1 target_lang, не только "ru"/"en"
    - использует LanguageDetector для точного определения языка
    - для смешанных элементов (два языка в одном тексте) возвращает "mixed"

    Параметры:
    - text:           текст элемента
    - target_lang:    целевой язык документа (ISO 639-1: "ru", "en", "ar", "fr"...)
    - structured_kind: результат _classify_structured_data() для этого текста

    Возвращает одну из пяти строк:
    - "target"  — элемент на целевом языке → retained
    - "foreign" — элемент явно на другом языке → excluded
    - "neutral" — нейтральный контент или pure structured data → retained
    - "mixed"   — два языка в одном элементе → flagged (retained с пометкой)
    - "unknown" — не удалось определить язык → flagged (retained с пометкой)
    """
    # Pure structured data (SWIFT, IBAN, телефон) → всегда neutral
    # Это технические коды, не языковой контент
    if structured_kind == "pure":
        return "neutral"

    if not text or not text.strip():
        return "neutral"

    # Используем LanguageDetector для определения языка
    language_code, script_code, confidence = _get_element_language(text)

    # Нейтральный контент: нет букв, только цифры/пунктуация
    if script_code == "other" or language_code == "unknown":
        char_count = _count_chars(text)
        if char_count <= _NEUTRAL_MAX_CHARS:
            return "neutral"
        # Длинный нейтральный/неизвестный → unknown (retain с флагом)
        return "unknown"

    # Низкая уверенность детектора → unknown (retain с флагом)
    if not _is_detection_reliable(language_code, confidence):
        char_count = _count_chars(text)
        if char_count <= _NEUTRAL_MAX_CHARS:
            return "neutral"
        return "unknown"

    # Определённый язык совпадает с целевым → target
    if language_code == target_lang:
        return "target"

    # Проверяем смешанный контент:
    # Если в тексте значимо присутствуют символы целевого языка
    # (например, "Buyer (Покупатель) обязуется") → mixed
    if _has_significant_target_script(text, target_lang):
        return "mixed"

    # Определённо другой язык → foreign
    return "foreign"


def _is_detection_reliable(language_code: str, confidence: float) -> bool:
    """
    Проверить, можно ли доверять результату language detection.

    Для непрофессионального программиста:
    - если lingua говорит "это арабский" с уверенностью 0.9 → доверяем
    - если lingua говорит "это французский" с уверенностью 0.2 → не доверяем,
      лучше пометим как unknown и не будем удалять этот элемент
    """
    if language_code == "unknown":
        return False
    try:
        from core.config import settings
        threshold = getattr(settings, "LANGUAGE_DETECTOR_CONFIDENCE_THRESHOLD", 0.50)
    except Exception:
        threshold = 0.50
    return confidence >= threshold


def _has_significant_target_script(text: str, target_lang: str) -> bool:
    """
    Проверить, есть ли в тексте значимое присутствие символов целевого языка.

    Используется для определения mixed-content элементов.
    Например: "Buyer (Покупатель) обязуется" — содержит и латиницу, и кириллицу.

    Логика:
    - Определяем script целевого языка по его ISO коду
    - Считаем долю символов этого script в тексте
    - Если доля >= 15% → значимое присутствие → mixed
    """
    from services.language_detector import get_language_detector
    detector = get_language_detector()

    # Определяем script целевого языка
    # Для этого создаём "пробный" текст на целевом языке и смотрим его script
    # Но проще — используем заранее известный маппинг
    target_script = _lang_to_expected_script(target_lang)
    if not target_script:
        return False

    # Считаем символы целевого script в тексте
    target_count = 0
    total_letter_count = 0

    from services.language_detector import _SCRIPT_RANGES
    target_ranges = next(
        (ranges for script, ranges in _SCRIPT_RANGES if script == target_script),
        None,
    )
    if not target_ranges:
        return False

    # Считаем все буквы и буквы целевого script
    for ch in text:
        code = ord(ch)
        is_any_letter = any(
            any(s <= code <= e for s, e in ranges)
            for _, ranges in _SCRIPT_RANGES
        )
        if is_any_letter:
            total_letter_count += 1
            if any(s <= code <= e for s, e in target_ranges):
                target_count += 1

    if total_letter_count == 0:
        return False

    target_ratio = target_count / total_letter_count
    return target_ratio >= _MULTILINGUAL_MIN_RATIO


def _lang_to_expected_script(lang_code: str) -> str | None:
    """
    Маппинг ISO language code → ожидаемый script code.

    Для наиболее распространённых языков в нашем контексте.
    Используется для определения mixed-content.
    """
    _LANG_SCRIPT_MAP: dict[str, str] = {
        # Кириллица
        "ru": "cyrillic", "uk": "cyrillic", "be": "cyrillic",
        "bg": "cyrillic", "sr": "cyrillic", "mk": "cyrillic",
        "kk": "cyrillic", "ky": "cyrillic", "tg": "cyrillic",
        "mn": "cyrillic",
        # Латиница
        "en": "latin", "fr": "latin", "de": "latin", "es": "latin",
        "it": "latin", "pt": "latin", "nl": "latin", "pl": "latin",
        "cs": "latin", "sk": "latin", "sl": "latin", "hr": "latin",
        "ro": "latin", "hu": "latin", "sv": "latin", "da": "latin",
        "nb": "latin", "fi": "latin", "et": "latin", "lv": "latin",
        "lt": "latin", "tr": "latin", "uz": "latin", "az": "latin",
        "id": "latin", "ms": "latin",
        # Арабица
        "ar": "arabic", "fa": "arabic", "ur": "arabic",
        # Иврит
        "he": "hebrew",
        # CJK
        "zh": "cjk", "ja": "cjk", "ko": "cjk",
        # Деванагари
        "hi": "devanagari", "mr": "devanagari",
    }
    return _LANG_SCRIPT_MAP.get(lang_code)


# ---------------------------------------------------------------------------
# Таблица решений для фильтрации по language label
# ---------------------------------------------------------------------------

_RETENTION_POLICY: dict[str, tuple[str, str]] = {
    "target":  ("retained", "target_language_match"),
    "neutral": ("retained", "neutral_block_preserved"),
    "mixed":   ("flagged",  "mixed_content_retained_with_flag"),
    "unknown": ("flagged",  "unknown_language_retained_with_flag"),
    "foreign": ("excluded", "foreign_language_excluded"),
}


# ---------------------------------------------------------------------------
# Вспомогательные функции очистки текста
# ---------------------------------------------------------------------------


def _clean_artifacts(text: str) -> str:
    """
    Очистка типичных PDF/OCR/layout-артефактов перед анализом.

    ВАЖНО: только для детекции языка и оценки качества.
    Оригинальный текст элемента НЕ переписываем — lossless инвариант.
    """
    if not text:
        return ""

    cleaned = text

    # Zero-width / soft noise
    cleaned = (
        cleaned.replace("\u200b", "")
        .replace("\u200c", "")
        .replace("\u200d", "")
        .replace("\ufeff", "")
    )

    # Частые символы деградации
    cleaned = cleaned.replace("�", " ")
    cleaned = cleaned.replace("■", " ")
    cleaned = cleaned.replace("□", " ")
    cleaned = cleaned.replace("▪", " ")
    cleaned = cleaned.replace("▫", " ")

    # Схлопываем длинные серии шумовых символов
    cleaned = re.sub(rf"([_\-–—.=~*•·])\1{{{_MAX_REPEATED_SYMBOL_RUN - 1},}}", r"\1", cleaned)

    # Нормализуем пробелы
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _count_chars(text: str) -> int:
    """Число символов без пробелов и переносов, после мягкой очистки."""
    prepared = _clean_artifacts(text)
    return len(prepared.replace(" ", "").replace("\n", "")) if prepared else 0


def _should_keep_neutral(text: str) -> bool:
    """
    Нейтральный блок включаем только если он короткий.
    Длинный нейтральный текст — ошибка детекции или мусор.
    """
    return _count_chars(text) <= _NEUTRAL_MAX_CHARS


def _sanitize_text_to_script(text: str, target_lang: str) -> str:
    """
    УСТАРЕВШАЯ функция. НЕ вызывается в canonical filter path.

    Оставлена для совместимости. Нарушает lossless инвариант.
    В фильтрах (_simple_filter, _structural_filter) не используется.
    """
    if not text:
        return ""

    target = (target_lang or "").lower()

    allowed_ranges: dict[str, list[tuple[int, int]]] = {
        "ru": [(0x0400, 0x04FF), (0x0500, 0x052F)],
        "en": [(0x0041, 0x005A), (0x0061, 0x007A), (0x00C0, 0x00FF)],
    }

    allowed = allowed_ranges.get(target)
    if not allowed:
        return text

    cleaned_chars: list[str] = []
    for ch in text:
        code = ord(ch)
        is_target_letter = any(start <= code <= end for start, end in allowed)
        is_digit = ch.isdigit()
        is_space = ch.isspace()
        is_punct = ch in ".,;:!?()[]{}-–—/\\"

        if is_target_letter or is_digit or is_space or is_punct:
            cleaned_chars.append(ch)

    return "".join(cleaned_chars).strip()


def _safe_int_page(value: Any, default: int = 1) -> int:
    try:
        page = int(float(str(value).strip()))
        return page if page > 0 else default
    except (ValueError, TypeError, AttributeError):
        return default


def _safe_bbox(raw_bbox: Any) -> list[float]:
    """Нормализовать bbox к [x0, top, x1, bottom] из float."""
    if not isinstance(raw_bbox, list | tuple) or len(raw_bbox) < 4:
        return [0.0, 0.0, 0.0, 0.0]

    result: list[float] = []
    for value in raw_bbox[:4]:
        try:
            result.append(float(str(value).strip()))
        except (ValueError, TypeError, AttributeError):
            result.append(0.0)

    x0, top, x1, bottom = result
    if x1 < x0:
        x0, x1 = x1, x0
    if bottom < top:
        top, bottom = bottom, top

    return [x0, top, x1, bottom]


def _is_zero_bbox(bbox: list[float]) -> bool:
    return len(bbox) >= 4 and all(abs(v) < 1e-9 for v in bbox[:4])


def _bbox_sort_key(element: dict[str, Any]) -> tuple[int, float, float]:
    bbox = _safe_bbox(element.get("bbox"))
    return (
        _safe_int_page(element.get("page", 1)),
        bbox[1],
        bbox[0],
    )


def _reading_order_sort_key(el: dict[str, Any]) -> tuple:
    """
    Ключ сортировки с приоритетом исходного reading_order.
    Если reading_order задан — используем его.
    Иначе — bbox-based сортировка.
    """
    raw_order = el.get("reading_order")
    if isinstance(raw_order, int):
        return (0, raw_order)
    bbox = _safe_bbox(el.get("bbox"))
    page = _safe_int_page(el.get("page", 1))
    return (1, page, bbox[1], bbox[0])


# ---------------------------------------------------------------------------
# MULTILINGUAL: Публичные функции обнаружения языков
# ---------------------------------------------------------------------------


def detect_languages_in_layout(layout: dict[str, Any]) -> list[str]:
    """
    Определить, какие языки реально присутствуют в layout.

    MULTILINGUAL версия (Фаза 2A):
    - использует LanguageDetector для определения реального языка каждого элемента
    - возвращает ISO 639-1 коды ВСЕХ найденных языков: ["en", "ar"], ["ru", "kk"], ...
    - pure structured data (IBAN, SWIFT, email) игнорируется при подсчёте языков
    - элементы с низкой уверенностью детектора игнорируются

    Возвращает отсортированный список кодов языков.
    Если ни одного языка не обнаружено — возвращает пустой список
    (вызывающий код сам решает что делать с пустым списком).

    Для непрофессионального программиста:
    - раньше эта функция умела находить только "ru" и "en"
    - теперь она находит любой из 75+ языков которые умеет lingua
    - результат используется для показа пользователю списка языков документа
    """
    elements: list[dict[str, Any]] = layout.get("elements") or []
    if not elements:
        return []

    # Собираем языки с количеством символов для каждого
    # Это позволяет отфильтровать языки с ничтожным присутствием
    lang_char_counts: dict[str, int] = {}
    total_natural_chars = 0

    from services.language_detector import get_language_detector
    detector = get_language_detector()

    for el in elements:
        text = (el.get("text") or "").strip()
        if not text:
            continue

        # Pure structured data не влияет на языковой состав документа
        if _classify_structured_data(text) == "pure":
            continue

        char_count = _count_chars(text)
        if char_count == 0:
            continue

        result = detector.detect_language(text)

        # Пропускаем неопределённые языки и нейтральный контент
        if result.language_code in ("unknown",):
            continue
        if result.script_code == "other":
            continue

        # Пропускаем ненадёжные результаты
        if not _is_detection_reliable(result.language_code, result.confidence):
            continue

        lang_char_counts[result.language_code] = (
            lang_char_counts.get(result.language_code, 0) + char_count
        )
        total_natural_chars += char_count

    if not lang_char_counts or total_natural_chars == 0:
        return []

    # Фильтруем языки которые занимают слишком малую долю
    # (менее 5% от всего текста) — это вероятно шум или единичные слова
    significant_langs = [
        lang for lang, count in lang_char_counts.items()
        if count / total_natural_chars >= 0.05
    ]

    return sorted(significant_langs)


# ---------------------------------------------------------------------------
# MULTILINGUAL: Структурный анализатор
#
# Обновлён для работы с любыми языками, не только ru/en.
# Ключевое изменение: _StructElement.detected_lang теперь хранит ISO код
# языка, а _StructBlock работает с generic language_elements dict.
# ---------------------------------------------------------------------------


@dataclass
class _StructElement:
    """Внутреннее представление одного элемента layout."""

    original: dict[str, Any]
    element_id: str
    text: str
    page: int
    bbox: list[float]
    element_type: str
    detected_lang: str   # ISO 639-1 код: "ru", "en", "ar", "fr"... или "unknown"
    detected_script: str # "cyrillic", "latin", "arabic", "hebrew", "cjk", "other"
    clause_number: str | None = None
    y_center: float = 0.0
    x_center: float = 0.0

    def __post_init__(self) -> None:
        if self.bbox and len(self.bbox) >= 4:
            try:
                floats = [float(v) for v in self.bbox[:4]]
                self.y_center = (floats[1] + floats[3]) / 2.0
                self.x_center = (floats[0] + floats[2]) / 2.0
            except (ValueError, TypeError):
                self.y_center = 0.0
                self.x_center = 0.0
        else:
            self.y_center = float("inf")
            self.x_center = 0.0


@dataclass
class _StructBlock:
    """
    Группа параллельных элементов на одной вертикальной позиции.

    MULTILINGUAL версия: поддерживает любые языки.
    Вместо жёстких ru_element/en_element — универсальный словарь
    language_elements: {lang_code → best_element}.
    """

    block_id: str | None
    y_position: float
    page: int
    elements: list[_StructElement] = field(default_factory=list)
    # Универсальный маппинг: ISO lang code → лучший элемент для этого языка
    language_elements: dict[str, _StructElement] = field(default_factory=dict)
    is_heading: bool = False

    def resolve_languages(self) -> None:
        """
        Выбрать по одному лучшему представителю для каждого найденного языка.

        Лучший элемент для языка = тот с наибольшим числом символов
        (из heading-элементов если есть heading, иначе из всех).
        """
        # Группируем элементы по языку
        lang_candidates: dict[str, list[_StructElement]] = {}

        for el in self.elements:
            lang = el.detected_lang
            if lang not in lang_candidates:
                lang_candidates[lang] = []
            lang_candidates[lang].append(el)

        # Для каждого языка выбираем лучший элемент
        self.language_elements = {}
        for lang, candidates in lang_candidates.items():
            if lang in ("unknown",):
                # Для нейтрального/unknown — оставляем в нейтральный слот
                continue
            headings = [e for e in candidates if e.element_type == "heading"]
            pool = headings if headings else candidates
            best = max(pool, key=lambda e: (_count_chars(e.text), len(e.text)))
            self.language_elements[lang] = best

        # Нейтральные элементы: добавляем в специальный слот "neutral"
        # если нет ни одного языкового элемента
        if not self.language_elements:
            all_neutral = [e for e in self.elements if e.detected_lang == "unknown"]
            if all_neutral:
                best_neutral = max(
                    all_neutral,
                    key=lambda e: (_count_chars(e.text), len(e.text)),
                )
                self.language_elements["unknown"] = best_neutral

    def get_for_language(self, target_lang: str) -> _StructElement | None:
        """
        Вернуть лучший элемент для целевого языка.

        Логика:
        1. Если в блоке есть элемент на целевом языке → возвращаем его.
        2. Если нет — возвращаем None (блок будет пропущен для этого языка).

        Fallback на нейтральный/unknown элемент не делаем,
        потому что такой элемент может принадлежать другому языку.
        """
        return self.language_elements.get(target_lang)

    @property
    def has_multiple_languages(self) -> bool:
        """True если блок содержит элементы на двух и более языках."""
        real_langs = {
            lang for lang in self.language_elements
            if lang != "unknown"
        }
        return len(real_langs) >= 2


_CLAUSE_PATTERNS = [
    re.compile(r"^(\d+(?:\.\d+)*)\s*[.)]\s*(.+)?$"),
    re.compile(r"^(\d+)\s*[.)]\s*(.+)?$"),
    re.compile(r"^(I{1,3}|IV|V?I{0,3})[.)]\s*(.+)?$", re.IGNORECASE),
    re.compile(r"^([A-Fa-f])[.)]\s*(.+)?$"),
]


class _StructuralAnalyzer:
    """
    Multilingual структурный анализатор.

    Группирует элементы layout по вертикальной позиции (page, y_center),
    выравнивает параллельные блоки по номерам пунктов,
    и для каждого блока предоставляет выбор нужного языка.
    """

    def __init__(self, y_tolerance: float = _Y_TOLERANCE):
        self.y_tolerance = y_tolerance

    def analyze(self, elements: list[dict[str, Any]]) -> list[_StructBlock]:
        """Основная точка входа."""
        if not elements:
            return []

        struct_els = self._convert_elements(elements)
        if not struct_els:
            return []

        y_groups = self._group_by_y(struct_els)
        sorted_keys = sorted(y_groups.keys())

        blocks: list[_StructBlock] = []
        for key in sorted_keys:
            block = self._create_block(
                y_center=key[1],
                page=key[0],
                elements=y_groups[key],
            )
            if block:
                blocks.append(block)

        blocks = self._align_by_clause_numbers(blocks)
        return self._finalize_blocks(blocks)

    def _convert_elements(self, elements: list[dict[str, Any]]) -> list[_StructElement]:
        result: list[_StructElement] = []

        from services.language_detector import get_language_detector
        detector = get_language_detector()

        for el in elements:
            raw_text = el.get("text", "")
            text = raw_text.strip()
            if len(_clean_artifacts(text)) < _STRUCT_MIN_TEXT_LEN:
                continue

            page_val = _safe_int_page(el.get("page", 1), default=1)
            safe_bbox = _safe_bbox(el.get("bbox", [0, 0, 0, 0]))

            if _is_zero_bbox(safe_bbox):
                continue

            el_type = str(el.get("type", "text") or "text").lower()

            # Pure structured data → unknown lang, не влияет на language grouping
            if _classify_structured_data(text) == "pure":
                detected_lang = "unknown"
                detected_script = detector.detect_script(text)
            else:
                lang_result = detector.detect_language(text)
                detected_lang = lang_result.language_code
                detected_script = lang_result.script_code
                # Низкая уверенность → unknown
                if not _is_detection_reliable(detected_lang, lang_result.confidence):
                    detected_lang = "unknown"

            clause_num = self._extract_clause_number(text, el_type)

            result.append(
                _StructElement(
                    original=el,
                    element_id=str(el.get("element_id", "")),
                    text=text,
                    page=page_val,
                    bbox=safe_bbox,
                    element_type=el_type,
                    detected_lang=detected_lang,
                    detected_script=detected_script,
                    clause_number=clause_num,
                )
            )

        return result

    @staticmethod
    def _extract_clause_number(text: str, el_type: str) -> str | None:
        is_heading = el_type == "heading" or text.strip().isupper()
        stripped = text.strip()

        if not is_heading:
            if not any(p.match(stripped) for p in _CLAUSE_PATTERNS):
                return None

        for pattern in _CLAUSE_PATTERNS:
            match = pattern.match(stripped)
            if match:
                return match.group(1)
        return None

    def _group_by_y(
        self,
        elements: list[_StructElement],
    ) -> dict[tuple[int, float], list[_StructElement]]:
        """Группировка по (page, y_center) с допуском y_tolerance."""
        groups: dict[tuple[int, float], list[_StructElement]] = {}
        current_key: tuple[int, float] | None = None

        sorted_els = sorted(elements, key=lambda e: (e.page, e.y_center, e.x_center))

        for el in sorted_els:
            if (
                current_key is not None
                and current_key[0] == el.page
                and abs(el.y_center - current_key[1]) <= self.y_tolerance
            ):
                groups[current_key].append(el)
            else:
                current_key = (el.page, el.y_center)
                groups[current_key] = [el]

        return groups

    def _create_block(
        self,
        y_center: float,
        page: int,
        elements: list[_StructElement],
    ) -> _StructBlock | None:
        if not elements:
            return None

        block = _StructBlock(
            block_id=None,
            y_position=y_center,
            page=page,
            elements=elements,
        )
        block.resolve_languages()

        headings_with_num = [
            e for e in elements
            if e.element_type == "heading" and e.clause_number
        ]
        if headings_with_num:
            best_heading = max(
                headings_with_num,
                key=lambda e: (_count_chars(e.text), len(e.text)),
            )
            block.block_id = best_heading.clause_number
            block.is_heading = True

        return block

    def _align_by_clause_numbers(self, blocks: list[_StructBlock]) -> list[_StructBlock]:
        """Объединяем блоки с одинаковым block_id (номером пункта)."""
        num_to_blocks: dict[str, list[_StructBlock]] = {}
        unnumbered: list[_StructBlock] = []

        for block in blocks:
            if block.block_id:
                num_to_blocks.setdefault(block.block_id, []).append(block)
            else:
                unnumbered.append(block)

        merged: list[_StructBlock] = []
        for number, blks in num_to_blocks.items():
            if len(blks) == 1:
                merged.append(blks[0])
            else:
                merged.append(self._merge_blocks(number, blks))

        merged.extend(unnumbered)
        return merged

    @staticmethod
    def _merge_blocks(number: str, blocks: list[_StructBlock]) -> _StructBlock:
        avg_y = sum(b.y_position for b in blocks) / len(blocks)
        all_els = [e for b in blocks for e in b.elements]
        result = _StructBlock(
            block_id=number,
            y_position=avg_y,
            page=blocks[0].page,
            elements=all_els,
        )
        result.resolve_languages()
        result.is_heading = any(b.is_heading for b in blocks)
        return result

    @staticmethod
    def _finalize_blocks(blocks: list[_StructBlock]) -> list[_StructBlock]:
        """Сортируем и дедуплицируем элементы внутри блоков."""
        blocks.sort(key=lambda b: (b.page, b.y_position))
        seen_ids: set[str] = set()

        for block in blocks:
            unique: list[_StructElement] = []
            for element in sorted(
                block.elements,
                key=lambda e: (e.y_center, e.x_center, e.element_id),
            ):
                dedupe_key = (
                    element.element_id
                    or f"{element.page}:{element.bbox}:{element.text}"
                )
                if dedupe_key not in seen_ids:
                    seen_ids.add(dedupe_key)
                    unique.append(element)
            block.elements = unique

        return blocks


# ---------------------------------------------------------------------------
# Оценка качества фильтрации
# ---------------------------------------------------------------------------


def _assess_quality(
    original: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    is_multilingual: bool = False,
) -> dict[str, Any]:
    e_b = len(original)
    e_a = len(selected)
    c_b = sum(_count_chars(el.get("text", "")) for el in original)
    c_a = sum(_count_chars(el.get("text", "")) for el in selected)

    element_retention_ratio = e_a / e_b if e_b else 0.0
    char_retention_ratio = c_a / c_b if c_b else 0.0

    degraded_reasons: list[str] = []

    # Абсолютные провалы — проверяем всегда
    if e_b > 0 and e_a == 0:
        degraded_reasons.append("no_elements_after_filter")
    if c_b > 0 and c_a == 0:
        degraded_reasons.append("no_chars_after_filter")

    # Пороги retention применяем только для multilingual документов
    # (для монолингвальных низкий retention означает баг фильтра)
    if is_multilingual:
        if (
            e_b >= _STRUCTURAL_MIN_ELEMENTS
            and element_retention_ratio < _MIN_ELEMENT_RETENTION_RATIO
        ):
            degraded_reasons.append(
                f"low_element_retention_ratio:{element_retention_ratio:.3f}"
            )
        if c_b > 0 and char_retention_ratio < _MIN_CHAR_RETENTION_RATIO:
            degraded_reasons.append(
                f"low_char_retention_ratio:{char_retention_ratio:.3f}"
            )

    degraded = bool(degraded_reasons)

    return {
        "elements_before": e_b,
        "elements_after": e_a,
        "chars_before": c_b,
        "chars_after": c_a,
        "element_retention_ratio": element_retention_ratio,
        "char_retention_ratio": char_retention_ratio,
        "degraded": degraded,
        "degraded_reason": ";".join(degraded_reasons) if degraded_reasons else None,
    }


def _build_metadata(
    layout: dict[str, Any],
    target: str,
    quality: dict[str, Any],
    is_multilingual: bool = False,
    structural_filter_used: bool = False,
) -> dict[str, Any]:
    """Собрать metadata для layout_primary."""
    base = dict(layout.get("metadata") or {})
    base["language_filter"] = {
        "target_language": target,
        "multilingual_mode": is_multilingual,
        "structural_filter_used": structural_filter_used,
        **quality,
    }
    base["element_count"] = quality["elements_after"]
    return base


# ---------------------------------------------------------------------------
# Простой фильтр — LOSSLESS, MULTILINGUAL, с provenance
# ---------------------------------------------------------------------------


def _simple_filter(
    layout: dict[str, Any],
    target: str,
    elements: list[dict[str, Any]],
    tables: list[Any],
    is_multilingual: bool = False,
) -> dict[str, Any]:
    """
    Lossless простой фильтр с multilingual поддержкой.

    КРИТИЧЕСКИ ВАЖНО: retained_element["text"] == raw_element["text"] БЕЗ ИСКЛЮЧЕНИЙ.

    Возвращает dict с ключами:
    - elements:             отфильтрованные элементы (retained + flagged)
    - tables:               таблицы без изменений
    - excluded_element_ids: список element_id удалённых элементов
    - filter_decisions:     audit trail каждого решения
    - metadata:             metadata с language_filter
    """
    retained_elements: list[dict[str, Any]] = []
    filter_decisions: list[dict[str, Any]] = []
    excluded_ids: list[str] = []
    seen_ids: set[str] = set()

    from services.language_detector import get_language_detector
    detector = get_language_detector()

    for el in elements:
        text = el.get("text", "")
        element_id = str(el.get("element_id") or "")

        dedupe_key = element_id or f"{_bbox_sort_key(el)}:{text.strip()}"
        if dedupe_key in seen_ids:
            continue
        seen_ids.add(dedupe_key)

        # Шаг 1: Структурированные данные
        structured_kind = _classify_structured_data(text)

        # Шаг 2: Language label
        language_label = classify_element_language(text, target, structured_kind)

        # Шаг 3: Structured data → всегда retained
        if structured_kind in ("pure", "contains"):
            decision = "retained"
            reason = "structured_data_preserved"
        else:
            decision, reason = _RETENTION_POLICY[language_label]

        # Шаг 4: Language detection для audit trail
        if text.strip():
            lang_result = detector.detect_language(text)
            lang_detected = lang_result.language_code
            lang_script = lang_result.script_code
            lang_confidence = lang_result.confidence
        else:
            lang_detected = "unknown"
            lang_script = "other"
            lang_confidence = 0.0

        # Шаг 5: Audit trail
        filter_decisions.append({
            "source_element_id": element_id,
            "output_element_id": element_id if decision != "excluded" else None,
            "page": el.get("page", 1),
            "decision": decision,
            "language_detected": lang_detected,
            "language_script": lang_script,
            "language_confidence": round(lang_confidence, 4),
            "language_label": language_label,
            "reason": reason,
            "is_structured_data": structured_kind != "none",
            "structured_data_kind": structured_kind,
        })

        # Шаг 6: Применяем решение
        if decision in ("retained", "flagged"):
            el_copy = dict(el)
            el_copy["retention_status"] = decision
            el_copy["language_label"] = language_label
            retained_elements.append(el_copy)
        else:
            excluded_ids.append(element_id)

    retained_sorted = sorted(retained_elements, key=_reading_order_sort_key)
    for order, element in enumerate(retained_sorted):
        element["reading_order"] = order

    quality = _assess_quality(elements, retained_sorted, is_multilingual=is_multilingual)
    metadata = _build_metadata(
        layout, target, quality,
        is_multilingual=is_multilingual,
        structural_filter_used=False,
    )

    return {
        "document_version_id": layout.get("document_version_id"),
        "document_id": layout.get("document_id"),
        "elements": retained_sorted,
        "tables": tables,
        "excluded_element_ids": excluded_ids,
        "filter_decisions": filter_decisions,
        "metadata": metadata,
    }


# ---------------------------------------------------------------------------
# Структурный фильтр — LOSSLESS, MULTILINGUAL, с provenance
# ---------------------------------------------------------------------------


def _structural_filter(
    layout: dict[str, Any],
    target: str,
    elements: list[dict[str, Any]],
    tables: list[Any],
) -> dict[str, Any]:
    """
    Lossless структурный фильтр с multilingual поддержкой.

    LOSSLESS ИНВАРИАНТ: текст выбранных элементов не мутирует.
    """
    analyzer = _StructuralAnalyzer()
    blocks = analyzer.analyze(elements)

    raw_elements_by_id: dict[str, dict[str, Any]] = {
        str(el.get("element_id") or ""): el
        for el in elements
        if el.get("element_id")
    }
    all_raw_ids: set[str] = set(raw_elements_by_id.keys())

    selected_elements: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    last_heading_uid: str | None = None
    multilingual_block_count = 0

    from services.language_detector import get_language_detector
    detector = get_language_detector()

    for block in blocks:
        if block.has_multiple_languages:
            multilingual_block_count += 1

        chosen = block.get_for_language(target)
        if not chosen:
            continue

        # Если язык выбранного элемента явно отличается от целевого
        # и он не neutral — пропускаем
        if chosen.detected_lang not in (target, "unknown"):
            continue

        out = dict(chosen.original)

        # Language label для provenance
        structured_kind = _classify_structured_data(chosen.text)
        language_label = classify_element_language(chosen.text, target, structured_kind)

        out["retention_status"] = "retained"
        out["language_label"] = language_label

        if block.is_heading and block.block_id:
            out["clause_uid"] = block.block_id
            last_heading_uid = block.block_id
        elif not block.is_heading and last_heading_uid and not out.get("parent_clause_uid"):
            out["parent_clause_uid"] = last_heading_uid

        dedupe_key = (
            str(out.get("element_id") or "")
            or (
                f"{_safe_int_page(out.get('page', 1))}"
                f":{_safe_bbox(out.get('bbox'))}"
                f":{out.get('text', '')}"
            )
        )
        if dedupe_key in selected_ids:
            continue

        selected_ids.add(dedupe_key)
        selected_elements.append(out)

    selected_sorted = sorted(selected_elements, key=_reading_order_sort_key)
    for order, element in enumerate(selected_sorted):
        element["reading_order"] = order

    selected_element_ids: set[str] = {
        str(el.get("element_id") or "")
        for el in selected_sorted
        if el.get("element_id")
    }
    excluded_ids: list[str] = sorted(all_raw_ids - selected_element_ids)

    # filter_decisions для selected
    filter_decisions: list[dict[str, Any]] = []
    for el in selected_sorted:
        eid = str(el.get("element_id") or "")
        el_text = el.get("text", "")
        lang_result = detector.detect_language(el_text) if el_text.strip() else None
        filter_decisions.append({
            "source_element_id": eid,
            "output_element_id": eid,
            "page": el.get("page", 1),
            "decision": el.get("retention_status", "retained"),
            "language_detected": lang_result.language_code if lang_result else "unknown",
            "language_script": lang_result.script_code if lang_result else "other",
            "language_confidence": round(lang_result.confidence, 4) if lang_result else 0.0,
            "language_label": el.get("language_label", "target"),
            "reason": "structural_filter_selected",
            "is_structured_data": _classify_structured_data(el_text) != "none",
            "structured_data_kind": _classify_structured_data(el_text),
        })

    # filter_decisions для excluded
    for eid in excluded_ids:
        raw_el = raw_elements_by_id.get(eid, {})
        raw_text = raw_el.get("text", "")
        lang_result = detector.detect_language(raw_text) if raw_text.strip() else None
        filter_decisions.append({
            "source_element_id": eid,
            "output_element_id": None,
            "page": raw_el.get("page", 1),
            "decision": "excluded",
            "language_detected": lang_result.language_code if lang_result else "unknown",
            "language_script": lang_result.script_code if lang_result else "other",
            "language_confidence": round(lang_result.confidence, 4) if lang_result else 0.0,
            "language_label": "foreign",
            "reason": "structural_filter_not_selected",
            "is_structured_data": _classify_structured_data(raw_text) != "none",
            "structured_data_kind": _classify_structured_data(raw_text),
        })

    quality = _assess_quality(elements, selected_sorted, is_multilingual=True)
    metadata = _build_metadata(
        layout, target, quality,
        is_multilingual=True,
        structural_filter_used=True,
    )
    metadata["language_filter"]["multilingual_blocks_found"] = multilingual_block_count
    metadata["language_filter"]["structural_blocks_total"] = len(blocks)

    return {
        "document_version_id": layout.get("document_version_id"),
        "document_id": layout.get("document_id"),
        "elements": selected_sorted,
        "tables": tables,
        "excluded_element_ids": excluded_ids,
        "filter_decisions": filter_decisions,
        "metadata": metadata,
    }


# ---------------------------------------------------------------------------
# Главная точка входа — MULTILINGUAL
# ---------------------------------------------------------------------------


def filter_layout_to_language(
    layout: dict[str, Any],
    target_language: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Отфильтровать layout до одного языка.

    MULTILINGUAL версия (Фаза 2A):
    - принимает любой ISO 639-1 target_language: "ru", "en", "ar", "fr", "kk"...
    - НЕ ограничен списком ("ru", "en")
    - использует LanguageDetector для определения языка каждого элемента

    Аргументы:
      layout          — text_layout_raw
      target_language — ISO 639-1 код целевого языка
      context         — опциональный dict с ключами:
                        "is_multilingual" (bool) — документ содержит несколько языков
                        "document_id"     (str)
                        "deal_id"         (str)

    Возвращает layout_primary с ключами:
      - elements:             отфильтрованные элементы
      - excluded_element_ids: list[str]  — удалённые element_id
      - filter_decisions:     list[dict] — audit trail решений
      - metadata:             metadata с language_filter
    """
    target = (target_language or "").lower().strip()

    # MULTILINGUAL: не ограничиваем список языков
    # Валидируем только что язык не пустой
    if not target:
        logger.warning(
            "filter_layout_to_language: empty target_language, returning raw layout",
            target_language=target_language,
        )
        return layout

    elements: list[dict[str, Any]] = layout.get("elements") or []
    tables: list[Any] = layout.get("tables") or []

    if not elements:
        return {
            "document_version_id": layout.get("document_version_id"),
            "document_id": layout.get("document_id"),
            "elements": [],
            "tables": tables,
            "excluded_element_ids": [],
            "filter_decisions": [],
            "metadata": _build_metadata(
                layout, target,
                _assess_quality([], [], is_multilingual=False),
                is_multilingual=False,
                structural_filter_used=False,
            ),
        }

    # "is_bilingual" для обратной совместимости → переименован в "is_multilingual"
    is_multilingual = bool(
        context.get("is_multilingual") or context.get("is_bilingual")
    ) if context else False
    doc_id = (context or {}).get("document_id", "unknown")

    if not is_multilingual or len(elements) < _STRUCTURAL_MIN_ELEMENTS:
        result = _simple_filter(
            layout, target, elements, tables,
            is_multilingual=is_multilingual,
        )
        logger.info(
            "filter_layout_to_language: simple filter applied",
            document_id=doc_id,
            target=target,
            elements_in=len(elements),
            elements_out=len(result.get("elements") or []),
            elements_excluded=len(result.get("excluded_element_ids") or []),
            degraded=result.get("metadata", {})
                .get("language_filter", {}).get("degraded", False),
            degraded_reason=result.get("metadata", {})
                .get("language_filter", {}).get("degraded_reason"),
        )
        return result

    try:
        result = _structural_filter(layout, target, elements, tables)
        logger.info(
            "filter_layout_to_language: structural filter applied",
            document_id=doc_id,
            target=target,
            elements_in=len(elements),
            elements_out=len(result.get("elements") or []),
            elements_excluded=len(result.get("excluded_element_ids") or []),
            multilingual_blocks=result.get("metadata", {})
                .get("language_filter", {}).get("multilingual_blocks_found", 0),
            degraded=result.get("metadata", {})
                .get("language_filter", {}).get("degraded", False),
            degraded_reason=result.get("metadata", {})
                .get("language_filter", {}).get("degraded_reason"),
        )
        return result

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "filter_layout_to_language: structural filter failed, "
            "falling back to simple filter",
            document_id=doc_id,
            target_language=target,
            error=str(exc),
            traceback=traceback.format_exc(),
        )

        result = _simple_filter(layout, target, elements, tables, is_multilingual=True)

        lf = (result.get("metadata") or {}).get("language_filter") or {}
        lf["degraded"] = True

        fallback_reason = "structural_filter_exception_fallback_to_simple"
        prev_reason = lf.get("degraded_reason")
        if prev_reason:
            if fallback_reason not in str(prev_reason):
                lf["degraded_reason"] = f"{prev_reason};{fallback_reason}"
        else:
            lf["degraded_reason"] = fallback_reason

        result.setdefault("metadata", {})["language_filter"] = lf

        logger.info(
            "filter_layout_to_language: simple fallback applied after structural failure",
            document_id=doc_id,
            target_language=target,
            elements_in=len(elements),
            elements_out=len(result.get("elements") or []),
            elements_excluded=len(result.get("excluded_element_ids") or []),
            degraded=lf.get("degraded", False),
            degraded_reason=lf.get("degraded_reason"),
        )
        return result


# ---------------------------------------------------------------------------
# Удобные алиасы (сохраняем для обратной совместимости)
# ---------------------------------------------------------------------------


def filter_layout_to_ru(layout: dict[str, Any]) -> dict[str, Any]:
    return filter_layout_to_language(layout, "ru")


def filter_layout_to_en(layout: dict[str, Any]) -> dict[str, Any]:
    return filter_layout_to_language(layout, "en")

    
