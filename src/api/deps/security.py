# src/api/deps/security.py

"""
Вспомогательные функции безопасности (RBAC) для эндпоинтов.

Здесь живёт логика проверки ролей пользователя в проектах (сделках).

Ключевая функция: require_project_role
--------------------------------------

Задача:
- Получить роль пользователя в проекте из ProjectRoleRepository;
- Сравнить её со списком разрешённых ролей;
- Если роли нет или она недостаточна — выбросить HTTP 403.

Как это используется в эндпоинтах:
----------------------------------
Пример (start_deal_run):

    @router.post("/{deal_id}/run", ...)
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

Таким образом:
- Фронтенд рисует кнопки/гварды по своим правилам;
- Бэкенд гарантирует, что даже при прямом вызове API
  пользователь с недостаточной ролью не выполнит действие.
"""

from __future__ import annotations

from typing import Iterable
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser
from db.repositories.project_role_repo import ProjectRoleRepository


async def require_project_role(
    db: AsyncSession,
    user: CurrentUser,
    deal_id: UUID,
    allowed_roles: Iterable[str],
) -> None:
    """
    Проверяет роль пользователя в проекте (сделке).

    Параметры:
    - db           : AsyncSession   — сессия БД, уже полученная через Depends(get_db)
    - user         : CurrentUser    — текущий пользователь (из get_current_user)
    - deal_id      : UUID           — идентификатор проекта/сделки
    - allowed_roles: Iterable[str]  — список допустимых ролей, например:
        ("admin", "editor") или ("admin", "editor", "viewer")

    Логика:
    1) Через ProjectRoleRepository получаем роль пользователя в этом проекте.
    2) Если роли нет (None) или она не входит в allowed_roles:
         выбрасываем HTTPException(403, "Forbidden").
    3) Если роль подходит — просто выходим (ничего не возвращаем).

    Текущее состояние (до реализации ProjectMemberModel и реальной auth):
    - ProjectRoleRepository.get_role возвращает "admin" для всех пользователей.
    - Это значит, что реальной защиты по ролям пока нет.
    - НО во всех нужных местах уже есть вызов require_project_role, и когда
      появится таблица project_members и нормальная auth, достаточно будет:
        * реализовать ProjectMemberModel и методы ProjectRoleRepository;
        * переписать get_current_user на реальный токен.
    """
    role_repo = ProjectRoleRepository(db)
    role = await role_repo.get_role(user_id=user.id, deal_id=deal_id)

    if role is None or role not in set(allowed_roles):
        raise HTTPException(status_code=403, detail="Forbidden")
