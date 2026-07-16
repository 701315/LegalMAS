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
from fastapi import HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.deps.auth import CurrentUser, get_current_user
from core.roles import ProjectRole
from db.models.deal import Deal
from db.models.run import Run
from db.repositories.project_role_repo import ProjectRoleRepository
from db.session import get_db

async def get_scoped_deal(
    deal_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Deal:
    """Возвращает сделку, только если она принадлежит тенанту пользователя."""
    stmt = select(Deal).where(Deal.id == deal_id, Deal.tenant_id == user.tenant_id)
    result = await db.execute(stmt)
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")
    return deal

async def get_scoped_run(
    run_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Run:
    """Возвращает Run, проверяя тенанта через цепочку к Сделке."""
    stmt = (
        select(Run)
        .join(Deal, Run.deal_id == Deal.id)
        .where(Run.id == run_id, Deal.tenant_id == user.tenant_id)
    )
    result = await db.execute(stmt)
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run

async def require_project_role(
    db: AsyncSession,
    user: CurrentUser,
    deal_id: UUID,
    allowed_roles: Iterable[ProjectRole],
) -> None:
    """Проверяет тенант И роль пользователя внутри проекта."""
    stmt = select(Deal.tenant_id).where(Deal.id == deal_id)
    res = await db.execute(stmt)
    deal_tenant_id = res.scalar_one_or_none()

    if deal_tenant_id is None:
        raise HTTPException(status_code=404, detail="Deal not found")

    if user.global_role != "superadmin" and deal_tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant access forbidden")

    if user.global_role in ("superadmin", "tenant_admin"):
        return

    role_repo = ProjectRoleRepository(db)
    project_role = await role_repo.get_role(user_id=user.id, deal_id=deal_id)
    if project_role is None or project_role not in set(allowed_roles):
        raise HTTPException(status_code=403, detail="Insufficient project role")
    

    
    

    