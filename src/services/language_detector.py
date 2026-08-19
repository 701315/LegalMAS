# src/services/language_detector.py

"""
Universal Language Detector Service.

Назначение:
- единая точка определения языка текстового фрагмента;
- используется layout_language_filter для классификации каждого элемента;
- поддерживает 75+ языков через lingua-language-detector;
- graceful fallback на Unicode script detection если lingua недоступна.

Архитектура:
- два уровня детекции:
  1. Script detection (быстро, Unicode ranges) — определяет письменность:
     "cyrillic", "latin", "arabic", "hebrew", "cjk", "devanagari", "other"
  2. Language detection (lingua) — определяет конкретный язык:
     "ru", "en", "ar", "fr", "de", "kk", "uz", "he", "zh", "hi", ...

- Для pure structured data (IBAN, SWIFT, email) — script/language detection
  не запускается, возвращаем "structured" сразу.

- Для коротких текстов (< LANGUAGE_DETECTOR_MIN_CHARS) — только script detection.

Контракт:
- LanguageDetector.detect_language(text) → LanguageDetectionResult
- LanguageDetector.detect_script(text) → str (script code)
- Singleton через get_language_detector()

Поддерживаемые языки lingua (неполный список):
  Кириллица:  ru (Russian), uk (Ukrainian), be (Belarusian),
               kk (Kazakh), bg (Bulgarian), sr (Serbian)
  Латиница:   en (English), fr (French), de (German), es (Spanish),
               it (Italian), pl (Polish), pt (Portuguese), nl (Dutch),
               cs (Czech), ro (Romanian), hu (Hungarian), sv (Swedish),
               fi (Finnish), da (Danish), nb (Norwegian), tr (Turkish),
               uz (Uzbek), az (Azerbaijani), et (Estonian), lv (Latvian),
               lt (Lithuanian), sk (Slovak), sl (Slovenian), hr (Croatian)
  Арабица:    ar (Arabic), fa (Persian/Farsi), ur (Urdu)
  CJK:        zh (Chinese), ja (Japanese), ko (Korean)
  Иврит:      he (Hebrew)
  Деванагари: hi (Hindi)
  Другие:     ...итого 75 языков
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Unicode script ranges для быстрого script detection
# ---------------------------------------------------------------------------

# Диапазоны Unicode кодпоинтов для каждой письменности.
# Порядок проверки важен: от более специфичных к менее специфичным.
_SCRIPT_RANGES: list[tuple[str, list[tuple[int, int]]]] = [
    ("cyrillic", [
        (0x0400, 0x04FF),   # Кириллица основная
        (0x0500, 0x052F),   # Кириллица дополнительная
        (0x2DE0, 0x2DFF),   # Кириллица расширенная A
        (0xA640, 0xA69F),   # Кириллица расширенная B
    ]),
    ("arabic", [
        (0x0600, 0x06FF),   # Арабский
        (0x0750, 0x077F),   # Арабский дополнительный
        (0x08A0, 0x08FF),   # Расширенный арабский A
        (0xFB50, 0xFDFF),   # Арабский презентационные формы A
        (0xFE70, 0xFEFF),   # Арабский презентационные формы B
    ]),
    ("hebrew", [
        (0x0590, 0x05FF),   # Иврит
        (0xFB00, 0xFB4F),   # Алфавитные презентационные формы
    ]),
    ("cjk", [
        (0x4E00, 0x9FFF),   # CJK Unified Ideographs
        (0x3400, 0x4DBF),   # CJK Extension A
        (0x20000, 0x2A6DF), # CJK Extension B
        (0x3040, 0x309F),   # Хирагана
        (0x30A0, 0x30FF),   # Катакана
        (0xAC00, 0xD7AF),   # Корейский хангыль
    ]),
    ("devanagari", [
        (0x0900, 0x097F),   # Деванагари (хинди, маратхи, санскрит)
        (0xA8E0, 0xA8FF),   # Деванагари расширенный
    ]),
    ("latin", [
        (0x0041, 0x005A),   # A-Z
        (0x0061, 0x007A),   # a-z
        (0x00C0, 0x00FF),   # Latin-1 supplement (французский, немецкий, испанский...)
        (0x0100, 0x017F),   # Latin Extended-A (польский, чешский...)
        (0x0180, 0x024F),   # Latin Extended-B
    ]),
]

# Маппинг script_code → список ISO language codes которые используют этот скрипт.
# Используется для fallback когда lingua недоступна или текст слишком короткий.
# В этом случае мы не можем точно сказать язык, только скрипт.
_SCRIPT_TO_LANGUAGE_FALLBACK: dict[str, str] = {
    "cyrillic": "ru",   # Наиболее распространённый кириллический язык в нашем контексте
    "arabic":   "ar",   # Арабский
    "hebrew":   "he",   # Иврит
    "cjk":      "zh",   # Китайский (наиболее распространённый CJK)
    "devanagari": "hi", # Хинди
    "latin":    "en",   # Английский (наиболее распространённый латинский)
    "other":    "unknown",
}


# ---------------------------------------------------------------------------
# Результат language detection
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class LanguageDetectionResult:
    """
    Результат определения языка одного текстового фрагмента.

    Для непрофессионального программиста:
    - language_code:  ISO 639-1 код языка ("ru", "en", "ar", "fr", "kk"...)
                      или "unknown" если не удалось определить.
    - script_code:    код письменности ("cyrillic", "latin", "arabic", "hebrew",
                      "cjk", "devanagari", "other").
    - confidence:     уверенность detector'а (0.0 — 1.0).
                      < 0.50 = ненадёжный результат.
    - is_reliable:    True если confidence >= threshold и текст достаточно длинный.
    - detection_method: "lingua" | "script_fallback" | "too_short" | "structured_data"
    """
    language_code: str       # ISO 639-1: "ru", "en", "ar", "fr", "kk", "unknown"
    script_code: str         # "cyrillic", "latin", "arabic", "hebrew", "cjk", "other"
    confidence: float        # 0.0 — 1.0
    is_reliable: bool        # True если детектор уверен
    detection_method: str    # "lingua" | "script_fallback" | "too_short" | "structured_data"


# ---------------------------------------------------------------------------
# Lingua availability check
# ---------------------------------------------------------------------------

_LINGUA_AVAILABLE = False
_LINGUA_IMPORT_ERROR: Exception | None = None

try:
    from lingua import Language, LanguageDetectorBuilder  # type: ignore[import]
    _LINGUA_AVAILABLE = True
except Exception as _exc:
    _LINGUA_IMPORT_ERROR = _exc
    logger.warning(
        "lingua-language-detector not available, falling back to script-only detection. "
        "Install with: pip install lingua-language-detector==2.0.2",
        error=str(_exc),
    )


# ---------------------------------------------------------------------------
# Lingua language code маппинг
# ---------------------------------------------------------------------------

def _lingua_language_to_iso(lingua_language: object) -> str:
    """
    Конвертировать lingua Language enum в ISO 639-1 строку.

    Для непрофессионального программиста:
    lingua возвращает объект типа Language.RUSSIAN, Language.ENGLISH, и т.д.
    Нам нужна строка "ru", "en", и т.д.
    Lingua предоставляет метод iso_code_639_1() — используем его.
    """
    try:
        # lingua Language enum имеет метод iso_code_639_1()
        iso = lingua_language.iso_code_639_1()  # type: ignore[union-attr]
        # iso_code_639_1() возвращает объект IsoCode639_1 enum
        # его строковое значение — это и есть ISO код
        return str(iso.name).lower()
    except Exception:
        # Последний fallback — пробуем через name напрямую
        try:
            name = str(lingua_language.name).lower()  # type: ignore[union-attr]
            # Lingua Language enum names: RUSSIAN → ru, ENGLISH → en, etc.
            # Это не идеально но работает для большинства языков
            _LANGUAGE_NAME_TO_ISO = {
                "russian": "ru", "english": "en", "german": "de",
                "french": "fr", "spanish": "es", "italian": "it",
                "portuguese": "pt", "dutch": "nl", "polish": "pl",
                "ukrainian": "uk", "belarusian": "be", "bulgarian": "bg",
                "serbian": "sr", "croatian": "hr", "slovak": "sk",
                "czech": "cs", "slovenian": "sl", "romanian": "ro",
                "hungarian": "hu", "swedish": "sv", "norwegian": "nb",
                "danish": "da", "finnish": "fi", "turkish": "tr",
                "arabic": "ar", "hebrew": "he", "persian": "fa",
                "chinese": "zh", "japanese": "ja", "korean": "ko",
                "hindi": "hi", "urdu": "ur", "kazakh": "kk",
                "uzbek": "uz", "azerbaijani": "az", "estonian": "et",
                "latvian": "lv", "lithuanian": "lt", "greek": "el",
                "armenian": "hy", "georgian": "ka",
            }
            return _LANGUAGE_NAME_TO_ISO.get(name, "unknown")
        except Exception:
            return "unknown"


# ---------------------------------------------------------------------------
# Основной Language Detector класс
# ---------------------------------------------------------------------------

class LanguageDetector:
    """
    Универсальный детектор языков.

    Использует lingua для точного определения языка.
    Fallback на script detection для коротких текстов или если lingua недоступна.

    Потокобезопасен: lingua detector thread-safe по документации.
    Singleton: создавайте через get_language_detector().
    """

    def __init__(
        self,
        backend: str = "lingua",
        min_chars: int = 10,
        confidence_threshold: float = 0.50,
    ) -> None:
        """
        Параметры:
        - backend:              "lingua" | "script_only"
        - min_chars:            минимум символов для запуска lingua
        - confidence_threshold: порог уверенности для is_reliable=True
        """
        self._backend = backend
        self._min_chars = min_chars
        self._confidence_threshold = confidence_threshold
        self._lingua_detector = None
        self._lock = threading.Lock()

        if backend == "lingua" and _LINGUA_AVAILABLE:
            self._init_lingua()
        elif backend == "lingua" and not _LINGUA_AVAILABLE:
            logger.warning(
                "LanguageDetector: lingua backend requested but not available. "
                "Falling back to script_only detection."
            )
            self._backend = "script_only"

    def _init_lingua(self) -> None:
        """
        Инициализировать lingua detector.

        Загружаем все доступные языки для максимальной универсальности.
        Lingua загружает compact language models (~5MB всего) — это быстро.
        """
        try:
            from lingua import LanguageDetectorBuilder  # type: ignore[import]

            self._lingua_detector = (
                LanguageDetectorBuilder
                .from_all_languages()
                .with_preloaded_language_models()
                .build()
            )
            logger.info(
                "LanguageDetector: lingua initialized successfully",
                backend="lingua",
                preloaded=True,
            )
        except Exception as exc:
            logger.warning(
                "LanguageDetector: lingua initialization failed, falling back to script_only",
                error=str(exc),
            )
            self._lingua_detector = None
            self._backend = "script_only"

    def detect_script(self, text: str) -> str:
        """
        Определить письменность (script) текста.

        Возвращает один из:
        "cyrillic" | "arabic" | "hebrew" | "cjk" | "devanagari" | "latin" | "other"

        Логика:
        - Считаем символы каждой письменности.
        - Побеждает та письменность, которой больше (если >= 30% от суммы).
        - Если ни одна не доминирует — "other".

        Для непрофессионального программиста:
        - "cyrillic" → скорее всего русский, украинский, казахский или другой
        - "arabic"   → арабский, персидский, урду
        - "latin"    → английский, французский, немецкий, испанский и т.д.
        - "other"    → цифры, пунктуация, неизвестная письменность
        """
        if not text:
            return "other"

        # Считаем символы по каждой письменности
        script_counts: dict[str, int] = {script: 0 for script, _ in _SCRIPT_RANGES}

        for ch in text:
            code = ord(ch)
            for script_name, ranges in _SCRIPT_RANGES:
                if any(start <= code <= end for start, end in ranges):
                    script_counts[script_name] += 1
                    break

        total = sum(script_counts.values())
        if total == 0:
            return "other"

        # Находим доминирующую письменность
        dominant_script = max(script_counts, key=lambda s: script_counts[s])
        dominant_count = script_counts[dominant_script]

        # Требуем хотя бы 30% доминирования
        # (меньше — это mixed или punctuation)
        if dominant_count / total >= 0.30:
            return dominant_script

        return "other"

    def detect_language(self, text: str) -> LanguageDetectionResult:
        """
        Определить язык текстового фрагмента.

        Алгоритм:
        1. Определяем script через detect_script().
        2. Если текст слишком короткий → script fallback.
        3. Если lingua доступна → запускаем lingua.
        4. Если lingua не уверена (confidence < threshold) → script fallback.
        5. Иначе → возвращаем результат lingua.

        Возвращает LanguageDetectionResult с language_code, script_code,
        confidence, is_reliable, detection_method.
        """
        if not text or not text.strip():
            return LanguageDetectionResult(
                language_code="unknown",
                script_code="other",
                confidence=0.0,
                is_reliable=False,
                detection_method="too_short",
            )

        script_code = self.detect_script(text)

        # Текст слишком короткий для надёжной language detection
        stripped_len = len(text.replace(" ", "").strip())
        if stripped_len < self._min_chars:
            lang_fallback = _SCRIPT_TO_LANGUAGE_FALLBACK.get(script_code, "unknown")
            return LanguageDetectionResult(
                language_code=lang_fallback,
                script_code=script_code,
                confidence=0.30,  # низкая уверенность для коротких текстов
                is_reliable=False,
                detection_method="too_short",
            )

        # Script-only backend
        if self._backend == "script_only" or self._lingua_detector is None:
            lang_fallback = _SCRIPT_TO_LANGUAGE_FALLBACK.get(script_code, "unknown")
            return LanguageDetectionResult(
                language_code=lang_fallback,
                script_code=script_code,
                confidence=0.60,  # средняя уверенность для script detection
                is_reliable=script_code != "other",
                detection_method="script_fallback",
            )

        # Lingua detection
        try:
            result = self._lingua_detector.detect_language_of(text)

            if result is None:
                # Lingua не смогла определить язык
                lang_fallback = _SCRIPT_TO_LANGUAGE_FALLBACK.get(script_code, "unknown")
                return LanguageDetectionResult(
                    language_code=lang_fallback,
                    script_code=script_code,
                    confidence=0.30,
                    is_reliable=False,
                    detection_method="script_fallback",
                )

            # Получаем confidence scores для всех языков
            confidence_values = self._lingua_detector.compute_language_confidence_values(text)
            # confidence_values — список объектов с .language и .value
            # Берём confidence для определённого языка
            confidence = 0.50  # дефолт
            for cv in confidence_values:
                if cv.language == result:
                    confidence = float(cv.value)
                    break

            language_code = _lingua_language_to_iso(result)
            is_reliable = (
                confidence >= self._confidence_threshold
                and language_code != "unknown"
            )

            return LanguageDetectionResult(
                language_code=language_code,
                script_code=script_code,
                confidence=round(confidence, 4),
                is_reliable=is_reliable,
                detection_method="lingua",
            )

        except Exception as exc:
            logger.warning(
                "LanguageDetector: lingua detection failed for text fragment, "
                "falling back to script detection",
                error=str(exc),
                text_preview=text[:50],
            )
            lang_fallback = _SCRIPT_TO_LANGUAGE_FALLBACK.get(script_code, "unknown")
            return LanguageDetectionResult(
                language_code=lang_fallback,
                script_code=script_code,
                confidence=0.40,
                is_reliable=False,
                detection_method="script_fallback",
            )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_detector_instance: LanguageDetector | None = None
_detector_lock = threading.Lock()


def get_language_detector() -> LanguageDetector:
    """
    Получить singleton экземпляр LanguageDetector.

    Потокобезопасно: использует double-checked locking.

    При первом вызове создаёт и инициализирует detector согласно settings.
    При последующих вызовах возвращает тот же экземпляр.

    Для непрофессионального программиста:
    - не создавайте LanguageDetector() напрямую;
    - всегда используйте get_language_detector();
    - это гарантирует что lingua загружается один раз, а не при каждом вызове.
    """
    global _detector_instance

    if _detector_instance is not None:
        return _detector_instance

    with _detector_lock:
        if _detector_instance is not None:
            return _detector_instance

        try:
            from core.config import settings
            backend = getattr(settings, "LANGUAGE_DETECTOR_BACKEND", "lingua")
            min_chars = getattr(settings, "LANGUAGE_DETECTOR_MIN_CHARS", 10)
            confidence_threshold = getattr(
                settings, "LANGUAGE_DETECTOR_CONFIDENCE_THRESHOLD", 0.50
            )
        except Exception:
            # Если settings недоступны — используем дефолты
            backend = "lingua"
            min_chars = 10
            confidence_threshold = 0.50

        _detector_instance = LanguageDetector(
            backend=backend,
            min_chars=min_chars,
            confidence_threshold=confidence_threshold,
        )

    return _detector_instance


def reset_language_detector() -> None:
    """
    Сбросить singleton (только для тестов).

    Не вызывайте в production коде.
    """
    global _detector_instance
    with _detector_lock:
        _detector_instance = None



