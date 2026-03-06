# src/api/schemas/deals.py

"""
Pydantic-схемы для работы со сделками в REST API.
"""

from uuid import UUID
from datetime import datetime

from pydantic import BaseModel

from core.constants import DealStatus, PIIMode


class DealResponse(BaseModel):
    """
    Краткая информация о сделке для списка сделок.

    Используется в списке сделок на главной странице.
    """
    id: UUID
    tenant_id: UUID

    name: str
    deal_type: str | None = None
    jurisdiction: str | None = None
    languages: list[str] | None = None

    status: str  # или DealStatus, если хочешь строго типизировать
    pii_mode: str  # или PIIMode
    profile: str

    playbook_version_id: UUID | None = None
    metadata_: dict | None = None

    created_at: datetime
    updated_at: datetime | None = None
    last_run_id: UUID | None = None
    
    model_config = {"from_attributes": True}
