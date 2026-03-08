# src/db/repositories/project_role_repo.py

"""
Репозиторий для ролей пользователей в проектах (сделках).

Зачем нужен этот репозиторий
----------------------------
На фронте уже есть разделение ролей по проектам (projectRoles[dealId]):
- "admin"  — полный доступ к проекту;
- "editor" — может запускать анализ, править QC, переклассифицировать документы;
- "viewer" — только просмотр.

На бэкенде нужно хранить эти роли в БД, чтобы:
- проверять права при запуске анализа (run);
- проверять права при QC (confirm/reject/override);
- проверять права при загрузке документов;
- проверять доступ при ручной переклассификации документа;
- управлять участниками проекта и их ролями.

Ожидаемая таблица (примерная схема)
-----------------------------------
Название таблицы: project_members (или deal_members, на твой вкус).

Поля:
- id         UUID (PK)                 — опционально, можно и без отдельного id
- deal_id    UUID (FK -> deals.id)     — проект/сделка
- user_id    UUID (FK -> users.id)     — пользователь
- role       TEXT                      — "admin" / "editor" / "viewer"
- created_at TIMESTAMP WITH TIME ZONE  — когда добавили
- updated_at TIMESTAMP WITH TIME ZONE  — когда поменяли роль

Далее ниже — простой репозиторий, который умеет:
- получить роль пользователя в проекте;
- задать/обновить роль (для административных эндпоинтов).
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, insert, update

# Здесь должен быть импорт ORM-модели таблицы project_members/deal_members.
# Когда такая таблица будет создана, нужно:
# 1) добавить её в db/models/...py
# 2) заменить ProjectMemberModel на реальную модель.
#
# Пример (который нужно будет реализовать позже):
# from db.models.project_member import ProjectMember as ProjectMemberModel
#
ProjectMemberModel = None  # ВРЕМЕННАЯ ЗАГЛУШКА, заменить на реальную модель.


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

    async def get_role(self, user_id: str, deal_id: UUID) -> Optional[str]:
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
        raise NotImplementedError("ProjectMemberModel is defined, implement get_role()")

    async def set_role(self, user_id: str, deal_id: UUID, role: str) -> None:
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
        raise NotImplementedError("ProjectMemberModel is defined, implement set_role()")
