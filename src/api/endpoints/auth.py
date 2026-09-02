# src/api/endpoints/auth.py

"""
Эндпоинты аутентификации с защитой от брутфорса и Timing Attacks.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser
from api.deps.rate_limit import check_login_rate_limit # Добавили лимитер
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

# Фиктивный хэш для защиты от атак по времени (Timing Attacks)
# bcrypt.verify по нему будет идти столько же времени, сколько по реальному паролю.
DUMMY_HASH = "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6L6s5WrTHotd0.mC"


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: CurrentUser


@router.post(
    "/login", 
    response_model=LoginResponse,
    dependencies=[Depends(check_login_rate_limit)] # Находка №5: защита от брутфорса
)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """
    Авторизация пользователя.
    Включает защиту от перебора (Rate Limit) и утечки существования email (Timing Guard).
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

    # Находка №5: Защита от Timing Attack.
    # Если юзер не найден, мы всё равно имитируем проверку пароля.
    if db_user is None:
        verify_password(password, DUMMY_HASH) # Тратим время CPU на хэширование
        logger.info("Login failed: user not found", email=email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Проверка реального пароля
    if not verify_password(password, db_user.password_hash):
        logger.info("Login failed: wrong password", email=email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Пользователь найден и пароль верен
    system_role = normalize_system_role(db_user.system_role)

    token = create_access_token(
        user_id=db_user.id,
        tenant_id=db_user.tenant_id,
        system_role=system_role,
        email=db_user.email,
        ui_locale=db_user.ui_locale,
    )

    current_user = CurrentUser(
        id=str(db_user.id),
        global_role=system_role,
        tenant_id=db_user.tenant_id,
        email=db_user.email,
        ui_locale=db_user.ui_locale,
    )

    logger.info(
        "Login successful",
        user_id=str(db_user.id),
        email=db_user.email,
    )

    return LoginResponse(
        access_token=token,
        user=current_user,
    )


    

