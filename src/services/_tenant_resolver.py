# src/services/_tenant_resolver.py

"""
Shared tenant resolution helpers for services-layer artifact writes.

Единый source of truth для tenant_id при записи артефактов из services layer:
1. Deal.tenant_id из БД, если валиден и не zero UUID;
2. payload_tenant_id, если валиден и не zero UUID;
3. deal_id как surrogate tenant fallback.

Важно:
- helper не использует ORM lazy-relationships вроде doc.deal;
- helper безопасен для async SQLAlchemy;
- services layer не должен импортировать worker-level helpers, поэтому
  этот модуль живёт отдельно в services.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import PermanentError
from core.logging import get_logger
from db.repositories.deal_repo import DealRepository
from db.repositories.document_repo import DocumentRepository

logger = get_logger(__name__)

ZERO_UUID = uuid.UUID(int=0)


def _parse_uuid_or_none(value: uuid.UUID | str | None) -> uuid.UUID | None:
    """Безопасно распарсить UUID из str/UUID; вернуть None для пустых/битых значений."""
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _is_non_zero_uuid(value: uuid.UUID | str | None) -> bool:
    """True только для валидного и ненулевого UUID."""
    parsed = _parse_uuid_or_none(value)
    return parsed is not None and parsed != ZERO_UUID


async def resolve_artifact_tenant_id(
    *,
    session: AsyncSession,
    deal_id: uuid.UUID | str | None = None,
    document_id: uuid.UUID | str | None = None,
    payload_tenant_id: uuid.UUID | str | None = None,
) -> str:
    """
    Единый helper для tenant_id при записи артефактов из services layer.

    Приоритет:
    1. Deal.tenant_id из БД, если валиден и не zero UUID
    2. payload_tenant_id, если валиден и не zero UUID
    3. deal_id как surrogate tenant fallback

    Если deal_id не передан, но передан document_id, helper сначала
    резолвит deal_id через DocumentRepository.
    """
    parsed_deal_id = _parse_uuid_or_none(deal_id)
    parsed_document_id = _parse_uuid_or_none(document_id)
    payload_tenant_uuid = _parse_uuid_or_none(payload_tenant_id)

    if parsed_deal_id is None:
        if parsed_document_id is None:
            raise PermanentError(
                "resolve_artifact_tenant_id requires deal_id or document_id",
                details={
                    "deal_id": str(deal_id) if deal_id is not None else None,
                    "document_id": str(document_id) if document_id is not None else None,
                    "payload_tenant_id": (
                        str(payload_tenant_id) if payload_tenant_id is not None else None
                    ),
                },
            )

        doc_repo = DocumentRepository(session)
        document = await doc_repo.get_by_id(parsed_document_id)
        if document is None:
            raise PermanentError(
                f"Document not found while resolving artifact tenant_id: {parsed_document_id}",
                details={
                    "document_id": str(parsed_document_id),
                    "payload_tenant_id": (
                        str(payload_tenant_id) if payload_tenant_id is not None else None
                    ),
                },
            )

        parsed_deal_id = _parse_uuid_or_none(getattr(document, "deal_id", None))
        if parsed_deal_id is None:
            raise PermanentError(
                f"Document {parsed_document_id} has no deal_id while resolving artifact tenant_id",
                details={
                    "document_id": str(parsed_document_id),
                    "payload_tenant_id": (
                        str(payload_tenant_id) if payload_tenant_id is not None else None
                    ),
                },
            )

    deal_repo = DealRepository(session)
    deal = await deal_repo.internal_unsafe_get_by_id(parsed_deal_id)
    deal_tenant_uuid = _parse_uuid_or_none(getattr(deal, "tenant_id", None) if deal else None)

    if _is_non_zero_uuid(deal_tenant_uuid):
        if (
            _is_non_zero_uuid(payload_tenant_uuid)
            and payload_tenant_uuid is not None
            and payload_tenant_uuid != deal_tenant_uuid
        ):
            logger.warning(
                "Payload tenant_id differs from DB tenant_id; DB value will be used for artifact writes",
                extra={
                    "document_id": str(parsed_document_id) if parsed_document_id else None,
                    "deal_id": str(parsed_deal_id),
                    "payload_tenant_id": str(payload_tenant_uuid),
                    "db_tenant_id": str(deal_tenant_uuid),
                },
            )
        return str(deal_tenant_uuid)

    if _is_non_zero_uuid(payload_tenant_uuid):
        logger.warning(
            "Using payload tenant_id for artifact writes because deal.tenant_id is missing or zero",
            extra={
                "document_id": str(parsed_document_id) if parsed_document_id else None,
                "deal_id": str(parsed_deal_id),
                "payload_tenant_id": str(payload_tenant_uuid),
                "db_tenant_id": str(deal_tenant_uuid) if deal_tenant_uuid else None,
            },
        )
        return str(payload_tenant_uuid)

    surrogate = str(parsed_deal_id)
    logger.warning(
        "tenant_id not resolvable from DB or payload, using deal_id as surrogate tenant",
        extra={
            "document_id": str(parsed_document_id) if parsed_document_id else None,
            "deal_id": surrogate,
            "payload_tenant_id": str(payload_tenant_uuid) if payload_tenant_uuid else None,
            "db_tenant_id": str(deal_tenant_uuid) if deal_tenant_uuid else None,
        },
    )
    return surrogate

    
