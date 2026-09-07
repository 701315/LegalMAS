# src/db/models/user.py

"""
ORM-модель User — пользователь системы.

User принадлежит ровно одному Tenant и имеет:
- system_role — определяет глобальные права в системе;
- email и password_hash — для аутентификации;
- флаг активности is_active.

Системные роли (system_role):
- "superadmin"   : полный доступ ко всем tenant'ам и всем данным системы.
                   Не привязан к конкретному tenant'у (хотя технически
                   хранится с tenant_id для целостности данных).
                   Назначается только вручную через seed или SQL.
- "tenant_admin" : управляет своим tenant'ом — создаёт пользователей,
                   назначает их на проекты, видит все сделки tenant'а.
- "member"       : базовая роль. Видит только те сделки, в которые добавлен
                   через DealMember. Права внутри сделки определяются
                   ProjectRole из таблицы deal_members.

Двухуровневая модель ролей:
- system_role (эта модель) — кто ты в системе глобально.
- ProjectRole (deal_members) — что ты можешь в конкретной сделке.

Связь с auth:
- При логине: найти User по email, проверить password_hash через bcrypt,
  выдать JWT с payload {user_id, tenant_id, system_role, email}.
- get_current_user декодирует JWT и возвращает CurrentUser
  with данные из этого payload.

Безопасность:
- Никогда не хранить пароль в открывом виде.
- password_hash генерируется через bcrypt в auth_service.py.
- При деактивации пользователя (is_active = False) логин блокируется
  на уровне get_by_email (фильтр is_active = True).
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class User(Base):
    """
    Пользователь системы.

    Поля:
    - tenant_id            : к какому tenant принадлежит (FK → tenants.id);
    - email                : уникальный email — основной идентификатор для логина;
    - password_hash        : bcrypt-хэш пароля;
    - full_name            : отображаемое имя в UI (опционально);
    - ui_locale            : выбранный язык интерфейса (UI);
    - default_output_locale: дефолтный язык результатов анализа (отдельная ось!).
    - system_role          : глобальная роль: superadmin / tenant_admin / member;
    - is_active            : False — пользователь деактивирован, логин заблокирован.
    """

    __tablename__ = "users"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Tenant, которому принадлежит пользователь (FK → tenants.id)",
    )

    email: Mapped[str] = mapped_column(
        String(320),
        nullable=False,
        unique=True,
        index=True,
        comment=(
            "Email пользователя — уникальный по всей системе. "
            "Используется как логин."
        ),
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment=(
            "bcrypt-хэш пароля. "
            "Никогда не хранить пароль в открытом виде. "
            "Генерируется через auth_service.hash_password()."
        ),
    )

    full_name: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Полное имя пользователя для отображения в UI",
    )

    ui_locale: Mapped[str | None] = mapped_column(
        String(35),
        nullable=True,
        default=None,
        server_default=None,
        comment="Выбранный язык интерфейса (BCP 47 tag: 'en', 'ru' и др.)",
    )

    default_output_locale: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        default=None,
        server_default=None,
        comment=(
            "Preferred output locale for result presentations (BCP 47: 'en', 'ru'). "
            "Separate axis from ui_locale (Invariant #5). "
            "Used as level-2 fallback in locale resolution chain when "
            "no explicit presentation_locale is requested. "
            "Validated against result_locales.json at write/update time."
        ),
    )

    system_role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="member",
        server_default="member",
        comment=(
            "Системная роль пользователя: "
            "superadmin — полный доступ ко всем tenant'ам; "
            "tenant_admin — управляет своим tenant'ом; "
            "member — доступ только к разрешённым проектам."
        ),
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment=(
            "False — пользователь деактивирован, логин заблокирован. "
            "Данные пользователя при этом не удаляются."
        ),
    )


    