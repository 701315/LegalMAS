# src/services/deal_language_service.py

"""
Сервис для обновления языков сделки (Deal.languages и primary_language).

Назначение:
- аккуратно добавлять новые языки в список Deal.languages
  после появления честной информации (например, после извлечения layout);
- не затирать уже сохранённые языки, а объединять их с новыми;
- по возможности автоматически выставлять primary_language, если это безопасно.
"""

from __future__ import annotations

import uuid
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories.deal_repo import DealRepository


async def update_deal_languages(
    db: AsyncSession,
    deal_id: uuid.UUID,
    new_languages: Iterable[str],
) -> None:
    """
    Обновить Deal.languages и при необходимости скорректировать primary_language.

    Для непрофессионального программиста:
    - deal.languages предполагается списком строк, например ["ru", "en"].
    - Функция делает три шага:
      1) читает из БД текущие языки сделки и текущий primary_language;
      2) объединяет их с new_languages (без дублей);
      3) сохраняет обновлённый список и, если это безопасно, обновляет primary_language.

    Поведение для primary_language:
    - если после объединения в списке ровно один язык → делаем его primary_language;
    - если языков несколько:
        * если среди них есть "ru" → primary_language остаётся как есть
          (предполагаем, что юрист сам выберет в UI);
        * если "ru" нет и primary_language пока пустой → берём первый язык
          из отсортированного списка (например, "en").
    - если сделка не найдена, функция просто выйдет без ошибок.
    """
    repo = DealRepository(db)
    deal = await repo.get_by_id(deal_id)
    if not deal:
        return

    # 1. Текущее состояние
    existing_languages = set(deal.languages or [])
    current_primary = deal.primary_language

    # 2. Добавляем новые языки
    for lang in new_languages:
        if not lang:
            continue
        existing_languages.add(lang)

    if not existing_languages:
        # Вообще нет языков — ничего не меняем.
        return

    # Приводим к отсортированному списку для предсказуемого порядка.
    languages_sorted = sorted(existing_languages)

    # 3. Вычисляем новое значение primary_language (если нужно).
    new_primary: str | None = current_primary

    if len(languages_sorted) == 1:
        # Ровно один язык — его логично считать основным.
        new_primary = languages_sorted[0]
    else:
        # Несколько языков.
        has_ru = "ru" in languages_sorted

        if not has_ru and not current_primary:
            # Русского нет, явного primary ещё не было — ставим первым
            # встречным (по алфавиту) языком, например "en".
            new_primary = languages_sorted[0]
        # Если есть "ru" или уже задан current_primary — не трогаем,
        # пусть выбор делает юрист через UI.

    # 4. Сохраняем изменения в БД через репозиторий.
    await repo.update_languages(
        deal_id=deal_id,
        languages=languages_sorted,
    )

    # Обновляем primary_language только если мы его реально изменили.
    if new_primary != current_primary:
        await repo.update_primary_language(
            deal_id=deal_id,
            primary_language=new_primary,
        )