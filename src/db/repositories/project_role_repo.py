# src/db/repositories/project_role_repo.py
"""
Репозиторий для работы с ролями участников проектов (сделок).

Назначение:
- Инкапсулирует доступ к таблице deal_members.
- Предоставляет методы:
  - get_role(user_id, deal_id)     — получить проектную роль пользователя;
  - set_role(user_id, deal_id, ..) — установить/обновить проектную роль;
  - list_members(deal_id)          — список участников сделки;
  - create_member(...)             — создать участника проекта;
  - update_member(member_id, ...)  — обновить данные участника;
  - remove_member(member_id)       — удалить участника.

Роль в архитектуре RBAC:
- Используется:
  - в require_project_role для проверки прав на уровне одной сделки;
  - в эндпоинтах project_members для CRUD участников проекта.
- Не содержит бизнес-логики UI или глобальных ролей (GlobalRole),
  только работу с данными deal_members.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, update, delete

from db.models.deal_member import DealMember
from core.roles import ProjectRole  # Literal["admin", "editor", "viewer"]


class ProjectRoleRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_role(self, user_id: str, deal_id: UUID) -> Optional[ProjectRole]:
        """
        Вернуть проектную роль пользователя в сделке или None, если записи нет.
        """
        stmt = (
            select(DealMember.role)
            .where(
                DealMember.user_id == user_id,
                DealMember.deal_id == deal_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def set_role(self, user_id: str, deal_id: UUID, role: ProjectRole) -> None:
        """
        Установить/обновить проектную роль пользователя в сделке.

        Поведение:
        - если запись (deal_id, user_id) существует — обновляет поле role;
        - если записи нет — создаёт новую запись с минимально заполненными
          name/login (name="", login=user_id).

        Используется в low-level сценариях, когда нужно именно задать роль,
        а не управлять участниками через UI-форму.
        """
        stmt = (
            update(DealMember)
            .where(
                DealMember.user_id == user_id,
                DealMember.deal_id == deal_id,
            )
            .values(role=role)
            .execution_options(synchronize_session="fetch")
        )
        result = await self.db.execute(stmt)

        if result.rowcount == 0:
            stmt_insert = insert(DealMember).values(
                user_id=user_id,
                deal_id=deal_id,
                role=role,
                name="",   # при чистом set_role пока не трогаем name/login
                login=user_id,
            )
            await self.db.execute(stmt_insert)

        await self.db.flush()

    async def list_members(self, deal_id: UUID) -> list[DealMember]:
        """
        Вернуть всех участников сделки с их ролями.
        """
        stmt = (
            select(DealMember)
            .where(DealMember.deal_id == deal_id)
            .order_by(DealMember.created_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create_member(
        self,
        deal_id: UUID,
        name: str,
        login: str,
        role: ProjectRole,
    ) -> DealMember:
        """
        Создать нового участника проекта.

        В текущем dev-варианте:
        - user_id равен login (до появления реальной таблицы users).
        """
        member = DealMember(
            deal_id=deal_id,
            name=name,
            login=login,
            user_id=login,
            role=role,
        )
        self.db.add(member)
        await self.db.flush()
        return member

    async def update_member(
        self,
        member_id: UUID,
        *,
        name: str | None = None,
        login: str | None = None,
        role: ProjectRole | None = None,
    ) -> DealMember | None:
        """
        Обновить данные участника проекта по его идентификатору.

        - Если указаны name/login/role — обновляет только их.
        - Если ничего не указано — просто возвращает текущую запись.
        - При смене login синхронизирует и user_id (пока user_id=login).
        """
        values: dict = {}
        if name is not None:
            values["name"] = name
        if login is not None:
            values["login"] = login
            values["user_id"] = login
        if role is not None:
            values["role"] = role

        if not values:
            stmt = select(DealMember).where(DealMember.id == member_id)
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()

        stmt = (
            update(DealMember)
            .where(DealMember.id == member_id)
            .values(**values)
            .returning(DealMember)
        )
        result = await self.db.execute(stmt)
        member = result.scalar_one_or_none()
        if member:
            await self.db.flush()
        return member

    async def remove_member(self, member_id: UUID) -> bool:
        """
        Удалить участника проекта по его идентификатору.

        Возвращает:
        - True, если участник был удалён;
        - False, если записи с таким id не было.
        """
        stmt = delete(DealMember).where(DealMember.id == member_id)
        result = await self.db.execute(stmt)
        deleted = result.rowcount > 0
        if deleted:
            await self.db.flush()
        return deleted
