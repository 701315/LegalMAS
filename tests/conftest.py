"""
Shared test fixtures.
Provides database session with automatic rollback for each test.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import settings
from src.db.base import Base


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture
async def db_session():
    """
    Creates a fresh database session for each test.
    Uses a transaction that is rolled back after the test,
    so tests don't affect each other.
    """
    engine = create_async_engine(settings.DATABASE_URL)

    async with engine.begin() as conn:
        # Create all tables (if not exist)
        await conn.run_sync(Base.metadata.create_all)

    # Create session with transaction
    async_session = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)

        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()

    await engine.dispose()


@pytest.fixture
def tenant_id() -> uuid.UUID:
    """Fixed tenant ID for tests."""
    return uuid.UUID("00000000-0000-0000-0000-000000000099")
