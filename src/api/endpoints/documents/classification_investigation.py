# src/api/endpoints/documents/classification_investigation.py

"""
Document-level classification investigation endpoints.

Назначение:
- вернуть explainability / investigation detail по классификации одного документа;
- не перегружать обычный document detail endpoint;
- использоваться UI-экраном Audit -> Classification Investigation.

Важно:
- endpoint read-only;
- authorization следует тому же паттерну, что и обычный document detail:
  сначала загрузка документа, затем require_project_role(...);
- доменная логика explainability находится в
  ClassificationInvestigationQueryService.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from api.schemas.classification_investigation import (
    ClassificationInvestigationDetailResponse,
)
from db.repositories.document_repo import DocumentRepository
from db.session import get_db
from services.classification_investigation_query import (
    ClassificationInvestigationQueryService,
)

router = APIRouter()


@router.get(
    "/{document_id}/classification-investigation",
    response_model=ClassificationInvestigationDetailResponse,
    summary="Получить explainability по классификации документа",
)
async def get_document_classification_investigation(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Вернуть подробный explainability/investigation detail по классификации документа.

    Для непрофессионального программиста:
    - endpoint ничего не изменяет;
    - сначала находит документ;
    - затем проверяет, что пользователь имеет доступ к сделке документа;
    - после этого возвращает:
      * финальные classification поля;
      * какие уровни были задействованы;
      * кандидатов;
      * voting / override;
      * raw explainability payload;
      * composition / segment summary.
    """
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    await require_project_role(
        db=db,
        user=user,
        deal_id=doc.deal_id,
        allowed_roles=("viewer", "editor", "admin"),
    )

    service = ClassificationInvestigationQueryService(db)
    detail = await service.get_document_detail(document_id=document_id)
    if detail is None:
        # Теоретически сюда уже не должны попасть, потому что doc найден выше,
        # но defensive-check делает endpoint устойчивее к будущим изменениям.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return detail

