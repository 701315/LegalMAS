# src/core/tenant_resolver.py

"""
Canonical tenant resolution for workers and services.

Single source of truth для tenant_id при записи артефактов.

Заменяет оба дублирующихся модуля:
- src/workers/_tenant_resolver.py  (удалить после миграции импортов)
- src/services/_tenant_resolver.py (удалить после миграции импортов)

Resolution priority:
1. Deal.tenant_id из БД — всегда primary source.
   Deal.tenant_id NOT NULL, поэтому surrogate deal_id fallback не нужен.
2. payload_tenant_id — advisory fallback, логируется когда используется.

Surrogate deal_id как tenant_id удалён.

ВАЖНЫЙ КОНТРАКТ:
- функция возвращает canonical UUID string, а не uuid.UUID object;
- это безопасно для:
  * Celery kwargs / JSON payloads,
  * ArtifactPath / MinIO paths,
  * structured logs,
  * downstream-кода, который потом при необходимости сам делает uuid.UUID(...).
- такой контракт устраняет класс ошибок вида:
  AttributeError: 'asyncpg.pgproto.pgproto.UUID' object has no attribute 'replace'
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import PermanentError
from core.logging import get_logger
from db.repositories.deal_repo import DealRepository
from db.repositories.document_repo import DocumentRepository

logger = get_logger(__name__)

_ZERO_UUID = uuid.UUID(int=0)


def _parse_uuid_or_none(value: uuid.UUID | str | None) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _is_valid_tenant(value: uuid.UUID | None) -> bool:
    return value is not None and value != _ZERO_UUID


async def resolve_artifact_tenant_id(
    *,
    session: AsyncSession,
    deal_id: uuid.UUID | str | None = None,
    document_id: uuid.UUID | str | None = None,
    payload_tenant_id: uuid.UUID | str | None = None,
) -> str:
    """
    Canonical tenant_id resolver для записи артефактов.

    Returns:
        str — canonical UUID string (непустой валидный UUID).

    Raises:
        PermanentError — если tenant_id не удалось определить.
    """
    parsed_deal_id = _parse_uuid_or_none(deal_id)
    parsed_document_id = _parse_uuid_or_none(document_id)
    payload_tenant = _parse_uuid_or_none(payload_tenant_id)

    # Resolve deal_id через document если нужно
    if parsed_deal_id is None:
        if parsed_document_id is None:
            raise PermanentError(
                "resolve_artifact_tenant_id requires deal_id or document_id",
                details={
                    "deal_id": str(deal_id) if deal_id is not None else None,
                    "document_id": str(document_id) if document_id is not None else None,
                },
            )

        doc_repo = DocumentRepository(session)
        document = await doc_repo.get_by_id(parsed_document_id)
        if document is None:
            raise PermanentError(
                f"Document not found while resolving artifact tenant_id: {parsed_document_id}",
                details={"document_id": str(parsed_document_id)},
            )
        parsed_deal_id = _parse_uuid_or_none(getattr(document, "deal_id", None))
        if parsed_deal_id is None:
            raise PermanentError(
                f"Document {parsed_document_id} has no deal_id",
                details={"document_id": str(parsed_document_id)},
            )

    # Primary: Deal.tenant_id
    deal_repo = DealRepository(session)
    deal = await deal_repo.internal_unsafe_get_by_id(parsed_deal_id)
    deal_tenant = _parse_uuid_or_none(getattr(deal, "tenant_id", None) if deal else None)

    if _is_valid_tenant(deal_tenant):
        if _is_valid_tenant(payload_tenant) and payload_tenant != deal_tenant:
            logger.warning(
                "resolve_artifact_tenant_id: payload tenant_id differs from deal.tenant_id; "
                "using deal.tenant_id as canonical source",
                deal_id=str(parsed_deal_id),
                payload_tenant_id=str(payload_tenant),
                db_tenant_id=str(deal_tenant),
                document_id=str(parsed_document_id) if parsed_document_id else None,
            )
        return str(deal_tenant)

    # Advisory fallback: payload_tenant_id
    if _is_valid_tenant(payload_tenant):
        logger.warning(
            "resolve_artifact_tenant_id: deal.tenant_id is missing or zero; "
            "using payload_tenant_id — this indicates a data integrity issue",
            deal_id=str(parsed_deal_id),
            payload_tenant_id=str(payload_tenant),
            document_id=str(parsed_document_id) if parsed_document_id else None,
        )
        return str(payload_tenant)

    raise PermanentError(
        "resolve_artifact_tenant_id: cannot resolve tenant_id — "
        "deal.tenant_id is NULL/zero and payload_tenant_id is also absent",
        details={
            "deal_id": str(parsed_deal_id),
            "document_id": str(parsed_document_id) if parsed_document_id else None,
            "payload_tenant_id": str(payload_tenant_id) if payload_tenant_id is not None else None,
        },
    )


