# src/db/models/deal_member.py

# src/db/models/deal_member.py

"""
ORM-модель участника сделки (проекта).

Назначение:
- Хранит проектные роли пользователей в разрезе конкретной сделки.
- Является источником данных для:
  - проверки прав доступа на уровне проекта (deal_id);
  - экрана "Участники проекта" во фронтенде;
  - функций репозитория ProjectRoleRepository.

Связь с архитектурой RBAC:
- Глобальная роль пользователя хранится отдельно (GlobalRole).
- В этой таблице хранится только проектная роль (ProjectRole: admin/editor/viewer)
  для пары (deal_id, user_id).
- При проверке прав используется комбинация:
  global_role (из CurrentUser) + role из DealMember.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .deal import Deal
from core.roles import ProjectRole  # Literal["admin", "editor", "viewer"]


class DealMember(Base):
    __tablename__ = "deal_members"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(Deal.id, ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Идентификатор пользователя (пока строка/login)",
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    login: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        comment="Уникальный login для dev/pseudo-users",
    )

    role: Mapped[ProjectRole] = mapped_column(
        String(20),
        nullable=False,
        comment="Роль в проекте: admin/editor/viewer",
    )

    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("deal_id", "user_id", name="uq_deal_members_deal_user"),
    )
    
