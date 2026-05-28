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

Дополнительный контракт для downstream:
- decision.pipeline_mode = "PRIMARY_ONLY_DOWNSTREAM"
- primary_layout.metadata.language_filter.contract_version = 1
- primary_layout.metadata.language_filter.downstream_requires_primary_source = True
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
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

SUPPORTED_DOCUMENT_LANGUAGES = ("ru", "en")

# Минимальная доля букв целевого языка в документе.
# Если доля ниже этого порога — документ уходит в карантин,
# так как целевой язык либо отсутствует, либо представлен лишь
# техническими вхождениями (реквизиты, email и т.п.).
MIN_TARGET_LANGUAGE_RATIO = 0.15


@dataclass
class DocumentLanguageDecision:
    """
    Результат языкового анализа документа.

    detected_languages:
    - какие языки реально найдены в layout документа.

    target_language:
    - язык, переданный снаружи (из Deal.primary_language).
      Это решение пользователя, сервис его не меняет.

    is_bilingual:
    - True, если документ содержит два языка, каждый из которых
      занимает >= MIN_TARGET_LANGUAGE_RATIO букв.

    target_language_ratio:
    - доля букв целевого языка в тексте документа (0.0–1.0).

    route:
    - "proceed"   — документ соответствует целевому языку, обработка продолжается.
    - "quarantine" — целевой язык отсутствует или слишком мал по доле.

    quarantine_reason:
    - причина карантина (None если route == "proceed"):
      "target_language_absent"    — язык вообще не обнаружен в документе;
      "target_language_negligible" — язык найден, но доля < MIN_TARGET_LANGUAGE_RATIO.

    deal_primary_language_before / after:
    - primary_language сделки до и после update_deal_languages.

    deal_languages_before / after:
    - список языков сделки до и после update_deal_languages.

    pipeline_mode:
    - режим пайплайна для downstream.
      "PRIMARY_ONLY_DOWNSTREAM" — все последующие стадии работают
      только с primary_source_ref / primary layout.

    requires_user_selection:
    - всегда False в новой логике (язык уже выбран пользователем до запуска).
      Поле сохранено для обратной совместимости с metadata downstream.
    """

    detected_languages: list[str]
    target_language: str
    is_bilingual: bool
    target_language_ratio: float
    route: str  # "proceed" | "quarantine"
    quarantine_reason: str | None
    deal_primary_language_before: str | None
    deal_languages_before: list[str]
    deal_primary_language_after: str | None
    deal_languages_after: list[str]
    requires_user_selection: bool = False  # всегда False в новой логике
    pipeline_mode: str = "PRIMARY_ONLY_DOWNSTREAM"


