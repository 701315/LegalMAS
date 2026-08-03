# src/api/endpoints/deals/llm_usage.py

"""
GET /api/v1/deals/{deal_id}/llm-usage-summary

Агрегат потребления LLM-токенов по проекту.
Данные из immutable ledger llm_usage_events.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from db.session import get_db
from services.llm_usage_recorder import LLMUsageRecorder

router = APIRouter()


@router.get(
    "/{deal_id}/llm-usage-summary",
    summary="Потребление LLM-токенов по проекту",
    tags=["deals"],
)
async def get_deal_llm_usage_summary(
    deal_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Агрегат потребления LLM-токенов по всем стадиям проекта.

    Доступен для viewer и выше.
    Возвращает total_tokens, total_calls и разбивку by_stage.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    recorder = LLMUsageRecorder(db)
    summary = await recorder.get_deal_summary(deal_id)
    return summary

