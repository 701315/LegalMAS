# src/db/repositories/user_repo.py

"""
Репозиторий для CRUD-операций с пользователями (User).

Чистая модель:
- только реальные пользователи из таблицы users;
- логин по email;
- get_by_email возвращает только активного пользователя
  из активного tenant'а.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.tenant import Tenant
from db.models.user import User


class UserRepository:
    """
    Репозиторий для работы с пользователями системы.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        email: str,
        password_hash: str,
        full_name: str | None = None,
        system_role: str = "member",
        user_id: uuid.UUID | None = None,
    ) -> User:
        """
        Создать нового пользователя.

        email всегда нормализуется к lowercase.
        """
        normalized_email = email.strip().lower()

        kwargs: dict = {
            "tenant_id": tenant_id,
            "email": normalized_email,
            "password_hash": password_hash,
            "full_name": full_name,
            "system_role": system_role,
        }
        if user_id is not None:
            kwargs["id"] = user_id

        user = User(**kwargs)
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """Найти пользователя по UUID."""
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """
        Найти активного пользователя по email.

        Возвращает пользователя только если:
        - user.is_active = True
        - tenant.is_active = True
        """
        normalized_email = email.strip().lower()

        stmt = (
            select(User)
            .join(Tenant, User.tenant_id == Tenant.id)
            .where(
                User.email == normalized_email,
                User.is_active.is_(True),
                Tenant.is_active.is_(True),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email_any(self, email: str) -> User | None:
        """
        Найти пользователя по email без фильтра по is_active.
        Используется в admin-операциях.
        """
        normalized_email = email.strip().lower()

        result = await self.session.execute(
            select(User).where(User.email == normalized_email)
        )
        return result.scalar_one_or_none()

    async def get_by_tenant(
        self,
        tenant_id: uuid.UUID,
        *,
        include_inactive: bool = False,
    ) -> list[User]:
        """
        Вернуть всех пользователей tenant'а.
        """
        stmt = (
            select(User)
            .where(User.tenant_id == tenant_id)
            .order_by(User.created_at.asc())
        )
        if not include_inactive:
            stmt = stmt.where(User.is_active.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        user_id: uuid.UUID,
        *,
        full_name: str | None = None,
        clear_full_name: bool = False,
        system_role: str | None = None,
        password_hash: str | None = None,
    ) -> User | None:
        """
        Обновить данные пользователя.
        """
        values: dict = {}
        if clear_full_name:
            values["full_name"] = None
        elif full_name is not None:
            values["full_name"] = full_name

        if system_role is not None:
            values["system_role"] = system_role

        if password_hash is not None:
            values["password_hash"] = password_hash

        if not values:
            return await self.get_by_id(user_id)

        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(**values)
            .returning(User)
        )
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            await self.session.flush()
        return user

    async def set_active(
        self,
        user_id: uuid.UUID,
        *,
        is_active: bool,
    ) -> User | None:
        """
        Активировать или деактивировать пользователя.
        """
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(is_active=is_active)
            .returning(User)
        )
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            await self.session.flush()
        return user
    

    