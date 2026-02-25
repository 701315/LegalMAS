"""
Database session management.
Provides async engine, session factory, and dependency for FastAPI.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)

# Create async engine (connection pool to PostgreSQL)
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,  # Set True to see SQL queries in logs (very verbose)
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Check connection health before using
)

# Session factory: creates new sessions
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Don't expire objects after commit
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database sessions.
    Use in workers and services:

        async with get_session() as session:
            result = await session.execute(select(Deal))
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
    FastAPI dependency for database sessions.
    Use in API route handlers:

        @router.get("/deals")
        async def list_deals(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with get_session() as session:
        yield session
