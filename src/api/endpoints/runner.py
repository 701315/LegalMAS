# src/api/endpoints/runner.py

"""
Legacy Runner API.

Содержит устаревший эндпоинт запуска анализа сделки:
- POST /runner/runs — больше не выполняет анализ, всегда возвращает 410 Gone
  и указывает на новый API:
    * POST /api/v1/deals/{deal_id}/run — запуск анализа по сделке;
    * POST /api/v1/classifier/runs — ручная переклассификация.

Эндпоинт сохранён для обратной совместимости со старыми клиентами.
Права доступа по-прежнему проверяются, чтобы не раскрывать информацию
о сделках неавторизованным пользователям, но поведение для клиента
всегда одинаковое (410 Gone).
"""

import uuid as uuid_lib

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from core.config import settings
from core.logging import get_logger
from db.session import get_db

router = APIRouter(prefix="/runner", tags=["runner"])
logger = get_logger(__name__)


@router.post("/runs", status_code=status.HTTP_410_GONE)
async def run_deal(
    deal_id: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    LEGACY endpoint: больше не используется.

    Вместо этого нужно вызывать:
    - POST /api/v1/deals/{deal_id}/run — запуск анализа по сделке (run-пайплайн).
    - при необходимости ручной переклассификации — POST /api/v1/classifier/runs.
    """

    # Для прод и дев — одинаковое поведение: подсказываем новый путь.
    # RBAC оставляем, чтобы не давать лишнюю информацию неавторизованным.
    try:
        await require_project_role(
            db=db,
            user=user,
            deal_id=uuid_lib.UUID(deal_id),
            allowed_roles=("admin", "editor"),
        )
    except Exception:
        # Даже если нет прав — не раскрываем деталей, просто 410.
        pass

    logger.warning(
        "Legacy Runner endpoint called (disabled)",
        endpoint="POST /runner/runs",
        user_id=str(user.id),
        deal_id=deal_id,
        environment=settings.ENVIRONMENT,
    )

    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Legacy endpoint disabled. Use /api/v1/deals/{deal_id}/run instead.",
    )
