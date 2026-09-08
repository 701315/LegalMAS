"""
FastAPI endpoints for translation review actions (Sprint 6.2).

Routes:
  POST /localization-review/{presentation_id}/approve
  POST /localization-review/{presentation_id}/reject
  POST /localization-review/{presentation_id}/edit
  POST /localization-review/{presentation_id}/reset

All endpoints require admin or editor project role.
Canonical CheckResult is never modified (Invariants #1, #3).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from api.schemas.localization_review import (
    ReviewApproveRequest,
    ReviewEditRequest,
    ReviewRejectRequest,
    ReviewResponse,
)
from db.models.deal import Deal
from db.models.result import CheckResult, CheckResultPresentation
from db.models.run import Run
from db.session import get_db
from services.result_localization_review_service import (
    ResultLocalizationReviewService,
    ReviewStateError,
)

router = APIRouter(prefix="/localization-review", tags=["localization_review"])


async def _resolve_deal_and_check_access(
    db: AsyncSession,
    presentation_id: uuid.UUID,
    user: CurrentUser,
) -> Deal:
    """
    Resolve the Deal linked to a presentation and verify project role.

    Returns the Deal object for downstream use (tenant_id, etc.).
    Raises 404 if presentation not found, 403 if access denied.
    """
    stmt = (
        select(Deal)
        .select_from(CheckResultPresentation)
        .join(CheckResult, CheckResult.id == CheckResultPresentation.check_result_id)
        .join(Run, Run.id == CheckResult.run_id)
        .join(Deal, Deal.id == Run.deal_id)
        .where(CheckResultPresentation.id == presentation_id)
    )
    result = await db.execute(stmt)
    deal = result.scalar_one_or_none()

    if deal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Presentation not found",
        )

    await require_project_role(
        db=db,
        user=user,
        deal_id=deal.id,
        allowed_roles=("admin", "editor"),
    )

    return deal


def _build_response(presentation: CheckResultPresentation) -> ReviewResponse:
    """Build a standardized response DTO from a presentation ORM object."""
    return ReviewResponse(
        presentation_id=str(presentation.id),
        translation_status=presentation.translation_status,
        locale=presentation.locale,
        reviewed_by=str(presentation.reviewed_by) if presentation.reviewed_by else None,
        reviewed_at=presentation.reviewed_at.isoformat() if presentation.reviewed_at else None,
        approved_by=str(presentation.approved_by) if presentation.approved_by else None,
        approved_at=presentation.approved_at.isoformat() if presentation.approved_at else None,
        review_comment=presentation.review_comment,
        has_human_override=presentation.human_override_text is not None,
        has_original_snapshot=presentation.original_translation_snapshot is not None,
    )


@router.post(
    "/{presentation_id}/approve",
    response_model=ReviewResponse,
    summary="Approve a localized presentation translation",
)
async def approve_translation(
    presentation_id: uuid.UUID,
    payload: ReviewApproveRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> ReviewResponse:
    await _resolve_deal_and_check_access(db, presentation_id, user)

    service = ResultLocalizationReviewService(db)
    try:
        presentation = await service.approve_translation(
            presentation_id=presentation_id,
            user_id=user.id,
            user_email=user.email,
            comment=payload.comment,
        )
    except ReviewStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    await db.commit()
    return _build_response(presentation)


@router.post(
    "/{presentation_id}/reject",
    response_model=ReviewResponse,
    summary="Reject a localized presentation translation",
)
async def reject_translation(
    presentation_id: uuid.UUID,
    payload: ReviewRejectRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> ReviewResponse:
    await _resolve_deal_and_check_access(db, presentation_id, user)

    service = ResultLocalizationReviewService(db)
    try:
        presentation = await service.reject_translation(
            presentation_id=presentation_id,
            user_id=user.id,
            user_email=user.email,
            comment=payload.comment,
        )
    except ReviewStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    await db.commit()
    return _build_response(presentation)


@router.post(
    "/{presentation_id}/edit",
    response_model=ReviewResponse,
    summary="Apply a human override to a localized presentation",
)
async def edit_translation(
    presentation_id: uuid.UUID,
    payload: ReviewEditRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> ReviewResponse:
    await _resolve_deal_and_check_access(db, presentation_id, user)

    service = ResultLocalizationReviewService(db)
    try:
        presentation = await service.edit_translation_override(
            presentation_id=presentation_id,
            user_id=user.id,
            user_email=user.email,
            localized_check_name=payload.localized_check_name,
            display_text=payload.display_text,
            review_message=payload.review_message,
            dd_request_text=payload.dd_request_text,
            comment=payload.comment,
        )
    except ReviewStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    await db.commit()
    return _build_response(presentation)


@router.post(
    "/{presentation_id}/reset",
    response_model=ReviewResponse,
    summary="Reset a rejected presentation back to pending for re-translation",
)
async def reset_translation(
    presentation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> ReviewResponse:
    await _resolve_deal_and_check_access(db, presentation_id, user)

    service = ResultLocalizationReviewService(db)
    try:
        presentation = await service.reset_to_pending(
            presentation_id=presentation_id,
            user_email=user.email,
        )
    except ReviewStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    await db.commit()
    return _build_response(presentation)
