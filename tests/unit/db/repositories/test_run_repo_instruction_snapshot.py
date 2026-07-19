"""Unit tests: RunRepository.update_instruction_snapshot (mocked AsyncSession, no real DB)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.repositories.run_repo import RunRepository


def _make_execute_result(run: MagicMock | None) -> MagicMock:
    """Мок результата session.execute(stmt) с .scalar_one_or_none()."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = run
    return result


def _make_run(run_id: uuid.UUID, *, versions=None, manifest=None, payload=None) -> MagicMock:
    run = MagicMock()
    run.id = run_id
    run.instruction_versions = versions
    run.instruction_snapshot_manifest = manifest
    run.instruction_snapshot_payload = payload
    return run


@pytest.fixture
def mock_session() -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.mark.asyncio
class TestUpdateInstructionSnapshot:
    async def test_success(self, mock_session: MagicMock) -> None:
        run_id = uuid.uuid4()
        versions = {"nda": "11111111-1111-1111-1111-111111111111"}
        manifest = {"nda": {"version_id": versions["nda"], "content_hash": "abc123", "override_id": None}}
        payload = {"nda": {"checks_v8": [{"id": "check_1"}]}}

        run = _make_run(run_id, versions=versions, manifest=manifest, payload=payload)
        mock_session.execute.return_value = _make_execute_result(run)

        repo = RunRepository(mock_session)
        updated = await repo.update_instruction_snapshot(run_id, versions, manifest, payload)

        assert updated is not None
        assert updated.instruction_versions == versions
        assert updated.instruction_snapshot_manifest == manifest
        assert updated.instruction_snapshot_payload == payload
        mock_session.flush.assert_awaited_once()

    async def test_empty_dicts_valid(self, mock_session: MagicMock) -> None:
        run_id = uuid.uuid4()
        run = _make_run(run_id, versions={}, manifest={}, payload={})
        mock_session.execute.return_value = _make_execute_result(run)

        repo = RunRepository(mock_session)
        updated = await repo.update_instruction_snapshot(run_id, {}, {}, {})

        assert updated is not None
        assert updated.instruction_versions == {}
        assert updated.instruction_snapshot_manifest == {}
        assert updated.instruction_snapshot_payload == {}

    async def test_none_rejected(self, mock_session: MagicMock) -> None:
        repo = RunRepository(mock_session)

        result = await repo.update_instruction_snapshot(uuid.uuid4(), None, {}, {})

        assert result is None
        mock_session.execute.assert_not_called()

    async def test_non_dict_rejected(self, mock_session: MagicMock) -> None:
        repo = RunRepository(mock_session)

        result = await repo.update_instruction_snapshot(uuid.uuid4(), ["not", "a", "dict"], {}, {})

        assert result is None
        mock_session.execute.assert_not_called()

    async def test_run_not_found(self, mock_session: MagicMock) -> None:
        mock_session.execute.return_value = _make_execute_result(None)

        repo = RunRepository(mock_session)
        result = await repo.update_instruction_snapshot(uuid.uuid4(), {}, {}, {})

        assert result is None

    async def test_idempotent(self, mock_session: MagicMock) -> None:
        run_id = uuid.uuid4()
        versions = {"nda": "11111111-1111-1111-1111-111111111111"}
        run = _make_run(run_id, versions=versions, manifest={}, payload={})
        mock_session.execute.return_value = _make_execute_result(run)

        repo = RunRepository(mock_session)

        first = await repo.update_instruction_snapshot(run_id, versions, {}, {})
        second = await repo.update_instruction_snapshot(run_id, versions, {}, {})

        assert first.instruction_versions == second.instruction_versions == versions


        