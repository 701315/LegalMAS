# src/db/models/tenant.py

"""
ORM-модель Tenant — клиент системы.

Tenant — верхнеуровневая сущность изоляции данных.

Каждый Deal, User и все связанные артефакты принадлежат ровно одному Tenant.
Это обеспечивает:
- data isolation: клиент A никогда не видит данные клиента B;
- namespace в MinIO: tenants/{tenant_id}/deals/...;
- фильтрацию в API: все запросы автоматически ограничены tenant'ом
  текущего пользователя.

Жизненный цикл:
- SUPER_ADMIN создаёт Tenant через административный API;
- при создании Tenant SUPER_ADMIN назначает первого пользователя
  с system_role = 'tenant_admin';
- Tenant можно деактивировать (is_active = False) — тогда
  все пользователи этого tenant'а не смогут войти в систему.

Историческая справка:
- tenant layer был введён миграцией B1;
- на раннем этапе существующие deals были backfill'ены в seed tenant;
- current runtime больше не использует DEV_TENANT_ID.

Следующий шаг (B5):
- добавляется admin UI для управления tenant'ами через браузер.
"""

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class Tenant(Base):
    """
    Клиент системы (организация или физическое лицо).

    Поля:
    - name     : отображаемое название клиента (например "Ромашка Лигал");
    - slug     : короткий уникальный идентификатор (латиница, цифры, дефис);
    - is_active: флаг активности; деактивация блокирует всех пользователей
                 этого tenant'а без удаления данных;
    - notes    : произвольные заметки системного администратора (опционально).
    """

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Отображаемое название клиента",
    )

    slug: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        comment=(
            "Короткий уникальный идентификатор: только латиница, цифры, дефис. "
            "Используется в логах, отладке и URL-friendly контекстах."
        ),
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment=(
            "False — tenant деактивирован, логин всех его пользователей заблокирован. "
            "Данные при этом не удаляются."
        ),
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Произвольные заметки системного администратора о клиенте",
    )

    