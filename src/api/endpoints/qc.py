# src/api/endpoints/qc.py

"""
API‑эндпоинты QC‑действий для review mode.

Назначение:
- дать фронтенду отдельный mutation‑контракт для approve / reject finding'ов
  в DD Matrix / review panel;
- не смешивать review‑ориентированный QC path с legacy QC API,
  который может использовать result_id.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from db.session import get_db
from api.deps.security import require_project_role
from api.schemas.qc import (
    ReviewQCBulkUpdateRequest,
    ReviewQCBulkUpdateResponse,
    ReviewQCUpdateRequest,
    ReviewQCUpdateResponse,
)
from services.review_qc_service import (
    apply_bulk_review_qc_update,
    apply_review_qc_update,
    build_bulk_review_qc_response,
    build_review_qc_response,
    load_review_qc_scope,
)

router = APIRouter(prefix="/qc", tags=["qc"])


@router.post(
    "/review",
    response_model=ReviewQCUpdateResponse,
    summary="Apply QC action to a review finding",
)
async def update_review_qc(
    payload: ReviewQCUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ReviewQCUpdateResponse:
    scope = await load_review_qc_scope(db=db, run_id=payload.finding.run_id)

    await require_project_role(
        db=db,
        user=current_user,
        deal_id=scope.deal_id,
        allowed_roles=("admin", "editor"),
    )

    result = await apply_review_qc_update(
        db=db,
        user=current_user,
        payload=payload,
        commit=False,
    )
    await db.commit()
    return build_review_qc_response(result)


@router.post(
    "/review/bulk",
    response_model=ReviewQCBulkUpdateResponse,
    summary="Apply QC action to multiple review findings",
)
async def bulk_update_review_qc(
    payload: ReviewQCBulkUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ReviewQCBulkUpdateResponse:
    scope = await load_review_qc_scope(db=db, run_id=payload.findings[0].run_id)

    await require_project_role(
        db=db,
        user=current_user,
        deal_id=scope.deal_id,
        allowed_roles=("admin", "editor"),
    )

    result = await apply_bulk_review_qc_update(
        db=db,
        user=current_user,
        payload=payload,
        commit=False,
    )
    await db.commit()
    return build_bulk_review_qc_response(result)



