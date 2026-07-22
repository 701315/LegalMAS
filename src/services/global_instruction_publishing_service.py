# src/services/global_instruction_publishing_service.py

"""
Global instruction publishing service.

Lifecycle: create_draft → update_draft → validate_draft → publish_draft → archive_version
clone_draft доступен через GlobalInstructionEditorService.

Паттерн идентичен InstructionPublishingService.
Использует расширенный InstructionCompiler.compile_global_instruction().
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.models.global_instruction import GlobalInstructionVersion
from db.repositories.global_instruction_version_repo import (
    GlobalInstructionVersionRepository,
)
from db.repositories.instruction_override_repo import InstructionOverrideRepository
from services.instruction_compiler import (
    CompiledGlobalInstruction,
    InstructionCompilationError,
    InstructionCompiler,
)

logger = get_logger(__name__)


class GlobalInstructionLifecycleError(Exception):
    """Base lifecycle error."""


class GlobalInstructionNotFoundError(GlobalInstructionLifecycleError):
    pass


class GlobalInstructionImmutableError(GlobalInstructionLifecycleError):
    pass


class GlobalInstructionDuplicateContentError(GlobalInstructionLifecycleError):
    pass


class GlobalInstructionDraftValidationError(GlobalInstructionLifecycleError):
    pass


class GlobalInstructionInvalidTransitionError(GlobalInstructionLifecycleError):
    pass


class GlobalInstructionPublishingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = GlobalInstructionVersionRepository(session)
        self.override_repo = InstructionOverrideRepository(session)
        self.compiler = InstructionCompiler()

    # ── Create draft ───────────────────────────────────────────────

    async def create_draft(
        self,
        *,
        instruction_code: str,
        source: str | dict,
        name: str | None = None,
        source_path: str | None = None,
        git_commit: str | None = None,
        semver: str | None = None,
        created_by: uuid.UUID | None = None,
        change_summary: str | None = None,
        parent_version_id: uuid.UUID | None = None,
        owner_scope: str = "platform",
        tenant_id: uuid.UUID | None = None,
    ) -> GlobalInstructionVersion:
        compiled = self.compiler.compile_global_instruction(
            instruction_code=instruction_code,
            source=source,
        )

        existing = await self.repo.get_by_instruction_code_and_sha256(
            instruction_code=compiled.instruction_code,
            source_sha256=compiled.source_sha256,
            owner_scope=owner_scope,
            tenant_id=tenant_id,
        )
        if existing is not None:
            raise GlobalInstructionDuplicateContentError(
                f"Cannot create draft: identical snapshot already exists "
                f"for instruction_code='{compiled.instruction_code}' "
                f"(existing_version_id={existing.id})."
            )

        version = await self.repo.create_version(
            instruction_code=compiled.instruction_code,
            name=name or compiled.name,
            group=compiled.group,
            source_yaml=compiled.source_yaml,
            source_sha256=compiled.source_sha256,
            source_path=source_path,
            git_commit=git_commit,
            semver=semver,
            compiled_payload=compiled.compiled_payload,
            version_status="draft",
            immutable_content_hash=None,
            validation_report=compiled.validation_report,
            parent_version_id=parent_version_id,
            published_at=None,
            created_by=created_by,
            change_summary=change_summary,
            owner_scope=owner_scope,
            tenant_id=tenant_id,
        )

        logger.info(
            "Global instruction draft created",
            extra={
                "global_instruction_version_id": str(version.id),
                "instruction_code": compiled.instruction_code,
                "owner_scope": owner_scope,
            },
        )
        return version

    # ── Update draft ───────────────────────────────────────────────

    async def update_draft(
        self,
        *,
        version_id: uuid.UUID,
        source: str | dict,
        name: str | None = None,
        source_path: str | None = None,
        git_commit: str | None = None,
        semver: str | None = None,
        change_summary: str | None = None,
    ) -> GlobalInstructionVersion:
        version = await self.repo.get_version_for_update(version_id)
        if version is None:
            raise GlobalInstructionNotFoundError(
                f"Global instruction version not found: {version_id}"
            )
        self._ensure_draft(version)

        compiled = self.compiler.compile_global_instruction(
            instruction_code=version.instruction_code,
            source=source,
        )

        duplicate = await self.repo.get_by_instruction_code_and_sha256(
            instruction_code=compiled.instruction_code,
            source_sha256=compiled.source_sha256,
            owner_scope=version.owner_scope,
            tenant_id=version.tenant_id,
        )
        if duplicate is not None and duplicate.id != version.id:
            raise GlobalInstructionDuplicateContentError(
                f"Cannot update draft: identical snapshot already exists "
                f"(existing_version_id={duplicate.id})."
            )

        updated = await self.repo.update_version(
            version,
            source_yaml=compiled.source_yaml,
            source_sha256=compiled.source_sha256,
            compiled_payload=compiled.compiled_payload,
            name=name if name is not None else version.name,
            group=compiled.group,
            source_path=source_path if source_path is not None else version.source_path,
            git_commit=git_commit if git_commit is not None else version.git_commit,
            semver=semver if semver is not None else version.semver,
            validation_report=compiled.validation_report,
            change_summary=change_summary if change_summary is not None else version.change_summary,
            version_status="draft",
        )

        logger.info(
            "Global instruction draft updated",
            extra={
                "global_instruction_version_id": str(updated.id),
                "instruction_code": updated.instruction_code,
            },
        )
        return updated

    # ── Validate draft ─────────────────────────────────────────────

    async def validate_draft(
        self,
        *,
        version_id: uuid.UUID,
    ) -> CompiledGlobalInstruction:
        version = await self.repo.get_version_for_update(version_id)
        if version is None:
            raise GlobalInstructionNotFoundError(
                f"Global instruction version not found: {version_id}"
            )
        self._ensure_draft(version)

        compiled = self.compiler.compile_global_instruction(
            instruction_code=version.instruction_code,
            source=version.source_yaml,
        )

        duplicate = await self.repo.get_by_instruction_code_and_sha256(
            instruction_code=compiled.instruction_code,
            source_sha256=compiled.source_sha256,
            owner_scope=version.owner_scope,
            tenant_id=version.tenant_id,
        )
        if duplicate is not None and duplicate.id != version.id:
            raise GlobalInstructionDuplicateContentError(
                f"Cannot validate draft: identical snapshot already exists "
                f"(existing_version_id={duplicate.id})."
            )

        await self.repo.update_version(
            version,
            source_yaml=compiled.source_yaml,
            source_sha256=compiled.source_sha256,
            compiled_payload=compiled.compiled_payload,
            name=version.name,
            group=compiled.group,
            source_path=version.source_path,
            git_commit=version.git_commit,
            semver=version.semver,
            validation_report=compiled.validation_report,
            change_summary=version.change_summary,
            version_status="draft",
        )

        logger.info(
            "Global instruction draft validated",
            extra={
                "global_instruction_version_id": str(version.id),
                "instruction_code": version.instruction_code,
                "is_valid": compiled.is_valid,
            },
        )
        return compiled

    # ── Publish draft ──────────────────────────────────────────────

    async def publish_draft(
        self,
        *,
        version_id: uuid.UUID,
    ) -> GlobalInstructionVersion:
        version = await self.repo.get_version_for_update(version_id)
        if version is None:
            raise GlobalInstructionNotFoundError(
                f"Global instruction version not found: {version_id}"
            )
        if version.version_status != "draft":
            raise GlobalInstructionInvalidTransitionError(
                f"Version {version_id} has status='{version.version_status}'. "
                "Only draft versions can be published."
            )

        compiled = self.compiler.compile_global_instruction(
            instruction_code=version.instruction_code,
            source=version.source_yaml,
        )
        if not compiled.is_valid:
            raise GlobalInstructionDraftValidationError(
                f"Draft {version_id} has validation errors and cannot be published."
            )

        duplicate = await self.repo.get_by_instruction_code_and_sha256(
            instruction_code=compiled.instruction_code,
            source_sha256=compiled.source_sha256,
            owner_scope=version.owner_scope,
            tenant_id=version.tenant_id,
        )
        if duplicate is not None and duplicate.id != version.id:
            raise GlobalInstructionDuplicateContentError(
                f"Cannot publish: identical snapshot already exists "
                f"(existing_version_id={duplicate.id})."
            )

        archived_count = await self.repo.archive_previous_published(
            instruction_code=version.instruction_code,
            exclude_version_id=version.id,
            owner_scope=version.owner_scope,
            tenant_id=version.tenant_id,
        )

        now = datetime.now(UTC)
        published = await self.repo.update_version(
            version,
            source_yaml=compiled.source_yaml,
            source_sha256=compiled.source_sha256,
            compiled_payload=compiled.compiled_payload,
            name=version.name,
            group=compiled.group,
            source_path=version.source_path,
            git_commit=version.git_commit,
            semver=version.semver,
            validation_report=compiled.validation_report,
            change_summary=version.change_summary,
            immutable_content_hash=compiled.compiled_payload_sha256,
            version_status="published",
            published_at=now,
        )

        stale_count = await self.override_repo.mark_stale_where_global_base_outdated(
            instruction_code=published.instruction_code,
            latest_version_id=published.id,
        )

        logger.info(
            "Global instruction draft published",
            extra={
                "global_instruction_version_id": str(published.id),
                "instruction_code": published.instruction_code,
                "archived_previous_count": archived_count,
                "stale_overrides_count": stale_count,
            },
        )
        return published

    # ── Archive ────────────────────────────────────────────────────

    async def archive_version(
        self,
        *,
        version_id: uuid.UUID,
    ) -> GlobalInstructionVersion:
        version = await self.repo.get_version_for_update(version_id)
        if version is None:
            raise GlobalInstructionNotFoundError(
                f"Global instruction version not found: {version_id}"
            )
        if version.version_status == "archived":
            return version

        archived = await self.repo.update_version(
            version,
            source_yaml=version.source_yaml,
            source_sha256=version.source_sha256,
            compiled_payload=version.compiled_payload,
            name=version.name,
            group=version.group,
            source_path=version.source_path,
            git_commit=version.git_commit,
            semver=version.semver,
            validation_report=version.validation_report,
            change_summary=version.change_summary,
            immutable_content_hash=version.immutable_content_hash,
            version_status="archived",
            published_at=version.published_at,
        )

        logger.info(
            "Global instruction version archived",
            extra={
                "global_instruction_version_id": str(archived.id),
                "instruction_code": archived.instruction_code,
            },
        )
        return archived

    # ── Guard ──────────────────────────────────────────────────────

    def _ensure_draft(self, version: GlobalInstructionVersion) -> None:
        if version.version_status != "draft":
            raise GlobalInstructionImmutableError(
                f"Version {version.id} has status='{version.version_status}'. "
                "Only draft versions can be edited."
            )



        