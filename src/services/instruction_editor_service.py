# src/services/instruction_editor_service.py

"""
Instruction editor service.

Удобные операции для редактора инструкций:
- clone_draft: создать новый draft из существующей версии
- preview: compile/validate YAML без сохранения в БД
- diff: получить diff между двумя версиями по source_yaml

Read-only операции (preview, diff) не изменяют состояние БД.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.models.document_type_instruction import DocumentTypeInstructionVersion
from db.repositories.document_type_instruction_version_repo import (
    DocumentTypeInstructionVersionRepository,
)
from services.instruction_compiler import (
    CompiledDocTypeInstruction,
    InstructionCompilationError,
    InstructionCompiler,
)
from services.instruction_publishing_service import (
    InstructionVersionNotFoundError,
)


@dataclass(slots=True)
class InstructionDiffResult:
    from_version_id: str
    to_version_id: str
    from_source_sha256: str
    to_source_sha256: str
    are_identical: bool
    unified_diff: list[str] = field(default_factory=list)


@dataclass(slots=True)
class InstructionPreviewResult:
    is_valid: bool
    checks_count: int
    triggers_used: list[str]
    diagnostics: list[dict[str, Any]]
    validation_report: dict[str, Any]
    compiled_payload: dict[str, Any]
    source_sha256: str
    already_exists: bool
    existing_version_id: str | None = None


class InstructionEditorService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.version_repo = DocumentTypeInstructionVersionRepository(session)
        self.compiler = InstructionCompiler()

    async def clone_draft(
        self,
        *,
        source_version_id,
        change_summary: str | None = None,
        created_by=None,
    ) -> DocumentTypeInstructionVersion:
        """
        Создать новый draft из существующей версии.

        Полезно для:
        - "Edit published" flow: пользователь нажимает кнопку,
          получает редактируемый draft на основе published версии;
        - восстановление archived-версии в новый рабочий draft;
        - создание вариантов для review.

        Дубликат-чек по sha256 намеренно отсутствует: клон создаётся
        с тем же YAML, что и source — это рабочая копия для редактирования.
        После создания пользователь вносит изменения через update_draft,
        который уже содержит нужные проверки.

        Raises:
            InstructionVersionNotFoundError: source не найден
        """
        source = await self.version_repo.get_by_id(source_version_id)
        if source is None:
            raise InstructionVersionNotFoundError(
                f"Source instruction version not found: {source_version_id}"
            )

        compiled = self.compiler.compile_doc_type_instruction(
            doc_type_code=source.doc_type_code,
            source=source.source_yaml,
        )

        cloned = await self.version_repo.create_version(
            doc_type_code=compiled.doc_type_code,
            name=source.name,
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
                change_summary
                or f"Cloned from version {source_version_id}"
            ),
        )

        return cloned

    async def preview(
        self,
        *,
        doc_type_code: str,
        source_yaml: str,
    ) -> InstructionPreviewResult:
        """
        Compile и validate YAML без сохранения в БД.

        Показывает:
        - is_valid
        - checks_count
        - triggers
        - validation_report
        - compiled_payload
        - уже ли существует такая версия в БД

        Не создаёт никаких записей.
        """
        try:
            compiled = self.compiler.compile_doc_type_instruction(
                doc_type_code=doc_type_code,
                source=source_yaml,
            )
        except InstructionCompilationError:
            raise

        existing = await self.version_repo.get_by_doc_type_and_sha256(
            doc_type_code=doc_type_code,
            source_sha256=compiled.source_sha256,
        )

        return InstructionPreviewResult(
            is_valid=compiled.is_valid,
            checks_count=compiled.checks_count,
            triggers_used=compiled.triggers_used_for_validation,
            diagnostics=[
                {
                    "level": d.level,
                    "message": d.message,
                    "path": d.path,
                }
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
    ) -> InstructionDiffResult:
        """
        Unified diff между source_yaml двух instruction versions.

        Полезно для:
        - просмотра изменений между версиями в UI
        - code review перед publish
        - audit trail "что изменилось"

        Raises:
            InstructionVersionNotFoundError: один из version_id не найден
        """
        from_version = await self.version_repo.get_by_id(from_version_id)
        if from_version is None:
            raise InstructionVersionNotFoundError(
                f"Instruction version not found: {from_version_id}"
            )

        to_version = await self.version_repo.get_by_id(to_version_id)
        if to_version is None:
            raise InstructionVersionNotFoundError(
                f"Instruction version not found: {to_version_id}"
            )

        from_yaml = (from_version.source_yaml or "").splitlines(keepends=True)
        to_yaml = (to_version.source_yaml or "").splitlines(keepends=True)

        are_identical = from_version.source_sha256 == to_version.source_sha256

        unified = list(difflib.unified_diff(
            from_yaml,
            to_yaml,
            fromfile=f"version/{from_version_id}",
            tofile=f"version/{to_version_id}",
            lineterm="",
        ))

        return InstructionDiffResult(
            from_version_id=str(from_version_id),
            to_version_id=str(to_version_id),
            from_source_sha256=from_version.source_sha256,
            to_source_sha256=to_version.source_sha256,
            are_identical=are_identical,
            unified_diff=unified,
        )


        