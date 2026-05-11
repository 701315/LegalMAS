# src/services/deal_language_discovery_service.py

"""
Deal-level language discovery aggregation service.

Назначение:
- собрать union detected_languages по всем документам сделки;
- вычислить итоговый language_discovery_status сделки;
- сохранить агрегированный результат в Deal.
"""

from __future__ import annotations

import uuid
from typing import Any, Final, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.repositories.deal_repo import DealRepository
from db.repositories.document_repo import DocumentRepository

logger = get_logger(__name__)

LANG_DISCOVERY_PENDING: Final[str] = "pending"
LANG_DISCOVERY_PROCESSING: Final[str] = "processing"
LANG_DISCOVERY_COMPLETED: Final[str] = "completed"
LANG_DISCOVERY_FAILED: Final[str] = "failed"
LANG_DISCOVERY_PARTIAL: Final[str] = "partial"

KNOWN_DISCOVERY_STATUSES: Final[set[str]] = {
    LANG_DISCOVERY_PENDING,
    LANG_DISCOVERY_PROCESSING,
    LANG_DISCOVERY_COMPLETED,
    LANG_DISCOVERY_FAILED,
    LANG_DISCOVERY_PARTIAL,
}


def _normalize_status(value: Any) -> str | None:
    if value is None or not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized or None


def _collect_languages_union(docs: Sequence[Any]) -> list[str]:
    union: set[str] = set()

    for doc in docs:
        langs = getattr(doc, "detected_languages", None) or []
        for lang in langs:
            if isinstance(lang, str):
                normalized = lang.strip().lower()
                if normalized:
                    union.add(normalized)

    return sorted(union)


def _compute_discovery_status(docs: Sequence[Any]) -> str:
    """
    Правила агрегации:
    - если документов нет -> completed (discovery нечего обрабатывать);
    - если у всех документов статус отсутствует -> pending;
    - если есть хотя бы один pending/processing -> processing;
    - если есть документы без статуса и нет processing -> pending;
    - если есть completed и failed одновременно -> partial;
    - если есть completed без failed и без missing statuses -> completed;
    - если только failed -> failed;
    - если встретились неизвестные статусы -> warning + partial.
    """
    if not docs:
        return LANG_DISCOVERY_COMPLETED

    statuses: list[str] = []
    unknown_statuses: set[str] = set()
    null_status_count = 0

    for doc in docs:
        status = _normalize_status(getattr(doc, "language_detection_status", None))
        if status is None:
            null_status_count += 1
            continue
        if status not in KNOWN_DISCOVERY_STATUSES:
            unknown_statuses.add(status)
            continue
        statuses.append(status)

    if unknown_statuses:
        logger.warning(
            "Unknown language discovery statuses encountered during deal recompute",
            extra={"unknown_statuses": sorted(unknown_statuses)},
        )
        return LANG_DISCOVERY_PARTIAL

    if not statuses:
        return LANG_DISCOVERY_PENDING

    if any(st in {LANG_DISCOVERY_PENDING, LANG_DISCOVERY_PROCESSING} for st in statuses):
        return LANG_DISCOVERY_PROCESSING

    if null_status_count > 0:
        return LANG_DISCOVERY_PENDING

    completed = sum(1 for st in statuses if st == LANG_DISCOVERY_COMPLETED)
    failed = sum(1 for st in statuses if st == LANG_DISCOVERY_FAILED)

    if completed > 0 and failed > 0:
        return LANG_DISCOVERY_PARTIAL
    if completed > 0:
        return LANG_DISCOVERY_COMPLETED
    if failed > 0:
        return LANG_DISCOVERY_FAILED

    return LANG_DISCOVERY_PARTIAL


async def recompute_deal_language_discovery_state(
    *,
    db: AsyncSession,
    deal_id: uuid.UUID,
) -> dict[str, object]:
    """
    Пересчитать языки сделки и итоговый discovery status по документам.
    """
    doc_repo = DocumentRepository(db)
    deal_repo = DealRepository(db)

    docs = await doc_repo.get_for_language_discovery(
        deal_id=deal_id,
        document_ids=None,
        include_statuses=None,
    )

    languages = _collect_languages_union(docs)
    status = _compute_discovery_status(docs)

    await deal_repo.set_languages_and_discovery_status(
        deal_id=deal_id,
        languages=languages,
        discovery_status=status,
    )

    logger.info(
        "Deal language discovery state recomputed",
        extra={
            "deal_id": str(deal_id),
            "languages": languages,
            "language_discovery_status": status,
            "documents_total": len(docs),
        },
    )

    return {
        "deal_id": str(deal_id),
        "languages": languages,
        "language_discovery_status": status,
        "documents_total": len(docs),
    }



