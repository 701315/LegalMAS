# src/api/endpoints/deals/runs.py
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from api.endpoints.runs import _start_run_core
from api.schemas.runs import RunCreate, RunResponse
from db.repositories.run_repo import RunRepository
from db.session import get_db

router = APIRouter()


@router.get(
    "/{deal_id}/runs",
    response_model=list[RunResponse],
    summary="Список запусков по сделке",
)
async def list_deal_runs(
    deal_id: UUID,
    include_classification_stats: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )
    run_repo = RunRepository(db)
    runs = await run_repo.get_by_deal(deal_id)
    result = [RunResponse.model_validate(r) for r in runs]

    if include_classification_stats and runs:
        for i, run_obj in enumerate(runs):
            stats = await run_repo.get_classification_stats_for_run(run_obj.id)
            result[i].classification_stats = stats

    return result


@router.post(
    "/{deal_id}/run",
    response_model=RunResponse,
    summary="Запустить анализ по сделке",
)
async def start_deal_run(
    deal_id: UUID,
    payload: RunCreate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor"),
    )
    return await _start_run_core(deal_id, payload, db, user)
