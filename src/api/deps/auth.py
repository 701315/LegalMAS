# src/api/deps/auth.py

"""
Общие зависимости для авторизации / аутентификации в FastAPI.

ВНИМАНИЕ: сейчас здесь временная заглушка CurrentUser/get_current_user.
Когда будем выводить продукт в продакшен с реальными пользователями
и разделением прав, этот модуль НУЖНО будет переписать.

Что должно быть в финальной версии (после внедрения auth):
-----------------------------------------------------------

1. Аутентификация:
   - Фронтенд будет отправлять токен (например, JWT) в заголовке
     Authorization: Bearer <token> или HTTP-only cookie.
   - Функция get_current_user должна:
       а) достать токен из запроса;
       б) проверить его подпись и срок действия;
       в) извлечь из него user_id, глобальную роль, tenant_id и т.п.;
       г) найти пользователя в БД (если требуется) и вернуть объект CurrentUser.

   Примерно так (псевдокод):
       - считать Authorization header
       - проверить токен через библиотеку (pyjwt, authlib, свой код)
       - взять из payload: user_id, global_role, tenant_id
       - вернуть CurrentUser(id=..., global_role=..., tenant_id=..., email=...)

2. Глобальная роль:
   - Поле global_role может быть, например: "superadmin", "tenant_admin",
     "user" и т.п.
   - Сейчас оно используется в RequireSuperadmin на фронте.
   - На бэке global_role пригодится для:
       - эндпоинтов управления тенантами;
       - создания новых проектов;
       - просмотра/управления всеми проектами;
       - доступа к /admin/*.

3. Роли по проектам (projectRoles):
   - На фронте уже есть объект projectRoles[dealId] с ролями "admin"/"editor"/"viewer".
   - На бэке нужна таблица (например, deal_members или project_members),
     где для каждой пары (user_id, deal_id) хранится роль в этом проекте.

     Пример таблицы (логически):
         deal_id   UUID (FK на deals)
         user_id   UUID (FK на users)
         role      TEXT ("admin" / "editor" / "viewer")

   - На основе этой таблицы будет работать репозиторий ProjectRoleRepository
     (см. src/db/repositories/project_role_repo.py).

4. CurrentUser в финальной версии:
   - Должен содержать минимум:
       - id         : UUID | str   — идентификатор пользователя
       - global_role: str          — глобальная роль (superadmin / user / ...)
       - tenant_id  : UUID         — к какому tenant относится
   - Можно добавить:
       - email: str | None         — для удобства логирования и аудита
       - full_name: str | None     — если нужно на фронт
   - Любые дополнительные поля добавлять ТОЛЬКО после того,
     как они реально есть в токене / БД.

5. Как проверять доступ к проекту:
   - В эндпоинтах, которые завязаны на конкретную сделку (deal_id) или проект,
     нужно вызывать функцию вида require_project_role(db, user, deal_id, allowed_roles).
   - Эта функция использует ProjectRoleRepository, чтобы узнать проектную роль
     ("admin" / "editor" / "viewer") и сравнить её с allowed_roles.
   - При недостаточных правах возвращаем HTTP 403.

Текущее (временное) состояние:
------------------------------
- Сейчас CurrentUser и get_current_user — ЗАГЛУШКИ для упрощённой разработки.
- Они всегда возвращают одного и того же "фиктивного" пользователя.
- Это удобно для разработки, но НЕЛЬЗЯ так оставлять в продакшене.
- Временный логин admin/admin (см. src/api/endpoints/auth.py) никак
  не связан с get_current_user: это нормально для dev-режима.
- При внедрении реальной auth нужно будет:
    1) переписать get_current_user так, чтобы он читал и проверял токен;
    2) убедиться, что CurrentUser совпадает со структурой токена/пользователя в БД;
    3) оставить интерфейс (имя функции и поля CurrentUser) прежними,
       чтобы не ломать эндпоинты.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel


class CurrentUser(BaseModel):
    """
    Модель текущего пользователя для использования в эндпоинтах.

    ВРЕМЕННО (до внедрения настоящей авторизации):
    - id          = "system"
    - global_role = "system"
    - tenant_id   = UUID нулевой

    ПОТОМ:
    - id          = реальный user_id из токена / БД
    - global_role = "superadmin" / "tenant_admin" / "user" / ...
    - tenant_id   = реальный tenant_id пользователя
    - email       = e-mail пользователя (опционально)
    """

    id: str
    global_role: str
    tenant_id: uuid.UUID
    email: str | None = None  # опционально, но удобно иметь


def get_current_user() -> CurrentUser:
    """
    Временная заглушка для текущего пользователя (dev-режим).

    Сейчас:
    - возвращает пользователя с id="admin" и global_role="admin",
      чтобы можно было тестировать RBAC по сделкам.
    - позже будет заменено на логику, которая берёт данные из токена.
    """
    return CurrentUser(
        id="admin",
        global_role="admin",
        tenant_id=uuid.UUID(int=0),
        email="admin@example.com",
    )
