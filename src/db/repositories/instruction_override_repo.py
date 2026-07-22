# src/db/repositories/instruction_override_repo.py

"""
Repository для работы с instruction overrides.

Override — это diff (JSON Patch, RFC 6902) поверх конкретной версии
инструкции типа документа (DocumentTypeInstructionVersion).

Поддерживаемые scope:
- tenant override: override_scope='tenant', deal_id=NULL
- deal override: override_scope='deal', deal_id=<uuid>

Lifecycle:
- draft → active → archived

Инварианты на уровне БД:
- одна неархивная tenant override на (tenant_id, instruction_version_id)
- одна неархивная deal override на (deal_id, instruction_version_id)

Этот модуль инкапсулирует:
- создание override (с фиксацией base_content_hash);
- получение override по различным scope/filter комбинациям;
- lifecycle transitions (draft → active → archived);
- staleness management;
- rebase на новую base version.

ВАЖНО: сам apply patch (генерация эффективного YAML/dict) находится
в InstructionOverrideService, а не здесь.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger

from ..models.instruction_override import InstructionOverride

logger = get_logger(__name__)


class TenantOwnershipError(Exception):
    """Override не принадлежит данному tenant'у."""


class InvalidLifecycleTransitionError(Exception):
    """Lifecycle transition не разрешён для данного override."""


class InstructionOverrideRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ── Basic CRUD ────────────────────────────────────────────────────────────

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        override_scope: str,
        deal_id: uuid.UUID | None,
        instruction_version_id: uuid.UUID | None = None,
        global_instruction_version_id: uuid.UUID | None = None,
        base_content_hash: str,
        patch_ops: list[dict],
        status: str = "draft",
        change_summary: str | None = None,
        created_by: uuid.UUID | None = None,
    ) -> InstructionOverride:
        """
        Создать override.

        XOR: ровно одно из instruction_version_id / global_instruction_version_id
        должно быть задано.

        override_scope='tenant' → deal_id должен быть None.
        override_scope='deal' → deal_id обязателен.
        status по умолчанию 'draft'.
        """
        if (instruction_version_id is None) == (global_instruction_version_id is None):
            raise ValueError(
                "Exactly one of instruction_version_id or global_instruction_version_id "
                "must be provided (XOR constraint)."
            )

        override = InstructionOverride(
            tenant_id=tenant_id,
            override_scope=override_scope,
            deal_id=deal_id,
            instruction_version_id=instruction_version_id,
            global_instruction_version_id=global_instruction_version_id,
            base_content_hash=base_content_hash,
            patch_ops=patch_ops,
            status=status,
            change_summary=change_summary,
            created_by=created_by,
        )
        self.session.add(override)
        await self.session.flush()

        logger.info(
            "InstructionOverride created",
            extra={
                "tenant_id": str(tenant_id),
                "override_scope": override_scope,
                "deal_id": str(deal_id) if deal_id else None,
                "instruction_version_id": str(instruction_version_id) if instruction_version_id else None,
                "global_instruction_version_id": str(global_instruction_version_id) if global_instruction_version_id else None,
                "override_id": str(override.id),
                "status": status,
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

    async def assert_tenant_owns(
        self,
        override_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> InstructionOverride:
        """
        Загрузить override и проверить tenant ownership.

        Raises: TenantOwnershipError если override не принадлежит tenant.
        Используется как guard в service/endpoint layer.
        """
        override = await self.get_by_id(override_id)
        if override is None:
            raise TenantOwnershipError(
                f"Override {override_id} not found."
            )
        if override.tenant_id != tenant_id:
            raise TenantOwnershipError(
                f"Override {override_id} does not belong to tenant {tenant_id}. "
                f"override.tenant_id={override.tenant_id}"
            )
        return override

    # ── Scope-aware reads ─────────────────────────────────────────────────────

    async def get_by_deal_and_version(
        self,
        deal_id: uuid.UUID,
        instruction_version_id: uuid.UUID,
        *,
        status: str | None = None,
    ) -> InstructionOverride | None:
        """
        Вернуть deal-scope override для конкретной сделки и base version.

        Если status задан — фильтрует по нему.
        Если status не задан — возвращает любой (включая archived).

        Используется InstructionOverrideService при resolving effective
        instruction set для snapshot creation.
        """
        stmt = select(InstructionOverride).where(
            InstructionOverride.deal_id == deal_id,
            InstructionOverride.instruction_version_id == instruction_version_id,
            InstructionOverride.override_scope == "deal",
        )
        if status is not None:
            stmt = stmt.where(InstructionOverride.status == status)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_deal_override(
        self,
        deal_id: uuid.UUID,
        instruction_version_id: uuid.UUID,
    ) -> InstructionOverride | None:
        """
        Активный deal-level override для данной base version и сделки.
        status='active', override_scope='deal'.
        """
        return await self.get_by_deal_and_version(
            deal_id,
            instruction_version_id,
            status="active",
        )

    async def get_active_tenant_override(
        self,
        tenant_id: uuid.UUID,
        instruction_version_id: uuid.UUID,
    ) -> InstructionOverride | None:
        """
        Активный tenant-level override для данной base version.
        status='active', override_scope='tenant'.
        """
        result = await self.session.execute(
            select(InstructionOverride).where(
                InstructionOverride.tenant_id == tenant_id,
                InstructionOverride.instruction_version_id == instruction_version_id,
                InstructionOverride.override_scope == "tenant",
                InstructionOverride.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def list_for_deal(
        self,
        deal_id: uuid.UUID,
        *,
        status: str | None = None,
    ) -> list[InstructionOverride]:
        """
        Все deal-level overrides для данной сделки.
        Если status задан — фильтрует по нему.
        """
        stmt = select(InstructionOverride).where(
            InstructionOverride.deal_id == deal_id,
            InstructionOverride.override_scope == "deal",
        )
        if status is not None:
            stmt = stmt.where(InstructionOverride.status == status)
        stmt = stmt.order_by(InstructionOverride.created_at.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_tenant_scope(
        self,
        tenant_id: uuid.UUID,
        *,
        status: str | None = None,
    ) -> list[InstructionOverride]:
        """
        Все tenant-level overrides (override_scope='tenant') для данного tenant.
        Если status задан — фильтрует по нему.
        """
        stmt = select(InstructionOverride).where(
            InstructionOverride.tenant_id == tenant_id,
            InstructionOverride.override_scope == "tenant",
        )
        if status is not None:
            stmt = stmt.where(InstructionOverride.status == status)
        stmt = stmt.order_by(InstructionOverride.created_at.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_stale_for_deal(
        self,
        deal_id: uuid.UUID,
    ) -> list[InstructionOverride]:
        """
        Stale deal-level overrides для данной сделки.
        """
        result = await self.session.execute(
            select(InstructionOverride).where(
                InstructionOverride.deal_id == deal_id,
                InstructionOverride.override_scope == "deal",
                InstructionOverride.is_stale.is_(True),
            )
        )
        return list(result.scalars().all())

    async def list_stale_for_tenant(
        self,
        tenant_id: uuid.UUID,
    ) -> list[InstructionOverride]:
        """
        Stale tenant-level overrides для данного tenant.
        """
        result = await self.session.execute(
            select(InstructionOverride).where(
                InstructionOverride.tenant_id == tenant_id,
                InstructionOverride.override_scope == "tenant",
                InstructionOverride.is_stale.is_(True),
            )
        )
        return list(result.scalars().all())

    async def find_any_override_for_doc_type(
        self,
        *,
        deal_id: uuid.UUID | None = None,
        tenant_id: uuid.UUID | None = None,
        doc_type_code: str,
        scope: str,
    ) -> InstructionOverride | None:
        """
        Найти override для deal/tenant, привязанный к ЛЮБОЙ версии
        данного doc_type_code.

        Используется для staleness detection: если override ссылается
        на старую версию инструкции, нужно предупредить пользователя.
        """
        from db.models.document_type_instruction import DocumentTypeInstructionVersion

        stmt = select(InstructionOverride).where(
            InstructionOverride.override_scope == scope,
            InstructionOverride.instruction_version_id.in_(
                select(DocumentTypeInstructionVersion.id).where(
                    DocumentTypeInstructionVersion.doc_type_code == doc_type_code,
                )
            ),
        )
        if scope == "deal" and deal_id is not None:
            stmt = stmt.where(InstructionOverride.deal_id == deal_id)
        elif scope == "tenant" and tenant_id is not None:
            stmt = stmt.where(InstructionOverride.tenant_id == tenant_id)

        result = await self.session.execute(stmt)
        return result.scalars().first()

    # ── Lifecycle transitions ─────────────────────────────────────────────────

    async def transition_status(
        self,
        override_id: uuid.UUID,
        *,
        from_status: str,
        to_status: str,
        tenant_id: uuid.UUID,
    ) -> InstructionOverride | None:
        """
        Атомарный lifecycle transition с ownership check.

        Raises: TenantOwnershipError если override не принадлежит tenant.
        Raises: InvalidLifecycleTransitionError если from_status не совпадает.
        """
        override = await self.assert_tenant_owns(override_id, tenant_id)
        if override.status != from_status:
            raise InvalidLifecycleTransitionError(
                f"Override {override_id} has status='{override.status}', "
                f"expected='{from_status}'. Cannot transition to '{to_status}'."
            )
        stmt = (
            update(InstructionOverride)
            .where(
                InstructionOverride.id == override_id,
                InstructionOverride.status == from_status,
            )
            .values(status=to_status)
            .returning(InstructionOverride)
        )
        result = await self.session.execute(stmt)
        updated = result.scalar_one_or_none()
        if updated:
            await self.session.flush()
        return updated

    # ── Staleness management ──────────────────────────────────────────────────

    async def mark_stale(
        self,
        override_id: uuid.UUID,
    ) -> InstructionOverride | None:
        """
        Помечает override как stale.

        Вызывается, когда базовая instruction version изменилась.
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

        Независимо от scope (tenant/deal).
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

        Вызывается после публикации новой instruction version.
        Охватывает и tenant, и deal overrides.
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

    # ── Rebase ────────────────────────────────────────────────────────────────

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
        conflict resolution, никогда автоматически.
        is_stale сбрасывается в False только после успешного rebase.
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
    

    async def mark_stale_where_global_base_outdated(
        self,
        instruction_code: str,
        latest_version_id: uuid.UUID,
    ) -> int:
        """
        Пометить stale все overrides для данного instruction_code,
        чья global_instruction_version_id не совпадает с latest_version_id.

        Зеркало mark_stale_where_base_outdated для global instructions.
        """
        from ..models.global_instruction import GlobalInstructionVersion

        stmt = (
            update(InstructionOverride)
            .where(
                InstructionOverride.global_instruction_version_id.in_(
                    select(GlobalInstructionVersion.id).where(
                        GlobalInstructionVersion.instruction_code == instruction_code,
                        GlobalInstructionVersion.id != latest_version_id,
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
            "GlobalInstructionOverrides marked stale (base outdated)",
            extra={
                "instruction_code": instruction_code,
                "latest_version_id": str(latest_version_id),
                "affected_count": affected,
            },
        )
        return affected

    async def get_active_tenant_global_override(
        self,
        tenant_id: uuid.UUID,
        global_instruction_version_id: uuid.UUID,
    ) -> InstructionOverride | None:
        result = await self.session.execute(
            select(InstructionOverride).where(
                InstructionOverride.tenant_id == tenant_id,
                InstructionOverride.global_instruction_version_id == global_instruction_version_id,
                InstructionOverride.override_scope == "tenant",
                InstructionOverride.status == "active",
            )
        )
        return result.scalar_one_or_none()

    async def get_active_deal_global_override(
        self,
        deal_id: uuid.UUID,
        global_instruction_version_id: uuid.UUID,
    ) -> InstructionOverride | None:
        result = await self.session.execute(
            select(InstructionOverride).where(
                InstructionOverride.deal_id == deal_id,
                InstructionOverride.global_instruction_version_id == global_instruction_version_id,
                InstructionOverride.override_scope == "deal",
                InstructionOverride.status == "active",
            )
        )
        return result.scalar_one_or_none()



        