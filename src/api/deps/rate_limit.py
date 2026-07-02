# src/api/deps/rate_limit.py

"""
Rate limiting для admin endpoint'ов.

Реализация через FastAPI Depends — не через slowapi декораторы.
Причина: user identity (user_id) доступна из JWT через Depends(get_current_user),
а не из кастомных заголовков до вызова endpoint'а.

Текущий storage: in-memory (один процесс uvicorn).
При масштабировании на несколько процессов / инстансов
storage нужно переносить в Redis.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter

from api.deps.auth import CurrentUser, get_current_user
from core.logging import get_logger

logger = get_logger(__name__)

_storage = MemoryStorage()
_limiter = FixedWindowRateLimiter(_storage)

_LIMIT_LOGS = parse("60 per minute")
_LIMIT_ADMIN = parse("30 per minute")
_RETRY_AFTER_SECONDS = 60


def _check_limit(
    limit,
    *,
    request: Request,
    user_id: str,
    scope: str,
) -> None:
    """
    Проверить лимит для пользователя внутри заданного scope.

    scope нужен чтобы счётчики для /tenant/logs и остальных admin endpoints
    были независимыми.
    """
    allowed = _limiter.hit(limit, scope, user_id)

    if allowed:
        return

    logger.warning(
        "Rate limit exceeded for admin endpoint",
        user_id=user_id,
        scope=scope,
        client_host=request.client.host if request.client else None,
    )
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many requests. Please slow down.",
        headers={"Retry-After": str(_RETRY_AFTER_SECONDS)},
    )


def check_logs_rate_limit(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> None:
    """
    60 запросов/минуту per user для /tenant/logs.
    """
    _check_limit(
        _LIMIT_LOGS,
        request=request,
        user_id=user.id,
        scope="tenant_logs",
    )


def check_admin_rate_limit(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> None:
    """
    30 запросов/минуту per user для остальных tenant admin endpoints:
    /tenant/dashboard
    /tenant/metrics
    /tenant/projects/{deal_id}/insights
    """
    _check_limit(
        _LIMIT_ADMIN,
        request=request,
        user_id=user.id,
        scope="tenant_admin",
    )


    