"""
Repository for PlaybookVersion and ModelConfig operations.
"""

import uuid

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import PlaybookStatus
from src.db.models.deal import Deal
from src.db.models.playbook import ModelConfig, PlaybookVersion


class PlaybookRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_model_config(
        self,
        name: str,
        embeddings_primary: str = "intfloat/multilingual-e5-large",
        embeddings_fallback: str | None = "cointegrated/LaBSE",
        retrieval_config: dict | None = None,
        scoring_config: dict | None = None,
    ) -> ModelConfig:
        """Create a model configuration."""
        mc = ModelConfig(
            name=name,
            embeddings_primary=embeddings_primary,
            embeddings_fallback=embeddings_fallback,
            retrieval_config=retrieval_config or {},
            scoring_config=scoring_config or {},
        )
        self.session.add(mc)
        await self.session.flush()
        return mc

    async def create_version(
        self,
        name: str,
        semver: str,
        model_config_id: uuid.UUID,
        git_commit: str | None = None,
        yaml_sha256: str | None = None,
        compiled_checks: dict | None = None,
        status: str = PlaybookStatus.DRAFT.value,
    ) -> PlaybookVersion:
        """Create a new playbook version.

        If status='default', automatically archives the previous default version
        to ensure only one default exists at any time.
        """
        if status == PlaybookStatus.DEFAULT.value:
            await self.session.execute(
                text("UPDATE playbook_versions SET status = 'archived' WHERE status = 'default'")
            )

        pv = PlaybookVersion(
            name=name,
            semver=semver,
            model_config_id=model_config_id,
            git_commit=git_commit,
            yaml_sha256=yaml_sha256,
            compiled_checks=compiled_checks,
            status=status,
        )
        self.session.add(pv)
        await self.session.flush()
        return pv

    async def get_default(self) -> PlaybookVersion | None:
        """Get the playbook version with status='default'. Only one should exist."""
        result = await self.session.execute(
            select(PlaybookVersion).where(PlaybookVersion.status == PlaybookStatus.DEFAULT.value)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, version_id: uuid.UUID) -> PlaybookVersion | None:
        """Get playbook version by ID."""
        result = await self.session.execute(
            select(PlaybookVersion).where(PlaybookVersion.id == version_id)
        )
        return result.scalar_one_or_none()

    async def get_for_deal(self, deal_id: uuid.UUID) -> PlaybookVersion | None:
        """
        Get playbook for a specific deal:
        1) try Deal.playbook_version_id
        2) fallback to global default.
        """
        # 1) playbook, явно привязанный к сделке
        result = await self.session.execute(
            select(PlaybookVersion)
            .join(Deal, Deal.playbook_version_id == PlaybookVersion.id)
            .where(Deal.id == deal_id)
        )
        pb = result.scalar_one_or_none()
        if pb is not None:
            return pb

        # 2) глобальный default
        return await self.get_default()

    async def promote_to_default(self, version_id) -> "PlaybookVersion | None":
        """
        Переводит все текущие DEFAULT-версии в STABLE,
        затем устанавливает DEFAULT для version_id.
        """
        await self.session.execute(
            update(PlaybookVersion)
            .where(PlaybookVersion.status == PlaybookStatus.DEFAULT.value)
            .values(status=PlaybookStatus.STABLE.value)
        )

        await self.session.execute(
            update(PlaybookVersion)
            .where(PlaybookVersion.id == version_id)
            .values(status=PlaybookStatus.DEFAULT.value)
        )

        await self.session.flush()

        result = await self.session.execute(
            select(PlaybookVersion).where(PlaybookVersion.id == version_id)
        )
        return result.scalar_one_or_none()