@dataclass
class PrimaryLanguageLayoutResult:
    """
    Итог работы pipeline.

    decision:
    - решение по языкам документа.

    primary_layout:
    - layout, отфильтрованный до одного языка (если билингвальный),
      либо исходный layout с проставленной metadata (если одноязычный).

    raw_layout:
    - исходный layout, который пришёл в сервис.

    should_quarantine:
    - True, если worker должен перевести документ в статус QUARANTINE
      и остановить дальнейшую обработку.
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

    Параметры:
    - target_language: язык, выбранный пользователем (из Deal.primary_language).
      Передаётся обязательно — пайплайн не запускается без выбранного языка.

    Возвращает DocumentLanguageDecision с route="proceed" или route="quarantine".
    """
    deal_repo = DealRepository(db)
    deal_before = await deal_repo.get_by_id(deal_id)

    deal_primary_before = _normalize_lang(
        getattr(deal_before, "primary_language", None) if deal_before else None
    )
    deal_languages_before = _normalize_lang_list(
        getattr(deal_before, "languages", None) if deal_before else []
    )

    # Определяем языки документа по layout
    detected_languages = _normalize_lang_list(detect_languages_in_layout(layout))
    if not detected_languages:
        detected_languages = ["ru"]

    # Обновляем языки сделки на основе найденных в документе
    await update_deal_languages(
        db=db,
        deal_id=deal_id,
        new_languages=detected_languages,
    )

    deal_after = await deal_repo.get_by_id(deal_id)
    deal_primary_after = _normalize_lang(
        getattr(deal_after, "primary_language", None) if deal_after else None
    )
    deal_languages_after = _normalize_lang_list(
        getattr(deal_after, "languages", None) if deal_after else []
    )

    # Измеряем реальное соотношение скриптов в тексте layout
    presence = _measure_language_presence(layout, target_language)

    # Определяем маршрут: карантин или продолжение
    route, quarantine_reason = _classify_language_route(
        detected=detected_languages,
        target=target_language,
        target_presence=presence,
    )

    decision = DocumentLanguageDecision(
        detected_languages=detected_languages,
        target_language=target_language,
        is_bilingual=presence["is_bilingual"],
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
        is_bilingual=decision.is_bilingual,
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

    ВАЖНО: target_language обязателен. Пайплайн не должен вызываться
    без установленного Deal.primary_language.

    Три ветви обработки:

    1. КАРАНТИН: целевой язык отсутствует или < MIN_TARGET_LANGUAGE_RATIO.
       should_quarantine=True. Worker переводит документ в QUARANTINE.

    2. МОНОЛИНГВАЛЬНЫЙ: документ содержит только целевой язык
       (или второй язык занимает < MIN_TARGET_LANGUAGE_RATIO).
       Фильтр НЕ применяется — иначе потеряем реквизиты, email, банковские счета.
       should_quarantine=False.

    3. БИЛИНГВАЛЬНЫЙ: оба языка присутствуют значимо (>= MIN_TARGET_LANGUAGE_RATIO).
       Применяем filter_layout_to_language по целевому языку.
       should_quarantine=False.

    Дополнительный контракт:
    - primary_layout.metadata.language_filter содержит:
        * contract_version = 1
        * downstream_requires_primary_source = True
        * target_language, is_bilingual, quarantine_reason, fallback_used.
    """
    decision = await analyze_document_languages(
        db=db,
        deal_id=deal_id,
        layout=layout,
        target_language=target_language,
    )

    # ── ВЕТВЬ 1: КАРАНТИН ─────────────────────────────────────────────────
    # Целевой язык отсутствует или слишком мал — документ не подходит
    # для анализа по выбранному пользователем языку.
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
    # Документ содержит только целевой язык — фильтрация не нужна.
    # Применение фильтра уничтожило бы реквизиты, email и прочие
    # строки с латиницей в русском документе.
    if not decision.is_bilingual:
        logger.info(
            "Primary layout: monolingual document, language filter skipped",
            deal_id=str(deal_id),
            tenant_id=tenant_id,
            document_id=document_id,
            target_language=target_language,
            detected_languages=decision.detected_languages,
            target_language_ratio=round(decision.target_language_ratio, 3),
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
            should_quarantine=False,
        )

    # ── ВЕТВЬ 3: БИЛИНГВАЛЬНЫЙ ────────────────────────────────────────────
    # Документ содержит два языка с значимой долей каждого.
    # Фильтруем layout — оставляем только блоки на целевом языке.
    logger.info(
        "Primary layout: bilingual document, applying language filter",
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
        "is_bilingual": decision.is_bilingual,
    }

    primary_layout = filter_layout_to_language(
        layout,
        target_language,
        context=filter_context,
    )

    # Если фильтр вернул пустой layout — безопаснее карантин, не fallback.
    # Fallback (возврат исходного layout) опасен: он смешивает языки
    # и downstream получает неконсистентный контент.
    if not (primary_layout.get("elements") or []):
        logger.warning(
            "Primary layout is empty after language filtering, quarantining document",
            deal_id=str(deal_id),
            tenant_id=tenant_id,
            document_id=document_id,
            target_language=target_language,
            detected_languages=decision.detected_languages,
        )
        # Обновляем quarantine_reason — причина стала известна после фильтрации
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
# Вспомогательные функции
# ─────────────────────────────────────────────────────────────────────────────


def _measure_language_presence(
    layout: dict[str, Any],
    target_language: str,
) -> dict:
    """
    Измерить долю целевого языка в тексте layout.

    Считаем буквы кириллицы и латиницы по всем элементам layout.
    Возвращает словарь с метриками:
    - target_ratio: доля букв целевого языка (0.0–1.0);
    - cyr_ratio:    доля кириллицы;
    - lat_ratio:    доля латиницы;
    - is_bilingual: True если оба скрипта >= MIN_TARGET_LANGUAGE_RATIO.
    """
    all_text = " ".join(el.get("text", "") for el in (layout.get("elements") or []))

    cyr = sum(1 for c in all_text if "\u0400" <= c <= "\u04ff")
    lat = sum(1 for c in all_text if "a" <= c.lower() <= "z")
    total = cyr + lat

    if total == 0:
        # Документ не содержит текста — считаем соотношение неопределённым.
        # Для целей карантина возвращаем ratio=0.0 для любого языка.
        return {
            "target_ratio": 0.0,
            "cyr_ratio": 0.0,
            "lat_ratio": 0.0,
            "is_bilingual": False,
        }

    cyr_ratio = cyr / total
    lat_ratio = lat / total

    # Определяем долю целевого языка по его скриптовой системе письма
    if target_language == "ru":
        target_ratio = cyr_ratio
    else:
        # "en" и любой другой поддерживаемый язык с латиницей
        target_ratio = lat_ratio

    is_bilingual = cyr_ratio >= MIN_TARGET_LANGUAGE_RATIO and lat_ratio >= MIN_TARGET_LANGUAGE_RATIO

    return {
        "target_ratio": target_ratio,
        "cyr_ratio": cyr_ratio,
        "lat_ratio": lat_ratio,
        "is_bilingual": is_bilingual,
    }


def _classify_language_route(
    detected: list[str],
    target: str,
    target_presence: dict,
) -> tuple[str, str | None]:
    """
    Определить маршрут документа: продолжить обработку или в карантин.

    Возвращает кортеж (route, quarantine_reason):
    - ("proceed", None)                          — обработка продолжается;
    - ("quarantine", "target_language_absent")   — язык не обнаружен совсем;
    - ("quarantine", "target_language_negligible") — язык есть, но доля мала.

    Правила:
    1. Если target вообще не найден в detected — карантин (absent).
    2. Если target найден в detected, но его реальная доля букв
       < MIN_TARGET_LANGUAGE_RATIO — карантин (negligible).
       Это отсекает документы где "en" попало в detected из-за email/реквизитов,
       хотя весь содержательный текст на русском.
    3. Иначе — proceed.
    """
    ratio = target_presence["target_ratio"]

    if target not in detected:
        return "quarantine", "target_language_absent"

    if ratio < MIN_TARGET_LANGUAGE_RATIO:
        return "quarantine", "target_language_negligible"

    return "proceed", None


def _attach_language_metadata(
    layout: dict[str, Any],
    decision: DocumentLanguageDecision,
    fallback_used: bool,
) -> dict[str, Any]:
    """
    Добавить в metadata следы работы language pipeline + формальный контракт
    для downstream в language_filter.

    Эта функция не меняет исходный layout — создаёт копию верхнего уровня.
    """
    result = dict(layout)
    metadata = dict(result.get("metadata") or {})

    language_pipeline = dict(metadata.get("language_pipeline") or {})
    language_pipeline.update(
        {
            "detected_languages": decision.detected_languages,
            "target_language": decision.target_language,
            "is_bilingual": decision.is_bilingual,
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
            "contract_version": 1,
            "downstream_requires_primary_source": True,
            "target_language": decision.target_language,
            "is_bilingual": decision.is_bilingual,
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
    Нормализовать один код языка.
    Оставляем только поддерживаемые языки.
    """
    if not value:
        return None
    lang = str(value).strip().lower()
    if not lang:
        return None
    if lang not in SUPPORTED_DOCUMENT_LANGUAGES:
        return None
    return lang


def _normalize_lang_list(
    values: list[str] | tuple[str, ...] | set[str] | None,
) -> list[str]:
    """
    Нормализовать список языков:
    - lower();
    - убрать пустые;
    - оставить только поддерживаемые;
    - убрать дубли;
    - отсортировать для предсказуемости.
    """
    if not values:
        return []

    normalized: set[str] = set()
    for value in values:
        lang = _normalize_lang(value)
        if lang:
            normalized.add(lang)

    return sorted(normalized)
