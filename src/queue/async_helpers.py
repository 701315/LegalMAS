"""
Helpers for running async code inside synchronous Celery tasks.

Celery workers are synchronous. Our repositories use async SQLAlchemy.
This module provides a bridge between the two worlds.

IMPORTANT:
    - For new async workers and tests, DO NOT use run_async/get_worker_session.
    - Use src.db.session.get_session / get_db instead and native async tasks.
"""

import asyncio
from collections.abc import Coroutine
from contextlib import asynccontextmanager
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import settings

T = TypeVar("T")

# Lazy-initialized engine for worker processes
_engine = None
_session_factory = None


def _get_engine():
    """Get or create async engine (lazy singleton per worker process)."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.DATABASE_URL,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
    return _engine


def _get_session_factory():
    """Get or create session factory (lazy singleton per worker process)."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """
    Run an async coroutine from synchronous Celery task code.

    IMPORTANT:
        - Use only from *purely synchronous* worker processes.
        - Do not call from within already running event loops (pytest-asyncio, uvicorn, etc.).
    """
    # Всегда создаём свой loop для конкретного вызова,
    # не зависим от глобального event loop текущего потока.
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
        asyncio.set_event_loop(None)


@asynccontextmanager
async def get_legacy_worker_session():
    """
    LEGACY: Get a database session for use in *synchronous* Celery workers
    together with run_async().

    Do NOT use in:
        - FastAPI handlers
        - async workers (asyncio.run + get_session)
        - tests (use src.db.session.get_session instead)

    В async‑воркерах и тестах используется только src.db.session.get_session /
    get_db,

    get_worker_session и run_async остаются только в старых sync Celery‑тасках,
    которые ты постепенно заменишь.

    """
    factory = _get_session_factory()
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
