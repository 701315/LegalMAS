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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from db.models.document import Document
from db.models.run import Run
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
    needs_setup: bool = False
    analysis_completed: bool = False
    is_processing: bool = False


def _contact_person(deal) -> str | None:
    """Безопасно извлечь contact_person из metadata_."""
    meta = getattr(deal, "metadata_", None)
    if meta is None:
        return None
    return meta.get("contact_person")


async def _analysis_completed(db: AsyncSession, deal) -> bool:
    """
    Вернуть True если последний Run по проекту имеет статус completed.
    """
    last_run_id = getattr(deal, "last_run_id", None)
    if not last_run_id:
        return False

    result = await db.execute(
        select(Run.status).where(Run.id == last_run_id)
    )
    run_status = result.scalar_one_or_none()
    return run_status == "completed"


async def _is_processing(db: AsyncSession, deal) -> bool:
    """
    Вернуть True если проект находится в процессе обработки.

    Универсальная логика для любого юридического документа:
    - language discovery ещё не завершён (pre-run этап);
    - последний Run в нетерминальном статусе (основной анализ).
    """
    ld_status = getattr(deal, "language_discovery_status", None)
    if ld_status in ("pending", "processing"):
        return True

    last_run_id = getattr(deal, "last_run_id", None)
    if last_run_id:
        result = await db.execute(
            select(Run.status).where(Run.id == last_run_id)
        )
        run_status = result.scalar_one_or_none()
        if run_status in ("pending", "running"):
            return True

    return False


async def _needs_setup(db: AsyncSession, deal) -> bool:
    """
    Вернуть True если проект не готов к запуску анализа.

    Проект считается незавершённым если хотя бы одно из:
    - нет загруженных документов
    - не выбран playbook
    - не выбран основной язык анализа
    """
    if not deal.playbook_version_id or not deal.primary_language:
        return True

    result = await db.execute(
        select(func.count(Document.id)).where(
            Document.deal_id == deal.id
        )
    )
    documents_count = result.scalar_one()
    return documents_count == 0


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
        deals = await deal_repo.unsafe_get_all_platform_admin_only()
        projects = []
        for d in deals:
            projects.append(
                UserProject(
                    deal_id=str(d.id),
                    deal_name=d.name,
                    role="admin",
                    created_at=d.created_at.isoformat(),
                    contact_person=_contact_person(d),
                    needs_setup=await _needs_setup(db, d),
                    analysis_completed=await _analysis_completed(db, d),
                    is_processing=await _is_processing(db, d),
                )
            )
        return projects

    if current_user.global_role == "tenant_admin":
        deals = await deal_repo.get_by_tenant(current_user.tenant_id)
        projects = []
        for d in deals:
            projects.append(
                UserProject(
                    deal_id=str(d.id),
                    deal_name=d.name,
                    role="admin",
                    created_at=d.created_at.isoformat(),
                    contact_person=_contact_person(d),
                    needs_setup=await _needs_setup(db, d),
                    analysis_completed=await _analysis_completed(db, d),
                    is_processing=await _is_processing(db, d),
                )
            )
        return projects

    # member: только проекты через deal_members
    memberships = await role_repo.list_deals_for_user(current_user.id)

    projects: list[UserProject] = []
    for membership in memberships:
        deal = await deal_repo.get_by_id(
            deal_id=membership.deal_id,
            tenant_id=current_user.tenant_id,
        )
        if deal is None:
            continue

        projects.append(
            UserProject(
                deal_id=str(deal.id),
                deal_name=deal.name,
                role=membership.role,
                created_at=deal.created_at.isoformat(),
                contact_person=_contact_person(deal),
                needs_setup=await _needs_setup(db, deal),
                analysis_completed=await _analysis_completed(db, deal),
                is_processing=await _is_processing(db, deal),
            )
        )

    return projects


