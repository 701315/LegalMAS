# src/services/global_instruction_editor_service.py

"""
Global instruction editor service.
clone_draft, preview, diff — зеркало InstructionEditorService.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.models.global_instruction import GlobalInstructionVersion
from db.repositories.global_instruction_version_repo import (
    GlobalInstructionVersionRepository,
)
from services.instruction_compiler import (
    InstructionCompilationError,
    InstructionCompiler,
)
from services.global_instruction_publishing_service import (
    GlobalInstructionNotFoundError,
)


@dataclass(slots=True)
class GlobalInstructionPreviewResult:
    is_valid: bool
    instruction_code: str
    group: str | None
    diagnostics: list[dict[str, Any]]
    validation_report: dict[str, Any]
    compiled_payload: dict[str, Any]
    source_sha256: str
    already_exists: bool
    existing_version_id: str | None = None


@dataclass(slots=True)
class GlobalInstructionDiffResult:
    from_version_id: str
    to_version_id: str
    from_source_sha256: str
    to_source_sha256: str
    are_identical: bool
    unified_diff: list[str] = field(default_factory=list)


class GlobalInstructionEditorService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = GlobalInstructionVersionRepository(session)
        self.compiler = InstructionCompiler()

    async def clone_draft(
        self,
        *,
        source_version_id,
        change_summary: str | None = None,
        created_by=None,
    ) -> GlobalInstructionVersion:
        """
        Создать новый draft на основе существующей версии.

        Дубликат-чек по sha256 намеренно отсутствует: клон создаётся
        с тем же YAML что и source — это рабочая копия для редактирования.
        После создания пользователь вносит изменения через update_draft,
        который уже содержит дубликат-чек.
        """
        source = await self.repo.get_by_id(source_version_id)
        if source is None:
            raise GlobalInstructionNotFoundError(
                f"Source global instruction version not found: {source_version_id}"
            )

        # Компилируем source_yaml чтобы получить нормализованный canonical_yaml
        # и актуальный compiled_payload. Не проверяем дубликаты — см. docstring.
        compiled = self.compiler.compile_global_instruction(
            instruction_code=source.instruction_code,
            source=source.source_yaml,
        )

        cloned = await self.repo.create_version(
            instruction_code=compiled.instruction_code,
            name=source.name,
            group=compiled.group,
            source_yaml=compiled.source_yaml,
            source_sha256=compiled.source_sha256,
            source_path=source.source_path,
            git_commit=source.git_commit,
            semver=None,
            compiled_payload=compiled.compiled_payload,
            version_status="draft",
            immutable_content_hash=None,
            validation_report=compiled.validation_report,
            parent_version_id=source.id,
            published_at=None,
            created_by=created_by,
            change_summary=(
                change_summary or f"Cloned from version {source_version_id}"
            ),
            owner_scope=source.owner_scope,
            tenant_id=source.tenant_id,
        )
        return cloned

    async def preview(
        self,
        *,
        instruction_code: str,
        source_yaml: str,
    ) -> GlobalInstructionPreviewResult:
        try:
            compiled = self.compiler.compile_global_instruction(
                instruction_code=instruction_code,
                source=source_yaml,
            )
        except InstructionCompilationError:
            raise

        existing = await self.repo.get_by_instruction_code_and_sha256(
            instruction_code=instruction_code,
            source_sha256=compiled.source_sha256,
        )

        return GlobalInstructionPreviewResult(
            is_valid=compiled.is_valid,
            instruction_code=compiled.instruction_code,
            group=compiled.group,
            diagnostics=[
                {"level": d.level, "message": d.message, "path": d.path}
                for d in compiled.diagnostics
            ],
            validation_report=compiled.validation_report,
            compiled_payload=compiled.compiled_payload,
            source_sha256=compiled.source_sha256,
            already_exists=existing is not None,
            existing_version_id=str(existing.id) if existing else None,
        )

    async def diff(
        self,
        *,
        from_version_id,
        to_version_id,
    ) -> GlobalInstructionDiffResult:
        from_version = await self.repo.get_by_id(from_version_id)
        if from_version is None:
            raise GlobalInstructionNotFoundError(
                f"Global instruction version not found: {from_version_id}"
            )
        to_version = await self.repo.get_by_id(to_version_id)
        if to_version is None:
            raise GlobalInstructionNotFoundError(
                f"Global instruction version not found: {to_version_id}"
            )

        from_lines = (from_version.source_yaml or "").splitlines(keepends=True)
        to_lines = (to_version.source_yaml or "").splitlines(keepends=True)
        are_identical = from_version.source_sha256 == to_version.source_sha256

        unified = list(difflib.unified_diff(
            from_lines,
            to_lines,
            fromfile=f"version/{from_version_id}",
            tofile=f"version/{to_version_id}",
            lineterm="",
        ))

        return GlobalInstructionDiffResult(
            from_version_id=str(from_version_id),
            to_version_id=str(to_version_id),
            from_source_sha256=from_version.source_sha256,
            to_source_sha256=to_version.source_sha256,
            are_identical=are_identical,
            unified_diff=unified,
        )


    