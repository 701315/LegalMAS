# src/api/deps/rate_limit.py

"""
Rate limiting для API эндпоинтов.

Реализация:
- Использует Redis для хранения счетчиков (лимиты общие для всех инстансов API).
- Защита административных путей по user_id.
- Защита входа (/login) по IP-адресу.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from limits import parse
from limits.storage import RedisStorage
from limits.strategies import FixedWindowRateLimiter

from api.deps.auth import CurrentUser, get_current_user
from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

# СИСТЕМНЫЙ ФИКС: Переход на Redis для multi-process поддержки
_storage = RedisStorage(settings.REDIS_URL)
_limiter = FixedWindowRateLimiter(_storage)

# Конфигурация лимитов
_LIMIT_LOGS = parse("60 per minute")
_LIMIT_ADMIN = parse("30 per minute")
_LIMIT_LOGIN = parse("5 per minute")  # Находка №5: Лимит на попытки входа
_RETRY_AFTER_SECONDS = 60


def _check_limit(
    limit,
    *,
    request: Request,
    identity: str,
    scope: str,
) -> None:
    """Внутренняя логика проверки лимита."""
    allowed = _limiter.hit(limit, scope, identity)

    if not allowed:
        logger.warning(
            "Rate limit exceeded",
            identity=identity,
            scope=scope,
            path=request.url.path,
            client_host=request.client.host if request.client else None,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please slow down.",
            headers={"Retry-After": str(_RETRY_AFTER_SECONDS)},
        )


def check_login_rate_limit(request: Request) -> None:
    """
    Защита эндпоинта логина.
    Лимит: 5 попыток в минуту на один IP.
    """
    client_ip = request.client.host if request.client else "unknown"
    _check_limit(
        _LIMIT_LOGIN,
        request=request,
        identity=client_ip,
        scope="login_bruteforce",
    )


def check_logs_rate_limit(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> None:
    """Лимит для просмотра логов (60/мин на юзера)."""
    _check_limit(
        _LIMIT_LOGS,
        request=request,
        identity=user.id,
        scope="tenant_logs",
    )


def check_admin_rate_limit(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> None:
    """Лимит для админ-панели (30/мин на юзера)."""
    _check_limit(
        _LIMIT_ADMIN,
        request=request,
        identity=user.id,
        scope="tenant_admin",
    )


    


    