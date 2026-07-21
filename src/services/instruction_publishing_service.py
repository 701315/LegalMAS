# src/services/instruction_publishing_service.py

"""
Instruction publishing service.

Отвечает за lifecycle document-type instruction versions:

- create_draft / create_platform_draft / create_tenant_draft
- derive_tenant_draft_from_platform (copy-on-write)
- update_draft
- validate_draft
- publish_draft / publish_platform_draft / publish_tenant_draft
- archive_version

Инварианты:
- только draft можно редактировать;
- publish требует успешной compile/validation;
- published версия immutable;
- при publish предыдущие published версии по тому же (doc_type, scope) архивируются;
- stale propagation в overrides происходит после publish;
- tenant не редактирует platform instruction inplace;
- platform instructions публикуются только через publish_platform_draft;
- tenant instructions публикуются только через publish_tenant_draft.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.models.document_type_instruction import DocumentTypeInstructionVersion
from db.repositories.document_type_instruction_version_repo import (
    DocumentTypeInstructionVersionRepository,
    TenantOwnershipError,
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
    """Another version with identical doc_type_code + source_sha256 already exists in this scope."""


class DraftValidationError(InstructionLifecycleError):
    """Draft cannot be published because validation failed."""


class InvalidLifecycleTransitionError(InstructionLifecycleError):
    """Lifecycle transition is not allowed."""


class PlatformInstructionReadOnlyError(InstructionLifecycleError):
    """Tenant cannot edit platform instruction inplace."""


class InstructionPublishingService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.version_repo = DocumentTypeInstructionVersionRepository(session)
        self.override_repo = InstructionOverrideRepository(session)
        self.compiler = InstructionCompiler()

    # ------------------------------------------------------------------
    # Platform draft lifecycle (superadmin only)
    # ------------------------------------------------------------------

    async def create_platform_draft(
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
        Создать новую platform draft version.

        Только superadmin.
        owner_scope='platform', tenant_id=None.
        """
        compiled = self.compiler.compile_doc_type_instruction(
            doc_type_code=doc_type_code,
            source=source,
        )

        existing = await self.version_repo.get_by_doc_type_and_sha256(
            doc_type_code=compiled.doc_type_code,
            source_sha256=compiled.source_sha256,
            owner_scope="platform",
            tenant_id=None,
        )
        if existing is not None:
            raise DuplicateInstructionContentError(
                "Cannot create platform draft: identical instruction snapshot already exists "
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
            owner_scope="platform",
            tenant_id=None,
        )

        logger.info(
            "Platform instruction draft created",
            extra={
                "instruction_version_id": str(version.id),
                "doc_type_code": compiled.doc_type_code,
                "owner_scope": "platform",
            },
        )
        return version

    async def publish_platform_draft(
        self,
        *,
        version_id: uuid.UUID,
    ) -> DocumentTypeInstructionVersion:
        """
        Опубликовать platform draft.

        Только superadmin.
        Архивирует предыдущие platform published versions.
        """
        version = await self.version_repo.get_version_for_update(version_id)
        if version is None:
            raise InstructionVersionNotFoundError(
                f"Instruction version not found: {version_id}"
            )

        self._ensure_platform_scope(version)
        self._ensure_draft_publishable(version)

        return await self._do_publish(version)

    # ------------------------------------------------------------------
    # Tenant draft lifecycle (tenant admin)
    # ------------------------------------------------------------------

    async def create_tenant_draft(
        self,
        *,
        doc_type_code: str,
        source: str | dict,
        tenant_id: uuid.UUID,
        name: str | None = None,
        source_path: str | None = None,
        git_commit: str | None = None,
        semver: str | None = None,
        created_by: uuid.UUID | None = None,
        change_summary: str | None = None,
        parent_version_id: uuid.UUID | None = None,
    ) -> DocumentTypeInstructionVersion:
        """
        Создать новую tenant-owned draft version.

        Tenant admin.
        owner_scope='tenant', tenant_id=tenant_id.
        """
        compiled = self.compiler.compile_doc_type_instruction(
            doc_type_code=doc_type_code,
            source=source,
        )

        existing = await self.version_repo.get_by_doc_type_and_sha256(
            doc_type_code=compiled.doc_type_code,
            source_sha256=compiled.source_sha256,
            owner_scope="tenant",
            tenant_id=tenant_id,
        )
        if existing is not None:
            raise DuplicateInstructionContentError(
                "Cannot create tenant draft: identical instruction snapshot already exists "
                f"for doc_type_code='{compiled.doc_type_code}', tenant_id='{tenant_id}' "
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
            owner_scope="tenant",
            tenant_id=tenant_id,
        )

        logger.info(
            "Tenant instruction draft created",
            extra={
                "instruction_version_id": str(version.id),
                "doc_type_code": compiled.doc_type_code,
                "owner_scope": "tenant",
                "tenant_id": str(tenant_id),
            },
        )
        return version

    async def derive_tenant_draft_from_platform(
        self,
        *,
        platform_version_id: uuid.UUID,
        tenant_id: uuid.UUID,
        name: str | None = None,
        change_summary: str | None = None,
        created_by: uuid.UUID | None = None,
    ) -> DocumentTypeInstructionVersion:
        """
        Copy-on-write: создать tenant draft на основе platform published version.

        Инварианты:
        - source должен быть published platform version;
        - создаётся новая tenant-owned версия;
        - lineage через derived_from_version_id;
        - tenant не получает права на platform version.

        Это canonical "edit platform instruction as tenant" path.
        """
        source_version = await self.version_repo.get_by_id(platform_version_id)
        if source_version is None:
            raise InstructionVersionNotFoundError(
                f"Platform instruction version not found: {platform_version_id}"
            )

        self._ensure_platform_scope(source_version)

        if source_version.version_status != "published":
            raise InvalidLifecycleTransitionError(
                f"Can only derive from published platform version. "
                f"Version {platform_version_id} has status='{source_version.version_status}'."
            )

        compiled = self.compiler.compile_doc_type_instruction(
            doc_type_code=source_version.doc_type_code,
            source=source_version.source_yaml,
        )

        existing = await self.version_repo.get_by_doc_type_and_sha256(
            doc_type_code=compiled.doc_type_code,
            source_sha256=compiled.source_sha256,
            owner_scope="tenant",
            tenant_id=tenant_id,
        )
        if existing is not None:
            raise DuplicateInstructionContentError(
                "Cannot derive: identical instruction snapshot already exists "
                f"for doc_type_code='{compiled.doc_type_code}', tenant_id='{tenant_id}' "
                f"(existing_version_id={existing.id})."
            )

        version = await self.version_repo.create_version(
            doc_type_code=compiled.doc_type_code,
            name=name or source_version.name,
            source_yaml=compiled.source_yaml,
            source_sha256=compiled.source_sha256,
            source_path=source_version.source_path,
            git_commit=source_version.git_commit,
            semver=None,
            compiled_payload=compiled.compiled_payload,
            version_status="draft",
            immutable_content_hash=None,
            validation_report=compiled.validation_report,
            parent_version_id=None,
            derived_from_version_id=platform_version_id,
            published_at=None,
            created_by=created_by,
            change_summary=(
                change_summary
                or f"Derived from platform version {platform_version_id}"
            ),
            owner_scope="tenant",
            tenant_id=tenant_id,
        )

        logger.info(
            "Tenant instruction derived from platform version",
            extra={
                "instruction_version_id": str(version.id),
                "doc_type_code": compiled.doc_type_code,
                "platform_version_id": str(platform_version_id),
                "tenant_id": str(tenant_id),
            },
        )
        return version

    async def publish_tenant_draft(
        self,
        *,
        version_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> DocumentTypeInstructionVersion:
        """
        Опубликовать tenant draft.

        Tenant admin.
        Guard: version должна принадлежать tenant_id.
        Guard: owner_scope должен быть 'tenant'.
        Архивирует предыдущую published tenant version
        для того же (doc_type_code, tenant_id).
        """
        version = await self.version_repo.get_version_for_update(version_id)
        if version is None:
            raise InstructionVersionNotFoundError(
                f"Instruction version not found: {version_id}"
            )

        self._ensure_tenant_owns(version, tenant_id)
        self._ensure_draft_publishable(version)

        return await self._do_publish(version)

    # ------------------------------------------------------------------
    # Shared draft operations (update, validate, archive)
    # ------------------------------------------------------------------

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
        tenant_id: uuid.UUID | None = None,
    ) -> DocumentTypeInstructionVersion:
        """
        Обновить существующий draft.

        Если tenant_id задан — проверяет tenant ownership.
        Если tenant_id=None — платформенная операция (superadmin).
        Только draft может быть изменён.
        Нельзя обновить platform instruction от имени tenant.
        """
        version = await self.version_repo.get_version_for_update(version_id)
        if version is None:
            raise InstructionVersionNotFoundError(
                f"Instruction version not found: {version_id}"
            )

        if tenant_id is not None:
            self._ensure_tenant_owns(version, tenant_id)
        else:
            self._ensure_platform_scope(version)

        self._ensure_draft_editable(version)

        compiled = self.compiler.compile_doc_type_instruction(
            doc_type_code=version.doc_type_code,
            source=source,
        )

        duplicate = await self.version_repo.get_by_doc_type_and_sha256(
            doc_type_code=compiled.doc_type_code,
            source_sha256=compiled.source_sha256,
            owner_scope=version.owner_scope,
            tenant_id=version.tenant_id,
        )
        if duplicate is not None and duplicate.id != version.id:
            raise DuplicateInstructionContentError(
                "Cannot update draft: identical instruction snapshot already exists "
                f"for doc_type_code='{compiled.doc_type_code}' "
                f"(existing_version_id={duplicate.id})."
            )

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
                "owner_scope": updated.owner_scope,
            },
        )
        return updated

    async def validate_draft(
        self,
        *,
        version_id: uuid.UUID,
        tenant_id: uuid.UUID | None = None,
    ) -> CompiledDocTypeInstruction:
        """
        Перевалидировать draft и обновить validation_report + compiled_payload.

        Если tenant_id задан — проверяет tenant ownership.
        Только draft можно валидировать.
        """
        version = await self.version_repo.get_version_for_update(version_id)
        if version is None:
            raise InstructionVersionNotFoundError(
                f"Instruction version not found: {version_id}"
            )

        if tenant_id is not None:
            self._ensure_tenant_owns(version, tenant_id)

        self._ensure_draft_editable(version)

        compiled = self.compiler.compile_doc_type_instruction(
            doc_type_code=version.doc_type_code,
            source=version.source_yaml,
        )

        duplicate = await self.version_repo.get_by_doc_type_and_sha256(
            doc_type_code=compiled.doc_type_code,
            source_sha256=compiled.source_sha256,
            owner_scope=version.owner_scope,
            tenant_id=version.tenant_id,
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
                "owner_scope": version.owner_scope,
            },
        )
        return compiled

    async def archive_version(
        self,
        *,
        version_id: uuid.UUID,
        tenant_id: uuid.UUID | None = None,
    ) -> DocumentTypeInstructionVersion:
        """
        Архивировать версию.

        Если tenant_id задан — проверяет tenant ownership.
        Нельзя архивировать platform version от имени tenant.
        """
        version = await self.version_repo.get_version_for_update(version_id)
        if version is None:
            raise InstructionVersionNotFoundError(
                f"Instruction version not found: {version_id}"
            )

        if tenant_id is not None:
            self._ensure_tenant_owns(version, tenant_id)

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
                "owner_scope": archived.owner_scope,
            },
        )
        return archived

    # ------------------------------------------------------------------
    # Legacy backward-compatible entry point
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
        owner_scope: str = "platform",
        tenant_id: uuid.UUID | None = None,
    ) -> DocumentTypeInstructionVersion:
        """
        Backward-compatible entry point для создания draft.

        Используется существующим admin API endpoint.
        По умолчанию создаёт platform instruction.

        Новый код должен использовать create_platform_draft / create_tenant_draft.
        """
        if owner_scope == "tenant" and tenant_id is not None:
            return await self.create_tenant_draft(
                doc_type_code=doc_type_code,
                source=source,
                tenant_id=tenant_id,
                name=name,
                source_path=source_path,
                git_commit=git_commit,
                semver=semver,
                created_by=created_by,
                change_summary=change_summary,
                parent_version_id=parent_version_id,
            )
        return await self.create_platform_draft(
            doc_type_code=doc_type_code,
            source=source,
            name=name,
            source_path=source_path,
            git_commit=git_commit,
            semver=semver,
            created_by=created_by,
            change_summary=change_summary,
            parent_version_id=parent_version_id,
        )

    async def publish_draft(
        self,
        *,
        version_id: uuid.UUID,
        tenant_id: uuid.UUID | None = None,
    ) -> DocumentTypeInstructionVersion:
        """
        Backward-compatible publish entry point.

        Если tenant_id задан — publish_tenant_draft.
        Если нет — publish_platform_draft.
        """
        if tenant_id is not None:
            return await self.publish_tenant_draft(
                version_id=version_id,
                tenant_id=tenant_id,
            )
        return await self.publish_platform_draft(version_id=version_id)

    # ------------------------------------------------------------------
    # Internal shared publish implementation
    # ------------------------------------------------------------------

    async def _do_publish(
        self,
        version: DocumentTypeInstructionVersion,
    ) -> DocumentTypeInstructionVersion:
        """
        Единая внутренняя реализация publish для platform и tenant versions.

        Последовательность:
        1. compile + validate
        2. dedup check в том же scope
        3. archive previous published в том же scope
        4. mark current version published
        5. mark old overrides stale
        """
        compiled = self.compiler.compile_doc_type_instruction(
            doc_type_code=version.doc_type_code,
            source=version.source_yaml,
        )

        if not compiled.is_valid:
            raise DraftValidationError(
                f"Draft {version.id} has validation errors and cannot be published."
            )

        duplicate = await self.version_repo.get_by_doc_type_and_sha256(
            doc_type_code=compiled.doc_type_code,
            source_sha256=compiled.source_sha256,
            owner_scope=version.owner_scope,
            tenant_id=version.tenant_id,
        )
        if duplicate is not None and duplicate.id != version.id:
            raise DuplicateInstructionContentError(
                "Cannot publish draft: identical instruction snapshot already exists "
                f"for doc_type_code='{compiled.doc_type_code}' "
                f"(existing_version_id={duplicate.id})."
            )

        archived_count = await self.version_repo.archive_previous_published(
            doc_type_code=version.doc_type_code,
            exclude_version_id=version.id,
            owner_scope=version.owner_scope,
            tenant_id=version.tenant_id,
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
                "owner_scope": published.owner_scope,
                "tenant_id": str(published.tenant_id) if published.tenant_id else None,
                "archived_previous_count": archived_count,
                "stale_overrides_count": stale_count,
                "immutable_content_hash": compiled.compiled_payload_sha256,
            },
        )
        return published

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

    def _ensure_platform_scope(
        self,
        version: DocumentTypeInstructionVersion,
    ) -> None:
        if version.owner_scope != "platform":
            raise InvalidLifecycleTransitionError(
                f"Instruction version {version.id} is tenant-owned. "
                "Use tenant-specific methods for tenant instructions."
            )

    def _ensure_tenant_owns(
        self,
        version: DocumentTypeInstructionVersion,
        tenant_id: uuid.UUID,
    ) -> None:
        if version.owner_scope != "tenant" or version.tenant_id != tenant_id:
            raise PlatformInstructionReadOnlyError(
                f"Instruction version {version.id} does not belong to tenant {tenant_id}. "
                f"owner_scope={version.owner_scope}, version.tenant_id={version.tenant_id}. "
                "Tenant cannot edit platform instructions inplace. "
                "Use derive_tenant_draft_from_platform() to create a tenant copy."
            )
        

        