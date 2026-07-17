# src/api/endpoints/project_members.py

"""
Эндпоинты управления участниками проекта.

Чистая модель:
- создаём пользователей отдельно через admin panel;
- здесь только назначаем существующего пользователя в проект;
- здесь только управляем project role.

Маршруты:
- GET    /api/v1/projects/{deal_id}/members
- GET    /api/v1/projects/{deal_id}/available-users
- POST   /api/v1/projects/{deal_id}/members
- PUT    /api/v1/projects/{deal_id}/members/{member_id}
- DELETE /api/v1/projects/{deal_id}/members/{member_id}
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from api.mappers.project_members import (
    map_available_users_to_response,
    map_members_to_response,
    map_member_to_response,
)
from api.schemas.project_members import (
    AvailableProjectUserResponse,
    CreateProjectMember,
    ProjectMemberResponse,
    UpdateProjectMember,
)
from db.repositories.deal_repo import DealRepository
from db.repositories.project_role_repo import ProjectRoleRepository
from db.repositories.user_repo import UserRepository
from db.session import get_db

router = APIRouter(
    prefix="/projects",
    tags=["project-members"],
)


@router.get(
    "/{deal_id}/members",
    response_model=list[ProjectMemberResponse],
    summary="Список участников проекта",
)
async def list_project_members(
    deal_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Список участников проекта.

    Доступ:
    - superadmin
    - tenant_admin того же tenant'а
    - любой member, у которого есть access к проекту
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    repo = ProjectRoleRepository(db)
    members = await repo.list_members(deal_id)
    return map_members_to_response(members)


@router.get(
    "/{deal_id}/available-users",
    response_model=list[AvailableProjectUserResponse],
    summary="Пользователи tenant'а, которых можно добавить в проект",
)
async def list_available_users_for_project(
    deal_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Вернуть активных пользователей tenant'а сделки,
    которые ещё не добавлены в проект.

    Доступ:
    - superadmin
    - tenant_admin того же tenant'а
    - project admin
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin",),
    )

    repo = ProjectRoleRepository(db)
    users = await repo.list_available_users(deal_id)
    return map_available_users_to_response(users)


@router.post(
    "/{deal_id}/members",
    response_model=ProjectMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить существующего пользователя в проект",
)
async def create_project_member(
    deal_id: UUID,
    payload: CreateProjectMember,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Добавить существующего пользователя в проект и назначить project role.

    Проверки:
    - проект существует;
    - пользователь существует;
    - пользователь активен;
    - пользователь принадлежит тому же tenant'у, что и проект;
    - пользователь ещё не состоит в этом проекте.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin",),
    )

    deal_repo = DealRepository(db)
    user_repo = UserRepository(db)
    role_repo = ProjectRoleRepository(db)

    deal = await deal_repo.get_by_id(deal_id, tenant_id=user.tenant_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")

    target_user = await user_repo.get_by_id(payload.user_id)
    if target_user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if not target_user.is_active:
        raise HTTPException(
            status_code=400,
            detail="Cannot add inactive user to project",
        )

    if target_user.tenant_id != deal.tenant_id:
        raise HTTPException(
            status_code=400,
            detail="User belongs to another tenant",
        )

    existing_role = await role_repo.get_role(payload.user_id, deal_id)
    if existing_role is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="USER_ALREADY_IN_PROJECT",
        )

    try:
        member = await role_repo.create_member(
            deal_id=deal_id,
            user_id=payload.user_id,
            role=payload.role,
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="USER_ALREADY_IN_PROJECT",
        )

    member_view = await role_repo.get_member_view(member.id)
    if member_view is None:
        raise HTTPException(
            status_code=500,
            detail="Failed to build project member response",
        )

    return map_member_to_response(member_view)


@router.put(
    "/{deal_id}/members/{member_id}",
    response_model=ProjectMemberResponse,
    summary="Изменить project role участника",
)
async def update_project_member(
    deal_id: UUID,
    member_id: UUID,
    payload: UpdateProjectMember,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Изменить только project role участника проекта.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin",),
    )

    role_repo = ProjectRoleRepository(db)
    updated = await role_repo.update_member_role(
        member_id=member_id,
        role=payload.role,
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )

    await db.commit()

    member_view = await role_repo.get_member_view(member_id)
    if member_view is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )

    return map_member_to_response(member_view)


@router.delete(
    "/{deal_id}/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить участника из проекта",
)
async def delete_project_member(
    deal_id: UUID,
    member_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Удалить membership пользователя из проекта.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin",),
    )

    role_repo = ProjectRoleRepository(db)
    deleted = await role_repo.remove_member(member_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )

    await db.commit()

    