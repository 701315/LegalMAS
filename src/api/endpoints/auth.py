# src/api/endpoints/auth.py

"""
Эндпоинты аутентификации.

Чистая модель:
- Только реальный логин через таблицу users.
- Поле username в запросе временно сохраняем для контрактной совместимости,
  но фактически интерпретируем его как email.
- Никакого dev-fallback.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser
from core.logging import get_logger
from core.roles import normalize_system_role
from db.repositories.user_repo import UserRepository
from db.session import get_db
from services.auth_service import create_access_token, verify_password

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["auth"],
)


class LoginRequest(BaseModel):
    """
    Входные данные для логина.

    Поле username используется как email для входа.
    Переименовать в email можно позже отдельным шагом,
    когда фронтенд будет готов к изменению контракта.
    """

    username: str
    password: str


class LoginResponse(BaseModel):
    """
    Ответ на успешный логин.

    - access_token: JWT токен
    - token_type  : всегда "bearer"
    - user        : краткая информация о пользователе
    """

    access_token: str
    token_type: str = "bearer"
    user: CurrentUser


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """
    Логин по email + password.

    Алгоритм:
    1. Ищем активного пользователя по email.
    2. Проверяем bcrypt hash.
    3. Выдаём JWT.
    """
    email = payload.username.strip().lower()
    password = payload.password

    if not email or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email and password are required",
        )

    user_repo = UserRepository(db)
    db_user = await user_repo.get_by_email(email)

    if db_user is None:
        logger.info("Login failed: user not found", email=email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not verify_password(password, db_user.password_hash):
        logger.info("Login failed: wrong password", email=email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    system_role = normalize_system_role(db_user.system_role)

    token = create_access_token(
        user_id=db_user.id,
        tenant_id=db_user.tenant_id,
        system_role=system_role,
        email=db_user.email,
    )

    current_user = CurrentUser(
        id=str(db_user.id),
        global_role=system_role,
        tenant_id=db_user.tenant_id,
        email=db_user.email,
    )

    logger.info(
        "Login successful",
        user_id=str(db_user.id),
        email=db_user.email,
        system_role=system_role,
        tenant_id=str(db_user.tenant_id),
    )

    return LoginResponse(
        access_token=token,
        user=current_user,
    )


