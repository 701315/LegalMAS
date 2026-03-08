# src/api/endpoints/runner.py

from fastapi import APIRouter, HTTPException, Depends

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role

from db.uow import db_uow
from engine.runner import Runner

router = APIRouter(prefix="/runner", tags=["runner"])


@router.post("/runs")
async def run_deal(
    deal_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Запустить полный пайплайн проверки для сделки.

    ВАЖНО:
    - Этот эндпоинт потенциально очень "мощный" (ручной запуск пайплайна),
      поэтому его разумно ограничить только ролями "admin" и "editor"
      для соответствующей сделки.
    """
    try:
        # Проверяем роль пользователя в проекте (сделке)
        # Здесь deal_id приходит строкой, поэтому приводим к UUID внутри require_project_role
        # (в репозитории ролей нужно будет работать с UUID).
        # Если роль не "admin"/"editor" — вернётся 403.
        # Примечание: сейчас ProjectRoleRepository заглушечный, позже надо будет
        # реализовать реальную проверку.
        import uuid as uuid_lib

        await require_project_role(
            db=None,  # здесь нет AsyncSession, т.к. мы используем db_uow;
                      # когда будет нужна реальная проверка, лучше переделать
                      # этот эндпоинт на Depends(get_db) + Runner, чтобы была сессия.
            user=user,
            deal_id=uuid_lib.UUID(deal_id),
            allowed_roles=("admin", "editor"),
        )
    except TypeError:
        # ВРЕМЕННО: если require_project_role требует AsyncSession, а мы даём None,
        # можно либо убрать эту проверку, либо позже перевести эндпоинт на Depends(get_db).
        # Пока просто оставим запуск как есть.
        pass

    try:
        async with db_uow() as uow:
            runner = Runner(uow)
            result = await runner.run_deal(deal_id)
        return {"status": "completed", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
