"""
Shared fixtures для интеграционных тестов (Stage 4+).
"""

from unittest.mock import AsyncMock

import pytest_asyncio


@pytest_asyncio.fixture
async def mock_uow_factory():
    """Фабрика для создания mock UoW."""

    def create_uow():
        uow = AsyncMock()
        uow.__aenter__ = AsyncMock(return_value=uow)
        uow.__aexit__ = AsyncMock(return_value=None)
        uow.commit = AsyncMock()
        uow.rollback = AsyncMock()
        uow.documents = AsyncMock()
        uow.document_versions = AsyncMock()
        uow.audit_logs = AsyncMock()
        return uow

    return create_uow


@pytest_asyncio.fixture
async def mock_artifact_store_factory():
    """Фабрика для создания mock ArtifactStore."""

    def create_store(layout_data=None):
        store = AsyncMock()
        store.get_json = AsyncMock(return_value=layout_data or {"elements": []})
        store.put_json = AsyncMock()
        store.put_file = AsyncMock()
        store.delete = AsyncMock()
        return store

    return create_store
