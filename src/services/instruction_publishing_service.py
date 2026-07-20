# src/services/instruction_publishing_service.py

"""
Instruction publishing service.

Отвечает за lifecycle document-type instruction versions:

- create_draft
- update_draft
- validate_draft
- publish_draft
- archive_version

Инварианты:
- только draft можно редактировать;
- publish требует успешной compile/validation;
- published версия immutable;
- при publish предыдущие published версии по тому же doc_type архивируются;
- stale propagation в overrides происходит после publish.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.models.document_type_instruction import DocumentTypeInstructionVersion
from db.repositories.document_type_instruction_version_repo import (
    DocumentTypeInstructionVersionRepository,
)
from db.repositories.instruction_override_repo import InstructionOverrideRepository
from services.instruction_compiler import (
    CompiledDocTypeInstruction,
    InstructionCompilationError,
    InstructionCompiler,
)

logger = get_logger(__name__)


class InstructionLifecycleError(Exception):
    """Base lifecycle error."""


class InstructionVersionNotFoundError(InstructionLifecycleError):
    """Instruction version not found."""


class ImmutableVersionError(InstructionLifecycleError):
    """Published/archived versions cannot be edited."""


class DuplicateInstructionContentError(InstructionLifecycleError):
    """Another version with identical doc_type_code + source_sha256 already exists."""


class DraftValidationError(InstructionLifecycleError):
    """Draft cannot be published because validation failed."""


class InvalidLifecycleTransitionError(InstructionLifecycleError):
    """Lifecycle transition is not allowed."""


class InstructionPublishingService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.version_repo = DocumentTypeInstructionVersionRepository(session)
        self.override_repo = InstructionOverrideRepository(session)
        self.compiler = InstructionCompiler()

    # ------------------------------------------------------------------
    # Draft lifecycle
    # ------------------------------------------------------------------

    async def create_draft(
        self,
        *,
        doc_type_code: str,
        source: str | dict,
        name: str | None = None,
        source_path: str | None = None,
        git_commit: str | None = None,
        semver: str | None = None,
        created_by: uuid.UUID | None = None,
        change_summary: str | None = None,
        parent_version_id: uuid.UUID | None = None,
    ) -> DocumentTypeInstructionVersion:
        """
        Создать новую draft version.

        Важно:
        - identical content snapshots deduplicated by (doc_type_code, source_sha256);
        - поэтому если identical persisted version уже существует, поднимаем
          DuplicateInstructionContentError.
        """
        compiled = self.compiler.compile_doc_type_instruction(
            doc_type_code=doc_type_code,
            source=source,
        )

        existing = await self.version_repo.get_by_doc_type_and_sha256(
            doc_type_code=compiled.doc_type_code,
            source_sha256=compiled.source_sha256,
        )
        if existing is not None:
            raise DuplicateInstructionContentError(
                "Cannot create draft: identical instruction snapshot already exists "
                f"for doc_type_code='{compiled.doc_type_code}' "
                f"(existing_version_id={existing.id})."
            )

        version = await self.version_repo.create_version(
            doc_type_code=compiled.doc_type_code,
            name=name,
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
        )

        logger.info(
            "Instruction draft created",
            extra={
                "instruction_version_id": str(version.id),
                "doc_type_code": compiled.doc_type_code,
            },
        )
        return version

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
    ) -> DocumentTypeInstructionVersion:
        """
        Обновить существующий draft.

        Только draft может быть изменён.
        """
        version = await self.version_repo.get_version_for_update(version_id)
        if version is None:
            raise InstructionVersionNotFoundError(
                f"Instruction version not found: {version_id}"
            )

        self._ensure_draft_editable(version)

        compiled = self.compiler.compile_doc_type_instruction(
            doc_type_code=version.doc_type_code,
            source=source,
        )

        duplicate = await self.version_repo.get_by_doc_type_and_sha256(
            doc_type_code=compiled.doc_type_code,
            source_sha256=compiled.source_sha256,
        )
        if duplicate is not None and duplicate.id != version.id:
            raise DuplicateInstructionContentError(
                "Cannot update draft: identical instruction snapshot already exists "
                f"for doc_type_code='{compiled.doc_type_code}' "
                f"(existing_version_id={duplicate.id})."
            )

        # defensive: draft must never keep publish-only fields
        version.immutable_content_hash = None
        version.published_at = None
        version.version_status = "draft"

        updated = await self.version_repo.update_version(
            version,
            source_yaml=compiled.source_yaml,
            source_sha256=compiled.source_sha256,
            compiled_payload=compiled.compiled_payload,
            name=name if name is not None else version.name,
            source_path=source_path if source_path is not None else version.source_path,
            git_commit=git_commit if git_commit is not None else version.git_commit,
            semver=semver if semver is not None else version.semver,
            validation_report=compiled.validation_report,
            change_summary=change_summary if change_summary is not None else version.change_summary,
            version_status="draft",
        )

        logger.info(
            "Instruction draft updated",
            extra={
                "instruction_version_id": str(updated.id),
                "doc_type_code": updated.doc_type_code,
            },
        )
        return updated

    async def validate_draft(
        self,
        *,
        version_id: uuid.UUID,
    ) -> CompiledDocTypeInstruction:
        """
        Перевалидировать draft и обновить validation_report + compiled_payload.

        Только draft можно валидировать как активный редактируемый артефакт.
        """
        version = await self.version_repo.get_version_for_update(version_id)
        if version is None:
            raise InstructionVersionNotFoundError(
                f"Instruction version not found: {version_id}"
            )

        self._ensure_draft_editable(version)

        compiled = self.compiler.compile_doc_type_instruction(
            doc_type_code=version.doc_type_code,
            source=version.source_yaml,
        )

        duplicate = await self.version_repo.get_by_doc_type_and_sha256(
            doc_type_code=compiled.doc_type_code,
            source_sha256=compiled.source_sha256,
        )
        if duplicate is not None and duplicate.id != version.id:
            raise DuplicateInstructionContentError(
                "Cannot validate draft: identical instruction snapshot already exists "
                f"for doc_type_code='{compiled.doc_type_code}' "
                f"(existing_version_id={duplicate.id})."
            )

        version.immutable_content_hash = None
        version.published_at = None
        version.version_status = "draft"

        await self.version_repo.update_version(
            version,
            source_yaml=compiled.source_yaml,
            source_sha256=compiled.source_sha256,
            compiled_payload=compiled.compiled_payload,
            name=version.name,
            source_path=version.source_path,
            git_commit=version.git_commit,
            semver=version.semver,
            validation_report=compiled.validation_report,
            change_summary=version.change_summary,
            version_status="draft",
        )

        logger.info(
            "Instruction draft validated",
            extra={
                "instruction_version_id": str(version.id),
                "doc_type_code": version.doc_type_code,
                "is_valid": compiled.is_valid,
                "checks_count": compiled.checks_count,
            },
        )
        return compiled

    async def publish_draft(
        self,
        *,
        version_id: uuid.UUID,
    ) -> DocumentTypeInstructionVersion:
        """
        Опубликовать draft.

        Последовательность:
        1. lock draft FOR UPDATE
        2. compile + validate
        3. archive previous published for same doc_type
        4. mark current version published
        5. mark old overrides stale
        """
        version = await self.version_repo.get_version_for_update(version_id)
        if version is None:
            raise InstructionVersionNotFoundError(
                f"Instruction version not found: {version_id}"
            )

        self._ensure_draft_publishable(version)

        compiled = self.compiler.compile_doc_type_instruction(
            doc_type_code=version.doc_type_code,
            source=version.source_yaml,
        )

        if not compiled.is_valid:
            raise DraftValidationError(
                f"Draft {version_id} has validation errors and cannot be published."
            )

        duplicate = await self.version_repo.get_by_doc_type_and_sha256(
            doc_type_code=compiled.doc_type_code,
            source_sha256=compiled.source_sha256,
        )
        if duplicate is not None and duplicate.id != version.id:
            raise DuplicateInstructionContentError(
                "Cannot publish draft: identical instruction snapshot already exists "
                f"for doc_type_code='{compiled.doc_type_code}' "
                f"(existing_version_id={duplicate.id})."
            )

        # ВАЖНО: сначала архивируем старую published, потом делаем current published.
        # Иначе partial unique index не даст двух published одновременно.
        archived_count = await self.version_repo.archive_previous_published(
            doc_type_code=version.doc_type_code,
            exclude_version_id=version.id,
        )

        now = datetime.now(UTC)

        published = await self.version_repo.update_version(
            version,
            source_yaml=compiled.source_yaml,
            source_sha256=compiled.source_sha256,
            compiled_payload=compiled.compiled_payload,
            name=version.name,
            source_path=version.source_path,
            git_commit=version.git_commit,
            semver=version.semver,
            validation_report=compiled.validation_report,
            change_summary=version.change_summary,
            immutable_content_hash=compiled.compiled_payload_sha256,
            version_status="published",
            published_at=now,
        )

        stale_count = await self.override_repo.mark_stale_where_base_outdated(
            doc_type_code=published.doc_type_code,
            latest_version_id=published.id,
        )

        logger.info(
            "Instruction draft published",
            extra={
                "instruction_version_id": str(published.id),
                "doc_type_code": published.doc_type_code,
                "archived_previous_count": archived_count,
                "stale_overrides_count": stale_count,
                "immutable_content_hash": compiled.compiled_payload_sha256,
            },
        )
        return published

    async def archive_version(
        self,
        *,
        version_id: uuid.UUID,
    ) -> DocumentTypeInstructionVersion:
        """
        Архивировать версию.

        На этом шаге:
        - не удаляем версию;
        - не проверяем historical usage (это можно добавить следующим этапом);
        - переводим version_status в archived.
        """
        version = await self.version_repo.get_version_for_update(version_id)
        if version is None:
            raise InstructionVersionNotFoundError(
                f"Instruction version not found: {version_id}"
            )

        if version.version_status == "archived":
            return version

        archived = await self.version_repo.update_version(
            version,
            source_yaml=version.source_yaml,
            source_sha256=version.source_sha256,
            compiled_payload=version.compiled_payload,
            name=version.name,
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
            "Instruction version archived",
            extra={
                "instruction_version_id": str(archived.id),
                "doc_type_code": archived.doc_type_code,
            },
        )
        return archived

    # ------------------------------------------------------------------
    # Internal lifecycle guards
    # ------------------------------------------------------------------

    def _ensure_draft_editable(
        self,
        version: DocumentTypeInstructionVersion,
    ) -> None:
        if version.version_status != "draft":
            raise ImmutableVersionError(
                f"Instruction version {version.id} has status='{version.version_status}'. "
                "Only draft versions can be edited."
            )

    def _ensure_draft_publishable(
        self,
        version: DocumentTypeInstructionVersion,
    ) -> None:
        if version.version_status != "draft":
            raise InvalidLifecycleTransitionError(
                f"Instruction version {version.id} has status='{version.version_status}'. "
                "Only draft versions can be published."
            )
        

        