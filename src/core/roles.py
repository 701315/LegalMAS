# src/core/roles.py

"""
Общие типы ролей для всей системы (системные и проектные).

Двухуровневая модель ролей:
- SystemRole — кто пользователь в системе глобально (users.system_role).
- ProjectRole — что пользователь может в конкретной сделке
  (deal_members.role).

Важно:
- системные роли и проектные роли — разные измерения доступа;
- проектная роль не должна дублировать системную роль.
"""

from __future__ import annotations

from typing import Literal

# ── Проектные роли (per-deal) ─────────────────────────────────────────────

ProjectRole = Literal["admin", "editor", "viewer"]
"""
Роль пользователя на уровне конкретного проекта/сделки.

Семантика:
- "admin"  : полный доступ к проекту — управление участниками, документами,
             запуском анализа.
- "editor" : может изменять данные проекта и запускать анализ,
             но не управляет участниками.
- "viewer" : только просмотр.

Хранится в таблице deal_members.role.
"""

# ── Системные роли (global / tenant-level) ────────────────────────────────

SystemRole = Literal["superadmin", "tenant_admin", "member"]
"""
Канонические системные роли пользователя в платформе (users.system_role).

- "superadmin"   : полный доступ ко всем tenant'ам и всем данным.
                   Может управлять клиентами и их пользователями.
- "tenant_admin" : управляет своим tenant'ом.
                   Видит все проекты своего tenant'а без явного membership.
                   Может создавать проекты и управлять пользователями клиента.
- "member"       : обычный пользователь tenant'а.
                   Видит только проекты, в которые добавлен через deal_members.
"""

# Для совместимости с CurrentUser/globalRole на фронте оставляем тот же alias.
GlobalRole = SystemRole


def normalize_system_role(role: str | None) -> SystemRole:
    """
    Привести строковое значение роли к канонической системной роли.

    В чистой модели поддерживаются только:
    - superadmin
    - tenant_admin
    - member

    Любое неизвестное значение интерпретируется как "member".
    Это безопасный fail-closed вариант.
    """
    if role == "superadmin":
        return "superadmin"
    if role == "tenant_admin":
        return "tenant_admin"
    return "member"


def is_tenant_scoped_admin(role: str) -> bool:
    """
    True если роль даёт административные права на уровне tenant'а.
    """
    return role in ("superadmin", "tenant_admin")


__all__ = [
    "ProjectRole",
    "SystemRole",
    "GlobalRole",
    "normalize_system_role",
    "is_tenant_scoped_admin",
]


