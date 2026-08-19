# src/services/document_language_pipeline.py

"""
Document language pipeline service.

Назначение:
- определить фактические языки документа по layout;
- обновить Deal.languages;
- проверить, соответствует ли документ выбранному пользователем языку;
- построить одноязычный layout на основе исходного layout.

ВАЖНО:
- этот сервис НЕ читает PDF из MinIO;
- этот сервис НЕ сохраняет ничего в БД кроме языков сделки;
- этот сервис НЕ строит PDF-файл;
- этот сервис работает только с layout-структурой и данными сделки.
- этот сервис НЕ принимает решение о выборе языка — язык ВСЕГДА
  передаётся снаружи через параметр target_language (из Deal.primary_language).

Новый контракт выбора языка:
- пайплайн запускается только ПОСЛЕ того как пользователь выбрал язык;
- сервис проверяет наличие выбранного языка в документе;
- если язык отсутствует или занимает < MIN_TARGET_LANGUAGE_RATIO — карантин;
- если язык присутствует — обработка продолжается.

MULTILINGUAL поддержка (Фаза 2A):
- Поддерживаются все языки, которые умеет определять lingua (75+).
- SUPPORTED_DOCUMENT_LANGUAGES убран — нет жёсткого ограничения по языкам.
- _normalize_lang() теперь принимает любой валидный ISO 639-1 код.
- _measure_language_presence() работает через LanguageDetector, а не только
  через кириллица/латиница счётчики.
- DocumentLanguageDecision.is_multilingual заменяет is_bilingual.

Дополнительный контракт для downstream:
- decision.pipeline_mode = "PRIMARY_ONLY_DOWNSTREAM"
- primary_layout.metadata.language_filter.contract_version = 2
- primary_layout.metadata.language_filter.downstream_requires_primary_source = True
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.repositories.deal_repo import DealRepository
from services.deal_language_service import update_deal_languages
from services.layout_language_filter import (
    detect_languages_in_layout,
    filter_layout_to_language,
)

logger = get_logger(__name__)

# Минимальная доля символов целевого языка в документе.
# Если доля ниже этого порога — документ уходит в карантин,
# так как целевой язык либо отсутствует, либо представлен лишь
# техническими вхождениями (реквизиты, email и т.п.).
MIN_TARGET_LANGUAGE_RATIO = 0.15

# Минимальная доля символов языка для признания документа multilingual.
# Если второй (или третий) язык занимает >= этой доли — документ multilingual.
MIN_SECONDARY_LANGUAGE_RATIO = 0.15

# Минимальная длина ISO language code (защита от мусора)
_MIN_LANG_CODE_LEN = 2
# Максимальная длина ISO language code (ISO 639-1 = 2 символа, ISO 639-3 = 3)
_MAX_LANG_CODE_LEN = 8


@dataclass
class DocumentLanguageDecision:
    """
    Результат языкового анализа документа.

    MULTILINGUAL версия (Фаза 2A):
    - is_multilingual заменяет is_bilingual (может быть 3+ языков)
    - language_ratios содержит доли для ВСЕХ найденных языков
    - detected_languages содержит все языки, не только ru/en

    Поля:

    detected_languages:
    - какие языки реально найдены в layout документа (ISO 639-1 коды).
      Примеры: ["en"], ["ru", "en"], ["ar", "en"], ["ru", "kk", "en"]

    target_language:
    - язык, переданный снаружи (из Deal.primary_language).
      Любой ISO 639-1 код. Сервис его не меняет.

    is_multilingual:
    - True, если документ содержит 2+ языка, каждый из которых
      занимает >= MIN_SECONDARY_LANGUAGE_RATIO символов.

    language_ratios:
    - словарь {lang_code → ratio} для всех найденных языков.
      Пример: {"ru": 0.72, "en": 0.24, "kk": 0.04}

    target_language_ratio:
    - доля символов целевого языка в тексте документа (0.0–1.0).

    route:
    - "proceed"    — документ соответствует целевому языку.
    - "quarantine" — целевой язык отсутствует или слишком мал.

    quarantine_reason:
    - None если route == "proceed".
    - "target_language_absent"     — язык не обнаружен совсем.
    - "target_language_negligible" — язык найден, но доля < MIN_TARGET_LANGUAGE_RATIO.

    deal_primary_language_before / after:
    - primary_language сделки до и после update_deal_languages.

    deal_languages_before / after:
    - список языков сделки до и после update_deal_languages.

    pipeline_mode:
    - "PRIMARY_ONLY_DOWNSTREAM" — все стадии работают только с primary layout.

    requires_user_selection:
    - всегда False (язык выбирается до запуска пайплайна).
      Поле сохранено для совместимости с metadata downstream.

    is_bilingual:
    - DEPRECATED. Оставлено для backward compatibility.
      Используйте is_multilingual.
    """

    detected_languages: list[str]
    target_language: str
    is_multilingual: bool
    language_ratios: dict[str, float]
    target_language_ratio: float
    route: str                     # "proceed" | "quarantine"
    quarantine_reason: str | None
    deal_primary_language_before: str | None
    deal_languages_before: list[str]
    deal_primary_language_after: str | None
    deal_languages_after: list[str]
    requires_user_selection: bool = False
    pipeline_mode: str = "PRIMARY_ONLY_DOWNSTREAM"

    @property
    def is_bilingual(self) -> bool:
        """
        Backward-compatible alias для is_multilingual.
        Используйте is_multilingual в новом коде.
        """
        return self.is_multilingual


@dataclass
class PrimaryLanguageLayoutResult:
    """
    Итог работы pipeline.

    decision:
    - решение по языкам документа.

    primary_layout:
    - layout, отфильтрованный до одного языка (если multilingual),
      либо исходный layout с проставленной metadata (если монолингвальный).

    raw_layout:
    - исходный layout, который пришёл в сервис.

    should_quarantine:
    - True, если worker должен перевести документ в статус QUARANTINE.
    """

    decision: DocumentLanguageDecision
    primary_layout: dict[str, Any]
    raw_layout: dict[str, Any]
    should_quarantine: bool = False


async def analyze_document_languages(
    db: AsyncSession,
    deal_id: uuid.UUID,
    layout: dict[str, Any],
    target_language: str,
) -> DocumentLanguageDecision:
    """
    Определить языки документа и проверить соответствие целевому языку.

    MULTILINGUAL версия:
    - принимает любой ISO 639-1 target_language
    - возвращает реальные языки документа через lingua detector
    - поддерживает 3+ языков в документе

    Параметры:
    - target_language: язык выбранный пользователем (ISO 639-1 код).
      Передаётся обязательно — пайплайн не запускается без выбранного языка.

    Возвращает DocumentLanguageDecision с route="proceed" или route="quarantine".
    """
    deal_repo = DealRepository(db)
    deal_before = await deal_repo.internal_unsafe_get_by_id(deal_id)

    deal_primary_before = _normalize_lang(
        getattr(deal_before, "primary_language", None) if deal_before else None
    )
    deal_languages_before = _normalize_lang_list(
        getattr(deal_before, "languages", None) if deal_before else []
    )

    # Определяем языки документа по layout через lingua detector
    # detect_languages_in_layout теперь возвращает ISO коды любых языков
    raw_detected = detect_languages_in_layout(layout)
    detected_languages = _normalize_lang_list(raw_detected)

    # Если lingua ничего не нашла (очень короткий документ, только цифры, OCR мусор)
    # НЕ делаем fallback на "ru" — честнее вернуть пустой список
    # и дать пользователю самому решить. Но для карантин-логики нам нужен список —
    # если detect вернул пустой список, то target_language точно не найден → карантин.
    if not detected_languages:
        logger.warning(
            "Language detection returned no languages for document layout",
            deal_id=str(deal_id),
            target_language=target_language,
            elements_count=len(layout.get("elements") or []),
        )

    # Обновляем языки сделки на основе найденных в документе
    if detected_languages:
        await update_deal_languages(
            db=db,
            deal_id=deal_id,
            new_languages=detected_languages,
        )

    deal_after = await deal_repo.internal_unsafe_get_by_id(deal_id)
    deal_primary_after = _normalize_lang(
        getattr(deal_after, "primary_language", None) if deal_after else None
    )
    deal_languages_after = _normalize_lang_list(
        getattr(deal_after, "languages", None) if deal_after else []
    )

    # Измеряем реальное соотношение языков в документе
    presence = _measure_language_presence(layout, target_language, detected_languages)

    # Определяем маршрут: карантин или продолжение
    route, quarantine_reason = _classify_language_route(
        detected=detected_languages,
        target=target_language,
        target_presence=presence,
    )

    decision = DocumentLanguageDecision(
        detected_languages=detected_languages,
        target_language=target_language,
        is_multilingual=presence["is_multilingual"],
        language_ratios=presence["language_ratios"],
        target_language_ratio=presence["target_ratio"],
        route=route,
        quarantine_reason=quarantine_reason,
        deal_primary_language_before=deal_primary_before,
        deal_languages_before=deal_languages_before,
        deal_primary_language_after=deal_primary_after,
        deal_languages_after=deal_languages_after,
        requires_user_selection=False,
        pipeline_mode="PRIMARY_ONLY_DOWNSTREAM",
    )

    logger.info(
        "Document language analysis complete",
        deal_id=str(deal_id),
        detected_languages=decision.detected_languages,
        target_language=decision.target_language,
        is_multilingual=decision.is_multilingual,
        language_ratios={
            k: round(v, 3) for k, v in decision.language_ratios.items()
        },
        target_language_ratio=round(decision.target_language_ratio, 3),
        route=decision.route,
        quarantine_reason=decision.quarantine_reason,
        deal_primary_language_before=decision.deal_primary_language_before,
        deal_languages_before=decision.deal_languages_before,
        deal_primary_language_after=decision.deal_primary_language_after,
        deal_languages_after=decision.deal_languages_after,
    )

    return decision


async def build_primary_language_layout(
    db: AsyncSession,
    deal_id: uuid.UUID,
    tenant_id: str,
    document_id: str,
    layout: dict[str, Any],
    target_language: str,
) -> PrimaryLanguageLayoutResult:
    """
    Построить одноязычный layout для документа.

    MULTILINGUAL версия (Фаза 2A):
    - target_language — любой ISO 639-1 код
    - is_multilingual заменяет is_bilingual в filter_context
    - поддерживает арабский, французский, казахский и любые другие языки

    ВАЖНО: target_language обязателен.

    Три ветви обработки:

    1. КАРАНТИН: целевой язык отсутствует или < MIN_TARGET_LANGUAGE_RATIO.
       should_quarantine=True. Worker переводит документ в QUARANTINE.

    2. МОНОЛИНГВАЛЬНЫЙ: документ содержит только один значимый язык.
       Применяем мягкий simple filter (lossless, сохраняет structured data).
       should_quarantine=False.

    3. MULTILINGUAL: несколько языков с значимой долей каждого.
       Применяем filter_layout_to_language по целевому языку.
       should_quarantine=False.
    """
    decision = await analyze_document_languages(
        db=db,
        deal_id=deal_id,
        layout=layout,
        target_language=target_language,
    )

    # ── ВЕТВЬ 1: КАРАНТИН ─────────────────────────────────────────────────
    if decision.route == "quarantine":
        logger.warning(
            "Document must be quarantined: target language absent or negligible",
            deal_id=str(deal_id),
            tenant_id=tenant_id,
            document_id=document_id,
            target_language=target_language,
            detected_languages=decision.detected_languages,
            target_language_ratio=round(decision.target_language_ratio, 3),
            quarantine_reason=decision.quarantine_reason,
        )
        primary_layout = _attach_language_metadata(
            layout=layout,
            decision=decision,
            fallback_used=False,
        )
        return PrimaryLanguageLayoutResult(
            decision=decision,
            primary_layout=primary_layout,
            raw_layout=layout,
            should_quarantine=True,
        )

    # ── ВЕТВЬ 2: МОНОЛИНГВАЛЬНЫЙ ───────────────────────────────────────────
    if not decision.is_multilingual:
        logger.info(
            "Primary layout: monolingual document, applying simple language filter",
            deal_id=str(deal_id),
            tenant_id=tenant_id,
            document_id=document_id,
            target_language=target_language,
            detected_languages=decision.detected_languages,
            target_language_ratio=round(decision.target_language_ratio, 3),
        )

        filter_context = {
            "deal_id": str(deal_id),
            "tenant_id": tenant_id,
            "document_id": document_id,
            "is_multilingual": False,
            "is_bilingual": False,   # backward compat для filter
        }

        primary_layout = filter_layout_to_language(
            layout,
            target_language,
            context=filter_context,
        )

        if not (primary_layout.get("elements") or []):
            logger.warning(
                "Primary layout is empty after simple filter for monolingual document, "
                "falling back to raw layout",
                deal_id=str(deal_id),
                tenant_id=tenant_id,
                document_id=document_id,
                target_language=target_language,
                detected_languages=decision.detected_languages,
            )

            primary_layout = _build_raw_layout_filter_fallback(
                layout=layout,
                decision=decision,
                degraded_reason="empty_layout_after_simple_filter_fallback_to_raw_layout",
            )
            return PrimaryLanguageLayoutResult(
                decision=decision,
                primary_layout=primary_layout,
                raw_layout=layout,
                should_quarantine=False,
            )

        primary_layout = _attach_language_metadata(
            layout=primary_layout,
            decision=decision,
            fallback_used=False,
        )
        return PrimaryLanguageLayoutResult(
            decision=decision,
            primary_layout=primary_layout,
            raw_layout=layout,
            should_quarantine=False,
        )

    # ── ВЕТВЬ 3: MULTILINGUAL ─────────────────────────────────────────────
    logger.info(
        "Primary layout: multilingual document, applying language filter",
        deal_id=str(deal_id),
        tenant_id=tenant_id,
        document_id=document_id,
        target_language=target_language,
        detected_languages=decision.detected_languages,
        language_ratios={
            k: round(v, 3) for k, v in decision.language_ratios.items()
        },
        target_language_ratio=round(decision.target_language_ratio, 3),
    )

    filter_context = {
        "deal_id": str(deal_id),
        "tenant_id": tenant_id,
        "document_id": document_id,
        "is_multilingual": True,
        "is_bilingual": True,    # backward compat для filter
    }

    primary_layout = filter_layout_to_language(
        layout,
        target_language,
        context=filter_context,
    )

    if not (primary_layout.get("elements") or []):
        logger.warning(
            "Primary layout is empty after language filtering, quarantining document",
            deal_id=str(deal_id),
            tenant_id=tenant_id,
            document_id=document_id,
            target_language=target_language,
            detected_languages=decision.detected_languages,
        )
        decision.quarantine_reason = "filter_returned_empty_layout"
        primary_layout = _attach_language_metadata(
            layout=layout,
            decision=decision,
            fallback_used=False,
        )
        return PrimaryLanguageLayoutResult(
            decision=decision,
            primary_layout=primary_layout,
            raw_layout=layout,
            should_quarantine=True,
        )

    primary_layout = _attach_language_metadata(
        layout=primary_layout,
        decision=decision,
        fallback_used=False,
    )
    return PrimaryLanguageLayoutResult(
        decision=decision,
        primary_layout=primary_layout,
        raw_layout=layout,
        should_quarantine=False,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Вспомогательные функции — MULTILINGUAL
# ─────────────────────────────────────────────────────────────────────────────


def _measure_language_presence(
    layout: dict[str, Any],
    target_language: str,
    detected_languages: list[str],
) -> dict:
    """
    Измерить долю каждого языка в тексте layout.

    MULTILINGUAL версия (Фаза 2A):
    - использует LanguageDetector для точного определения языка каждого элемента
    - считает соотношение по реальным языкам, не только кириллица/латиница
    - работает с арабским, французским, казахским и любыми другими языками
    - pure structured data (IBAN, SWIFT, email) не влияет на языковой баланс

    Возвращает словарь:
    - target_ratio:   доля символов целевого языка (0.0–1.0)
    - language_ratios: {lang_code → ratio} для всех найденных языков
    - is_multilingual: True если 2+ языка имеют долю >= MIN_SECONDARY_LANGUAGE_RATIO

    Для непрофессионального программиста:
    - раньше функция считала только кириллицу и латиницу
    - теперь она определяет реальный язык каждого элемента через lingua
    - например для арабско-английского документа вернёт
      {"ar": 0.47, "en": 0.49, "unknown": 0.04}
    """
    from services.layout_language_filter import _classify_structured_data
    from services.language_detector import get_language_detector

    detector = get_language_detector()
    elements = layout.get("elements") or []

    # Считаем символы по языкам
    lang_char_counts: dict[str, int] = {}
    total_chars = 0

    for el in elements:
        text = el.get("text", "")
        if not text.strip():
            continue

        # Pure structured data не влияет на языковой баланс
        if _classify_structured_data(text) == "pure":
            continue

        # Определяем язык элемента
        lang_result = detector.detect_language(text)
        lang_code = lang_result.language_code

        # Пропускаем нейтральный контент
        if lang_result.script_code == "other":
            continue

        # Для ненадёжных результатов используем "unknown"
        if not _is_detection_reliable_local(lang_code, lang_result.confidence):
            lang_code = "unknown"

        # Считаем символы (без пробелов) как вес элемента
        char_count = len(text.replace(" ", "").strip())
        if char_count > 0:
            lang_char_counts[lang_code] = lang_char_counts.get(lang_code, 0) + char_count
            total_chars += char_count

    if total_chars == 0:
        return {
            "target_ratio": 0.0,
            "language_ratios": {},
            "is_multilingual": False,
        }

    # Вычисляем доли
    language_ratios: dict[str, float] = {
        lang: count / total_chars
        for lang, count in lang_char_counts.items()
        if lang != "unknown"  # unknown не показываем в ratios
    }

    # Нормализуем если сумма не равна 1.0 (из-за исключения unknown)
    ratio_sum = sum(language_ratios.values())
    if ratio_sum > 0 and abs(ratio_sum - 1.0) > 0.01:
        language_ratios = {
            lang: ratio / ratio_sum
            for lang, ratio in language_ratios.items()
        }

    # Доля целевого языка
    target_ratio = language_ratios.get(target_language, 0.0)

    # Документ считается multilingual если 2+ языка имеют значимую долю
    significant_langs = [
        lang for lang, ratio in language_ratios.items()
        if ratio >= MIN_SECONDARY_LANGUAGE_RATIO and lang != target_language
    ]
    is_multilingual = len(significant_langs) >= 1 and target_ratio >= MIN_SECONDARY_LANGUAGE_RATIO

    return {
        "target_ratio": target_ratio,
        "language_ratios": language_ratios,
        "is_multilingual": is_multilingual,
    }


def _is_detection_reliable_local(language_code: str, confidence: float) -> bool:
    """
    Локальная версия проверки надёжности detection.
    Дублирует логику из layout_language_filter чтобы избежать circular import.
    """
    if language_code == "unknown":
        return False
    try:
        from core.config import settings
        threshold = getattr(settings, "LANGUAGE_DETECTOR_CONFIDENCE_THRESHOLD", 0.50)
    except Exception:
        threshold = 0.50
    return confidence >= threshold


def _classify_language_route(
    detected: list[str],
    target: str,
    target_presence: dict,
) -> tuple[str, str | None]:
    """
    Определить маршрут документа: продолжить обработку или в карантин.

    MULTILINGUAL версия:
    - работает с любым ISO target_language
    - использует language_ratios из presence dict

    Возвращает кортеж (route, quarantine_reason):
    - ("proceed", None)                            — обработка продолжается
    - ("quarantine", "target_language_absent")     — язык не обнаружен
    - ("quarantine", "target_language_negligible") — язык есть, но доля мала

    Правила:
    1. Если target вообще не найден в detected → карантин (absent).
    2. Если target найден в detected, но его доля < MIN_TARGET_LANGUAGE_RATIO
       → карантин (negligible).
    3. Иначе → proceed.
    """
    ratio = target_presence.get("target_ratio", 0.0)

    if target not in detected:
        return "quarantine", "target_language_absent"

    if ratio < MIN_TARGET_LANGUAGE_RATIO:
        return "quarantine", "target_language_negligible"

    return "proceed", None


def _build_raw_layout_filter_fallback(
    *,
    layout: dict[str, Any],
    decision: DocumentLanguageDecision,
    degraded_reason: str,
) -> dict[str, Any]:
    """
    Безопасный fallback на исходный layout после неудачной monolingual filter.

    Используется только в ветке not decision.is_multilingual.
    Явно маркирует fallback и degraded_reason в metadata.
    """
    result = _attach_language_metadata(
        layout=layout,
        decision=decision,
        fallback_used=True,
    )

    metadata = dict(result.get("metadata") or {})
    language_filter = dict(metadata.get("language_filter") or {})

    language_filter["degraded"] = True
    previous_reason = language_filter.get("degraded_reason")
    if previous_reason:
        if degraded_reason not in str(previous_reason):
            language_filter["degraded_reason"] = f"{previous_reason};{degraded_reason}"
    else:
        language_filter["degraded_reason"] = degraded_reason

    language_filter.setdefault("structural_filter_used", False)
    language_filter.setdefault("multilingual_mode", False)

    metadata["language_filter"] = language_filter
    result["metadata"] = metadata
    return result


def _attach_language_metadata(
    layout: dict[str, Any],
    decision: DocumentLanguageDecision,
    fallback_used: bool,
) -> dict[str, Any]:
    """
    Добавить в metadata следы работы language pipeline.

    MULTILINGUAL версия: добавляет language_ratios и is_multilingual.
    Не меняет исходный layout — создаёт копию верхнего уровня.
    """
    result = dict(layout)
    metadata = dict(result.get("metadata") or {})

    language_pipeline = dict(metadata.get("language_pipeline") or {})
    language_pipeline.update(
        {
            "detected_languages": decision.detected_languages,
            "target_language": decision.target_language,
            "is_multilingual": decision.is_multilingual,
            "is_bilingual": decision.is_multilingual,  # backward compat
            "language_ratios": {
                k: round(v, 4) for k, v in decision.language_ratios.items()
            },
            "target_language_ratio": round(decision.target_language_ratio, 4),
            "route": decision.route,
            "quarantine_reason": decision.quarantine_reason,
            "fallback_used": fallback_used,
            "deal_primary_language_before": decision.deal_primary_language_before,
            "deal_languages_before": decision.deal_languages_before,
            "deal_primary_language_after": decision.deal_primary_language_after,
            "deal_languages_after": decision.deal_languages_after,
            "requires_user_selection": decision.requires_user_selection,
            "pipeline_mode": decision.pipeline_mode,
        }
    )
    metadata["language_pipeline"] = language_pipeline

    language_filter = dict(metadata.get("language_filter") or {})
    language_filter.update(
        {
            "contract_version": 2,           # обновлено с 1 до 2 (multilingual)
            "downstream_requires_primary_source": True,
            "target_language": decision.target_language,
            "is_multilingual": decision.is_multilingual,
            "is_bilingual": decision.is_multilingual,  # backward compat
            "requires_user_selection": decision.requires_user_selection,
            "quarantine_reason": decision.quarantine_reason,
            "fallback_used": fallback_used,
        }
    )
    metadata["language_filter"] = language_filter

    result["metadata"] = metadata
    return result


def _normalize_lang(value: str | None) -> str | None:
    """
    Нормализовать один ISO language code.

    MULTILINGUAL версия: принимает любой валидный ISO 639-1 или ISO 639-3 код.
    НЕ ограничивает список поддерживаемых языков.

    Валидация:
    - не пустой
    - только буквы (ISO коды содержат только буквы)
    - длина от 2 до 8 символов

    Для непрофессионального программиста:
    - раньше функция принимала только "ru" и "en"
    - теперь она принимает любой язык: "ar", "fr", "de", "kk", "uz", "he"...
    """
    if not value:
        return None
    lang = str(value).strip().lower()
    if not lang:
        return None

    # Базовая валидация ISO кода: только буквы, нормальная длина
    if not lang.isalpha():
        return None
    if len(lang) < _MIN_LANG_CODE_LEN or len(lang) > _MAX_LANG_CODE_LEN:
        return None

    return lang


def _normalize_lang_list(
    values: list[str] | tuple[str, ...] | set[str] | None,
) -> list[str]:
    """
    Нормализовать список ISO language codes.

    MULTILINGUAL версия: принимает любые валидные ISO коды, не только ru/en.

    - lower()
    - убрать пустые и невалидные
    - убрать дубли
    - отсортировать для предсказуемости
    """
    if not values:
        return []

    normalized: set[str] = set()
    for value in values:
        lang = _normalize_lang(value)
        if lang:
            normalized.add(lang)

    return sorted(normalized)

    
