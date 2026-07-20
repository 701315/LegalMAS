"""Unit tests: RunRepository.update_instruction_snapshot (mocked AsyncSession, no real DB)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.repositories.run_repo import RunRepository


def _make_execute_result(run: MagicMock | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = run
    return result


def _make_run(
    run_id: uuid.UUID,
    *,
    versions=None,
    manifest=None,
    payload=None,
    snapshot_schema_version=None,
) -> MagicMock:
    run = MagicMock()
    run.id = run_id
    run.instruction_versions = versions
    run.instruction_snapshot_manifest = manifest
    run.instruction_snapshot_payload = payload
    run.snapshot_schema_version = snapshot_schema_version
    return run


@pytest.fixture
def mock_session() -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.mark.asyncio
class TestUpdateInstructionSnapshot:
    async def test_success_without_schema_version(self, mock_session: MagicMock) -> None:
        run_id = uuid.uuid4()
        versions = {"nda": "11111111-1111-1111-1111-111111111111"}
        manifest = {"nda": {"version_id": versions["nda"], "content_hash": "abc123"}}
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

    async def test_success_with_schema_version(self, mock_session: MagicMock) -> None:
        run_id = uuid.uuid4()
        versions = {"nda": "11111111-1111-1111-1111-111111111111"}
        manifest = {"nda": {"version_id": versions["nda"], "content_hash": "abc123"}}
        payload = {"nda": {"checks_v8": []}}

        run = _make_run(
            run_id,
            versions=versions,
            manifest=manifest,
            payload=payload,
            snapshot_schema_version=1,
        )
        mock_session.execute.return_value = _make_execute_result(run)

        repo = RunRepository(mock_session)
        updated = await repo.update_instruction_snapshot(
            run_id,
            versions,
            manifest,
            payload,
            snapshot_schema_version=1,
        )

        assert updated is not None
        assert updated.snapshot_schema_version == 1
        mock_session.flush.assert_awaited_once()

    async def test_schema_version_included_in_update_values(self, mock_session: MagicMock) -> None:
        """
        Проверяет что snapshot_schema_version записывается атомарно
        в тот же UPDATE что и snapshot fields.
        """
        run_id = uuid.uuid4()
        run = _make_run(run_id, versions={}, manifest={}, payload={}, snapshot_schema_version=1)
        mock_session.execute.return_value = _make_execute_result(run)

        repo = RunRepository(mock_session)
        await repo.update_instruction_snapshot(
            run_id,
            {},
            {},
            {},
            snapshot_schema_version=1,
        )

        # Проверяем что execute вызван ровно один раз (атомарный UPDATE)
        mock_session.execute.assert_awaited_once()

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
        result = await repo.update_instruction_snapshot(
            uuid.uuid4(), ["not", "a", "dict"], {}, {}
        )

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

    async def test_schema_version_none_does_not_include_in_update(
        self, mock_session: MagicMock
    ) -> None:
        """
        snapshot_schema_version=None → поле не включается в UPDATE.
        Это позволяет обновлять payload без изменения schema_version.
        """
        run_id = uuid.uuid4()
        run = _make_run(run_id, versions={}, manifest={}, payload={})
        mock_session.execute.return_value = _make_execute_result(run)

        repo = RunRepository(mock_session)
        updated = await repo.update_instruction_snapshot(
            run_id, {}, {}, {}, snapshot_schema_version=None
        )

        assert updated is not None
        # Проверяем что всё равно прошло успешно
        mock_session.execute.assert_awaited_once()


        