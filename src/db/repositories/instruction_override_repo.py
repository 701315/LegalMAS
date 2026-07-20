# src/db/repositories/instruction_override_repo.py

"""
Repository для работы с instruction overrides.

Override — это diff (JSON Patch, RFC 6902) поверх конкретной версии
инструкции типа документа (DocumentTypeInstructionVersion), привязанный
к конкретной сделке (deal_id).

Этот модуль инкапсулирует:
- создание override (с фиксацией base_content_hash);
- получение override по deal_id + instruction_version_id;
- получение override по id;
- список всех override для сделки;
- пометку override как is_stale (когда базовая версия инструкции изменилась);
- обновление patch_ops при rebase override на новую базовую версию.

Важно: сам apply patch (генерация эффективного YAML/dict) находится
в InstructionOverrideService, а не здесь — репозиторий отвечает только
за persistence, не за бизнес-логику patch/conflict.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger

from ..models.instruction_override import InstructionOverride

logger = get_logger(__name__)


class InstructionOverrideRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ── Basic CRUD ────────────────────────────────────────────────────────────

    async def create(
        self,
        deal_id: uuid.UUID,
        instruction_version_id: uuid.UUID,
        base_content_hash: str,
        patch_ops: list[dict],
        change_summary: str | None = None,
        created_by: uuid.UUID | None = None,
    ) -> InstructionOverride:
        override = InstructionOverride(
            deal_id=deal_id,
            instruction_version_id=instruction_version_id,
            base_content_hash=base_content_hash,
            patch_ops=patch_ops,
            change_summary=change_summary,
            created_by=created_by,
        )
        self.session.add(override)
        await self.session.flush()

        logger.info(
            "InstructionOverride created",
            extra={
                "deal_id": str(deal_id),
                "instruction_version_id": str(instruction_version_id),
                "override_id": str(override.id),
            },
        )
        return override

    async def get_by_id(
        self,
        override_id: uuid.UUID,
    ) -> InstructionOverride | None:
        result = await self.session.execute(
            select(InstructionOverride).where(InstructionOverride.id == override_id)
        )
        return result.scalar_one_or_none()

    async def get_by_deal_and_version(
        self,
        deal_id: uuid.UUID,
        instruction_version_id: uuid.UUID,
    ) -> InstructionOverride | None:
        """
        Вернуть override для конкретной сделки и конкретной base version.

        Используется InstructionOverrideService при resolving effective
        instruction set для snapshot creation.
        """
        result = await self.session.execute(
            select(InstructionOverride).where(
                InstructionOverride.deal_id == deal_id,
                InstructionOverride.instruction_version_id == instruction_version_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_deal(
        self,
        deal_id: uuid.UUID,
    ) -> list[InstructionOverride]:
        result = await self.session.execute(
            select(InstructionOverride)
            .where(InstructionOverride.deal_id == deal_id)
            .order_by(InstructionOverride.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_stale_for_deal(
        self,
        deal_id: uuid.UUID,
    ) -> list[InstructionOverride]:
        result = await self.session.execute(
            select(InstructionOverride).where(
                InstructionOverride.deal_id == deal_id,
                InstructionOverride.is_stale.is_(True),
            )
        )
        return list(result.scalars().all())

    # ── Mutations ─────────────────────────────────────────────────────────────

    async def mark_stale(
        self,
        override_id: uuid.UUID,
    ) -> InstructionOverride | None:
        """
        Помечает override как stale.

        Вызывается, когда базовая instruction version, на которой
        построен override, была изменена/republished с новым content_hash.
        Не удаляет и не мутирует patch_ops — только флаг.
        """
        stmt = (
            update(InstructionOverride)
            .where(InstructionOverride.id == override_id)
            .values(is_stale=True)
            .returning(InstructionOverride)
        )
        result = await self.session.execute(stmt)
        override = result.scalar_one_or_none()
        if override:
            await self.session.flush()

        logger.info(
            "InstructionOverride marked stale",
            extra={"override_id": str(override_id)},
        )
        return override


    async def mark_stale_for_instruction_version(
        self,
        instruction_version_id: uuid.UUID,
    ) -> int:
        """
        Помечает stale все override, построенные на конкретной instruction version.

        Это низкоуровневая lifecycle-операция.
        Полезна для service-слоя, если нужно явно инвалидировать overrides
        для одной конкретной базовой версии.
        """
        stmt = (
            update(InstructionOverride)
            .where(
                InstructionOverride.instruction_version_id == instruction_version_id,
                InstructionOverride.is_stale.is_(False),
            )
            .values(is_stale=True)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()

        affected = result.rowcount or 0
        logger.info(
            "InstructionOverrides marked stale for exact instruction version",
            extra={
                "instruction_version_id": str(instruction_version_id),
                "affected_count": affected,
            },
        )
        return affected


    async def mark_stale_where_base_outdated(
        self,
        doc_type_code: str,
        latest_version_id: uuid.UUID,
    ) -> int:
        """
        Помечает stale все override для данного doc_type_code, чья
        instruction_version_id не совпадает с latest_version_id.

        Вызывается после публикации новой instruction version для
        doc_type_code — все override, построенные на предыдущих версиях,
        считаются stale и требуют явного rebase.
        """
        from ..models.document_type_instruction import DocumentTypeInstructionVersion

        stmt = (
            update(InstructionOverride)
            .where(
                InstructionOverride.instruction_version_id.in_(
                    select(DocumentTypeInstructionVersion.id).where(
                        DocumentTypeInstructionVersion.doc_type_code == doc_type_code,
                        DocumentTypeInstructionVersion.id != latest_version_id,
                    )
                ),
                InstructionOverride.is_stale.is_(False),
            )
            .values(is_stale=True)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()

        affected = result.rowcount or 0
        logger.info(
            "InstructionOverrides marked stale (base outdated)",
            extra={
                "doc_type_code": doc_type_code,
                "latest_version_id": str(latest_version_id),
                "affected_count": affected,
            },
        )
        return affected

    async def rebase(
        self,
        override_id: uuid.UUID,
        new_instruction_version_id: uuid.UUID,
        new_base_content_hash: str,
        new_patch_ops: list[dict],
    ) -> InstructionOverride | None:
        """
        Пересобирает override на новую базовую версию инструкции.

        Явная операция rebase — вызывается только пользователем через UI
        conflict resolution, никогда автоматически. is_stale сбрасывается
        в False только после успешного rebase.
        """
        stmt = (
            update(InstructionOverride)
            .where(InstructionOverride.id == override_id)
            .values(
                instruction_version_id=new_instruction_version_id,
                base_content_hash=new_base_content_hash,
                patch_ops=new_patch_ops,
                is_stale=False,
            )
            .returning(InstructionOverride)
        )
        result = await self.session.execute(stmt)
        override = result.scalar_one_or_none()
        if override:
            await self.session.flush()

        logger.info(
            "InstructionOverride rebased",
            extra={
                "override_id": str(override_id),
                "new_instruction_version_id": str(new_instruction_version_id),
            },
        )
        return override

    async def delete(self, override_id: uuid.UUID) -> bool:
        override = await self.get_by_id(override_id)
        if override is None:
            return False
        await self.session.delete(override)
        await self.session.flush()

        logger.info(
            "InstructionOverride deleted",
            extra={"override_id": str(override_id)},
        )
        return True
    
