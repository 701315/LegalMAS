# src/db/repositories/project_role_repo.py

"""
Репозиторий для работы с project memberships (deal_members).

Чистая модель:
- deal_members хранит только связь User ↔ Deal и project role;
- все display-поля (email, full_name, system_role) берутся через JOIN users;
- никакого login/password/name на уровне membership больше нет.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.roles import ProjectRole
from db.models.deal import Deal
from db.models.deal_member import DealMember
from db.models.user import User


@dataclass(frozen=True)
class ProjectMemberView:
    """
    Обогащённое представление участника проекта для API/UI.
    """

    member_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str | None
    system_role: str
    role: ProjectRole
    created_at: datetime


@dataclass(frozen=True)
class AvailableProjectUserView:
    """
    Пользователь tenant'а, которого можно добавить в проект.
    """

    user_id: uuid.UUID
    email: str
    full_name: str | None
    system_role: str


class ProjectRoleRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _coerce_user_id(user_id: str | uuid.UUID) -> uuid.UUID:
        if isinstance(user_id, uuid.UUID):
            return user_id
        return uuid.UUID(str(user_id))

    async def get_role(
        self,
        user_id: str | uuid.UUID,
        deal_id: uuid.UUID,
    ) -> ProjectRole | None:
        """
        Вернуть project role пользователя в проекте или None.
        """
        uid = self._coerce_user_id(user_id)

        stmt = select(DealMember.role).where(
            DealMember.user_id == uid,
            DealMember.deal_id == deal_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_deals_for_user(
        self,
        user_id: str | uuid.UUID,
    ) -> list[DealMember]:
        """
        Вернуть memberships пользователя во всех проектах.
        Используется в user_projects.py.
        """
        uid = self._coerce_user_id(user_id)

        stmt = (
            select(DealMember)
            .where(DealMember.user_id == uid)
            .order_by(DealMember.created_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_members(
        self,
        deal_id: uuid.UUID,
    ) -> list[ProjectMemberView]:
        """
        Вернуть обогащённый список участников проекта через JOIN users.
        """
        stmt = (
            select(
                DealMember.id.label("member_id"),
                User.id.label("user_id"),
                User.email.label("email"),
                User.full_name.label("full_name"),
                User.system_role.label("system_role"),
                DealMember.role.label("role"),
                DealMember.created_at.label("created_at"),
            )
            .join(User, User.id == DealMember.user_id)
            .where(DealMember.deal_id == deal_id)
            .order_by(DealMember.created_at.asc())
        )

        result = await self.db.execute(stmt)
        rows = result.mappings().all()

        return [
            ProjectMemberView(
                member_id=row["member_id"],
                user_id=row["user_id"],
                email=row["email"],
                full_name=row["full_name"],
                system_role=row["system_role"],
                role=row["role"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def get_member_view(
        self,
        member_id: uuid.UUID,
    ) -> ProjectMemberView | None:
        """
        Вернуть одного участника проекта в обогащённом виде.
        """
        stmt = (
            select(
                DealMember.id.label("member_id"),
                User.id.label("user_id"),
                User.email.label("email"),
                User.full_name.label("full_name"),
                User.system_role.label("system_role"),
                DealMember.role.label("role"),
                DealMember.created_at.label("created_at"),
            )
            .join(User, User.id == DealMember.user_id)
            .where(DealMember.id == member_id)
        )

        result = await self.db.execute(stmt)
        row = result.mappings().one_or_none()

        if row is None:
            return None

        return ProjectMemberView(
            member_id=row["member_id"],
            user_id=row["user_id"],
            email=row["email"],
            full_name=row["full_name"],
            system_role=row["system_role"],
            role=row["role"],
            created_at=row["created_at"],
        )

    async def list_available_users(
        self,
        deal_id: uuid.UUID,
    ) -> list[AvailableProjectUserView]:
        """
        Вернуть активных пользователей tenant'а сделки,
        которые ещё не добавлены в этот проект.
        """
        deal_tenant_subquery = (
            select(Deal.tenant_id)
            .where(Deal.id == deal_id)
            .scalar_subquery()
        )

        assigned_users_subquery = (
            select(DealMember.user_id)
            .where(DealMember.deal_id == deal_id)
        )

        stmt = (
            select(
                User.id.label("user_id"),
                User.email.label("email"),
                User.full_name.label("full_name"),
                User.system_role.label("system_role"),
            )
            .where(
                User.tenant_id == deal_tenant_subquery,
                User.is_active.is_(True),
                User.id.not_in(assigned_users_subquery),
            )
            .order_by(User.created_at.asc())
        )

        result = await self.db.execute(stmt)
        rows = result.mappings().all()

        return [
            AvailableProjectUserView(
                user_id=row["user_id"],
                email=row["email"],
                full_name=row["full_name"],
                system_role=row["system_role"],
            )
            for row in rows
        ]

    async def create_member(
        self,
        deal_id: uuid.UUID,
        user_id: str | uuid.UUID,
        role: ProjectRole,
    ) -> DealMember:
        """
        Создать membership пользователя в проекте.
        """
        uid = self._coerce_user_id(user_id)

        member = DealMember(
            deal_id=deal_id,
            user_id=uid,
            role=role,
        )
        self.db.add(member)
        await self.db.flush()
        return member

    async def update_member_role(
        self,
        member_id: uuid.UUID,
        role: ProjectRole,
    ) -> DealMember | None:
        """
        Обновить только project role участника.
        """
        stmt = (
            update(DealMember)
            .where(DealMember.id == member_id)
            .values(role=role)
            .returning(DealMember)
        )
        result = await self.db.execute(stmt)
        member = result.scalar_one_or_none()
        if member:
            await self.db.flush()
        return member

    async def remove_member(self, member_id: uuid.UUID) -> bool:
        """
        Удалить membership по member_id.
        """
        stmt = delete(DealMember).where(DealMember.id == member_id)
        result = await self.db.execute(stmt)
        deleted = result.rowcount > 0
        if deleted:
            await self.db.flush()
        return deleted
    

    