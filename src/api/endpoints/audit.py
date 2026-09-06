# src/api/endpoints/audit.py

"""
Endpoints for audit logging.

GET /api/v1/deals/{deal_id}/audit
    — Audit log for a deal, with filters and pagination.
    Used by the frontend AuditTab and useAuditLog hook.

POST /api/v1/audit-log
    — Create an audit log entry manually (used by the frontend
      via useCreateAuditLogEntry for client-side events).

Response contract strictly matches PaginatedResponse<AuditLogEntry>
from src/types/common.ts and src/types/exports.ts.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from core.config import settings
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.schemas.audit import AuditLogEntrySchema, AuditLogPage
from core.logging import get_logger
from db.repositories.audit_repo import AuditRepository
from db.session import get_db

logger = get_logger(__name__)

router = APIRouter(tags=["audit"])


# ---------------------------------------------------------------------------
# Tenant ID resolution helper
# ---------------------------------------------------------------------------


async def get_tenant_id(
    current_user: CurrentUser = Depends(get_current_user),
) -> str:
    """Retrieve tenant_id of current user from JWT token."""
    return str(current_user.tenant_id)


# ---------------------------------------------------------------------------
# GET /api/v1/deals/{deal_id}/audit
# ---------------------------------------------------------------------------


@router.get(
    "/deals/{deal_id}/audit",
    response_model=AuditLogPage,
    summary="Deal audit log records",
)
async def get_deal_audit_log(
    deal_id: uuid.UUID,
    # Pagination
    page: int = Query(1, ge=1, description="Page number, starting from 1"),
    per_page: int = Query(50, ge=1, le=200, description="Records per page"),
    # Filters - all optional
    action: str | None = Query(None, description="Filter by action type (exact match)"),
    actor: str | None = Query(None, description="Filter by user identifier (exact match)"),
    from_date: datetime | None = Query(None, description="Start date (ISO 8601)"),
    to_date: datetime | None = Query(None, description="End date (ISO 8601)"),
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
) -> AuditLogPage:
    """
    Returns a paginated list of audit log records for a deal.

    Used by frontend (AuditTab.tsx) for:
    - page / per_page pagination controls;
    - action filtering across tabs (Export, Import, QC, etc.);
    - actor / from_date / to_date extended filter capabilities.

    Strictly matches PaginatedResponse<AuditLogEntry>.
    """
    repo = AuditRepository(db)

    rows, total = await repo.get_page_by_deal(
        deal_id=deal_id,
        page=page,
        per_page=per_page,
        action=action or None,
        actor=actor or None,
        from_date=from_date,
        to_date=to_date,
    )

    items = [AuditLogEntrySchema.model_validate(row) for row in rows]

    logger.info(
        "Audit log page fetched",
        deal_id=str(deal_id),
        tenant_id=tenant_id,
        page=page,
        per_page=per_page,
        action=action,
        actor=actor,
        total=total,
        returned=len(items),
    )

    return AuditLogPage(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/audit-log
# ---------------------------------------------------------------------------


class AuditLogCreatePayload(BaseModel):
    """
    Request body for manual client-side audit entry creation.
    Used by the useCreateAuditLogEntry hook.
    """

    deal_id: uuid.UUID | None = None
    action: str
    details: dict = {}


@router.post(
    "/audit-log",
    response_model=AuditLogEntrySchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create audit log entry",
)
async def create_audit_log_entry(
    payload: AuditLogCreatePayload,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
) -> AuditLogEntrySchema:
    """
    Create an audit log record manually.

    Used by frontend clients to register sensitive UI events
    (e.g., viewing confidential evidence or sensitive findings).
    """
    repo = AuditRepository(db)

    entry = await repo.log(
        tenant_id=uuid.UUID(tenant_id),
        deal_id=payload.deal_id,
        action=payload.action,
        actor="frontend",
        actor_role="user",
        details=payload.details,
    )
    await db.commit()

    logger.info(
        "Audit log entry created from frontend",
        deal_id=str(payload.deal_id),
        action=payload.action,
    )

    return AuditLogEntrySchema.model_validate(entry)
