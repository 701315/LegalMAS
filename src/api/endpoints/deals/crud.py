# src/api/endpoints/deals/crud.py

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.schemas.deals import DealCreate, DealResponse, DealUpdate
from api.schemas.pagination import PaginatedResponse
from db.repositories.deal_repo import DealRepository
from db.repositories.playbook_repo import PlaybookRepository
from db.repositories.project_role_repo import ProjectRoleRepository
from db.session import get_db

router = APIRouter()


async def _build_deal_response(
    *,
    db: AsyncSession,
    deal,
) -> DealResponse:
    """
    Построить DealResponse с вычислением model_config_name.

    Для непрофессионального программиста:
    - сама ORM-модель сделки хранит model_config_id;
    - для UI дополнительно нужен model_config_name;
    - имя может приходить либо из явного model_config сделки,
      либо из связанной playbook version.
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


@router.get(
    "/",
    response_model=PaginatedResponse[DealResponse],
    summary="Список сделок",
)
async def list_deals(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = Query(
        None,
        description="Фильтр по статусу сделки (created, draft, ...)",
    ),
    tenant_id: UUID | None = Query(
        None,
        description="Фильтр по tenant_id (UUID арендатора)",
    ),
    db: AsyncSession = Depends(get_db),
):
    repo = DealRepository(db)

    items, total = await repo.get_page(
        page=page,
        per_page=per_page,
        status=status,
        tenant_id=tenant_id,
    )

    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    has_next = page < total_pages
    has_previous = page > 1

    deal_items = [await _build_deal_response(db=db, deal=deal) for deal in items]

    return PaginatedResponse[DealResponse](
        items=deal_items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        has_next=has_next,
        has_previous=has_previous,
    )


@router.post(
    "/",
    response_model=DealResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать новую сделку (проект)",
)
async def create_deal(
    payload: DealCreate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Создание сделки без автоматического выбора языка.

    Для непрофессионального программиста:
    - backend не делает догадок за пользователя;
    - если фронт хочет задать languages или primary_language,
      он обязан передать их явно в payload.
    """
    deal_repo = DealRepository(db)
    role_repo = ProjectRoleRepository(db)

    languages = payload.languages
    primary_language = payload.primary_language

    deal = await deal_repo.create(
        tenant_id=user.tenant_id,
        name=payload.name,
        summary=payload.summary,
        deal_type=payload.deal_type,
        jurisdiction=payload.jurisdiction,
        languages=languages,
        pii_mode=payload.pii_mode,
        profile=payload.profile,
        playbook_version_id=payload.playbook_version_id,
        metadata_=payload.metadata_,
    )

    if primary_language is not None:
        await deal_repo.update_primary_language(deal.id, primary_language)
        deal.primary_language = primary_language

    await role_repo.create_member(
        deal_id=deal.id,
        user_id=UUID(user.id),
        role="admin",
    )

    await db.commit()

    return await _build_deal_response(db=db, deal=deal)


@router.get(
    "/{deal_id}",
    response_model=DealResponse,
    summary="Детали одной сделки",
)
async def get_deal(
    deal_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    deal_repo = DealRepository(db)
    deal = await deal_repo.get_by_id(deal_id)

    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")

    return await _build_deal_response(db=db, deal=deal)


@router.patch(
    "/{deal_id}",
    response_model=DealResponse,
    summary="Частично обновить сделку",
)
async def update_deal(
    deal_id: UUID,
    payload: DealUpdate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Частичное обновление сделки.

    Поддерживаем:
    - summary;
    - languages;
    - primary_language.

    Контракты:
    - менять сделку могут только admin/editor или глобальный admin/superadmin;
    - если переданы и languages, и primary_language, то консистентность уже
      проверена на уровне pydantic схемы;
    - endpoint аккуратно применяет только переданные поля.
    """
    deal_repo = DealRepository(db)
    role_repo = ProjectRoleRepository(db)

    deal = await deal_repo.get_by_id(deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")

    project_role = await role_repo.get_role(user.id, deal_id)
    global_role = getattr(user, "global_role", None) or getattr(user, "role", None)

    if project_role not in ("admin", "editor") and global_role not in (
        "superadmin",
        "tenant_admin",
    ):
        raise HTTPException(
            status_code=403,
            detail="Not enough permissions to update deal",
        )

    update_data = payload.model_dump(exclude_unset=True)

    updated_deal = deal

    if "summary" in update_data:
        updated = await deal_repo.update_summary(deal_id, update_data["summary"])
        if updated is not None:
            updated_deal = updated

    if "languages" in update_data:
        languages = update_data["languages"]
        await deal_repo.update_languages(deal_id, languages or [])
        updated_deal.languages = languages

    if "primary_language" in update_data:
        primary_language = update_data["primary_language"]
        await deal_repo.update_primary_language(deal_id, primary_language)
        updated_deal.primary_language = primary_language

    await db.commit()

    refreshed_deal = await deal_repo.get_by_id(deal_id)
    if refreshed_deal is None:
        raise HTTPException(status_code=404, detail="Deal not found after update")

    return await _build_deal_response(db=db, deal=refreshed_deal)


@router.delete(
    "/{deal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить сделку (проект)",
)
async def delete_deal(
    deal_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    global_role = getattr(user, "global_role", None) or getattr(user, "role", None)
    if global_role not in ("superadmin", "tenant_admin"):
        raise HTTPException(
            status_code=403,
            detail="Not enough permissions to delete deal",
        )

    deal_repo = DealRepository(db)
    deal = await deal_repo.get_by_id(deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")

    await db.delete(deal)
    await db.commit()
