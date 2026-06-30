# src/api/endpoints/user_projects.py

"""
User projects API.

GET /api/v1/user/{user_id}/projects

Логика:
- superadmin   → все проекты всех клиентов
- tenant_admin → все проекты своего tenant'а
- member       → только проекты, в которые он добавлен через deal_members
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from db.repositories.deal_repo import DealRepository
from db.repositories.project_role_repo import ProjectRoleRepository
from db.session import get_db

router = APIRouter(prefix="/api/v1/user", tags=["user-projects"])


class UserProject(BaseModel):
    deal_id: str
    deal_name: str
    role: Literal["admin", "editor", "viewer"]
    created_at: str
    contact_person: str | None = None


@router.get("/{user_id}/projects", response_model=list[UserProject])
async def list_user_projects(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Список проектов, доступных пользователю.

    Правила:
    - superadmin может получать список проектов только для самого себя,
      но увидит все проекты всех клиентов;
    - tenant_admin может получать список проектов только для самого себя,
      и увидит все проекты своего tenant'а;
    - member может получать список проектов только для самого себя,
      и увидит только membership-проекты.
    """
    if user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ACCESS_DENIED: cannot request projects for another user",
        )

    deal_repo = DealRepository(db)
    role_repo = ProjectRoleRepository(db)

    if current_user.global_role == "superadmin":
        deals = await deal_repo.get_all()
        return [
            UserProject(
                deal_id=str(d.id),
                deal_name=d.name,
                role="admin",
                created_at=d.created_at.isoformat(),
                contact_person=(
                    (d.metadata_ or {}).get("contact_person")
                    if getattr(d, "metadata_", None) is not None
                    else None
                ),
            )
            for d in deals
        ]

    if current_user.global_role == "tenant_admin":
        deals = await deal_repo.get_by_tenant(current_user.tenant_id)
        return [
            UserProject(
                deal_id=str(d.id),
                deal_name=d.name,
                role="admin",
                created_at=d.created_at.isoformat(),
                contact_person=(
                    (d.metadata_ or {}).get("contact_person")
                    if getattr(d, "metadata_", None) is not None
                    else None
                ),
            )
            for d in deals
        ]

    memberships = await role_repo.list_deals_for_user(current_user.id)

    projects: list[UserProject] = []
    for membership in memberships:
        deal = await deal_repo.get_by_id(membership.deal_id)
        if deal is None:
            continue

        projects.append(
            UserProject(
                deal_id=str(deal.id),
                deal_name=deal.name,
                role=membership.role,
                created_at=deal.created_at.isoformat(),
                contact_person=(
                    (deal.metadata_ or {}).get("contact_person")
                    if getattr(deal, "metadata_", None) is not None
                    else None
                ),
            )
        )

    return projects


