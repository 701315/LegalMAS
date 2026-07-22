# src/db/repositories/global_instruction_version_repo.py

"""
Repository for GlobalInstructionVersion.

Зеркало DocumentTypeInstructionVersionRepository.
instruction_code вместо doc_type_code.
group — дополнительное поле, обновляется вместе с payload.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.models.global_instruction import GlobalInstructionVersion

logger = get_logger(__name__)


class GlobalInstructionVersionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Reads ──────────────────────────────────────────────────────

    async def get_by_id(
        self,
        version_id: uuid.UUID,
    ) -> GlobalInstructionVersion | None:
        result = await self.session.execute(
            select(GlobalInstructionVersion).where(
                GlobalInstructionVersion.id == version_id
            )
        )
        return result.scalar_one_or_none()

    async def get_version_for_update(
        self,
        version_id: uuid.UUID,
    ) -> GlobalInstructionVersion | None:
        """SELECT ... FOR UPDATE — защита от гонок при publish/archive."""
        result = await self.session.execute(
            select(GlobalInstructionVersion)
            .where(GlobalInstructionVersion.id == version_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_by_instruction_code_and_sha256(
        self,
        *,
        instruction_code: str,
        source_sha256: str,
        owner_scope: str = "platform",
        tenant_id: uuid.UUID | None = None,
    ) -> GlobalInstructionVersion | None:
        stmt = select(GlobalInstructionVersion).where(
            GlobalInstructionVersion.instruction_code == instruction_code,
            GlobalInstructionVersion.source_sha256 == source_sha256,
            GlobalInstructionVersion.owner_scope == owner_scope,
        )
        if owner_scope == "tenant":
            stmt = stmt.where(GlobalInstructionVersion.tenant_id == tenant_id)
        else:
            stmt = stmt.where(GlobalInstructionVersion.tenant_id.is_(None))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_instruction_code(
        self,
        instruction_code: str,
        *,
        owner_scope: str | None = None,
        tenant_id: uuid.UUID | None = None,
    ) -> list[GlobalInstructionVersion]:
        """Все версии для instruction_code, новые сначала."""
        stmt = select(GlobalInstructionVersion).where(
            GlobalInstructionVersion.instruction_code == instruction_code,
        )
        if owner_scope == "platform":
            stmt = stmt.where(
                GlobalInstructionVersion.owner_scope == "platform",
                GlobalInstructionVersion.tenant_id.is_(None),
            )
        elif owner_scope == "tenant" and tenant_id is not None:
            stmt = stmt.where(
                GlobalInstructionVersion.owner_scope == "tenant",
                GlobalInstructionVersion.tenant_id == tenant_id,
            )
        stmt = stmt.order_by(GlobalInstructionVersion.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_platform_versions(
        self,
        *,
        instruction_code: str | None = None,
        version_status: str | None = None,
    ) -> list[GlobalInstructionVersion]:
        """Platform-owned versions с опциональными фильтрами."""
        stmt = select(GlobalInstructionVersion).where(
            GlobalInstructionVersion.owner_scope == "platform",
            GlobalInstructionVersion.tenant_id.is_(None),
        )
        if instruction_code is not None:
            stmt = stmt.where(
                GlobalInstructionVersion.instruction_code == instruction_code
            )
        if version_status is not None:
            stmt = stmt.where(
                GlobalInstructionVersion.version_status == version_status
            )
        stmt = stmt.order_by(
            GlobalInstructionVersion.instruction_code.asc(),
            GlobalInstructionVersion.created_at.desc(),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_published(
        self,
        instruction_code: str,
        *,
        tenant_id: uuid.UUID | None = None,
    ) -> GlobalInstructionVersion | None:
        """
        Последняя published версия.
        tenant_id задан → сначала tenant, fallback на platform.
        """
        if tenant_id is not None:
            result = await self.session.execute(
                select(GlobalInstructionVersion)
                .where(
                    GlobalInstructionVersion.instruction_code == instruction_code,
                    GlobalInstructionVersion.owner_scope == "tenant",
                    GlobalInstructionVersion.tenant_id == tenant_id,
                    GlobalInstructionVersion.version_status == "published",
                )
                .order_by(GlobalInstructionVersion.created_at.desc())
                .limit(1)
            )
            tenant_ver = result.scalar_one_or_none()
            if tenant_ver is not None:
                return tenant_ver

        result = await self.session.execute(
            select(GlobalInstructionVersion)
            .where(
                GlobalInstructionVersion.instruction_code == instruction_code,
                GlobalInstructionVersion.owner_scope == "platform",
                GlobalInstructionVersion.tenant_id.is_(None),
                GlobalInstructionVersion.version_status == "published",
            )
            .order_by(GlobalInstructionVersion.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_all_published_platform(self) -> list[GlobalInstructionVersion]:
        """
        Все published platform versions — для runtime loader
        (замена file-based load_global_checks()).
        """
        result = await self.session.execute(
            select(GlobalInstructionVersion)
            .where(
                GlobalInstructionVersion.owner_scope == "platform",
                GlobalInstructionVersion.tenant_id.is_(None),
                GlobalInstructionVersion.version_status == "published",
            )
            .order_by(GlobalInstructionVersion.instruction_code.asc())
        )
        return list(result.scalars().all())

    # ── Writes ─────────────────────────────────────────────────────

    async def create_version(
        self,
        *,
        instruction_code: str,
        source_yaml: str,
        source_sha256: str,
        compiled_payload: dict | None,
        name: str | None = None,
        group: str | None = None,
        source_format: str = "yaml",
        source_path: str | None = None,
        git_commit: str | None = None,
        semver: str | None = None,
        version_status: str = "draft",
        immutable_content_hash: str | None = None,
        validation_report: dict | None = None,
        parent_version_id: uuid.UUID | None = None,
        published_at=None,
        created_by=None,
        change_summary: str | None = None,
        owner_scope: str = "platform",
        tenant_id: uuid.UUID | None = None,
    ) -> GlobalInstructionVersion:
        version = GlobalInstructionVersion(
            instruction_code=instruction_code,
            name=name,
            group=group,
            source_format=source_format,
            source_yaml=source_yaml,
            source_sha256=source_sha256,
            source_path=source_path,
            git_commit=git_commit,
            semver=semver,
            compiled_payload=compiled_payload,
            version_status=version_status,
            immutable_content_hash=immutable_content_hash,
            validation_report=validation_report,
            parent_version_id=parent_version_id,
            published_at=published_at,
            created_by=created_by,
            change_summary=change_summary,
            owner_scope=owner_scope,
            tenant_id=tenant_id,
        )
        self.session.add(version)
        await self.session.flush()

        logger.info(
            "GlobalInstructionVersion created",
            extra={
                "instruction_code": instruction_code,
                "global_instruction_version_id": str(version.id),
                "version_status": version_status,
                "owner_scope": owner_scope,
            },
        )
        return version

    async def update_version(
        self,
        version: GlobalInstructionVersion,
        *,
        source_yaml: str,
        source_sha256: str,
        compiled_payload: dict | None,
        name: str | None = None,
        group: str | None = None,
        source_path: str | None = None,
        git_commit: str | None = None,
        semver: str | None = None,
        validation_report: dict | None = None,
        change_summary: str | None = None,
        immutable_content_hash: str | None = None,
        version_status: str | None = None,
        parent_version_id: uuid.UUID | None = None,
        published_at=None,
    ) -> GlobalInstructionVersion:
        version.source_yaml = source_yaml
        version.source_sha256 = source_sha256
        version.compiled_payload = compiled_payload
        version.name = name
        version.group = group
        version.source_path = source_path
        version.git_commit = git_commit
        version.semver = semver
        version.validation_report = validation_report
        version.change_summary = change_summary

        if immutable_content_hash is not None:
            version.immutable_content_hash = immutable_content_hash
        if version_status is not None:
            version.version_status = version_status
        if parent_version_id is not None:
            version.parent_version_id = parent_version_id
        if published_at is not None:
            version.published_at = published_at

        await self.session.flush()
        return version

    async def archive_previous_published(
        self,
        *,
        instruction_code: str,
        exclude_version_id: uuid.UUID,
        owner_scope: str = "platform",
        tenant_id: uuid.UUID | None = None,
    ) -> int:
        stmt = update(GlobalInstructionVersion).where(
            GlobalInstructionVersion.instruction_code == instruction_code,
            GlobalInstructionVersion.version_status == "published",
            GlobalInstructionVersion.id != exclude_version_id,
            GlobalInstructionVersion.owner_scope == owner_scope,
        )
        if owner_scope == "tenant" and tenant_id is not None:
            stmt = stmt.where(GlobalInstructionVersion.tenant_id == tenant_id)
        else:
            stmt = stmt.where(GlobalInstructionVersion.tenant_id.is_(None))

        stmt = stmt.values(version_status="archived")
        result = await self.session.execute(stmt)
        await self.session.flush()

        affected = result.rowcount or 0
        logger.info(
            "Archived previous published global instruction versions",
            extra={
                "instruction_code": instruction_code,
                "exclude_version_id": str(exclude_version_id),
                "owner_scope": owner_scope,
                "affected_count": affected,
            },
        )
        return affected


    