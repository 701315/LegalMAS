# src/engine/instructions/override_service.py

"""
Instruction override service.

Отвечает за бизнес-логику работы с override инструкций типа документа:

- создание tenant/deal overrides как JSON Patch (RFC 6902);
- validate / activate / archive lifecycle;
- apply patch с явной обработкой конфликтов;
- resolve effective payload (base → tenant override → deal override);
- staleness detection и rebase.

Контракт ошибок:

- PatchConflictError — patch не применяется к base payload.
- StaleBaseError — override ссылается на устаревшую base version.
- BaseVersionNotFoundError — base instruction version не найдена.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import jsonpatch
from jsonpatch import JsonPatchConflict, JsonPatchTestFailed
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.models.instruction_override import InstructionOverride
from db.repositories.instruction_override_repo import (
    InstructionOverrideRepository,
    InvalidLifecycleTransitionError,
    TenantOwnershipError,
)
from db.repositories.document_type_instruction_version_repo import (
    DocumentTypeInstructionVersionRepository,
)
from services.instruction_compiler import InstructionCompiler

logger = get_logger(__name__)


class PatchConflictError(Exception):
    """Patch не применился к base payload — явный структурный конфликт."""


class StaleBaseError(Exception):
    """Override ссылается на устаревшую base version."""


class BaseVersionNotFoundError(Exception):
    """Instruction version, на которую ссылается override, не найдена."""


class OverrideNotActiveError(Exception):
    """Override не в статусе active."""


@dataclass(frozen=True, slots=True)
class EffectiveInstructionPayload:
    """
    Результат resolve effective payload для (doc_type_code, tenant/deal).

    Содержит финальный payload и полную provenance-информацию
    для snapshot/manifest записи.
    """
    doc_type_code: str
    base_version_id: uuid.UUID
    base_content_hash: str
    tenant_override_id: uuid.UUID | None
    deal_override_id: uuid.UUID | None
    effective_payload: dict
    effective_hash: str
    is_overridden: bool
    provenance: dict


class InstructionOverrideService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.override_repo = InstructionOverrideRepository(session)
        self.version_repo = DocumentTypeInstructionVersionRepository(session)
        self.compiler = InstructionCompiler()

    # ── Создание overrides ────────────────────────────────────────────────────

    async def create_tenant_override_draft(
        self,
        *,
        tenant_id: uuid.UUID,
        instruction_version_id: uuid.UUID,
        patch_ops: list[dict],
        change_summary: str | None = None,
        created_by: uuid.UUID | None = None,
    ) -> InstructionOverride:
        """
        Создать draft tenant-level override.

        Dry-run apply до сохранения.
        override_scope='tenant', deal_id=None, status='draft'.
        """
        base_version = await self.version_repo.get_by_id(instruction_version_id)
        if base_version is None:
            raise BaseVersionNotFoundError(
                f"Instruction version {instruction_version_id} not found"
            )

        base_payload = base_version.compiled_payload or {}
        self._apply_patch(base_payload, patch_ops)

        override = await self.override_repo.create(
            tenant_id=tenant_id,
            override_scope="tenant",
            deal_id=None,
            instruction_version_id=instruction_version_id,
            base_content_hash=base_version.source_sha256,
            patch_ops=patch_ops,
            status="draft",
            change_summary=change_summary,
            created_by=created_by,
        )

        logger.info(
            "Tenant InstructionOverride draft created",
            extra={
                "tenant_id": str(tenant_id),
                "instruction_version_id": str(instruction_version_id),
                "override_id": str(override.id),
            },
        )
        return override

    async def create_deal_override_draft(
        self,
        *,
        tenant_id: uuid.UUID,
        deal_id: uuid.UUID,
        instruction_version_id: uuid.UUID,
        patch_ops: list[dict],
        change_summary: str | None = None,
        created_by: uuid.UUID | None = None,
    ) -> InstructionOverride:
        """
        Создать draft deal-level override.

        tenant_id используется для authorization.
        override_scope='deal', status='draft'.
        """
        base_version = await self.version_repo.get_by_id(instruction_version_id)
        if base_version is None:
            raise BaseVersionNotFoundError(
                f"Instruction version {instruction_version_id} not found"
            )

        base_payload = base_version.compiled_payload or {}
        self._apply_patch(base_payload, patch_ops)

        override = await self.override_repo.create(
            tenant_id=tenant_id,
            override_scope="deal",
            deal_id=deal_id,
            instruction_version_id=instruction_version_id,
            base_content_hash=base_version.source_sha256,
            patch_ops=patch_ops,
            status="draft",
            change_summary=change_summary,
            created_by=created_by,
        )

        logger.info(
            "Deal InstructionOverride draft created",
            extra={
                "tenant_id": str(tenant_id),
                "deal_id": str(deal_id),
                "instruction_version_id": str(instruction_version_id),
                "override_id": str(override.id),
            },
        )
        return override

    # ── Lifecycle: validate / activate / archive ──────────────────────────────

    async def validate_override(
        self,
        *,
        override_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> dict[str, Any]:
        """
        Проверить override:
        - ownership
        - base version не stale
        - patch_ops применяются без конфликта
        - effective payload валиден через InstructionCompiler

        Возвращает validation result, не меняет статус.
        """
        override = await self.override_repo.assert_tenant_owns(override_id, tenant_id)

        if override.is_stale:
            return {
                "is_valid": False,
                "errors": ["Override is stale. Rebase required before activation."],
                "effective_payload": None,
            }

        base_version = await self.version_repo.get_by_id(
            override.instruction_version_id
        )
        if base_version is None:
            return {
                "is_valid": False,
                "errors": [f"Base version {override.instruction_version_id} not found."],
                "effective_payload": None,
            }

        base_payload = base_version.compiled_payload or {}

        try:
            effective_payload = self._apply_patch(base_payload, override.patch_ops)
        except PatchConflictError as e:
            return {
                "is_valid": False,
                "errors": [f"Patch conflict: {e}"],
                "effective_payload": None,
            }

        try:
            compiled = self.compiler.compile_doc_type_instruction(
                doc_type_code=base_version.doc_type_code,
                source=effective_payload,
            )
        except Exception as e:
            return {
                "is_valid": False,
                "errors": [f"Compilation failed: {e}"],
                "effective_payload": effective_payload,
            }

        return {
            "is_valid": compiled.is_valid,
            "errors": [
                d.message for d in compiled.diagnostics if d.level == "error"
            ],
            "warnings": [
                d.message for d in compiled.diagnostics if d.level == "warning"
            ],
            "checks_count": compiled.checks_count,
            "effective_payload": effective_payload,
            "validation_report": compiled.validation_report,
        }

    async def activate_override(
        self,
        *,
        override_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> InstructionOverride:
        """
        Активировать override: draft → active.

        Guard: нельзя активировать stale.
        Guard: ownership check.
        """
        override = await self.override_repo.assert_tenant_owns(override_id, tenant_id)

        if override.is_stale:
            raise StaleBaseError(
                f"Override {override_id} is stale. Rebase required before activation."
            )

        updated = await self.override_repo.transition_status(
            override_id,
            from_status="draft",
            to_status="active",
            tenant_id=tenant_id,
        )

        if updated is None:
            raise InvalidLifecycleTransitionError(
                f"Failed to activate override {override_id}."
            )

        logger.info(
            "InstructionOverride activated",
            extra={
                "override_id": str(override_id),
                "tenant_id": str(tenant_id),
            },
        )
        return updated

    async def archive_override(
        self,
        *,
        override_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> InstructionOverride:
        """
        Архивировать override: active | draft → archived.

        Ownership check.
        """
        override = await self.override_repo.assert_tenant_owns(override_id, tenant_id)

        if override.status == "archived":
            return override

        updated = await self.override_repo.transition_status(
            override_id,
            from_status=override.status,
            to_status="archived",
            tenant_id=tenant_id,
        )

        if updated is None:
            raise InvalidLifecycleTransitionError(
                f"Failed to archive override {override_id}."
            )

        logger.info(
            "InstructionOverride archived",
            extra={
                "override_id": str(override_id),
                "tenant_id": str(tenant_id),
            },
        )
        return updated

    async def rebase_override(
        self,
        *,
        override_id: uuid.UUID,
        new_base_version_id: uuid.UUID,
        new_patch_ops: list[dict],
        tenant_id: uuid.UUID,
    ) -> InstructionOverride:
        """
        Rebase override на новую base version.

        Всегда явная операция пользователя.
        Dry-run apply новых patch_ops.
        is_stale → False после успешного rebase.
        Ownership check.
        """
        await self.override_repo.assert_tenant_owns(override_id, tenant_id)

        new_base_version = await self.version_repo.get_by_id(new_base_version_id)
        if new_base_version is None:
            raise BaseVersionNotFoundError(
                f"New base instruction version {new_base_version_id} not found"
            )

        base_payload = new_base_version.compiled_payload or {}
        self._apply_patch(base_payload, new_patch_ops)

        updated = await self.override_repo.rebase(
            override_id=override_id,
            new_instruction_version_id=new_base_version_id,
            new_base_content_hash=new_base_version.source_sha256,
            new_patch_ops=new_patch_ops,
        )

        logger.info(
            "InstructionOverride rebased",
            extra={
                "override_id": str(override_id),
                "new_base_version_id": str(new_base_version_id),
                "tenant_id": str(tenant_id),
            },
        )
        return updated

    # ── Effective payload resolution ──────────────────────────────────────────

    async def resolve_effective_payload(
        self,
        *,
        doc_type_code: str,
        tenant_id: uuid.UUID,
        deal_id: uuid.UUID | None = None,
    ) -> EffectiveInstructionPayload:
        """
        Canonical effective payload resolution chain.

        Priority: deal override > tenant override > base published version

        1. Published platform OR tenant instruction version
        2. Apply tenant active override (если есть)
        3. Apply deal active override (если есть)
        4. Вернуть effective payload + effective_hash + provenance

        Raises StaleBaseError если override stale.
        Raises BaseVersionNotFoundError если нет published version.
        """
        base_version = await self.version_repo.get_latest_published(
            doc_type_code,
            tenant_id=tenant_id,
        )
        if base_version is None:
            raise BaseVersionNotFoundError(
                f"No published instruction version found for doc_type_code={doc_type_code}"
            )

        base_payload = base_version.compiled_payload or {}
        effective_payload = base_payload
        tenant_override_id: uuid.UUID | None = None
        deal_override_id: uuid.UUID | None = None

        # Step 1: apply tenant override
        tenant_override = await self.override_repo.get_active_tenant_override(
            tenant_id=tenant_id,
            instruction_version_id=base_version.id,
        )
        if tenant_override is not None:
            if tenant_override.is_stale:
                raise StaleBaseError(
                    f"Tenant override {tenant_override.id} is stale for "
                    f"doc_type_code={doc_type_code}; rebase required"
                )
            effective_payload = self._apply_patch(effective_payload, tenant_override.patch_ops)
            tenant_override_id = tenant_override.id

        # Step 2: apply deal override
        if deal_id is not None:
            deal_override = await self.override_repo.get_active_deal_override(
                deal_id=deal_id,
                instruction_version_id=base_version.id,
            )
            if deal_override is not None:
                if deal_override.is_stale:
                    raise StaleBaseError(
                        f"Deal override {deal_override.id} is stale for "
                        f"doc_type_code={doc_type_code}; rebase required"
                    )
                effective_payload = self._apply_patch(effective_payload, deal_override.patch_ops)
                deal_override_id = deal_override.id

        is_overridden = (tenant_override_id is not None or deal_override_id is not None)

        import json
        import hashlib
        effective_hash = hashlib.sha256(
            json.dumps(effective_payload, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

        provenance = {
            "base_version_id": str(base_version.id),
            "base_owner_scope": base_version.owner_scope,
            "base_content_hash": base_version.source_sha256,
            "tenant_override_id": str(tenant_override_id) if tenant_override_id else None,
            "deal_override_id": str(deal_override_id) if deal_override_id else None,
            "is_overridden": is_overridden,
            "effective_hash": effective_hash,
        }

        return EffectiveInstructionPayload(
            doc_type_code=doc_type_code,
            base_version_id=base_version.id,
            base_content_hash=base_version.source_sha256,
            tenant_override_id=tenant_override_id,
            deal_override_id=deal_override_id,
            effective_payload=effective_payload,
            effective_hash=effective_hash,
            is_overridden=is_overridden,
            provenance=provenance,
        )

    # ── Staleness propagation ────────────────────────────────────────────────

    async def mark_overrides_stale_for_version(
        self,
        instruction_version_id: uuid.UUID,
    ) -> int:
        """
        Помечает stale все override, построенные на данной версии.
        """
        return await self.override_repo.mark_stale_for_instruction_version(
            instruction_version_id
        )

    # ── Internal apply patch ─────────────────────────────────────────────────

    def _apply_patch(
        self,
        base_payload: dict[str, Any],
        patch_ops: list[dict],
    ) -> dict[str, Any]:
        """
        Применить JSON Patch (RFC 6902) к base_payload.

        Никакого silent fallback — любая ошибка явно поднимается как PatchConflictError.
        """
        try:
            patch = jsonpatch.JsonPatch(patch_ops)
            result = patch.apply(base_payload, in_place=False)
        except (JsonPatchConflict, JsonPatchTestFailed) as e:
            logger.warning(
                "InstructionOverride patch conflict",
                extra={
                    "error": str(e),
                    "patch_ops_count": len(patch_ops),
                },
            )
            raise PatchConflictError(str(e)) from e
        except Exception as e:
            logger.warning(
                "InstructionOverride patch failed unexpectedly",
                extra={
                    "error": str(e),
                    "patch_ops_count": len(patch_ops),
                },
            )
            raise PatchConflictError(str(e)) from e

        return result
    

    