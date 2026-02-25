"""
Shared test fixtures.
Provides database session with automatic rollback for each test.
"""

# Register test tasks into Celery app — test scope only, never in production
import uuid
import os
import pytest
from src.core.config import settings
import pytest_asyncio
from src.core.logging import deal_id_var, document_id_var, request_id_var
from src.db.base import Base
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# создаём отдельный engine только для тестов
test_engine = create_async_engine(settings.DATABASE_URL, future=True)
TestSession = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def prepare_db_schema():
    """
    Один раз создаёт схему БД на время тестовой сессии.
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # При желании можно дропнуть таблицы после тестов:
    # async with engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def db_session():
    async with TestSession() as session:
        yield session


@pytest.fixture
def tenant_id() -> uuid.UUID:
    """Fixed tenant ID for tests."""
    return uuid.UUID("00000000-0000-0000-0000-000000000099")


@pytest.fixture(autouse=True)
def reset_context_vars():
    """Сбрасывает ContextVar между тестами чтобы избежать утечки состояния."""

    request_id_var.set(None)
    deal_id_var.set(None)
    document_id_var.set(None)

    yield

    request_id_var.set(None)
    deal_id_var.set(None)
    document_id_var.set(None)


@pytest.fixture(scope="session", autouse=True)
def disable_downstream_tasks():
    """
    Отключить запуск downstream-тасок (PII Sanitizer, Structure Builder)
    в интеграционных тестах для изоляции стадий pipeline.
    """
    original_value = settings.DISABLE_DOWNSTREAM_TASKS
    os.environ["DISABLE_DOWNSTREAM_TASKS"] = "true"
    settings.DISABLE_DOWNSTREAM_TASKS = True
    
    yield
    
    settings.DISABLE_DOWNSTREAM_TASKS = original_value
    if "DISABLE_DOWNSTREAM_TASKS" in os.environ:
        os.environ.pop("DISABLE_DOWNSTREAM_TASKS")
