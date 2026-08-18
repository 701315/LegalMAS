# src/api/endpoints/run_summary.py

"""
Endpoints для executive summary run.

GET  /api/v1/runs/{run_id}/summary           — статус + текст + fallback
POST /api/v1/runs/{run_id}/summary/regenerate — принудительная перегенерация

Tenant-изоляция — через get_scoped_run (тот же контракт, что в runs.py).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import get_scoped_run
from db.models.run import Run
from db.session import get_session, transactional_session
from db.repositories.run_summary_repo import RunSummaryRepository
from services.run_summary_service import RunSummaryService

router = APIRouter(prefix="/runs", tags=["run_summary"])


class RunSummaryResponse(BaseModel):
    run_id: str
    status: str  # pending | generating | ready | failed
    text: Optional[str] = None
    claims: Optional[dict[str, Any]] = None
    fallback: Optional[dict[str, Any]] = None
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    error_message: Optional[str] = None
    generated_at: Optional[str] = None


@router.get("/{run_id}/summary", response_model=RunSummaryResponse)
async def get_run_summary(
    run: Run = Depends(get_scoped_run),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Вернуть summary для run.

    Если run terminal и записи ещё нет — создать 'pending' с fallback
    (dispatcher подхватит генерацию в фоне).
    """
    async with get_session() as session:
        service = RunSummaryService(session)
        await service.ensure_record(run.id)
        response = await service.get_response(run.id)

    if response is None:
        raise HTTPException(status_code=404, detail="Summary not available")

    return response


@router.post("/{run_id}/summary/regenerate", response_model=RunSummaryResponse)
async def regenerate_run_summary(
    run: Run = Depends(get_scoped_run),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Принудительная перегенерация: переводит ready/failed в pending
    и спавнит генерацию в фоне. Возвращает актуальное состояние.
    """
    async with transactional_session() as session:
        repo = RunSummaryRepository(session)
        summary = await repo.get_by_run_id(run.id)
        if summary is None:
            raise HTTPException(status_code=404, detail="Summary not found")

        if summary.status != "generating":
            await repo.update_status(run.id, "pending")

    # Фоновая генерация в API-процессе (claim защитит от дублей).
    async def _gen() -> None:
        async with transactional_session() as session:
            await RunSummaryService(session).generate(run.id)

    asyncio.create_task(_gen(), name=f"summary_regen_{run.id}")

    async with get_session() as session:
        response = await RunSummaryService(session).get_response(run.id)

    return response


    