from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.instruction_publishing_service import (
    DraftValidationError,
    DuplicateInstructionContentError,
    ImmutableVersionError,
    InstructionPublishingService,
    InstructionVersionNotFoundError,
    InvalidLifecycleTransitionError,
)


@pytest.fixture
def mock_session() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service(mock_session: MagicMock) -> InstructionPublishingService:
    svc = InstructionPublishingService(mock_session)
    svc.version_repo = MagicMock()
    svc.override_repo = MagicMock()
    svc.compiler = MagicMock()
    return svc


def _compiled(
    *,
    doc_type_code: str = "nda",
    source_yaml: str = "foo: bar",
    source_sha256: str = "sha123",
    compiled_payload: dict | None = None,
    compiled_payload_sha256: str = "payloadsha123",
    is_valid: bool = True,
    checks_count: int = 2,
):
    return SimpleNamespace(
        doc_type_code=doc_type_code,
        source_yaml=source_yaml,
        source_sha256=source_sha256,
        compiled_payload=compiled_payload if compiled_payload is not None else {"checks_v8": []},
        compiled_payload_sha256=compiled_payload_sha256,
        checks_count=checks_count,
        triggers_used_for_validation=["t1"],
        diagnostics=[],
        validation_report={"is_valid": is_valid, "checks_count": checks_count, "diagnostics": []},
        is_valid=is_valid,
    )


def _version(
    *,
    version_id: uuid.UUID | None = None,
    doc_type_code: str = "nda",
    version_status: str = "draft",
    owner_scope: str = "platform",
    tenant_id: uuid.UUID | None = None,
):
    v = MagicMock()
    v.id = version_id or uuid.uuid4()
    v.doc_type_code = doc_type_code
    v.version_status = version_status
    v.owner_scope = owner_scope
    v.tenant_id = tenant_id
    v.name = "NDA"
    v.source_yaml = "foo: bar"
    v.source_sha256 = "sha123"
    v.source_path = "/tmp/nda.yaml"
    v.git_commit = None
    v.semver = None
    v.compiled_payload = {"checks_v8": []}
    v.validation_report = None
    v.change_summary = "initial"
    v.immutable_content_hash = None
    v.parent_version_id = None
    v.derived_from_version_id = None
    v.published_at = None
    return v


@pytest.mark.asyncio
class TestInstructionPublishingService:
    async def test_create_draft_success(self, service: InstructionPublishingService) -> None:
        compiled = _compiled()
        created_version = _version()

        service.compiler.compile_doc_type_instruction.return_value = compiled
        service.version_repo.get_by_doc_type_and_sha256 = AsyncMock(return_value=None)
        service.version_repo.create_version = AsyncMock(return_value=created_version)

        result = await service.create_draft(
            doc_type_code="nda",
            source="foo: bar",
            created_by=uuid.uuid4(),
            change_summary="new draft",
        )

        assert result is created_version
        service.version_repo.create_version.assert_awaited_once()

    async def test_create_draft_duplicate_raises(self, service: InstructionPublishingService) -> None:
        compiled = _compiled()
        existing = _version(version_status="published")

        service.compiler.compile_doc_type_instruction.return_value = compiled
        service.version_repo.get_by_doc_type_and_sha256 = AsyncMock(return_value=existing)

        with pytest.raises(DuplicateInstructionContentError):
            await service.create_draft(
                doc_type_code="nda",
                source="foo: bar",
            )

    async def test_update_draft_rejects_non_draft(self, service: InstructionPublishingService) -> None:
        version = _version(version_status="published")
        service.version_repo.get_version_for_update = AsyncMock(return_value=version)

        with pytest.raises(ImmutableVersionError):
            await service.update_draft(
                version_id=version.id,
                source="foo: baz",
            )

    async def test_update_draft_success(self, service: InstructionPublishingService) -> None:
        version = _version(version_status="draft")
        compiled = _compiled(source_yaml="foo: baz", source_sha256="sha456")
        updated_version = version

        service.version_repo.get_version_for_update = AsyncMock(return_value=version)
        service.compiler.compile_doc_type_instruction.return_value = compiled
        service.version_repo.get_by_doc_type_and_sha256 = AsyncMock(return_value=version)
        service.version_repo.update_version = AsyncMock(return_value=updated_version)

        result = await service.update_draft(
            version_id=version.id,
            source="foo: baz",
            change_summary="changed",
        )

        assert result is updated_version
        service.version_repo.update_version.assert_awaited_once()

    async def test_validate_draft_success(self, service: InstructionPublishingService) -> None:
        version = _version(version_status="draft")
        compiled = _compiled()

        service.version_repo.get_version_for_update = AsyncMock(return_value=version)
        service.compiler.compile_doc_type_instruction.return_value = compiled
        service.version_repo.get_by_doc_type_and_sha256 = AsyncMock(return_value=version)
        service.version_repo.update_version = AsyncMock(return_value=version)

        result = await service.validate_draft(version_id=version.id)

        assert result is compiled
        service.version_repo.update_version.assert_awaited_once()

    async def test_publish_draft_success(self, service: InstructionPublishingService) -> None:
        version = _version(version_status="draft")
        compiled = _compiled(is_valid=True)

        service.version_repo.get_version_for_update = AsyncMock(return_value=version)
        service.compiler.compile_doc_type_instruction.return_value = compiled
        service.version_repo.get_by_doc_type_and_sha256 = AsyncMock(return_value=version)
        service.version_repo.archive_previous_published = AsyncMock(return_value=1)
        service.version_repo.update_version = AsyncMock(return_value=version)
        service.override_repo.mark_stale_where_base_outdated = AsyncMock(return_value=3)

        result = await service.publish_draft(version_id=version.id)

        assert result is version
        service.version_repo.archive_previous_published.assert_awaited_once()
        service.version_repo.update_version.assert_awaited_once()
        service.override_repo.mark_stale_where_base_outdated.assert_awaited_once()

    async def test_publish_draft_rejects_invalid_compilation(self, service: InstructionPublishingService) -> None:
        version = _version(version_status="draft")
        compiled = _compiled(is_valid=False)

        service.version_repo.get_version_for_update = AsyncMock(return_value=version)
        service.compiler.compile_doc_type_instruction.return_value = compiled

        with pytest.raises(DraftValidationError):
            await service.publish_draft(version_id=version.id)

    async def test_publish_draft_rejects_non_draft(self, service: InstructionPublishingService) -> None:
        version = _version(version_status="archived")
        service.version_repo.get_version_for_update = AsyncMock(return_value=version)

        with pytest.raises(InvalidLifecycleTransitionError):
            await service.publish_draft(version_id=version.id)

    async def test_archive_version_success(self, service: InstructionPublishingService) -> None:
        version = _version(version_status="published")

        service.version_repo.get_version_for_update = AsyncMock(return_value=version)
        service.version_repo.update_version = AsyncMock(return_value=version)

        result = await service.archive_version(version_id=version.id)

        assert result is version
        service.version_repo.update_version.assert_awaited_once()

    async def test_archive_version_not_found(self, service: InstructionPublishingService) -> None:
        service.version_repo.get_version_for_update = AsyncMock(return_value=None)

        with pytest.raises(InstructionVersionNotFoundError):
            await service.archive_version(version_id=uuid.uuid4())


            