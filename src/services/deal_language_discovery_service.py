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
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import LanguageDiscoveryStatus
from core.logging import get_logger
from db.repositories.deal_repo import DealRepository
from db.repositories.document_repo import DocumentRepository

logger = get_logger(__name__)

# Множество всех валидных строковых значений статуса — для детекции unknown.
# Строится из enum один раз при импорте модуля.
_KNOWN_DISCOVERY_STATUS_VALUES: frozenset[str] = frozenset(
    s.value for s in LanguageDiscoveryStatus
)


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

    Каноническое поле: Document.language_discovery_status.
    """
    return _normalize_status(getattr(doc, "language_discovery_status", None))


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
        return LanguageDiscoveryStatus.COMPLETED

    known_statuses: list[str] = []
    unknown_statuses: set[str] = set()
    missing_status_count = 0

    for doc in docs:
        status = _extract_document_status(doc)

        if status is None:
            missing_status_count += 1
            continue

        if status not in _KNOWN_DISCOVERY_STATUS_VALUES:
            unknown_statuses.add(status)
            continue

        known_statuses.append(status)

    if unknown_statuses:
        logger.warning(
            "Unknown language discovery statuses encountered during deal recompute",
            extra={"unknown_statuses": sorted(unknown_statuses)},
        )
        return LanguageDiscoveryStatus.PARTIAL

    if not known_statuses:
        return LanguageDiscoveryStatus.PENDING

    if any(
        status in {LanguageDiscoveryStatus.PENDING, LanguageDiscoveryStatus.PROCESSING}
        for status in known_statuses
    ):
        return LanguageDiscoveryStatus.PROCESSING

    if LanguageDiscoveryStatus.PARTIAL in known_statuses:
        return LanguageDiscoveryStatus.PARTIAL

    if missing_status_count > 0:
        return LanguageDiscoveryStatus.PENDING

    status_counts = Counter(known_statuses)
    completed_count = status_counts[LanguageDiscoveryStatus.COMPLETED]
    failed_count = status_counts[LanguageDiscoveryStatus.FAILED]

    if completed_count > 0 and failed_count > 0:
        return LanguageDiscoveryStatus.PARTIAL

    if completed_count > 0 and failed_count == 0:
        return LanguageDiscoveryStatus.COMPLETED

    if failed_count > 0 and completed_count == 0:
        return LanguageDiscoveryStatus.FAILED

    logger.warning(
        "Unexpected language discovery status combination during deal recompute",
        extra={
            "status_counts": dict(status_counts),
            "missing_status_count": missing_status_count,
        },
    )
    return LanguageDiscoveryStatus.PARTIAL


def _build_documents_debug_snapshot(docs: Sequence[Any]) -> list[dict[str, object]]:
    snapshot: list[dict[str, object]] = []

    for doc in docs:
        snapshot.append(
            {
                "document_id": str(getattr(doc, "id", "")),
                "language_discovery_status": getattr(
                    doc, "language_discovery_status", None
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


