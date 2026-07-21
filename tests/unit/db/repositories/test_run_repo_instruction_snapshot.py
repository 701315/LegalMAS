"""Unit tests: RunRepository.update_instruction_snapshot (mocked AsyncSession, no real DB)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Update

from db.repositories.run_repo import RunRepository


def _make_execute_result(obj) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = obj
    return result


def _make_run(
    run_id: uuid.UUID,
    *,
    playbook_version_id: uuid.UUID | None = None,
    model_config_id: uuid.UUID | None = None,
    versions=None,
    manifest=None,
    payload=None,
    snapshot_schema_version=None,
):
    return SimpleNamespace(
        id=run_id,
        playbook_version_id=playbook_version_id or uuid.uuid4(),
        model_config_id=model_config_id,
        instruction_versions=versions,
        instruction_snapshot_manifest=manifest,
        instruction_snapshot_payload=payload,
        snapshot_schema_version=snapshot_schema_version,
    )


def _make_playbook_version(
    playbook_version_id: uuid.UUID,
    *,
    immutable_content_hash: str | None = "playbook-hash",
):
    return SimpleNamespace(
        id=playbook_version_id,
        immutable_content_hash=immutable_content_hash,
    )


def _make_success_execute_side_effect(
    *,
    run,
    playbook_version,
    updated_run=None,
) -> list[MagicMock]:
    return [
        _make_execute_result(run),
        _make_execute_result(playbook_version),
        _make_execute_result(updated_run or run),
    ]


def _get_execute_statements(mock_session: MagicMock) -> list:
    return [call.args[0] for call in mock_session.execute.await_args_list]


def _get_single_update_statement(mock_session: MagicMock) -> Update:
    update_statements = [
        stmt for stmt in _get_execute_statements(mock_session) if isinstance(stmt, Update)
    ]
    assert len(update_statements) == 1, (
        "Expected exactly one UPDATE statement for atomic snapshot write, "
        f"got {len(update_statements)}"
    )
    return update_statements[0]


def _get_update_params(mock_session: MagicMock) -> dict:
    stmt = _get_single_update_statement(mock_session)
    compiled = stmt.compile(dialect=postgresql.dialect())
    return dict(compiled.params)


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
        playbook_version_id = uuid.uuid4()

        versions = {"nda": "11111111-1111-1111-1111-111111111111"}
        manifest = {"nda": {"version_id": versions["nda"], "content_hash": "abc123"}}
        payload = {"nda": {"checks_v8": [{"id": "check_1"}]}}

        run = _make_run(
            run_id,
            playbook_version_id=playbook_version_id,
            versions=versions,
            manifest=manifest,
            payload=payload,
        )
        playbook_version = _make_playbook_version(playbook_version_id)

        mock_session.execute.side_effect = _make_success_execute_side_effect(
            run=run,
            playbook_version=playbook_version,
            updated_run=run,
        )

        repo = RunRepository(mock_session)
        updated = await repo.update_instruction_snapshot(run_id, versions, manifest, payload)

        assert updated is not None
        assert updated.instruction_versions == versions
        assert updated.instruction_snapshot_manifest == manifest
        assert updated.instruction_snapshot_payload == payload
        mock_session.flush.assert_awaited_once()

        params = _get_update_params(mock_session)
        assert params["instruction_versions"] == versions
        assert params["instruction_snapshot_manifest"] == manifest
        assert params["instruction_snapshot_payload"] == payload
        assert "snapshot_schema_version" not in params

        execution_manifest = params["execution_manifest"]
        assert execution_manifest["schema_version"] == 1
        assert execution_manifest["playbook"]["version_id"] == str(playbook_version_id)
        assert execution_manifest["playbook"]["immutable_content_hash"] == "playbook-hash"
        assert execution_manifest["playbook"]["model_config_id"] is None
        assert execution_manifest["doc_type_instructions"]["nda"] == {
            "version_id": versions["nda"],
            "override_id": None,
            "tenant_override_id": None,
            "deal_override_id": None,
            "effective_hash": None,
            "is_overridden": False,
            "resolution_strategy": None,
        }

    async def test_success_with_schema_version(self, mock_session: MagicMock) -> None:
        run_id = uuid.uuid4()
        playbook_version_id = uuid.uuid4()

        versions = {"nda": "11111111-1111-1111-1111-111111111111"}
        manifest = {"nda": {"version_id": versions["nda"], "content_hash": "abc123"}}
        payload = {"nda": {"checks_v8": []}}

        run = _make_run(
            run_id,
            playbook_version_id=playbook_version_id,
            versions=versions,
            manifest=manifest,
            payload=payload,
            snapshot_schema_version=1,
        )
        playbook_version = _make_playbook_version(playbook_version_id)

        mock_session.execute.side_effect = _make_success_execute_side_effect(
            run=run,
            playbook_version=playbook_version,
            updated_run=run,
        )

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

        params = _get_update_params(mock_session)
        assert params["snapshot_schema_version"] == 1

    async def test_schema_version_included_in_update_values(
        self, mock_session: MagicMock
    ) -> None:
        """
        Проверяет что snapshot_schema_version записывается атомарно
        в тот же UPDATE что и snapshot fields.

        Важно:
        - execute может вызываться несколько раз (SELECT Run, SELECT PlaybookVersion, UPDATE Run);
        - инвариант — ровно один UPDATE statement, содержащий и snapshot fields, и schema_version.
        """
        run_id = uuid.uuid4()
        playbook_version_id = uuid.uuid4()

        run = _make_run(
            run_id,
            playbook_version_id=playbook_version_id,
            versions={},
            manifest={},
            payload={},
            snapshot_schema_version=1,
        )
        playbook_version = _make_playbook_version(playbook_version_id)

        mock_session.execute.side_effect = _make_success_execute_side_effect(
            run=run,
            playbook_version=playbook_version,
            updated_run=run,
        )

        repo = RunRepository(mock_session)
        await repo.update_instruction_snapshot(
            run_id,
            {},
            {},
            {},
            snapshot_schema_version=1,
        )

        params = _get_update_params(mock_session)
        assert "instruction_versions" in params
        assert "instruction_snapshot_manifest" in params
        assert "instruction_snapshot_payload" in params
        assert "execution_manifest" in params
        assert params["snapshot_schema_version"] == 1

    async def test_empty_dicts_valid(self, mock_session: MagicMock) -> None:
        run_id = uuid.uuid4()
        playbook_version_id = uuid.uuid4()

        run = _make_run(
            run_id,
            playbook_version_id=playbook_version_id,
            versions={},
            manifest={},
            payload={},
        )
        playbook_version = _make_playbook_version(playbook_version_id)

        mock_session.execute.side_effect = _make_success_execute_side_effect(
            run=run,
            playbook_version=playbook_version,
            updated_run=run,
        )

        repo = RunRepository(mock_session)
        updated = await repo.update_instruction_snapshot(run_id, {}, {}, {})

        assert updated is not None
        assert updated.instruction_versions == {}
        assert updated.instruction_snapshot_manifest == {}
        assert updated.instruction_snapshot_payload == {}

        params = _get_update_params(mock_session)
        assert params["instruction_versions"] == {}
        assert params["instruction_snapshot_manifest"] == {}
        assert params["instruction_snapshot_payload"] == {}
        assert params["execution_manifest"]["doc_type_instructions"] == {}

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
        assert mock_session.execute.await_count == 1
        mock_session.flush.assert_not_called()

    async def test_idempotent(self, mock_session: MagicMock) -> None:
        run_id = uuid.uuid4()
        playbook_version_id = uuid.uuid4()
        versions = {"nda": "11111111-1111-1111-1111-111111111111"}

        first_run = _make_run(
            run_id,
            playbook_version_id=playbook_version_id,
            versions=versions,
            manifest={},
            payload={},
        )
        second_run = _make_run(
            run_id,
            playbook_version_id=playbook_version_id,
            versions=versions,
            manifest={},
            payload={},
        )
        playbook_version = _make_playbook_version(playbook_version_id)

        mock_session.execute.side_effect = (
            _make_success_execute_side_effect(
                run=first_run,
                playbook_version=playbook_version,
                updated_run=first_run,
            )
            + _make_success_execute_side_effect(
                run=second_run,
                playbook_version=playbook_version,
                updated_run=second_run,
            )
        )

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
        playbook_version_id = uuid.uuid4()

        run = _make_run(
            run_id,
            playbook_version_id=playbook_version_id,
            versions={},
            manifest={},
            payload={},
        )
        playbook_version = _make_playbook_version(playbook_version_id)

        mock_session.execute.side_effect = _make_success_execute_side_effect(
            run=run,
            playbook_version=playbook_version,
            updated_run=run,
        )

        repo = RunRepository(mock_session)
        updated = await repo.update_instruction_snapshot(
            run_id, {}, {}, {}, snapshot_schema_version=None
        )

        assert updated is not None

        params = _get_update_params(mock_session)
        assert "snapshot_schema_version" not in params

    async def test_execution_manifest_contains_override_provenance(
        self, mock_session: MagicMock
    ) -> None:
        run_id = uuid.uuid4()
        playbook_version_id = uuid.uuid4()
        model_config_id = uuid.uuid4()

        versions = {"nda": "11111111-1111-1111-1111-111111111111"}
        manifest = {
            "nda": {
                "version_id": versions["nda"],
                "content_hash": "base-hash",
                "override_id": "33333333-3333-3333-3333-333333333333",
                "tenant_override_id": "22222222-2222-2222-2222-222222222222",
                "deal_override_id": "33333333-3333-3333-3333-333333333333",
                "effective_hash": "effective-hash",
                "is_overridden": True,
                "resolution_strategy": "effective_override_chain",
            }
        }
        payload = {"nda": {"checks_v8": [{"id": "tenant-customized"}]}}

        run = _make_run(
            run_id,
            playbook_version_id=playbook_version_id,
            model_config_id=model_config_id,
            versions=versions,
            manifest=manifest,
            payload=payload,
        )
        playbook_version = _make_playbook_version(
            playbook_version_id,
            immutable_content_hash="playbook-immutable-hash",
        )

        mock_session.execute.side_effect = _make_success_execute_side_effect(
            run=run,
            playbook_version=playbook_version,
            updated_run=run,
        )

        repo = RunRepository(mock_session)
        updated = await repo.update_instruction_snapshot(run_id, versions, manifest, payload)

        assert updated is not None

        params = _get_update_params(mock_session)
        execution_manifest = params["execution_manifest"]

        assert execution_manifest["schema_version"] == 1
        assert execution_manifest["playbook"] == {
            "version_id": str(playbook_version_id),
            "immutable_content_hash": "playbook-immutable-hash",
            "model_config_id": str(model_config_id),
        }
        assert execution_manifest["doc_type_instructions"]["nda"] == {
            "version_id": versions["nda"],
            "override_id": "33333333-3333-3333-3333-333333333333",
            "tenant_override_id": "22222222-2222-2222-2222-222222222222",
            "deal_override_id": "33333333-3333-3333-3333-333333333333",
            "effective_hash": "effective-hash",
            "is_overridden": True,
            "resolution_strategy": "effective_override_chain",
        }


        