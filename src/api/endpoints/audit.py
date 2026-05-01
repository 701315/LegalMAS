# src/api/endpoints/audit.py

"""
Endpoints для журнала аудита.

GET /api/v1/deals/{deal_id}/audit
    — журнал аудита по сделке, с фильтрами и пагинацией.
    Используется фронтовым AuditTab и хуком useAuditLog.

POST /api/v1/audit-log
    — создать запись аудита вручную (используется фронтом
      через useCreateAuditLogEntry для клиентских событий).

Контракт ответа строго соответствует PaginatedResponse<AuditLogEntry>
из src/types/common.ts и src/types/exports.ts.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.audit import AuditLogEntrySchema, AuditLogPage
from core.logging import get_logger
from db.repositories.audit_repo import AuditRepository
from db.session import get_db

logger = get_logger(__name__)

router = APIRouter(tags=["audit"])


# ---------------------------------------------------------------------------
# Временная заглушка tenant_id — потом заменить на чтение из токена
# ---------------------------------------------------------------------------

async def get_tenant_id() -> str:
    """Временная заглушка. Позже — из JWT-токена или middleware."""
    return "default"


# ---------------------------------------------------------------------------
# GET /api/v1/deals/{deal_id}/audit
# ---------------------------------------------------------------------------

@router.get(
    "/deals/{deal_id}/audit",
    response_model=AuditLogPage,
    summary="Журнал аудита по сделке",
)
async def get_deal_audit_log(
    deal_id: uuid.UUID,
    # Пагинация
    page: int = Query(1, ge=1, description="Номер страницы, начиная с 1"),
    per_page: int = Query(50, ge=1, le=200, description="Записей на страницу"),
    # Фильтры — все необязательные
    action: Optional[str] = Query(None, description="Фильтр по типу действия (точное совпадение)"),
    actor: Optional[str] = Query(None, description="Фильтр по пользователю (точное совпадение)"),
    from_date: Optional[datetime] = Query(None, description="Начало диапазона (ISO 8601)"),
    to_date: Optional[datetime] = Query(None, description="Конец диапазона (ISO 8601)"),
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
) -> AuditLogPage:
    """
    Возвращает страницу записей журнала аудита по сделке.

    Фронт (AuditTab.tsx) использует:
    - page / per_page для навигации по страницам;
    - action для фильтрации по вкладкам (Экспорт, Импорт, QC и т.д.);
    - actor / from_date / to_date — расширенные фильтры.

    Ответ строго соответствует PaginatedResponse<AuditLogEntry>.
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
    Тело запроса для ручного создания записи аудита с фронта.
    Используется хуком useCreateAuditLogEntry.
    """
    deal_id: Optional[uuid.UUID] = None
    action: str
    details: dict = {}


@router.post(
    "/audit-log",
    response_model=AuditLogEntrySchema,
    status_code=status.HTTP_201_CREATED,
    summary="Создать запись аудита",
)
async def create_audit_log_entry(
    payload: AuditLogCreatePayload,
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
) -> AuditLogEntrySchema:
    """
    Создать запись аудита вручную.

    Используется фронтом для фиксации клиентских событий
    (например, открытие страницы с чувствительными данными).

    actor и actor_role пока берутся из заглушки.
    Позже — из JWT-токена.
    """
    repo = AuditRepository(db)

    entry = await repo.log(
        tenant_id=uuid.UUID(tenant_id) if tenant_id != "default" else uuid.UUID(int=0),
        deal_id=payload.deal_id,
        action=payload.action,
        actor="frontend",          # TODO: заменить на реального пользователя из токена
        actor_role="user",         # TODO: заменить на роль из токена
        details=payload.details,
    )
    await db.commit()

    logger.info(
        "Audit log entry created from frontend",
        deal_id=str(payload.deal_id),
        action=payload.action,
    )

    return AuditLogEntrySchema.model_validate(entry)


