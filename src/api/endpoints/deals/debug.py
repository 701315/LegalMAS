# src/api/endpoints/deals/debug.py

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from core.config import settings
from db.repositories.deal_repo import DealRepository
from db.session import get_db

router = APIRouter()


@router.get(
    "/debug/all-deals",
    summary="Временный список всех сделок (debug)",
)
async def debug_list_all_deals(
    db: AsyncSession = Depends(get_db),
):
    repo = DealRepository(db)
    deals = await repo.get_all()
    return [
        {
            "id": str(d.id),
            "name": d.name,
            "status": d.status,
        }
        for d in deals
    ]


class DebugDealCreate(BaseModel):
    name: str = "Test deal"
    deal_type: str | None = None


@router.post(
    "/debug/create-deal",
    summary="Создать тестовую сделку (debug)",
)
async def debug_create_deal(
    body: DebugDealCreate,
    db: AsyncSession = Depends(get_db),
):
    repo = DealRepository(db)
    deal = await repo.create(
        tenant_id=uuid.UUID(settings.DEV_TENANT_ID),
        name=body.name,
        deal_type=body.deal_type,
        jurisdiction=None,
        languages=["ru"],
        pii_mode="local_only",
        profile="full",
        playbook_version_id=None,
        metadata_={},
    )
    await db.commit()
    return {
        "id": str(deal.id),
        "name": deal.name,
    }
