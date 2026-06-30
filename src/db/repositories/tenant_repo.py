# src/db/repositories/tenant_repo.py

"""
Репозиторий для CRUD-операций с клиентами (Tenant).

Принципы:
- Никакой бизнес-логики — только чтение/запись/поиск в БД.
- Все операции через переданную AsyncSession.
- Commit не вызывается внутри репозитория — это ответственность вызывающего кода.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.tenant import Tenant


class TenantRepository:
    """
    Репозиторий для работы с tenant'ами (клиентами системы).

    Экземпляр живёт внутри одного запроса / юнита работы.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        name: str,
        slug: str,
        notes: str | None = None,
        tenant_id: uuid.UUID | None = None,
    ) -> Tenant:
        """
        Создать нового tenant'а и сохранить в БД (flush, без commit).

        Параметры:
        - name      : отображаемое название клиента;
        - slug      : уникальный короткий идентификатор (латиница, цифры, дефис);
        - notes     : заметки администратора (опционально);
        - tenant_id : явный UUID — только для seed/миграций, обычно None
                      (в обычных сценариях UUID генерируется автоматически).
        """
        kwargs: dict = {"name": name, "slug": slug, "notes": notes}
        if tenant_id is not None:
            kwargs["id"] = tenant_id
        tenant = Tenant(**kwargs)
        self.session.add(tenant)
        await self.session.flush()
        return tenant

    async def get_by_id(self, tenant_id: uuid.UUID) -> Tenant | None:
        """
        Найти tenant по UUID.

        Возвращает Tenant или None если не найден.
        """
        result = await self.session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Tenant | None:
        """
        Найти tenant по slug.

        Возвращает Tenant или None если не найден.
        Используется для проверки уникальности при создании.
        """
        result = await self.session.execute(
            select(Tenant).where(Tenant.slug == slug)
        )
        return result.scalar_one_or_none()

    async def get_all(self, *, include_inactive: bool = False) -> list[Tenant]:
        """
        Вернуть список всех tenant'ов, отсортированный по дате создания.

        Параметры:
        - include_inactive: True — вернуть все tenant'ы включая деактивированных;
                            False (по умолчанию) — только активные.
        """
        stmt = select(Tenant).order_by(Tenant.created_at.asc())
        if not include_inactive:
            stmt = stmt.where(Tenant.is_active.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        tenant_id: uuid.UUID,
        *,
        name: str | None = None,
        slug: str | None = None,
        notes: str | None = None,
        clear_notes: bool = False,
    ) -> Tenant | None:
        """
        Обновить данные tenant'а. Изменяются только переданные поля.

        Параметры:
        - name       : новое название (None → не менять);
        - slug       : новый slug (None → не менять);
        - notes      : новые заметки (None → не менять, если clear_notes=False);
        - clear_notes: True → записать NULL в notes независимо от значения notes.

        Возвращает обновлённый Tenant или None если не найден.
        """
        values: dict = {}
        if name is not None:
            values["name"] = name
        if slug is not None:
            values["slug"] = slug
        if clear_notes:
            values["notes"] = None
        elif notes is not None:
            values["notes"] = notes

        if not values:
            return await self.get_by_id(tenant_id)

        stmt = (
            update(Tenant)
            .where(Tenant.id == tenant_id)
            .values(**values)
            .returning(Tenant)
        )
        result = await self.session.execute(stmt)
        tenant = result.scalar_one_or_none()
        if tenant:
            await self.session.flush()
        return tenant

    async def set_active(
        self,
        tenant_id: uuid.UUID,
        *,
        is_active: bool,
    ) -> Tenant | None:
        """
        Активировать или деактивировать tenant.

        При деактивации (is_active=False) логин всех пользователей
        этого tenant'а блокируется на уровне get_by_email в UserRepository.

        Возвращает обновлённый Tenant или None если не найден.
        """
        stmt = (
            update(Tenant)
            .where(Tenant.id == tenant_id)
            .values(is_active=is_active)
            .returning(Tenant)
        )
        result = await self.session.execute(stmt)
        tenant = result.scalar_one_or_none()
        if tenant:
            await self.session.flush()
        return tenant
    
    