# src/api/endpoints/auth.py
"""
Эндпоинты авторизации / аутентификации для FastAPI (dev-режим).

Назначение:
- Предоставить простой, но структурный механизм логина для разработки.
- Эмулировать реальные глобальные роли (GlobalRole), чтобы проверять RBAC:
  superadmin / admin / editor / viewer.
- Не хранить пользователей в БД и не реализовывать настоящую авторизацию,
  но использовать те же модели (LoginRequest, LoginResponse, CurrentUser),
  что и в будущем боевом варианте.

Важно:
- Контракт эндпоинта /api/v1/auth/login (запрос/ответ) считается стабильным.
- Внутренняя реализация (dev-логины, фиктивные токены) может быть
  заменена на полноценный логин (users + JWT), не ломая фронтенд.
"""

from __future__ import annotations

import uuid
from typing import TypedDict

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from src.api.deps.auth import CurrentUser

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["auth"],
)


class LoginRequest(BaseModel):
    """
    Входные данные для логина.

    Сейчас:
    - ожидаем username и password из формы логина на фронтенде.

    Потом:
    - поля можно оставить те же, а внутри искать пользователя в БД.
    """
    username: str
    password: str


class LoginResponse(BaseModel):
    """
    Ответ на успешный логин.

    Поля:
    - access_token: строка с токеном доступа (пока фиктивная).
    - token_type : тип токена, по умолчанию "bearer".
    - user       : объект CurrentUser (см. src/api/deps/auth.py).
    """
    access_token: str
    token_type: str = "bearer"
    user: CurrentUser


class DevUserConfig(TypedDict):
    password: str
    global_role: str
    email: str | None


# Набор dev-пользователей для отладки RBAC.
# В будущем будет заменён на реальную таблицу users + хранилище паролей.
DEV_USERS: dict[str, DevUserConfig] = {
    # Полный доступ ко всем сделкам, игнорирует projectRole.
    "superadmin": {
        "password": "superadmin",
        "global_role": "superadmin",
        "email": "superadmin@example.com",
    },
    # Глобальный админ: максимальные права в рамках своего tenant,
    # но projectRole может урезать доступ в конкретной сделке.
    "admin": {
        "password": "admin",
        "global_role": "admin",
        "email": "admin@example.com",
    },
    # Пользователь с правами редактирования (например, загрузка документов,
    # запуск анализа) в рамках разрешённых проектов.
    "editor": {
        "password": "editor",
        "global_role": "editor",
        "email": "editor@example.com",
    },
    # Пользователь только для просмотра.
    "viewer": {
        "password": "viewer",
        "global_role": "viewer",
        "email": "viewer@example.com",
    },
}


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest) -> LoginResponse:
    """
    Простой dev-логин по username и password.

    Сейчас:
    - Поддерживаются dev-логины:
        * superadmin / superadmin
        * admin      / admin
        * editor     / editor
        * viewer     / viewer
    - Для каждого логина задаётся своя global_role.
    - user.id = username (строка), tenant_id = нулевой UUID.

    Позже:
    - Проверка логина/пароля будет заменена на запрос к БД и проверку хэша.
    - access_token станет JWT с user_id, global_role, tenant_id и т.п.
    """
    config = DEV_USERS.get(payload.username)

    if config is None or config["password"] != payload.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    user = CurrentUser(
        id=payload.username,                      # пока строка, позже UUID из таблицы users
        global_role=config["global_role"],        # GlobalRole: superadmin/admin/editor/viewer
        tenant_id=uuid.UUID(int=0),               # временный tenant_id
        email=config["email"],
    )

    # access_token остаётся фиктивным, но структура совместима с будущим JWT.
    token = f"dev-token-{payload.username}"

    return LoginResponse(
        access_token=token,
        user=user,
    )
