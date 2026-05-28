# src/api/endpoints/deals/classification_investigation.py

"""
Deal-level classification investigation endpoints.

Назначение:
- вернуть отдельный read-model для explainability / investigation классификации;
- не перегружать стандартный document list endpoint;
- использоваться UI-экраном Audit -> Classification Investigation.

Важно:
- endpoint read-only;
- access control следует существующему deal read-pattern;
- сначала явно проверяем, что сделка существует, чтобы вернуть корректный 404;
- затем проверяем project-level доступ через require_project_role(...);
- доменная логика explainability находится в сервисе
  ClassificationInvestigationQueryService.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from api.schemas.classification_investigation import (
    ClassificationInvestigationListResponse,
)
from db.repositories.deal_repo import DealRepository
from db.session import get_db
from services.classification_investigation_query import (
    ClassificationInvestigationQueryService,
)

router = APIRouter()


@router.get(
    "/{deal_id}/classification-investigation",
    response_model=ClassificationInvestigationListResponse,
    summary="Получить investigation по классификации документов сделки",
)
async def get_classification_investigation_page(
    deal_id: UUID,
    page: int = Query(
        1,
        ge=1,
        description="Номер страницы (начиная с 1)",
    ),
    per_page: int = Query(
        20,
        ge=1,
        le=200,
        description="Количество документов на странице",
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Вернуть страницу investigation/explainability по классификации документов сделки.

    Для непрофессионального программиста:
    - endpoint ничего не меняет;
    - сначала убеждается, что такая сделка вообще существует;
    - затем проверяет, что у пользователя есть доступ к этой сделке;
    - после этого возвращает summary и страницу investigation-элементов.
    """
    deal_repo = DealRepository(db)
    deal = await deal_repo.get_by_id(deal_id)
    if deal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deal not found",
        )

    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("viewer", "editor", "admin"),
    )

    service = ClassificationInvestigationQueryService(db)
    return await service.get_deal_page(
        deal_id=deal_id,
        page=page,
        per_page=per_page,
    )
