"""
Unit-тесты для engine.checks.instruction_snapshot.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engine.checks.instruction_snapshot import (
    build_doc_type_loader,
    freeze_instruction_snapshot,
)
from engine.doc_type_checks.loader import DatabaseInstructionProvider, DocTypeCheckLoader, FilesystemInstructionProvider


@pytest.fixture
def mock_run_repo():
    repo = AsyncMock()
    repo.update_instruction_snapshot = AsyncMock(return_value=MagicMock())
    return repo


@pytest.mark.asyncio
async def test_freeze_instruction_snapshot_no_doc_types_writes_empty(mock_run_repo):
    result = await freeze_instruction_snapshot(
        run_uuid=uuid.uuid4(),
        doc_types=set(),
        run_repo=mock_run_repo,
        session=MagicMock(),
    )

    assert result == {}
    mock_run_repo.update_instruction_snapshot.assert_called_once()
    call_args = mock_run_repo.update_instruction_snapshot.call_args[0]
    assert call_args[1] == {} and call_args[2] == {} and call_args[3] == {}


@pytest.mark.asyncio
async def test_freeze_instruction_snapshot_filters_unknown_doc_type(mock_run_repo):
    result = await freeze_instruction_snapshot(
        run_uuid=uuid.uuid4(),
        doc_types={"unknown", "UNKNOWN", "", None},
        run_repo=mock_run_repo,
        session=MagicMock(),
    )
    assert result == {}


@pytest.mark.asyncio
async def test_freeze_instruction_snapshot_resolves_valid_doc_type(mock_run_repo):
    fake_cfg = MagicMock()
    fake_cfg.raw = {"checks_v8": [{"id": "chk_1"}]}
    fake_cfg.source_sha256 = "hash123"

    fake_version = MagicMock()
    fake_version.id = uuid.uuid4()
    fake_resolve_result = MagicMock(version=fake_version, created=True)

    with patch("engine.checks.instruction_snapshot.YAMLRegistry") as mock_registry_cls, \
         patch("engine.checks.instruction_snapshot.DocumentTypeInstructionVersionRepository") as mock_version_repo_cls:

        mock_registry = MagicMock()
        mock_registry.get_config.return_value = fake_cfg
        mock_registry_cls.get_instance.return_value = mock_registry

        mock_version_repo = AsyncMock()
        mock_version_repo.resolve_or_create_from_config = AsyncMock(return_value=fake_resolve_result)
        mock_version_repo_cls.return_value = mock_version_repo

        result = await freeze_instruction_snapshot(
            run_uuid=uuid.uuid4(),
            doc_types={"nda"},
            run_repo=mock_run_repo,
            session=MagicMock(),
        )

    assert result == {"nda": str(fake_version.id)}

    call_args = mock_run_repo.update_instruction_snapshot.call_args[0]
    versions, manifest, payload = call_args[1], call_args[2], call_args[3]
    assert versions == {"nda": str(fake_version.id)}
    assert manifest["nda"]["content_hash"] == "hash123"
    assert payload["nda"] == fake_cfg.raw


@pytest.mark.asyncio
async def test_freeze_instruction_snapshot_missing_config_does_not_raise(mock_run_repo):
    with patch("engine.checks.instruction_snapshot.YAMLRegistry") as mock_registry_cls:
        mock_registry = MagicMock()
        mock_registry.get_config.return_value = None
        mock_registry_cls.get_instance.return_value = mock_registry

        result = await freeze_instruction_snapshot(
            run_uuid=uuid.uuid4(),
            doc_types={"nonexistent_type"},
            run_repo=mock_run_repo,
            session=MagicMock(),
        )

    assert result == {}
    # Должен всё равно записать (пустой) снапшот, не поднимать исключение
    mock_run_repo.update_instruction_snapshot.assert_called_once()


@pytest.mark.asyncio
async def test_freeze_instruction_snapshot_resolve_exception_isolated(mock_run_repo):
    """Ошибка резолюции одного doc_type не должна ронять весь freeze."""
    fake_cfg = MagicMock()
    fake_cfg.raw = {}

    with patch("engine.checks.instruction_snapshot.YAMLRegistry") as mock_registry_cls, \
         patch("engine.checks.instruction_snapshot.DocumentTypeInstructionVersionRepository") as mock_version_repo_cls:

        mock_registry = MagicMock()
        mock_registry.get_config.return_value = fake_cfg
        mock_registry_cls.get_instance.return_value = mock_registry

        mock_version_repo = AsyncMock()
        mock_version_repo.resolve_or_create_from_config = AsyncMock(
            side_effect=Exception("DB connection lost")
        )
        mock_version_repo_cls.return_value = mock_version_repo

        result = await freeze_instruction_snapshot(
            run_uuid=uuid.uuid4(),
            doc_types={"nda"},
            run_repo=mock_run_repo,
            session=MagicMock(),
        )

    assert result == {}  # doc_type упал, но функция не подняла exception


def test_build_doc_type_loader_uses_db_provider_when_payload_present():
    run_snap = MagicMock()
    run_snap.instruction_snapshot_payload = {"nda": {"checks_v8": []}}

    loader = build_doc_type_loader(run_snap)

    assert isinstance(loader, DocTypeCheckLoader)
    assert isinstance(loader.provider, DatabaseInstructionProvider)


def test_build_doc_type_loader_falls_back_to_filesystem_when_no_payload():
    run_snap = MagicMock()
    run_snap.instruction_snapshot_payload = None

    loader = build_doc_type_loader(run_snap)

    assert isinstance(loader, DocTypeCheckLoader)
    assert isinstance(loader.provider, FilesystemInstructionProvider)


def test_build_doc_type_loader_falls_back_when_payload_empty_dict():
    run_snap = MagicMock()
    run_snap.instruction_snapshot_payload = {}

    loader = build_doc_type_loader(run_snap)

    assert isinstance(loader.provider, FilesystemInstructionProvider)

    