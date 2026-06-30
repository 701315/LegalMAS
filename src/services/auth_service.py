# src/services/auth_service.py

"""
Сервис аутентификации: хэширование паролей и работа с JWT-токенами.

Этот модуль — единственное место в системе, где работают:
- bcrypt (хэширование и проверка паролей);
- PyJWT (создание и декодирование токенов).

Принципы:
- Репозитории не знают про пароли и токены — только этот сервис.
- Endpoint'ы не знают про bcrypt и JWT — только этот сервис.
- Токен содержит минимально необходимый payload:
  {user_id, tenant_id, system_role, email}.

Схема работы при логине:
1. Endpoint принимает email + password.
2. UserRepository.get_by_email() ищет активного пользователя.
3. auth_service.verify_password() проверяет пароль против хэша.
4. auth_service.create_access_token() выдаёт JWT.
5. Клиент хранит токен и передаёт в заголовке Authorization: Bearer <token>.

Схема работы при запросе:
1. get_current_user() читает заголовок Authorization.
2. auth_service.decode_access_token() декодирует и проверяет JWT.
3. Возвращает CurrentUser с данными из payload.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)


# ── Password hashing ────────────────────────────────────────────────────────


def hash_password(plain_password: str) -> str:
    """
    Хэшировать пароль через bcrypt.

    Параметры:
    - plain_password: пароль в открытом виде.

    Возвращает:
    - bcrypt-хэш в виде строки (60 символов).

    Использование:
        hashed = hash_password("my_secret_password")
        # Сохранить hashed в user.password_hash
    """
    password_bytes = plain_password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Проверить пароль против bcrypt-хэша.

    Параметры:
    - plain_password  : пароль в открытом виде (из формы логина);
    - hashed_password : хэш из таблицы users.password_hash.

    Возвращает:
    - True если пароль верный;
    - False если неверный.

    Использование:
        if not verify_password(payload.password, user.password_hash):
            raise HTTPException(401, "Invalid credentials")
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        # Защита от malformed hash или encoding issues
        logger.warning("Password verification failed unexpectedly")
        return False


# ── JWT tokens ──────────────────────────────────────────────────────────────


def create_access_token(
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    system_role: str,
    email: str,
) -> str:
    """
    Создать JWT access token.

    Payload токена:
    - sub        : user_id (строка UUID) — стандартное поле JWT "subject";
    - tenant_id  : UUID tenant'а пользователя;
    - system_role: системная роль (superadmin / tenant_admin / member);
    - email      : email пользователя;
    - exp        : время истечения токена (UTC).

    Параметры:
    - user_id    : UUID пользователя;
    - tenant_id  : UUID tenant'а;
    - system_role: системная роль;
    - email      : email.

    Возвращает:
    - подписанный JWT токен в виде строки.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload: dict = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "system_role": system_role,
        "email": email,
        "exp": expire,
    }

    token = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    return token


def decode_access_token(token: str) -> dict | None:
    """
    Декодировать и верифицировать JWT access token.

    Проверяет:
    - подпись (JWT_SECRET_KEY + JWT_ALGORITHM);
    - срок действия (exp).

    Возвращает:
    - dict с payload если токен валиден;
    - None если токен невалиден, истёк или повреждён.

    Использование в get_current_user():
        payload = decode_access_token(token)
        if payload is None:
            raise HTTPException(401, "Invalid or expired token")
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except jwt.ExpiredSignatureError:
        logger.debug("JWT token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.debug("JWT token invalid", error=str(e))
        return None
    
    