# src/db/repositories/project_role_repo.py

from __future__ import annotations

from typing import Optional, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, update

ProjectMemberModel = None  # ВРЕМЕННАЯ ЗАГЛУШКА, заменить на реальную модель.

# Явный тип ролей проекта, синхронизированный с фронтендом
ProjectRole = Literal["admin", "editor", "viewer"]


class ProjectRoleRepository:
    """
    Репозиторий для чтения/записи ролей пользователей в проектах.

    ВАЖНО:
    - Сейчас реализация заглушечная (ProjectMemberModel = None).
    - После появления реальной модели нужно:
        1) импортировать её (см. комментарий выше),
        2) заменить заглушки в методах на реальные запросы.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_role(self, user_id: str, deal_id: UUID) -> Optional[ProjectRole]:
        """
        Вернуть роль пользователя в проекте (сделке), либо None, если записи нет.

        Ожидаемая логика (после реализации ORM-модели):

            stmt = (
                select(ProjectMemberModel.role)
                .where(
                    ProjectMemberModel.user_id == user_id,
                    ProjectMemberModel.deal_id == deal_id,
                )
            )
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()

        ВРЕМЕННО:
        - Пока таблицы нет, просто возвращаем "admin", чтобы не ломать
          существующую логику.
        - В ПРОДАКШЕНЕ ТАК ОСТАВЛЯТЬ НЕЛЬЗЯ.
        """
        if ProjectMemberModel is None:
            # Заглушка: считаем всех админами.
            return "admin"

        # Реальный код будет здесь (см. комментарий выше).
        raise NotImplementedError(
            "ProjectMemberModel is defined, implement get_role()"
        )

    async def set_role(self, user_id: str, deal_id: UUID, role: ProjectRole) -> None:
        """
        Установить/обновить роль пользователя в проекте.

        Ожидаемая логика (после реализации ORM-модели):

            # попытаться обновить существующую запись
            stmt = (
                update(ProjectMemberModel)
                .where(
                    ProjectMemberModel.user_id == user_id,
                    ProjectMemberModel.deal_id == deal_id,
                )
                .values(role=role)
                .execution_options(synchronize_session="fetch")
            )
            result = await self.db.execute(stmt)
            if result.rowcount == 0:
                # если запись не обновилась — вставляем новую
                stmt_insert = insert(ProjectMemberModel).values(
                    user_id=user_id,
                    deal_id=deal_id,
                    role=role,
                )
                await self.db.execute(stmt_insert)

            await self.db.commit()

        ВРЕМЕННО:
        - Пока модели нет, метод ничего не делает, но интерфейс уже готов.
        """
        if ProjectMemberModel is None:
            # Заглушка: роль никуда не сохраняется.
            return

        # Реальный код будет здесь (см. комментарий выше).
        raise NotImplementedError(
            "ProjectMemberModel is defined, implement set_role()"
        )
