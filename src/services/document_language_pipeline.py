# src/services/document_language_pipeline.py

"""
Document language pipeline service.

Назначение:
- определить фактические языки документа по layout;
- обновить Deal.languages;
- определить, можно ли выбрать основной язык автоматически,
  либо требуется выбор пользователя;
- (при наличии target_language) построить одноязычный layout
  на основе исходного layout.

ВАЖНО:
- этот сервис НЕ читает PDF из MinIO;
- этот сервис НЕ сохраняет ничего в БД кроме языков сделки;
- этот сервис НЕ строит PDF-файл;
- этот сервис работает только с layout-структурой и данными сделки.

То есть это чистый слой бизнес-логики для этапа:
build_primary_language_source -> language analysis -> primary layout -> PDF builder.

Дополнительный контракт для downstream:
- decision.pipeline_mode = "PRIMARY_ONLY_DOWNSTREAM"
  (показывает, что downstream обязан работать только по primary_source_ref /
   производным от него layout’ам).
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


@dataclass
class DocumentLanguageDecision:
    """
    Результат языкового анализа документа.

    detected_languages:
    - какие языки реально найдены в layout документа.

    target_language:
    - какой язык выбран как основной для дальнейшей обработки.
      Может быть None, если требуется выбор пользователя.

    is_bilingual:
    - True, если найдено 2 и более поддерживаемых языка.

    deal_primary_language_before:
    - primary_language сделки до обновления / выбора.

    deal_languages_before:
    - список языков сделки до обновления.

    deal_primary_language_after:
    - primary_language сделки после update_deal_languages + повторного чтения сделки.

    deal_languages_after:
    - список языков сделки после update_deal_languages + повторного чтения сделки.

    requires_user_selection:
    - True, если документ многоязычный и нельзя безопасно выбрать язык автоматически
      без явного решения пользователя.

    pipeline_mode:
    - режим пайплайна для downstream.
      "PRIMARY_ONLY_DOWNSTREAM" означает, что все последующие стадии обязаны
      работать только с primary_source_ref / primary layout.
    """

    detected_languages: list[str]
    target_language: str | None
    is_bilingual: bool
    deal_primary_language_before: str | None
    deal_languages_before: list[str]
    deal_primary_language_after: str | None
    deal_languages_after: list[str]
    requires_user_selection: bool
    pipeline_mode: str = "PRIMARY_ONLY_DOWNSTREAM"


@dataclass
class PrimaryLanguageLayoutResult:
    """
    Итог работы pipeline.

    decision:
    - решение по языкам документа.

    primary_layout:
    - layout, отфильтрованный до одного языка (если target_language есть),
      либо исходный layout с проставленной metadata, если язык не выбран.

    raw_layout:
    - исходный layout, который пришёл в сервис.
    """

    decision: DocumentLanguageDecision
    primary_layout: dict[str, Any]
    raw_layout: dict[str, Any]


async def analyze_document_languages(
    db: AsyncSession,
    deal_id: uuid.UUID,
    layout: dict[str, Any],
) -> DocumentLanguageDecision:
    """
    Определить языки документа, обновить языки сделки и принять решение,
    можно ли выбрать target_language автоматически либо требуется выбор пользователя.

    Логика:

    1. Определяем detected_languages по layout.
       Если детект не вернул ничего — считаем ["ru"] как conservative fallback.

    2. Обновляем Deal.languages через update_deal_languages.

    3. Решаем, есть ли безопасный target_language:

       - Если документ одноязычный (len(detected_languages) == 1),
         target_language = detected[0], requires_user_selection = False.

       - Если документ многоязычный (>= 2 языка):
         * Если у сделки уже есть primary_language, и он найден в detected_languages:
             target_language = deal.primary_language,
             requires_user_selection = False
         * Иначе:
             target_language = None,
             requires_user_selection = True.

    4. Если вообще ничего не найдено (pathological case),
       detected_languages уже приведён к ["ru"], target_language = "ru",
       requires_user_selection = False.
    """
    deal_repo = DealRepository(db)
    deal_before = await deal_repo.get_by_id(deal_id)

    deal_primary_before = _normalize_lang(
        getattr(deal_before, "primary_language", None) if deal_before else None
    )
    deal_languages_before = _normalize_lang_list(
        getattr(deal_before, "languages", None) if deal_before else []
    )

    detected_languages = _normalize_lang_list(detect_languages_in_layout(layout))
    if not detected_languages:
        detected_languages = ["ru"]

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

    target_language, requires_user_selection = _select_target_language(
        detected_languages=detected_languages,
        deal_primary_language=deal_primary_after or deal_primary_before,
    )

    decision = DocumentLanguageDecision(
        detected_languages=detected_languages,
        target_language=target_language,
        is_bilingual=len(detected_languages) >= 2,
        deal_primary_language_before=deal_primary_before,
        deal_languages_before=deal_languages_before,
        deal_primary_language_after=deal_primary_after,
        deal_languages_after=deal_languages_after,
        requires_user_selection=requires_user_selection,
        pipeline_mode="PRIMARY_ONLY_DOWNSTREAM",
    )

    logger.info(
        "Document language analysis complete",
        deal_id=str(deal_id),
        detected_languages=decision.detected_languages,
        target_language=decision.target_language,
        is_bilingual=decision.is_bilingual,
        deal_primary_language_before=decision.deal_primary_language_before,
        deal_languages_before=decision.deal_languages_before,
        deal_primary_language_after=decision.deal_primary_language_after,
        deal_languages_after=decision.deal_languages_after,
        requires_user_selection=decision.requires_user_selection,
        pipeline_mode=decision.pipeline_mode,
    )

    return decision


async def build_primary_language_layout(
    db: AsyncSession,
    deal_id: uuid.UUID,
    tenant_id: str,
    document_id: str,
    layout: dict[str, Any],
) -> PrimaryLanguageLayoutResult:
    """
    Построить одноязычный layout для документа.

    Делает три вещи:
    1. определяет языки документа;
    2. обновляет языки сделки;
    3. если target_language определён — фильтрует layout до одного языка.

    Дополнительный контракт:
    - primary_layout.metadata.language_filter содержит:
        * contract_version = 1
        * downstream_requires_primary_source = True
        * target_language, is_bilingual, requires_user_selection, fallback_used.
    """
    decision = await analyze_document_languages(
        db=db,
        deal_id=deal_id,
        layout=layout,
    )

    if decision.target_language is None and decision.requires_user_selection:
        logger.info(
            "Primary layout not built: user primary language selection required",
            deal_id=str(deal_id),
            tenant_id=tenant_id,
            document_id=document_id,
            detected_languages=decision.detected_languages,
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
        )

    filter_context = {
        "deal_id": str(deal_id),
        "tenant_id": tenant_id,
        "document_id": document_id,
        "is_bilingual": decision.is_bilingual,
    }

    primary_layout = filter_layout_to_language(
        layout,
        decision.target_language,
        context=filter_context,
    )

    if not (primary_layout.get("elements") or []):
        logger.warning(
            "Primary layout is empty after language filtering, using raw layout fallback",
            deal_id=str(deal_id),
            document_id=document_id,
            target_language=decision.target_language,
            detected_languages=decision.detected_languages,
        )
        primary_layout = _attach_language_metadata(
            layout=layout,
            decision=decision,
            fallback_used=True,
        )
    else:
        primary_layout = _attach_language_metadata(
            layout=primary_layout,
            decision=decision,
            fallback_used=False,
        )

    return PrimaryLanguageLayoutResult(
        decision=decision,
        primary_layout=primary_layout,
        raw_layout=layout,
    )


def _select_target_language(
    detected_languages: list[str],
    deal_primary_language: str | None,
) -> tuple[str | None, bool]:
    """
    Решить, можно ли безопасно выбрать target_language автоматически.

    Правила:

    - Если detected_languages пустой:
        target_language = "ru", requires_user_selection = False.

    - Если документ одноязычный (len(detected) == 1):
        target_language = detected[0], requires_user_selection = False.

    - Если документ многоязычный (len(detected) >= 2):
        * если deal_primary_language задан и входит в detected:
            target_language = deal_primary_language,
            requires_user_selection = False;
        * иначе:
            target_language = None,
            requires_user_selection = True.
    """
    detected = _normalize_lang_list(detected_languages)
    deal_primary = _normalize_lang(deal_primary_language)

    if not detected:
        return "ru", False

    if len(detected) == 1:
        return detected[0], False

    if deal_primary and deal_primary in detected:
        return deal_primary, False

    return None, True


def _attach_language_metadata(
    layout: dict[str, Any],
    decision: DocumentLanguageDecision,
    fallback_used: bool,
) -> dict[str, Any]:
    """
    Добавить в metadata следы работы language pipeline + формальный контракт
    для downstream в language_filter.
    """
    result = dict(layout)
    metadata = dict(result.get("metadata") or {})

    language_pipeline = dict(metadata.get("language_pipeline") or {})
    language_pipeline.update(
        {
            "detected_languages": decision.detected_languages,
            "target_language": decision.target_language,
            "is_bilingual": decision.is_bilingual,
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

