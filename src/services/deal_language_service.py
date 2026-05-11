# src/services/deal_language_service.py

"""
Сервис для обновления языков сделки (Deal.languages и primary_language).

Назначение:
- аккуратно добавлять новые языки в список Deal.languages
  после появления честной информации (например, после извлечения layout);
- не затирать уже сохранённые языки, а объединять их с новыми;
- по возможности автоматически выставлять primary_language, если это безопасно.

Production policy:
- Deal.languages обновляем по merge-модели: старые + новые, без дублей.
- Уже установленный primary_language НЕ перезаписываем автоматически.
- Автоматически выставляем primary_language только если он пустой.
- Нормализуем входные коды языков: trim + lower.
- По умолчанию оставляем только поддерживаемые языки документа ("ru", "en"),
  чтобы не тащить в сделку шумовые/случайные значения.

Важно:
- Этот сервис предназначен для системного фонового обновления языков сделки
  из результатов detection/layout pipeline.
- Явный выбор пользователя через API имеет приоритет и не должен
  перезаписываться автоматически этим сервисом.
"""

from __future__ import annotations

import uuid
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories.deal_repo import DealRepository

SUPPORTED_DOCUMENT_LANGUAGES = {"ru", "en"}


async def update_deal_languages(
    db: AsyncSession,
    deal_id: uuid.UUID,
    new_languages: Iterable[str],
) -> None:
    """
    Обновить Deal.languages и при необходимости скорректировать primary_language.

    Поведение:
    - читаем текущее состояние сделки;
    - нормализуем и объединяем existing + new языки;
    - сохраняем Deal.languages в предсказуемом порядке;
    - primary_language обновляем ТОЛЬКО если он пока пустой.

    Правила для primary_language:
    - если primary_language уже задан -> не меняем его автоматически;
    - если primary_language пустой и после merge ровно один язык ->
      делаем его primary_language;
    - если primary_language пустой и языков несколько:
        * если среди них нет "ru" -> ставим первый язык из отсортированного списка;
        * если среди них есть "ru" -> не выбираем автоматически, оставляем None,
          чтобы пользователь/бизнес-логика выбрали явно позже.
    - если сделка не найдена, функция просто выходит без ошибок.
    """
    repo = DealRepository(db)
    deal = await repo.get_by_id(deal_id)
    if not deal:
        return

    existing_languages = _normalize_lang_iterable(getattr(deal, "languages", None))
    current_primary = _normalize_lang(getattr(deal, "primary_language", None))
    incoming_languages = _normalize_lang_iterable(new_languages)

    merged_languages = sorted(existing_languages | incoming_languages)
    if not merged_languages:
        return

    new_primary = _select_primary_language(
        languages=merged_languages,
        current_primary=current_primary,
    )

    existing_languages_sorted = sorted(existing_languages)
    if (
        merged_languages == existing_languages_sorted
        and new_primary == current_primary
    ):
        return

    if merged_languages != existing_languages_sorted:
        await repo.update_languages(
            deal_id=deal_id,
            languages=merged_languages,
        )

    if new_primary != current_primary:
        await repo.update_primary_language(
            deal_id=deal_id,
            primary_language=new_primary,
        )


def _select_primary_language(
    languages: list[str],
    current_primary: str | None,
) -> str | None:
    """
    Вычислить новое значение primary_language.

    Ключевой принцип:
    - уже существующий primary_language сохраняем;
    - автоматический выбор делаем только когда primary_language пустой.
    """
    if current_primary:
        return current_primary

    if not languages:
        return None

    if len(languages) == 1:
        return languages[0]

    has_ru = "ru" in languages
    if not has_ru:
        return languages[0]

    return None


def _normalize_lang(value: str | None) -> str | None:
    """
    Нормализовать один код языка:
    - trim
    - lower
    - оставить только поддерживаемые языки
    """
    if value is None:
        return None

    lang = str(value).strip().lower()
    if not lang:
        return None

    if lang not in SUPPORTED_DOCUMENT_LANGUAGES:
        return None

    return lang


def _normalize_lang_iterable(values: Iterable[str] | None) -> set[str]:
    """
    Нормализовать iterable языков:
    - trim/lower
    - убрать пустые
    - оставить только поддерживаемые
    - убрать дубли
    """
    if not values:
        return set()

    normalized: set[str] = set()
    for value in values:
        lang = _normalize_lang(value)
        if lang:
            normalized.add(lang)

    return normalized



