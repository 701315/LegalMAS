# src/api/deps/auth.py

"""
Зависимости для аутентификации / авторизации в FastAPI.

Чистая модель:
- Только JWT-аутентификация.
- Никакого dev-fallback пользователя.
- Нет dev-token-*.
- Нет admin/admin или superadmin/superadmin.

Если токена нет или он невалиден — всегда 401.
"""

from __future__ import annotations

import uuid

from fastapi import Header, HTTPException, status
from pydantic import BaseModel

from core.logging import get_logger
from core.roles import normalize_system_role
from services.auth_service import decode_access_token

logger = get_logger(__name__)


class CurrentUser(BaseModel):
    """
    Текущий пользователь, извлечённый из JWT.

    Поля:
    - id          : UUID пользователя, сериализованный в строку
    - global_role : одна из канонических системных ролей:
                    superadmin | tenant_admin | member
    - tenant_id   : UUID tenant'а пользователя
    - email       : email пользователя
    """

    id: str
    global_role: str
    tenant_id: uuid.UUID
    email: str | None = None


def get_current_user(
    authorization: str | None = Header(default=None),
) -> CurrentUser:
    """
    Получить текущего пользователя из JWT Bearer token.

    Контракт:
    - Authorization header обязателен;
    - формат строго: Bearer <token>;
    - невалидный/просроченный токен => 401.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must use Bearer token",
        )

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty Bearer token",
        )

    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    try:
        user_id = str(payload["sub"])
        tenant_id = uuid.UUID(payload["tenant_id"])
        raw_role = payload.get("system_role")
        email = payload.get("email")
    except (KeyError, ValueError) as e:
        logger.warning("JWT payload malformed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token payload",
        ) from e

    return CurrentUser(
        id=user_id,
        global_role=normalize_system_role(raw_role),
        tenant_id=tenant_id,
        email=email,
    )


