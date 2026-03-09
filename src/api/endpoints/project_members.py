# src/api/endpoints/project_members.py

"""
Эндпоинты управления участниками проектов (project members).

Назначение файла:
- Даёт REST-API для списка участников проекта и их ролей.
- Позволяет добавлять, изменять и удалять участников конкретной сделки (deal_id).
- Используется фронтендом на странице "Участники проекта".

Ключевые моменты:
- Все данные берутся из таблицы deal_members через ProjectRoleRepository.
- Проверка прав делается через require_project_role:
  - смотреть список участников могут все залогиненные пользователи (пока без ограничений);
  - добавлять/изменять/удалять участников могут только project admin-ы.
- В ответах API внешний идентификатор участника называется member_id,
- внутри ORM-модели это поле называется id (есть явное отображение id -> member_id).
+ В ответах API внешний идентификатор участника называется member_id,
+ внутри ORM-модели это поле называется id; отображение id -> member_id
+ инкапсулировано в api.mappers.project_members.

"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.mappers.project_members import (
    map_member_to_response,
    map_members_to_response,
)

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from api.schemas.project_members import (
    ProjectMemberResponse,
    CreateProjectMember,
    UpdateProjectMember,
)
from db.session import get_db
from db.repositories.project_role_repo import ProjectRoleRepository
from db.models.deal_member import DealMember

router = APIRouter(
    prefix="/projects",
    tags=["project-members"],
)


@router.get(
    "/{deal_id}/members",
    response_model=List[ProjectMemberResponse],
    summary="Список участников проекта",
)
async def list_project_members(
    deal_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Список участников проекта для указанной сделки.

    Сейчас:
    - любой залогиненный пользователь может смотреть список участников;
    - позже можно добавить require_project_role(..., allowed_roles=("viewer","editor","admin")).
    """
    repo = ProjectRoleRepository(db)
    members = await repo.list_members(deal_id)

    return map_members_to_response(members)


@router.post(
    "/{deal_id}/members",
    response_model=ProjectMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить участника проекта",
)
async def create_project_member(
    deal_id: UUID,
    payload: CreateProjectMember,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    # Разрешаем только project admin (при глобальной роли admin/editor).
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin",),
    )

    repo = ProjectRoleRepository(db)

    # Проверка уникальности логина
    existing = await db.execute(
        select(DealMember).where(DealMember.login == payload.login)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LOGIN_TAKEN",
        )

    member = await repo.create_member(
        deal_id=deal_id,
        name=payload.name,
        login=payload.login,
        role=payload.role,
    )

    await db.commit()

    return map_member_to_response(member)


@router.put(
    "/{deal_id}/members/{member_id}",
    response_model=ProjectMemberResponse,
    summary="Обновить участника проекта",
)
async def update_project_member(
    deal_id: UUID,
    member_id: UUID,
    payload: UpdateProjectMember,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin",),
    )

    repo = ProjectRoleRepository(db)

    # Найти текущего участника для проверки логина
    current = await db.get(DealMember, member_id)
    if current is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )

    # Если логин меняется – проверяем уникальность
    if payload.login is not None and payload.login != current.login:
        existing = await db.execute(
            select(DealMember).where(DealMember.login == payload.login)
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="LOGIN_TAKEN",
            )

    member = await repo.update_member(
        member_id=member_id,
        name=payload.name,
        login=payload.login,
        role=payload.role,
    )
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )

    await db.commit()

    return map_member_to_response(member)


@router.delete(
    "/{deal_id}/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить участника проекта",
)
async def delete_project_member(
    deal_id: UUID,
    member_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin",),
    )

    repo = ProjectRoleRepository(db)
    deleted = await repo.remove_member(member_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )

    await db.commit()
