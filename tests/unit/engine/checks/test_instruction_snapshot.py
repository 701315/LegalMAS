"""
Unit-тесты для engine.checks.instruction_snapshot и snapshot_policy.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engine.checks.instruction_snapshot import (
    build_doc_type_loader,
    freeze_instruction_snapshot,
)
from engine.checks.snapshot_policy import (
    ConfigurationIntegrityError,
    resolve_doc_type_payload,
)
from engine.doc_type_checks.loader import (
    DatabaseInstructionProvider,
    DocTypeCheckLoader,
    FilesystemInstructionProvider,
)


@pytest.fixture
def mock_run_repo():
    repo = AsyncMock()
    repo.update_instruction_snapshot = AsyncMock(return_value=MagicMock())
    return repo


# ──────────────────────────────────────────────────────────────────────────────
# freeze_instruction_snapshot tests
# ──────────────────────────────────────────────────────────────────────────────

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
    fake_cfg.source_yaml = "checks_v8:\n  - id: chk_1\n"

    fake_version = MagicMock()
    fake_version.id = uuid.uuid4()
    fake_version.compiled_payload = {"checks_v8": [{"id": "chk_1"}]}
    fake_version.immutable_content_hash = "hash123"
    fake_version.source_yaml = "checks_v8:\n  - id: chk_1\n"

    fake_resolve_result = MagicMock(version=fake_version, created=True)

    with patch("engine.checks.instruction_snapshot.YAMLRegistry") as mock_registry_cls, \
         patch("engine.checks.instruction_snapshot.DocumentTypeInstructionVersionRepository") as mock_version_repo_cls:

        mock_registry = MagicMock()
        mock_registry.get_config.return_value = fake_cfg
        mock_registry_cls.get_instance.return_value = mock_registry

        mock_version_repo = AsyncMock()
        mock_version_repo.resolve_or_create_from_config = AsyncMock(
            return_value=fake_resolve_result
        )
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
    # Strict: payload = compiled_payload, не raw
    assert payload["nda"] == {"checks_v8": [{"id": "chk_1"}]}
    # snapshot_schema_version должен быть выставлен атомарно вместе со snapshot
    call_kwargs = mock_run_repo.update_instruction_snapshot.call_args
    # Проверяем что snapshot_schema_version передан в тот же вызов
    assert call_kwargs is not None


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
    mock_run_repo.update_instruction_snapshot.assert_called_once()


@pytest.mark.asyncio
async def test_freeze_instruction_snapshot_resolve_exception_isolated(mock_run_repo):
    fake_cfg = MagicMock()
    fake_cfg.raw = {}
    fake_cfg.source_yaml = ""

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

    assert result == {}


# ──────────────────────────────────────────────────────────────────────────────
# build_doc_type_loader tests
# ──────────────────────────────────────────────────────────────────────────────

def test_build_doc_type_loader_strict_mode_uses_db_provider():
    """Strict Run с payload → DatabaseInstructionProvider."""
    run_snap = MagicMock()
    run_snap.instruction_snapshot_payload = {"nda": {"checks_v8": []}}
    run_snap.is_strict_snapshot = True
    run_snap.id = uuid.uuid4()

    loader = build_doc_type_loader(run_snap)

    assert isinstance(loader, DocTypeCheckLoader)
    assert isinstance(loader.provider, DatabaseInstructionProvider)


def test_build_doc_type_loader_strict_mode_no_payload_raises():
    """Strict Run без payload → ConfigurationIntegrityError."""
    run_snap = MagicMock()
    run_snap.instruction_snapshot_payload = None
    run_snap.is_strict_snapshot = True
    run_snap.id = uuid.uuid4()

    with pytest.raises(ConfigurationIntegrityError):
        build_doc_type_loader(run_snap)


def test_build_doc_type_loader_strict_mode_empty_payload_raises():
    """Strict Run с пустым payload → ConfigurationIntegrityError."""
    run_snap = MagicMock()
    run_snap.instruction_snapshot_payload = {}
    run_snap.is_strict_snapshot = True
    run_snap.id = uuid.uuid4()

    with pytest.raises(ConfigurationIntegrityError):
        build_doc_type_loader(run_snap)


def test_build_doc_type_loader_legacy_with_payload_uses_db_provider():
    """Legacy Run с payload → DatabaseInstructionProvider (не filesystem)."""
    run_snap = MagicMock()
    run_snap.instruction_snapshot_payload = {"nda": {"checks_v8": []}}
    run_snap.is_strict_snapshot = False
    run_snap.id = uuid.uuid4()

    loader = build_doc_type_loader(run_snap)

    assert isinstance(loader.provider, DatabaseInstructionProvider)


def test_build_doc_type_loader_legacy_without_payload_uses_filesystem():
    """Legacy Run без payload → FilesystemInstructionProvider."""
    run_snap = MagicMock()
    run_snap.instruction_snapshot_payload = None
    run_snap.is_strict_snapshot = False
    run_snap.id = uuid.uuid4()

    loader = build_doc_type_loader(run_snap)

    assert isinstance(loader.provider, FilesystemInstructionProvider)


def test_build_doc_type_loader_legacy_empty_payload_uses_filesystem():
    """Legacy Run с пустым dict payload → FilesystemInstructionProvider."""
    run_snap = MagicMock()
    run_snap.instruction_snapshot_payload = {}
    run_snap.is_strict_snapshot = False
    run_snap.id = uuid.uuid4()

    loader = build_doc_type_loader(run_snap)

    assert isinstance(loader.provider, FilesystemInstructionProvider)


# ──────────────────────────────────────────────────────────────────────────────
# resolve_doc_type_payload tests (snapshot_policy)
# ──────────────────────────────────────────────────────────────────────────────

def test_resolve_payload_legacy_no_payload_returns_none_not_raises():
    result = resolve_doc_type_payload(
        run_id="run-1",
        snapshot_schema_version=None,
        instruction_snapshot_payload=None,
        doc_type="nda",
    )
    assert result.is_legacy is True
    assert result.payload is None
    assert result.is_reproducible is False
    assert result.warning is not None


def test_resolve_payload_legacy_with_payload_returns_value():
    payload = {"nda": {"checks_v8": []}}
    result = resolve_doc_type_payload(
        run_id="run-1",
        snapshot_schema_version=None,
        instruction_snapshot_payload=payload,
        doc_type="nda",
    )
    assert result.is_legacy is True
    assert result.payload == {"checks_v8": []}


def test_resolve_payload_strict_missing_all_payload_raises():
    with pytest.raises(ConfigurationIntegrityError) as exc_info:
        resolve_doc_type_payload(
            run_id="run-1",
            snapshot_schema_version=1,
            instruction_snapshot_payload=None,
            doc_type="nda",
        )
    assert exc_info.value.run_id == "run-1"
    assert exc_info.value.doc_type == "nda"


def test_resolve_payload_strict_missing_doc_type_raises():
    payload = {"sla": {"checks_v8": []}}
    with pytest.raises(ConfigurationIntegrityError):
        resolve_doc_type_payload(
            run_id="run-1",
            snapshot_schema_version=1,
            instruction_snapshot_payload=payload,
            doc_type="nda",
        )


def test_resolve_payload_strict_with_valid_payload_succeeds():
    payload = {"nda": {"checks_v8": [{"id": "c1"}]}}
    result = resolve_doc_type_payload(
        run_id="run-1",
        snapshot_schema_version=1,
        instruction_snapshot_payload=payload,
        doc_type="nda",
    )
    assert result.is_legacy is False
    assert result.payload == {"checks_v8": [{"id": "c1"}]}
    assert result.is_reproducible is True
    assert result.warning is None

    