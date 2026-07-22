"""
Pydantic-схемы для read-only Run check-plan API.

GET /api/runs/{run_id}/check-plan
GET /api/runs/{run_id}/check-plan/{plan_item_id}
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RunCheckPlanItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    document_id: uuid.UUID
    segment_id: str | None = None
    doc_type: str | None = None
    check_id: str
    check_name: str | None = None
    check_origin: str | None = None
    playbook_version_id: uuid.UUID | None = None
    status: str
    attempt_count: int
    dispatch_ref: str | None = None
    error_details: dict | None = None
    dispatched_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class RunCheckPlanSummary(BaseModel):
    """
    Агрегированная статистика execution ledger.

    ВАЖНО: summary всегда отражает состояние ВСЕГО Run,
    независимо от query-параметра status в GET /runs/{run_id}/check-plan.
    Это осознанный контракт: items — filtered view, summary — неизмен��ый
    overall progress indicator для UI (progress bar/header), который не
    должен "мигать" при переключении фильтра статуса.
    """

    total_items: int
    terminal_items: int
    active_items: int
    has_errors: bool



class RunCheckPlanResponse(BaseModel):
    """
    Response для GET /runs/{run_id}/check-plan.

    items   — filtered по query-параметру status (если передан).
    summary — overall статистика по всему Run (см. RunCheckPlanSummary).
    """

    run_id: uuid.UUID
    items: list[RunCheckPlanItemResponse]
    summary: RunCheckPlanSummary

    