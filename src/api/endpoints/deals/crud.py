# src/api/endpoints/deals/crud.py

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

router = APIRouter()


async def _build_deal_response(*, db: AsyncSession, deal) -> DealResponse:
    """
    Построить DealResponse из ORM-объекта Deal.
    Вынесена в отдельную функцию для переиспользования в router.py.
    """
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


# ── Detail routes (/api/v1/deals/{deal_id}) ───────────────────────────────────


@router.get("/{deal_id}", response_model=DealResponse)
async def get_deal(
    deal: Deal = Depends(get_scoped_deal),
    db: AsyncSession = Depends(get_db),
) -> DealResponse:
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
) -> DealResponse:
    # 1. Проверяем тенант и наличие сделки
    await get_scoped_deal(deal_id=deal_id, user=user, db=db)

    # 2. Проверяем права на редактирование через системный RBAC
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor"),
    )

    deal_repo = DealRepository(db)
    update_data = payload.model_dump(exclude_unset=True)

    # ИСПРАВЛЕНО: все вызовы репозитория теперь передают tenant_id.
    # Ранее вызывались без tenant_id — TypeError при первом PATCH.
    if "summary" in update_data:
        await deal_repo.update_summary(deal_id, user.tenant_id, update_data["summary"])
    if "languages" in update_data:
        await deal_repo.update_languages(deal_id, user.tenant_id, update_data["languages"] or [])
    if "primary_language" in update_data:
        await deal_repo.update_primary_language(
            deal_id, user.tenant_id, update_data["primary_language"]
        )

    await db.commit()

    refreshed = await deal_repo.get_by_id(deal_id, tenant_id=user.tenant_id)
    if refreshed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deal not found after update.",
        )

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
) -> None:
    # 1. Сначала проверяем существование и тенант
    deal = await get_scoped_deal(deal_id=deal_id, user=user, db=db)

    # 2. Проверяем глобальную роль
    global_role = getattr(user, "global_role", None) or getattr(user, "role", None)
    if global_role not in ("superadmin", "tenant_admin"):
        raise HTTPException(status_code=403, detail="Not enough permissions")

    await db.delete(deal)
    await db.commit()

    