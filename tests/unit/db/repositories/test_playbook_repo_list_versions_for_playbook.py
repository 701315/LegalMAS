# tests/unit/db/repositories/test_playbook_repo_list_versions_for_playbook.py

"""Unit tests: PlaybookRepository.list_versions_for_playbook (mocked AsyncSession, no real DB)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.repositories.playbook_repo import PlaybookRepository


def _make_version(
    *,
    version_id: uuid.UUID | None = None,
    playbook_id: uuid.UUID,
    name: str = "Test Playbook",
    semver: str = "1.0.0",
    status: str = "draft",
):
    return SimpleNamespace(
        id=version_id or uuid.uuid4(),
        playbook_id=playbook_id,
        name=name,
        semver=semver,
        status=status,
        published_at=None,
        created_at=None,
    )


def _make_scalars_result(items: list) -> MagicMock:
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    result.scalars.return_value = scalars
    return result


@pytest.fixture
def mock_session() -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.mark.asyncio
class TestListVersionsForPlaybook:
    async def test_returns_versions_for_playbook(self, mock_session: MagicMock) -> None:
        playbook_id = uuid.uuid4()
        versions = [
            _make_version(playbook_id=playbook_id, semver="1.0.0"),
            _make_version(playbook_id=playbook_id, semver="1.1.0"),
        ]
        mock_session.execute.return_value = _make_scalars_result(versions)

        repo = PlaybookRepository(mock_session)
        result = await repo.list_versions_for_playbook(playbook_id)

        assert result == versions
        mock_session.execute.assert_awaited_once()

    async def test_empty_list_for_playbook_without_versions(
        self, mock_session: MagicMock
    ) -> None:
        playbook_id = uuid.uuid4()
        mock_session.execute.return_value = _make_scalars_result([])

        repo = PlaybookRepository(mock_session)
        result = await repo.list_versions_for_playbook(playbook_id)

        assert result == []

    async def test_query_contains_playbook_filter(self, mock_session: MagicMock) -> None:
        playbook_id = uuid.uuid4()
        mock_session.execute.return_value = _make_scalars_result([])

        repo = PlaybookRepository(mock_session)
        await repo.list_versions_for_playbook(playbook_id)

        stmt = mock_session.execute.await_args.args[0]
        compiled_sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))

        assert "playbook_versions" in compiled_sql
        assert "playbook_id" in compiled_sql

    async def test_query_contains_sorting(self, mock_session: MagicMock) -> None:
        playbook_id = uuid.uuid4()
        mock_session.execute.return_value = _make_scalars_result([])

        repo = PlaybookRepository(mock_session)
        await repo.list_versions_for_playbook(playbook_id)

        stmt = mock_session.execute.await_args.args[0]
        compiled_sql = str(stmt.compile(compile_kwargs={"literal_binds": False}))

        assert "ORDER BY" in compiled_sql.upper()
        assert "published_at" in compiled_sql
        assert "created_at" in compiled_sql


        