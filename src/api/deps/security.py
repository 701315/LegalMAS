# src/api/deps/security.py

"""
RBAC-проверки для доступа к проекту (сделке) и tenant-scope ресурсам.

Трёхуровневая модель доступа:

1. Tenant isolation (get_scoped_deal, get_scoped_run):
   - superadmin   → доступ к любому tenant
   - tenant_admin → только свой tenant
   - member       → только свой tenant

2. Deal-level access (require_project_role):
   - superadmin   → доступ всегда
   - tenant_admin → доступ ко всем проектам своего tenant'а
   - member       → доступ только через deal_members + project role

3. Tenant-scope access (require_tenant_scope_access):
   Для tenant-wide ресурсов (instructions, overrides), не привязанных к deal:
   - superadmin   → любой tenant
   - tenant_admin → только свой tenant
   - member       → forbidden
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from core.roles import ProjectRole
from db.models.deal import Deal
from db.models.run import Run
from db.repositories.project_role_repo import ProjectRoleRepository
from db.session import get_db


async def get_scoped_deal(
    deal_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Deal:
    """
    Возвращает сделку с tenant isolation.

    Правила:
    - superadmin   → может видеть deal любого tenant'а
    - tenant_admin → только deal своего tenant'а
    - member       → только deal своего tenant'а

    ВАЖНО: этот guard НЕ проверяет membership.
    Для проверки project role используй require_project_role() отдельно.
    """
    if user.global_role == "superadmin":
        # superadmin может видеть любой deal
        stmt = select(Deal).where(Deal.id == deal_id)
    else:
        # tenant_admin и member — только свой tenant
        stmt = select(Deal).where(
            Deal.id == deal_id,
            Deal.tenant_id == user.tenant_id,
        )

    result = await db.execute(stmt)
    deal = result.scalar_one_or_none()
    if not deal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deal not found",
        )
    return deal


async def get_scoped_run(
    run_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Run:
    """
    Возвращает Run с tenant isolation через связанную Deal.

    Правила:
    - superadmin   → может видеть run любого tenant'а
    - tenant_admin → только run своего tenant'а
    - member       → только run своего tenant'а

    ВАЖНО: этот guard НЕ проверяет membership/project role.
    """
    if user.global_role == "superadmin":
        stmt = (
            select(Run)
            .join(Deal, Run.deal_id == Deal.id)
            .where(Run.id == run_id)
        )
    else:
        stmt = (
            select(Run)
            .join(Deal, Run.deal_id == Deal.id)
            .where(Run.id == run_id, Deal.tenant_id == user.tenant_id)
        )

    result = await db.execute(stmt)
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found",
        )
    return run


async def require_project_role(
    db: AsyncSession,
    user: CurrentUser,
    deal_id: UUID,
    allowed_roles: Iterable[ProjectRole],
) -> None:
    """
    Проверяет tenant isolation И роль пользователя внутри проекта.

    Правила:
    - superadmin   → доступ всегда
    - tenant_admin → доступ ко всем проектам своего tenant'а
    - member       → только через deal_members с разрешённой ролью

    Raises:
      403 — cross-tenant access
      403 — insufficient project role
      404 — deal not found
    """
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


def require_tenant_scope_access(
    user: CurrentUser,
    tenant_id: UUID,
) -> None:
    """
    Проверяет доступ к tenant-scope ресурсам.

    Для endpoints /tenants/{tenant_id}/... (instruction overrides, etc.)

    Правила:
    - superadmin   → любой tenant
    - tenant_admin → только свой tenant
    - member       → forbidden (tenant-wide ресурсы недоступны member'ам)

    Raises:
      403 — forbidden
    """
    if user.global_role == "superadmin":
        return

    if user.global_role == "tenant_admin":
        if user.tenant_id == tenant_id:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant access forbidden",
        )

    # member → forbidden for tenant-wide resources
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Tenant-wide resources require tenant_admin or superadmin role",
    )


