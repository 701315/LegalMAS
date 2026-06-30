# src/db/models/deal_member.py

"""
ORM-модель membership пользователя в конкретном проекте (сделке).

Чистая модель:
- deal_members не создаёт пользователей;
- deal_members только связывает существующего User с Deal;
- membership хранит исключительно project role.

Итоговая схема:
- deal_id  -> FK deals.id
- user_id  -> FK users.id
- role     -> ProjectRole (admin/editor/viewer)

Один пользователь может участвовать в любом количестве проектов
своего tenant'а.
В рамках одного проекта пользователь может иметь только одну роль:
UNIQUE (deal_id, user_id).
"""

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.roles import ProjectRole

from ..base import Base


class DealMember(Base):
    __tablename__ = "deal_members"

    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Проект (сделка), в котором состоит пользователь",
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Существующий пользователь системы (FK users.id)",
    )

    role: Mapped[ProjectRole] = mapped_column(
        String(20),
        nullable=False,
        comment="Роль пользователя внутри проекта: admin/editor/viewer",
    )

    __table_args__ = (
        UniqueConstraint(
            "deal_id",
            "user_id",
            name="uq_deal_members_deal_user",
        ),
    )


    