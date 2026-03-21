# src/api/endpoints/runner.py

import uuid as uuid_lib

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from core.config import settings
from core.logging import get_logger
from db.session import get_db
from db.uow import db_uow
from engine.runner import Runner

router = APIRouter(prefix="/runner", tags=["runner"])
logger = get_logger(__name__)


@router.post("/runs", status_code=status.HTTP_200_OK)
async def run_deal(
    deal_id: str,
    # ✅ ИСПРАВЛЕНИЕ БАГа 2, шаг 1:
    # Добавляем db через Depends(get_db) — теперь у нас есть реальная AsyncSession
    # для передачи в require_project_role вместо None.
    # get_db и db_uow — независимые сессии, не конфликтуют между собой.
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Запустить полный пайплайн проверки для сделки.

    Доступно только пользователям с проектной ролью "admin" или "editor".

    В режиме development (ENVIRONMENT=development) проверка ролей пропускается
    явно — для удобства разработки. В production проверка всегда активна.
    """
    # ✅ ИСПРАВЛЕНИЕ БАГа 2, шаг 2:
    # Dev-bypass: явный и прозрачный пропуск RBAC в режиме разработки.
    # Логируем факт пропуска — чтобы в логах было видно что проверка обойдена.
    # В production (ENVIRONMENT=production) этот блок не выполняется никогда.
    if settings.ENVIRONMENT == "development":
        logger.warning(
            "RBAC check skipped in development mode",
            endpoint="POST /runner/runs",
            user_id=str(user.id),
            deal_id=deal_id,
        )
    else:
        # ✅ ИСПРАВЛЕНИЕ БАГа 2, шаг 3:
        # Убираем try/except TypeError — теперь db реальная, TypeError не возникнет.
        # Если у пользователя нет прав — require_project_role бросит HTTPException(403),
        # FastAPI сам вернёт его клиенту. Ничего не проглатываем.
        await require_project_role(
            db=db,
            user=user,
            deal_id=uuid_lib.UUID(deal_id),
            allowed_roles=("admin", "editor"),
        )

    # Запуск пайплайна через db_uow (отдельная сессия от RBAC-проверки)
    try:
        async with db_uow() as uow:
            runner = Runner(uow)
            result = await runner.run_deal(deal_id)
        return {"status": "completed", "result": result}
    except Exception as e:
        logger.exception(
            "Pipeline run failed",
            deal_id=deal_id,
            user_id=str(user.id),
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )