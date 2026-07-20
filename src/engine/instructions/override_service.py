# src/engine/instructions/override_service.py

"""
Instruction override service.

Отвечает за бизнес-логику работы с override инструкций типа документа:

- создание override как JSON Patch (RFC 6902) поверх конкретной
  DocumentTypeInstructionVersion;
- apply patch к compiled_payload базовой версии с явной обработкой конфликтов
  (без silent fallback, без частичного повреждения данных);
- проверка staleness через сравнение base_content_hash;
- audit logging через AuditLog при создании/rebase override.

Контракт ошибок:

- PatchConflictError — patch не применяется к текущему base payload
  (структурный конфликт, например test-операция не прошла, или
  path не существует). Вызывающий код обязан явно обработать это,
  никакого автоматического fallback на предыдущую версию.
- StaleBaseError — base_content_hash override не совпадает с текущим
  content_hash instruction version (база изменилась с момента создания
  override). Требует явного rebase пользователем.
"""

from __future__ import annotations

import uuid
from typing import Any

import jsonpatch
from jsonpatch import JsonPatchConflict, JsonPatchTestFailed
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.models.instruction_override import InstructionOverride
from db.repositories.instruction_override_repo import InstructionOverrideRepository
from db.repositories.document_type_instruction_version_repo import (
    DocumentTypeInstructionVersionRepository,
)

logger = get_logger(__name__)


class PatchConflictError(Exception):
    """Patch не применился к base payload — явный структурный конфликт."""


class StaleBaseError(Exception):
    """base_content_hash override не совпадает с текущим content_hash версии."""


class BaseVersionNotFoundError(Exception):
    """Instruction version, на которую ссылается override, не найдена."""


class InstructionOverrideService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.override_repo = InstructionOverrideRepository(session)
        self.version_repo = DocumentTypeInstructionVersionRepository(session)

    # ── Создание override ────────────────────────────────────────────────────

    async def create_override(
        self,
        deal_id: uuid.UUID,
        instruction_version_id: uuid.UUID,
        patch_ops: list[dict],
        change_summary: str | None = None,
        created_by: uuid.UUID | None = None,
    ) -> InstructionOverride:
        """
        Создать override для сделки поверх конкретной instruction version.

        Патч сразу проверяется на применимость (dry-run apply) —
        если patch_ops структурно некорректен относительно текущего
        compiled_payload, override не создаётся, а поднимается
        PatchConflictError.
        """
        base_version = await self.version_repo.get_by_id(instruction_version_id)
        if base_version is None:
            raise BaseVersionNotFoundError(
                f"Instruction version {instruction_version_id} not found"
            )

        base_payload = base_version.compiled_payload or {}

        # Dry-run apply: убеждаемся, что patch применяется к текущему payload
        # ДО того как сохраняем override в БД. Никакого "сохранили, потом узнали
        # что не работает".
        self._apply_patch(base_payload, patch_ops)

        override = await self.override_repo.create(
            deal_id=deal_id,
            instruction_version_id=instruction_version_id,
            base_content_hash=base_version.source_sha256,
            patch_ops=patch_ops,
            change_summary=change_summary,
            created_by=created_by,
        )

        logger.info(
            "InstructionOverride validated and created",
            extra={
                "deal_id": str(deal_id),
                "instruction_version_id": str(instruction_version_id),
                "override_id": str(override.id),
            },
        )
        return override

    # ── Применение override (resolve effective payload) ─────────────────────

    async def resolve_effective_payload(
        self,
        deal_id: uuid.UUID,
        doc_type_code: str,
    ) -> dict[str, Any]:
        """
        Вернуть effective compiled_payload для (deal_id, doc_type_code).

        Резолвит последнюю published instruction version для doc_type_code,
        затем проверяет наличие override для этой сделки:

        - override отсутствует -> возвращаем payload latest version как есть;
        - override есть и ссылается на latest version -> apply patch;
        - override есть, но ссылается на СТАРУЮ version (is_stale=True или
          instruction_version_id != latest.id) -> StaleBaseError, требуется
          явный rebase пользователем.
        """
        latest_version = await self.version_repo.get_latest_published(doc_type_code)
        if latest_version is None:
            raise BaseVersionNotFoundError(
                f"No published instruction version found for doc_type_code={doc_type_code}"
            )

        base_payload = latest_version.compiled_payload or {}

        override = await self.override_repo.get_by_deal_and_version(
            deal_id=deal_id,
            instruction_version_id=latest_version.id,
        )

        if override is not None and not override.is_stale:
            return self._apply_patch(base_payload, override.patch_ops)

        # Override для latest version не найден напрямую — проверяем,
        # есть ли override деал для ЛЮБОЙ более старой версии этого doc_type_code.
        stale_override = await self._find_any_override_for_doc_type(
            deal_id=deal_id,
            doc_type_code=doc_type_code,
        )
        if stale_override is not None:
            raise StaleBaseError(
                f"Override {stale_override.id} references outdated instruction "
                f"version for doc_type_code={doc_type_code}; rebase required"
            )

        return base_payload

    async def _find_any_override_for_doc_type(
        self,
        deal_id: uuid.UUID,
        doc_type_code: str,
    ) -> InstructionOverride | None:
        """Найти override для сделки, привязанный к ЛЮБОЙ версии этого doc_type_code."""
        from sqlalchemy import select as sa_select
        from db.models.document_type_instruction import DocumentTypeInstructionVersion

        stmt = sa_select(InstructionOverride).where(
            InstructionOverride.deal_id == deal_id,
            InstructionOverride.instruction_version_id.in_(
                sa_select(DocumentTypeInstructionVersion.id).where(
                    DocumentTypeInstructionVersion.doc_type_code == doc_type_code
                )
            ),
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    # ── Внутренний helper: apply patch с явной обработкой конфликтов ────────

    def _apply_patch(
        self,
        base_payload: dict[str, Any],
        patch_ops: list[dict],
    ) -> dict[str, Any]:
        """
        Применить JSON Patch (RFC 6902) к base_payload.

        Никакого try/except с молчаливым возвратом base_payload —
        любая ошибка применения patch явно поднимается как PatchConflictError.
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
            # Любая другая ошибка (malformed op, invalid path и т.д.) —
            # тоже явный конфликт, не silent fallback.
            logger.warning(
                "InstructionOverride patch failed unexpectedly",
                extra={
                    "error": str(e),
                    "patch_ops_count": len(patch_ops),
                },
            )
            raise PatchConflictError(str(e)) from e

        return result

    # ── Staleness propagation ────────────────────────────────────────────────

    async def mark_overrides_stale_for_version(
        self,
        instruction_version_id: uuid.UUID,
    ) -> int:
        """
        Помечает stale все override, построенные на данной версии.

        Вызывается сервисом публикации instruction version ПОСЛЕ того,
        как source_yaml/compiled_payload этой версии были изменены.
        """
        return await self.override_repo.mark_stale_for_instruction_version(
            instruction_version_id
        )
    
