# src/services/language_discovery_helpers.py

"""
Shared helpers for document-level language discovery workers.

Назначение:
- инкапсулировать повторяющийся паттерн «записать failed + пересчитать сделку»,
  который используется в нескольких воркерах language discovery pipeline;
- гарантировать вызов recompute_deal_language_discovery_state при любом исходе
  воркера — в том числе при permanent errors и неожиданных исключениях;
- предоставить безопасный wrapper для recompute в idempotent-replay ветках,
  где сбой recompute не должен маскировать основной результат.

Этот модуль используется:
- workers.detect_document_languages_native
- workers.detect_document_languages_ocr

Важно:
- Этот модуль не содержит бизнес-логики агрегации статусов — она живёт
  в services.deal_language_discovery_service.
- Этот модуль не содержит Celery-специфичного кода.
- Все функции async, принимают AsyncSession явно через keyword-only аргументы.
- Функции не пробрасывают исключения наружу — это намеренно: они вызываются
  из finally / permanent-error блоков, где важно не маскировать исходную ошибку.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import LanguageDiscoveryStatus
from core.logging import get_logger
from db.repositories.document_repo import DocumentRepository
from services.deal_language_discovery_service import (
    recompute_deal_language_discovery_state,
)

logger = get_logger(__name__)


async def mark_document_discovery_failed_and_recompute(
    *,
    db: AsyncSession,
    document_id: uuid.UUID,
    deal_id: uuid.UUID,
    reason: str,
    extra_log: dict[str, Any] | None = None,
) -> None:
    """
    Зафиксировать terminal failed-state document language discovery
    и пересчитать агрегированный статус сделки.

    Предназначен для вызова из permanent-error и finally-блоков воркеров.
    Гарантирует вызов recompute даже при сбое записи failed-статуса документа.

    Семантика:
    - Сначала пишет language_discovery_status=failed на документе.
      При сбое записи — логирует exception, продолжает выполнение.
    - Затем всегда вызывает recompute сделки.
      При сбое recompute — логирует exception, не пробрасывает.
    - Никогда не пробрасывает исключения наружу: вызывается из контекста,
      где уже есть исходная ошибка, которую нельзя подменить.

    Args:
        db: AsyncSession активной транзакции воркера.
        document_id: UUID документа, у которого фиксируется failed.
        deal_id: UUID сделки для пересчёта агрегированного статуса.
        reason: Машиночитаемая причина сбоя — только для structured log.
        extra_log: Дополнительные поля для structured log (опционально).
    """
    log_context: dict[str, Any] = {
        "document_id": str(document_id),
        "deal_id": str(deal_id),
        "reason": reason,
        **(extra_log or {}),
    }

    try:
        doc_repo = DocumentRepository(db)
        await doc_repo.update_language_discovery(
            document_id,
            detected_languages=None,
            status=LanguageDiscoveryStatus.FAILED,
        )
        logger.info(
            "Document language discovery marked as failed",
            extra=log_context,
        )
    except Exception:
        logger.exception(
            "Failed to persist document language_discovery_status=failed — "
            "proceeding to recompute deal state regardless",
            extra=log_context,
        )

    try:
        await recompute_deal_language_discovery_state(
            db=db,
            deal_id=deal_id,
        )
    except Exception:
        logger.exception(
            "Failed to recompute deal language discovery state "
            "after document failure — deal status may remain stale",
            extra={
                "deal_id": str(deal_id),
                "document_id": str(document_id),
                "reason": reason,
            },
        )


async def recompute_deal_discovery_or_log(
    *,
    db: AsyncSession,
    deal_id: uuid.UUID,
    context: str,
    extra_log: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Безопасный wrapper для recompute_deal_language_discovery_state.

    Используется в idempotent-replay ветках воркеров (already_completed,
    already_failed, claim_not_acquired), где recompute желателен, но его
    сбой не должен превращать успешный idempotent-ответ в ошибку.

    При сбое recompute логирует exception и возвращает пустой dict.
    Caller обязан обрабатывать пустой dict — не полагаться на ключи.

    Args:
        db: AsyncSession активной транзакции воркера.
        deal_id: UUID сделки для пересчёта.
        context: Строка-описание точки вызова — только для structured log.
        extra_log: Дополнительные поля для structured log (опционально).

    Returns:
        Словарь результата recompute (ключи: deal_id, languages,
        language_discovery_status, documents_total) или пустой dict при сбое.
    """
    log_context: dict[str, Any] = {
        "deal_id": str(deal_id),
        "context": context,
        **(extra_log or {}),
    }

    try:
        return await recompute_deal_language_discovery_state(
            db=db,
            deal_id=deal_id,
        )
    except Exception:
        logger.exception(
            "Failed to recompute deal language discovery state",
            extra=log_context,
        )
        return {}
    

    

