"""
Helpers for running async code inside synchronous Celery tasks.

Celery workers are synchronous. Our repositories use async SQLAlchemy.
This module provides a bridge between the two worlds.
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

    Usage in a Celery task:
        result = run_async(some_async_function(arg1, arg2))
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're inside an already-running loop (shouldn't happen in Celery,
            # but handle gracefully)
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        # No event loop exists — create one
        return asyncio.run(coro)


@asynccontextmanager
async def get_worker_session():
    """
    Get a database session for use in Celery workers.

    Usage:
        async with get_worker_session() as session:
            repo = DealRepository(session)
            deal = await repo.get_by_id(deal_id)
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
