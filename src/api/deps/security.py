# src/api/deps/security.py

"""
RBAC-проверки для доступа к проекту (сделке).

Чистая логика:
1. superadmin   → доступ всегда
2. tenant_admin → доступ ко всем проектам своего tenant'а
3. member       → доступ только через deal_members + project role
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser
from core.roles import ProjectRole
from db.repositories.deal_repo import DealRepository
from db.repositories.project_role_repo import ProjectRoleRepository


async def require_project_role(
    db: AsyncSession,
    user: CurrentUser,
    deal_id: UUID,
    allowed_roles: Iterable[ProjectRole],
) -> None:
    """
    Проверить права пользователя на действие в проекте.

    Логика:
    - superadmin   → always allow
    - tenant_admin → allow if deal belongs to same tenant
    - member       → require membership with sufficient role
    """
    deal_repo = DealRepository(db)
    deal = await deal_repo.get_by_id(deal_id)

    if deal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deal not found",
        )

    if user.global_role == "superadmin":
        return

    if user.global_role == "tenant_admin":
        if deal.tenant_id != user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="ACCESS_DENIED: deal belongs to another tenant",
            )
        return

    role_repo = ProjectRoleRepository(db)
    project_role = await role_repo.get_role(
        user_id=user.id,
        deal_id=deal_id,
    )

    if project_role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ACCESS_DENIED: no project role",
        )

    if project_role not in set(allowed_roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ACCESS_DENIED: insufficient project role",
        )
    

    