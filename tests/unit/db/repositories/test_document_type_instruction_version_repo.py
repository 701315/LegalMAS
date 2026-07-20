"""Unit tests for DocumentTypeInstructionVersionRepository (mocked AsyncSession)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.models.document_type_instruction import DocumentTypeInstructionVersion
from db.repositories.document_type_instruction_version_repo import (
    DocumentTypeInstructionVersionRepository,
    ResolveInstructionVersionResult,
)


def _make_execute_result(*, scalar=None, scalars_all=None) -> MagicMock:
    """
    Универсальный мок результата session.execute(stmt).
    """
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar

    scalars_obj = MagicMock()
    scalars_obj.all.return_value = scalars_all or []
    result.scalars.return_value = scalars_obj

    return result


def _make_version(
    *,
    version_id: uuid.UUID | None = None,
    doc_type_code: str = "nda",
    source_sha256: str = "abc123",
    version_status: str = "draft",
) -> MagicMock:
    version = MagicMock(spec=DocumentTypeInstructionVersion)
    version.id = version_id or uuid.uuid4()
    version.doc_type_code = doc_type_code
    version.source_sha256 = source_sha256
    version.version_status = version_status
    version.created_at = None
    version.source_yaml = "foo: bar"
    version.compiled_payload = {"checks": []}
    version.name = "NDA"
    version.source_path = "/tmp/nda.yaml"
    version.git_commit = None
    version.semver = None
    version.validation_report = None
    version.change_summary = None
    version.immutable_content_hash = None
    version.parent_version_id = None
    version.published_at = None
    return version


@pytest.fixture
def mock_session() -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.mark.asyncio
class TestDocumentTypeInstructionVersionRepository:

    async def test_get_latest_published_returns_value(self, mock_session: MagicMock) -> None:
        version = _make_version(version_status="published")
        mock_session.execute.return_value = _make_execute_result(scalar=version)

        repo = DocumentTypeInstructionVersionRepository(mock_session)
        result = await repo.get_latest_published("nda")

        assert result is version
        mock_session.execute.assert_awaited_once()

    async def test_get_latest_by_doc_type_code_draft_allowed(self, mock_session: MagicMock) -> None:
        version = _make_version(version_status="draft")
        mock_session.execute.return_value = _make_execute_result(scalar=version)

        repo = DocumentTypeInstructionVersionRepository(mock_session)
        result = await repo.get_latest_by_doc_type_code("nda", published_only=False)

        assert result is version
        mock_session.execute.assert_awaited_once()

    async def test_get_version_for_update_returns_row(self, mock_session: MagicMock) -> None:
        version = _make_version()
        mock_session.execute.return_value = _make_execute_result(scalar=version)

        repo = DocumentTypeInstructionVersionRepository(mock_session)
        result = await repo.get_version_for_update(version.id)

        assert result is version
        mock_session.execute.assert_awaited_once()

    async def test_list_by_doc_type_code_returns_all_rows(self, mock_session: MagicMock) -> None:
        versions = [_make_version(), _make_version()]
        mock_session.execute.return_value = _make_execute_result(scalars_all=versions)

        repo = DocumentTypeInstructionVersionRepository(mock_session)
        result = await repo.list_by_doc_type_code("nda")

        assert result == versions
        mock_session.execute.assert_awaited_once()

    async def test_archive_previous_published_returns_rowcount(self, mock_session: MagicMock) -> None:
        execute_result = MagicMock()
        execute_result.rowcount = 3
        mock_session.execute.return_value = execute_result

        repo = DocumentTypeInstructionVersionRepository(mock_session)
        affected = await repo.archive_previous_published(
            doc_type_code="nda",
            exclude_version_id=uuid.uuid4(),
        )

        assert affected == 3
        mock_session.flush.assert_awaited_once()

    async def test_update_version_updates_fields_and_flushes(self, mock_session: MagicMock) -> None:
        version = _make_version()

        repo = DocumentTypeInstructionVersionRepository(mock_session)
        result = await repo.update_version(
            version,
            source_yaml="new: yaml",
            source_sha256="newsha",
            compiled_payload={"checks": [{"id": "c1"}]},
            name="Updated name",
            source_path="/new/path.yaml",
            git_commit="abcdef",
            semver="1.2.3",
            validation_report={"is_valid": True},
            change_summary="updated",
            immutable_content_hash="hash123",
            version_status="published",
            parent_version_id=uuid.uuid4(),
            published_at="2026-01-01T00:00:00Z",
        )

        assert result is version
        assert version.source_yaml == "new: yaml"
        assert version.source_sha256 == "newsha"
        assert version.compiled_payload == {"checks": [{"id": "c1"}]}
        assert version.name == "Updated name"
        assert version.source_path == "/new/path.yaml"
        assert version.git_commit == "abcdef"
        assert version.semver == "1.2.3"
        assert version.validation_report == {"is_valid": True}
        assert version.change_summary == "updated"
        assert version.immutable_content_hash == "hash123"
        assert version.version_status == "published"
        mock_session.flush.assert_awaited_once()

    async def test_build_persistence_payload_uses_cfg_source_yaml(self, mock_session: MagicMock) -> None:
        cfg = SimpleNamespace(
            type_code="nda",
            name="NDA",
            source_yaml="foo: bar",
            source_sha256="sha123",
            source_path="/tmp/nda.yaml",
            source_kind="file",
            raw={"checks": []},
        )

        repo = DocumentTypeInstructionVersionRepository(mock_session)
        payload = repo._build_persistence_payload(
            cfg,
            git_commit="abcdef",
            semver="1.0.0",
            compiled_payload={"checks": []},
        )

        assert payload["doc_type_code"] == "nda"
        assert payload["source_yaml"] == "foo: bar"
        assert payload["source_sha256"] == "sha123"
        assert payload["compiled_payload"] == {"checks": []}
        assert payload["version_status"] == "draft"
        assert payload["immutable_content_hash"] is None
        assert payload["validation_report"] is None
        assert payload["parent_version_id"] is None

    async def test_build_persistence_payload_rejects_empty_type_code(self, mock_session: MagicMock) -> None:
        cfg = SimpleNamespace(
            type_code="",
            name="NDA",
            source_yaml="foo: bar",
            source_sha256="sha123",
            source_path="/tmp/nda.yaml",
            source_kind="file",
            raw={"checks": []},
        )

        repo = DocumentTypeInstructionVersionRepository(mock_session)

        with pytest.raises(ValueError, match="cfg.type_code is empty"):
            repo._build_persistence_payload(
                cfg,
                git_commit=None,
                semver=None,
                compiled_payload=None,
            )


            