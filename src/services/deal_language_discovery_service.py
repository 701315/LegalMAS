# src/services/deal_language_discovery_service.py

"""
Deal-level language discovery aggregation service.

Назначение:
- собрать union detected_languages по всем документам сделки;
- вычислить итоговый language_discovery_status сделки;
- сохранить агрегированный результат в Deal.

Агрегация статусов документов -> статус сделки:
- нет документов -> completed
- у всех документов статус отсутствует -> pending
- есть хотя бы один pending/processing -> processing
- есть документы без статуса и нет processing/pending -> pending
- есть completed и failed одновременно -> partial
- все известные статусы completed -> completed
- все известные статусы failed -> failed
- любые неизвестные статусы -> partial + warning
"""

from __future__ import annotations

import uuid
from collections import Counter
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


def _normalize_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized or None


def _normalize_status(value: Any) -> str | None:
    return _normalize_string(value)


def _extract_document_status(doc: Any) -> str | None:
    """
    Возвращает нормализованный статус language discovery для документа.

    Поддерживает оба имени поля:
    - language_discovery_status: актуальное имя
    - language_detection_status: legacy/fallback
    """
    raw_status = getattr(doc, "language_discovery_status", None)
    if raw_status is None:
        raw_status = getattr(doc, "language_detection_status", None)
    return _normalize_status(raw_status)


def _extract_document_languages(doc: Any) -> list[str]:
    raw_languages = getattr(doc, "detected_languages", None) or []
    normalized_languages: list[str] = []

    for lang in raw_languages:
        normalized = _normalize_string(lang)
        if normalized:
            normalized_languages.append(normalized)

    return normalized_languages


def _collect_languages_union(docs: Sequence[Any]) -> list[str]:
    union: set[str] = set()

    for doc in docs:
        union.update(_extract_document_languages(doc))

    return sorted(union)


def _compute_discovery_status(docs: Sequence[Any]) -> str:
    """
    Правила агрегации:
    - если документов нет -> completed;
    - если у всех документов статус отсутствует -> pending;
    - если есть хотя бы один pending/processing -> processing;
    - если есть документы без статуса и нет pending/processing -> pending;
    - если есть completed и failed одновременно -> partial;
    - если все известные статусы completed -> completed;
    - если все известные статусы failed -> failed;
    - если есть partial среди документов -> partial;
    - если встретились неизвестные статусы -> partial.
    """
    if not docs:
        return LANG_DISCOVERY_COMPLETED

    known_statuses: list[str] = []
    unknown_statuses: set[str] = set()
    missing_status_count = 0

    for doc in docs:
        status = _extract_document_status(doc)

        if status is None:
            missing_status_count += 1
            continue

        if status not in KNOWN_DISCOVERY_STATUSES:
            unknown_statuses.add(status)
            continue

        known_statuses.append(status)

    if unknown_statuses:
        logger.warning(
            "Unknown language discovery statuses encountered during deal recompute",
            extra={"unknown_statuses": sorted(unknown_statuses)},
        )
        return LANG_DISCOVERY_PARTIAL

    if not known_statuses:
        return LANG_DISCOVERY_PENDING

    if any(
        status in {LANG_DISCOVERY_PENDING, LANG_DISCOVERY_PROCESSING}
        for status in known_statuses
    ):
        return LANG_DISCOVERY_PROCESSING

    if LANG_DISCOVERY_PARTIAL in known_statuses:
        return LANG_DISCOVERY_PARTIAL

    if missing_status_count > 0:
        return LANG_DISCOVERY_PENDING

    status_counts = Counter(known_statuses)
    completed_count = status_counts[LANG_DISCOVERY_COMPLETED]
    failed_count = status_counts[LANG_DISCOVERY_FAILED]

    if completed_count > 0 and failed_count > 0:
        return LANG_DISCOVERY_PARTIAL

    if completed_count > 0 and failed_count == 0:
        return LANG_DISCOVERY_COMPLETED

    if failed_count > 0 and completed_count == 0:
        return LANG_DISCOVERY_FAILED

    logger.warning(
        "Unexpected language discovery status combination during deal recompute",
        extra={
            "status_counts": dict(status_counts),
            "missing_status_count": missing_status_count,
        },
    )
    return LANG_DISCOVERY_PARTIAL


def _build_documents_debug_snapshot(docs: Sequence[Any]) -> list[dict[str, object]]:
    snapshot: list[dict[str, object]] = []

    for doc in docs:
        snapshot.append(
            {
                "document_id": str(getattr(doc, "id", "")),
                "language_discovery_status": getattr(
                    doc, "language_discovery_status", None
                ),
                "language_detection_status": getattr(
                    doc, "language_detection_status", None
                ),
                "detected_languages": getattr(doc, "detected_languages", None) or [],
            }
        )

    return snapshot


async def recompute_deal_language_discovery_state(
    *,
    db: AsyncSession,
    deal_id: uuid.UUID,
) -> dict[str, object]:
    """
    Пересчитать агрегированные языки и discovery status сделки по документам сделки.

    Возвращает сериализуемый словарь с результатом пересчёта.
    """
    doc_repo = DocumentRepository(db)
    deal_repo = DealRepository(db)

    docs = await doc_repo.get_for_language_discovery(
        deal_id=deal_id,
        document_ids=None,
        include_statuses=None,
    )

    languages = _collect_languages_union(docs)
    discovery_status = _compute_discovery_status(docs)

    await deal_repo.set_languages_and_discovery_status(
        deal_id=deal_id,
        languages=languages,
        discovery_status=discovery_status,
    )

    logger.info(
        "Deal language discovery state recomputed",
        extra={
            "deal_id": str(deal_id),
            "languages": languages,
            "language_discovery_status": discovery_status,
            "documents_total": len(docs),
        },
    )

    logger.debug(
        "Deal language discovery documents snapshot",
        extra={
            "deal_id": str(deal_id),
            "documents": _build_documents_debug_snapshot(docs),
        },
    )

    return {
        "deal_id": str(deal_id),
        "languages": languages,
        "language_discovery_status": discovery_status,
        "documents_total": len(docs),
    }


