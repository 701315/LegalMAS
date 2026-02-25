import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import create_engine as create_sync_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import settings
from src.core.logging import deal_id_var, document_id_var, request_id_var

# --- Sync engine для инициализации схемы (DDL один раз перед тестами) ---
sync_engine = create_sync_engine(settings.DATABASE_URL.replace("+asyncpg", ""), future=True)

# --- Async engine только для тестов (используется в коде) ---
test_engine = create_async_engine(settings.DATABASE_URL, future=True)
TestSession = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.mark.asyncio
async def test__sanity_db_session(db_session: AsyncSession):
    from src.db.repositories import PlaybookRepository

    repo = PlaybookRepository(db_session)
    pb = await repo.get_default()
    assert pb is not None


@pytest.fixture
def anyio_backend():
    return "asyncio"


# @pytest.fixture(scope="session", autouse=True)
# def prepare_db_schema():
#    """Один раз создаёт схему БД синхронно перед всеми тестами."""
#    with sync_engine.begin() as conn:
#        Base.metadata.create_all(bind=conn)
#    yield
#    # при желании можно дропнуть таблицы после тестов:
#    # with sync_engine.begin() as conn:
#    #     Base.metadata.drop_all(bind=conn)


@pytest_asyncio.fixture(scope="function")
async def db_session():
    async with TestSession() as session:
        yield session


@pytest.fixture
def tenant_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000099")


@pytest.fixture(autouse=True)
def reset_context_vars():
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
