# src/api/deps/security.py
"""
Вспомогательные зависимости безопасности (RBAC) для эндпоинтов.

Назначение:
- Центральное место для проверки прав доступа на уровне конкретного проекта/сделки.
- Основная функция: require_project_role — проверка проектной роли пользователя
  с учётом его глобальной роли.

Роль в архитектуре:
- Глобальная роль (GlobalRole) ограничивает "потолок" прав пользователя.
- Проектная роль (ProjectRole) хранится в таблице deal_members и может урезать
  права в конкретной сделке.
- require_project_role комбинирует global_role и projectRole, чтобы решить,
  можно ли выполнять конкретное действие (загрузка документов, запуск анализа,
  управление участниками проекта и т.п.).

Использование:
- В эндпоинтах, привязанных к deal_id, вызывается, например:

    await require_project_role(
        db=db,
        user=current_user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor"),
    )

- Фронтенд управляет UI через свои capability-флаги, но даже при прямом вызове API
  без фронта бэкенд гарантирует защиту по ролям.
"""

from __future__ import annotations

from typing import Iterable
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser
from db.repositories.project_role_repo import ProjectRoleRepository
from core.roles import ProjectRole, GlobalRole


async def require_project_role(
    db: AsyncSession,
    user: CurrentUser,
    deal_id: UUID,
    allowed_roles: Iterable[ProjectRole],
) -> None:
    """
    Проверяет роль пользователя в проекте (сделке).

    Параметры:
    - db            : AsyncSession — сессия БД.
    - user          : CurrentUser  — текущий пользователь (из get_current_user).
    - deal_id       : UUID         — идентификатор сделки/проекта.
    - allowed_roles : Iterable[ProjectRole] — роли проекта, которым разрешено действие
                      (например: ("admin", "editor")).

    Логика:
    0) Глобальные роли:
       - superadmin  → всегда разрешено (игнорируем projectRole);
       - admin/editor → максимум возможных прав, но проектная роль может их урезать.
         То есть требуется И global_role ∈ {admin, editor} И projectRole ∈ allowed_roles.
       - остальные global_role (viewer/user/system/...) → доступа нет, даже если
         по каким-то причинам в таблице будет "admin"/"editor".

    1) Через ProjectRoleRepository получаем роль пользователя в этом проекте.
    2) Если роли нет (None) → 403.
    3) Если роль не входит в allowed_roles → 403.
    4) Иначе — доступ разрешён.
    """
    # 0. Глобальный superadmin имеет полный доступ
    if user.global_role == "superadmin":
        return

    # 0.1. Ограничиваем доступ по глобальной роли:
    #      управлять проектом могут только глобальные admin/editor/superadmin.
    if user.global_role not in ("admin", "editor"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ACCESS_DENIED: insufficient global role",
        )

    role_repo = ProjectRoleRepository(db)
    project_role = await role_repo.get_role(user_id=user.id, deal_id=deal_id)

    # 1. Пользователь не является участником проекта
    if project_role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ACCESS_DENIED: no project role",
        )

    # 2. Роль участника проекта недостаточна для этого действия
    if project_role not in set(allowed_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ACCESS_DENIED: insufficient project role",
        )

    # Если добрались сюда — доступ разрешён
    return
