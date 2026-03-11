# src/db/session.py

"""
Database session management.

Слои работы с БД:

- engine / AsyncSessionLocal:
    общая фабрика подключения к PostgreSQL (asyncpg-пул).

- get_session():
    низкоуровневый контекстный менеджер "один unit of work":
    создаёт AsyncSession, управляет commit/rollback/close.
    Используется в:
        * воркерах (Celery),
        * фоновых сервисах,
        * middleware, которым нужна БД.

- get_db():
    обёртка над get_session для FastAPI.
    Используется только как зависимость в HTTP-эндпоинтах:
        db: AsyncSession = Depends(get_db)

Важно:
- middleware и worker'ы НЕ должны использовать get_db.
- HTTP-эндпоинты НЕ должны вызывать get_session напрямую.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

# Общий async engine (пул подключений к PostgreSQL)
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,          # Set True to see SQL queries in logs (very verbose)
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Check connection health before using
)

# Фабрика сессий: создаёт новые AsyncSession при каждом вызове
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Don't expire objects after commit
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Низкоуровневый контекстный менеджер для одной транзакции / unit of work.

    Использование вне FastAPI (воркеры, сервисы, middleware):

        async with get_session() as session:
            result = await session.execute(select(Deal))

    Гарантии:
    - при успешном выходе из блока делается commit;
    - при исключении — rollback;
    - в любом случае сессия закрывается (close).
    """
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency для работы с БД в HTTP-эндпоинтах.

    Использование:

        @router.get("/deals")
        async def list_deals(db: AsyncSession = Depends(get_db)):
            ...

    Контракт:
    - каждый HTTP-запрос получает свою AsyncSession;
    - логика эндпоинта использует db для репозиториев/сервисов;
    - commit/rollback/close управляются внутри get_session().
    """
    async with get_session() as session:
        yield session
