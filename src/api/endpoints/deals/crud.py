# src/api/endpoints/deals/crud.py

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import get_scoped_deal, require_project_role # Добавили
from api.schemas.deals import DealCreate, DealResponse, DealUpdate
from api.schemas.pagination import PaginatedResponse
from db.models.deal import Deal
from db.repositories.deal_repo import DealRepository
from db.repositories.playbook_repo import PlaybookRepository
from db.repositories.project_role_repo import ProjectRoleRepository
from db.session import get_db

router = APIRouter()

# Вспомогательная функция _build_deal_response остается без изменений...
async def _build_deal_response(*, db: AsyncSession, deal) -> DealResponse:
    deal_resp = DealResponse.model_validate(deal)
    model_config_name: str | None = None
    pb_repo = PlaybookRepository(db)
    explicit_model_config_id = getattr(deal, "model_config_id", None)
    if explicit_model_config_id is not None:
        mc = await pb_repo.get_model_config(explicit_model_config_id)
        if mc is not None:
            model_config_name = mc.name
    elif deal.playbook_version_id:
        pv = await pb_repo.get_by_id(deal.playbook_version_id)
        if pv is not None and getattr(pv, "model_config_id", None):
            mc = await pb_repo.get_model_config(pv.model_config_id)
            if mc is not None:
                model_config_name = mc.name
    deal_resp.model_config_name = model_config_name
    return deal_resp

@router.get("/", response_model=PaginatedResponse[DealResponse])
async def list_deals(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user), # Теперь обязателен
):
    repo = DealRepository(db)
    # Используем tenant_id пользователя из токена
    items, total = await repo.get_page(
        page=page, per_page=per_page, status=status, tenant_id=user.tenant_id
    )
    # ... маппинг
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    deal_items = [await _build_deal_response(db=db, deal=deal) for deal in items]
    return PaginatedResponse[DealResponse](
        items=deal_items, total=total, page=page, per_page=per_page,
        total_pages=total_pages, has_next=page < total_pages, has_previous=page > 1,
    )

@router.get("/{deal_id}", response_model=DealResponse)
async def get_deal(
    # Используем автоматическую проверку тенанта
    deal: Deal = Depends(get_scoped_deal),
    db: AsyncSession = Depends(get_db),
):
    return await _build_deal_response(db=db, deal=deal)

@router.patch(
    "/{deal_id}",
    response_model=DealResponse,
    summary="Обновить сделку (RBAC + Scoped)",
)
async def update_deal(
    deal_id: UUID,
    payload: DealUpdate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    # 1. Проверяем тенант и наличие сделки
    deal = await get_scoped_deal(deal_id=deal_id, user=user, db=db)
    
    # 2. Проверяем права на редактирование через системный RBAC
    await require_project_role(
        db=db, user=user, deal_id=deal_id, 
        allowed_roles=("admin", "editor")
    )

    deal_repo = DealRepository(db)
    update_data = payload.model_dump(exclude_unset=True)

    if "summary" in update_data:
        await deal_repo.update_summary(deal_id, update_data["summary"])
    if "languages" in update_data:
        await deal_repo.update_languages(deal_id, update_data["languages"] or [])
    if "primary_language" in update_data:
        await deal_repo.update_primary_language(deal_id, update_data["primary_language"])

    await db.commit()
    # Перечитываем сделку для актуального ответа
    refreshed = await deal_repo.get_by_id(deal_id, tenant_id=user.tenant_id)
    return await _build_deal_response(db=db, deal=refreshed)

@router.delete(
    "/{deal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить сделку (Admin Scoped)",
)
async def delete_deal(
    deal_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    # 1. Сначала проверяем существование и тенант (даже админ не может удалять чужое)
    deal = await get_scoped_deal(deal_id=deal_id, user=user, db=db)

    # 2. Проверяем глобальную роль
    global_role = getattr(user, "global_role", None) or getattr(user, "role", None)
    if global_role not in ("superadmin", "tenant_admin"):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    await db.delete(deal)
    await db.commit()
    