from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.instruction_editor_service import InstructionEditorService
from services.instruction_publishing_service import (
    InstructionVersionNotFoundError,
)


def _version(
    *,
    version_id: uuid.UUID | None = None,
    doc_type_code: str = "nda",
    version_status: str = "published",
    source_yaml: str = "checks_v8: []",
    source_sha256: str = "sha123",
    name: str = "NDA",
):
    return SimpleNamespace(
        id=version_id or uuid.uuid4(),
        doc_type_code=doc_type_code,
        version_status=version_status,
        source_yaml=source_yaml,
        source_sha256=source_sha256,
        name=name,
        source_path="/tmp/nda.yaml",
        git_commit=None,
        semver=None,
        compiled_payload={"checks_v8": []},
        validation_report={"is_valid": True, "checks_count": 0},
        change_summary=None,
        parent_version_id=None,
    )


def _compiled(
    *,
    doc_type_code: str = "nda",
    source_sha256: str = "sha123",
    is_valid: bool = True,
    checks_count: int = 2,
):
    return SimpleNamespace(
        doc_type_code=doc_type_code,
        source_yaml="checks_v8: []",
        source_sha256=source_sha256,
        compiled_payload={"checks_v8": []},
        compiled_payload_sha256="payloadsha",
        checks_count=checks_count,
        triggers_used_for_validation=["t1"],
        diagnostics=[],
        validation_report={
            "is_valid": is_valid,
            "checks_count": checks_count,
            "diagnostics": [],
        },
        is_valid=is_valid,
    )


@pytest.fixture
def service() -> InstructionEditorService:
    svc = InstructionEditorService(MagicMock())
    svc.version_repo = MagicMock()
    svc.compiler = MagicMock()
    return svc


@pytest.mark.asyncio
class TestCloneDraft:
    async def test_clone_draft_success(self, service: InstructionEditorService) -> None:
        source = _version(version_status="published")
        compiled = _compiled(source_sha256="newsha")
        cloned = _version(version_status="draft", source_sha256="newsha")

        service.version_repo.get_by_id = AsyncMock(return_value=source)
        service.compiler.compile_doc_type_instruction.return_value = compiled
        service.version_repo.get_by_doc_type_and_sha256 = AsyncMock(return_value=None)
        service.version_repo.create_version = AsyncMock(return_value=cloned)

        result = await service.clone_draft(
            source_version_id=source.id,
            change_summary="cloned for editing",
            created_by=uuid.uuid4(),
        )

        assert result is cloned
        service.version_repo.create_version.assert_awaited_once()
        call_kwargs = service.version_repo.create_version.call_args.kwargs
        assert call_kwargs["version_status"] == "draft"
        assert call_kwargs["parent_version_id"] == source.id
        assert call_kwargs["immutable_content_hash"] is None

    async def test_clone_draft_source_not_found_raises(
        self, service: InstructionEditorService
    ) -> None:
        service.version_repo.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(InstructionVersionNotFoundError):
            await service.clone_draft(source_version_id=uuid.uuid4())

    async def test_clone_draft_creates_draft_copy(
        self, service: InstructionEditorService
    ) -> None:
        """clone_draft creates a working draft copy from source.

        Дубликат-чек по sha256 намеренно отсутствует (см. docstring
        InstructionEditorService.clone_draft): клон — рабочая копия
        для редактирования, тот же YAML/sha — норма.
        """
        source = _version()
        compiled = _compiled()
        cloned = _version(
            version_id=uuid.uuid4(),
            version_status="draft",
        )

        service.version_repo.get_by_id = AsyncMock(return_value=source)
        service.compiler.compile_doc_type_instruction.return_value = compiled
        service.version_repo.create_version = AsyncMock(return_value=cloned)

        result = await service.clone_draft(source_version_id=source.id)

        assert result is cloned
        service.version_repo.create_version.assert_awaited_once()
        # Дубликат-чек по sha256 не должен вызываться в clone_draft.
        service.version_repo.get_by_doc_type_and_sha256.assert_not_called()


@pytest.mark.asyncio
class TestPreview:
    async def test_preview_valid_yaml(self, service: InstructionEditorService) -> None:
        compiled = _compiled(is_valid=True, checks_count=5)

        service.compiler.compile_doc_type_instruction.return_value = compiled
        service.version_repo.get_by_doc_type_and_sha256 = AsyncMock(return_value=None)

        result = await service.preview(
            doc_type_code="nda",
            source_yaml="checks_v8: []",
        )

        assert result.is_valid is True
        assert result.checks_count == 5
        assert result.already_exists is False
        assert result.existing_version_id is None

    async def test_preview_existing_version_detected(
        self, service: InstructionEditorService
    ) -> None:
        compiled = _compiled()
        existing = _version()

        service.compiler.compile_doc_type_instruction.return_value = compiled
        service.version_repo.get_by_doc_type_and_sha256 = AsyncMock(return_value=existing)

        result = await service.preview(
            doc_type_code="nda",
            source_yaml="checks_v8: []",
        )

        assert result.already_exists is True
        assert result.existing_version_id == str(existing.id)

    async def test_preview_invalid_yaml_raises(
        self, service: InstructionEditorService
    ) -> None:
        from services.instruction_compiler import InstructionCompilationError

        service.compiler.compile_doc_type_instruction.side_effect = (
            InstructionCompilationError("YAML parse error: ...")
        )

        with pytest.raises(InstructionCompilationError):
            await service.preview(
                doc_type_code="nda",
                source_yaml="}{invalid{",
            )


@pytest.mark.asyncio
class TestDiff:
    async def test_diff_identical_versions(
        self, service: InstructionEditorService
    ) -> None:
        yaml_content = "checks_v8: []\n"
        v1 = _version(source_yaml=yaml_content, source_sha256="samesha")
        v2 = _version(source_yaml=yaml_content, source_sha256="samesha")

        service.version_repo.get_by_id = AsyncMock(side_effect=[v1, v2])

        result = await service.diff(
            from_version_id=v1.id,
            to_version_id=v2.id,
        )

        assert result.are_identical is True
        assert result.unified_diff == []

    async def test_diff_different_versions(
        self, service: InstructionEditorService
    ) -> None:
        v1 = _version(
            source_yaml="checks_v8:\n  - id: check_1\n",
            source_sha256="sha_old",
        )
        v2 = _version(
            source_yaml="checks_v8:\n  - id: check_2\n",
            source_sha256="sha_new",
        )

        service.version_repo.get_by_id = AsyncMock(side_effect=[v1, v2])

        result = await service.diff(
            from_version_id=v1.id,
            to_version_id=v2.id,
        )

        assert result.are_identical is False
        assert len(result.unified_diff) > 0
        diff_text = "\n".join(result.unified_diff)
        assert "check_1" in diff_text
        assert "check_2" in diff_text

    async def test_diff_from_not_found_raises(
        self, service: InstructionEditorService
    ) -> None:
        service.version_repo.get_by_id = AsyncMock(return_value=None)

        with pytest.raises(InstructionVersionNotFoundError):
            await service.diff(
                from_version_id=uuid.uuid4(),
                to_version_id=uuid.uuid4(),
            )

    async def test_diff_to_not_found_raises(
        self, service: InstructionEditorService
    ) -> None:
        v1 = _version()
        service.version_repo.get_by_id = AsyncMock(side_effect=[v1, None])

        with pytest.raises(InstructionVersionNotFoundError):
            await service.diff(
                from_version_id=v1.id,
                to_version_id=uuid.uuid4(),
            )


            