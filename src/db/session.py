# src/db/session.py

"""
Database session management.

Слои работы с БД:

- engine / AsyncSessionLocal:
    process-level async engine и фабрика AsyncSession для PostgreSQL.

- get_session():
    низкоуровневый context manager для короткоживущей AsyncSession
    без auto-commit.
    Используется в:
        * read-only сервисах,
        * SSE/polling,
        * middleware,
        * специальных внутренних сценариях, где commit контролируется явно.

- db_uow():
    явный transactional Unit of Work.
    Используется в:
        * Celery worker'ах,
        * фоновых write-сервисах,
        * местах, где нужно commit-on-success поведение.

- get_db():
    FastAPI dependency для HTTP-эндпоинтов.
    Даёт request-scoped AsyncSession без implicit commit.

Важно:
- middleware и worker'ы не должны использовать get_db;
- обычные HTTP-эндпоинты должны получать session через get_db;
- long-lived response (например StreamingResponse / SSE) не должен
  удерживать одну и ту же request-scoped session на весь срок жизни ответа;
- read lifecycle и write lifecycle разделены явно.
"""

from __future__ import annotations

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
    echo=False,  # Set True to see SQL queries in logs (very verbose)
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Check connection health before using
)

# Фабрика сессий: создаёт новые AsyncSession при каждом вызове.
# expire_on_commit=False обычно удобен для async SQLAlchemy-кода,
# чтобы не получать неожиданные lazy refresh после commit.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Низкоуровневый context manager для одной AsyncSession без auto-commit.

    Использование вне FastAPI (read-only сервисы, SSE polling, middleware):

        async with get_session() as session:
            result = await session.execute(select(Deal))

    Гарантии:
    - создаёт новую AsyncSession;
    - при исключении делает rollback;
    - в любом случае закрывает session.

    Важно:
    - этот context manager никогда не делает commit автоматически;
    - если вызывающий код изменяет данные, он должен сам вызвать commit(),
      либо использовать db_uow().
    """
    session = AsyncSessionLocal()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@asynccontextmanager
async def db_uow() -> AsyncGenerator[AsyncSession, None]:
    """
    Явный transactional Unit of Work.

    Использование:

        async with db_uow() as session:
            ...
            session.add(obj)

    Гарантии:
    - создаёт новую AsyncSession;
    - при успешном выходе делает commit;
    - при исключении делает rollback;
    - в любом случае закрывает session.

    Используйте db_uow() для write-сценариев:
    - create/update/delete,
    - Celery jobs,
    - фоновые операции,
    - сервисы, где commit должен происходить атомарно в конце блока.
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
    - dependency отвечает только за lifecycle session;
    - commit в HTTP-эндпоинте вызывается явно там, где endpoint меняет данные;
    - dependency не должна использоваться в long-lived background loop
      или внутри streaming generator.

    Это делает границы транзакции явными и безопасными для StreamingResponse.
    """
    async with get_session() as session:
        yield session

