# src/api/endpoints/deals/router.py

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import get_scoped_deal, require_project_role
from api.schemas.deals import DealCreate, DealResponse, DealUpdate
from api.schemas.pagination import PaginatedResponse
from db.models.deal import Deal
from db.repositories.deal_repo import DealRepository
from db.repositories.playbook_repo import PlaybookRepository
from db.session import get_db

from .classification_investigation import router as classification_investigation_router
from .debug import router as debug_router
from .documents import router as documents_router
from .history import router as history_router
from .runs import router as runs_router
from .settings import router as settings_router

# ВАЖНО: crud_router больше не включается через include_router.
# Collection routes (GET /deals, POST /deals) объявлены прямо здесь,
# потому что FastAPI не разрешает path="" в sub-router без prefix.
# Detail routes (GET/PATCH/DELETE /deals/{id}) остаются в crud.py
# и включаются через include_router ниже.
from .crud import (
    _build_deal_response,
    router as crud_router,
)

router = APIRouter(prefix="/deals", tags=["deals"])


# ── Collection routes (/api/v1/deals и /api/v1/deals/) ────────────────────────
#
# Два декоратора на каждую функцию:
# - "/" → для backward compatibility и прямых вызовов с trailing slash
# - ""  → для фронта который шлёт POST /api/v1/deals без slash
#
# Это работает только когда у родительского APIRouter есть prefix ("/deals").
# FastAPI разрешает path="" если prefix непустой.


@router.get("/", response_model=PaginatedResponse[DealResponse], include_in_schema=False)
@router.get("", response_model=PaginatedResponse[DealResponse])
async def list_deals(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> PaginatedResponse[DealResponse]:
    repo = DealRepository(db)
    items, total = await repo.get_page(
        page=page,
        per_page=per_page,
        status=status,
        tenant_id=user.tenant_id,
    )
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    deal_items = [await _build_deal_response(db=db, deal=deal) for deal in items]
    return PaginatedResponse[DealResponse](
        items=deal_items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_previous=page > 1,
    )


@router.post(
    "/",
    response_model=DealResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
@router.post(
    "",
    response_model=DealResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать новую сделку (проект)",
)
async def create_deal(
    payload: DealCreate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> DealResponse:
    """
    Создать новую сделку для текущего тенанта.
    tenant_id берётся из JWT-токена текущего пользователя.
    """
    repo = DealRepository(db)

    deal = await repo.create(
        tenant_id=user.tenant_id,
        name=payload.name,
        deal_type=payload.deal_type,
        jurisdiction=payload.jurisdiction,
        languages=payload.languages,
        pii_mode=payload.pii_mode,
        profile=payload.profile,
        playbook_version_id=payload.playbook_version_id,
        metadata_=payload.metadata_ or {},
        summary=payload.summary,
    )

    await db.commit()

    refreshed = await repo.get_by_id(deal.id, tenant_id=user.tenant_id)
    if refreshed is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Deal was created but could not be reloaded.",
        )

    return await _build_deal_response(db=db, deal=refreshed)


# ── Detail + nested routes (/api/v1/deals/{deal_id}/...) ─────────────────────
#
# crud_router содержит GET/PATCH/DELETE /{deal_id}.
# Остальные роутеры содержат вложенные маршруты.

router.include_router(crud_router)
router.include_router(classification_investigation_router)
router.include_router(documents_router)
router.include_router(runs_router)
router.include_router(settings_router)
router.include_router(history_router)
router.include_router(debug_router)


