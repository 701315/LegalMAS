# src/api/endpoints/instruction_preview.py

"""
Unified instruction preview endpoint.

POST /api/v1/instruction-preview

Позволяет безопасно превью effective instruction payload перед:
- publish override
- activate override
- formulate playbook

Access:
- Любой аутентифицированный пользователь может вызвать preview,
  но видит только то, к чему имеет доступ:
  - tenant_override_id/deal_override_id проверяются по tenant ownership
  - base_version_id — только published versions
"""

from __future__ import annotations

import difflib
import hashlib
import json
import uuid

import jsonpatch
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.schemas.instruction_overrides import (
    InstructionPreviewRequest,
    InstructionPreviewResponse,
)
from db.repositories.document_type_instruction_version_repo import (
    DocumentTypeInstructionVersionRepository,
)
from db.repositories.instruction_override_repo import InstructionOverrideRepository
from db.session import get_db
from services.instruction_compiler import InstructionCompilationError, InstructionCompiler

router = APIRouter(tags=["instruction-preview"])


@router.post(
    "/instruction-preview",
    response_model=InstructionPreviewResponse,
    summary="Preview effective instruction payload",
)
async def preview_instruction(
    body: InstructionPreviewRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> InstructionPreviewResponse:
    """
    Preview effective instruction payload без записи в БД.

    Порядок применения:
    1. Загружаем base instruction version
    2. Применяем tenant override если указан
    3. Применяем deal override если указан
    4. Применяем draft_patch_ops если указаны (live preview)
    5. Компилируем и валидируем effective payload
    6. Возвращаем: valid, errors, hashes, checks_count, diff

    Использование:
    - Перед activate override — убедиться что patch корректен
    - Перед publish tenant instruction — preview result
    - Live editor — real-time preview по мере редактирования patch
    """
    version_repo = DocumentTypeInstructionVersionRepository(db)
    override_repo = InstructionOverrideRepository(db)
    compiler = InstructionCompiler()

    # 1. Загружаем base version
    if body.base_version_id is not None:
        base_version = await version_repo.get_by_id(body.base_version_id)
        if base_version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "BASE_VERSION_NOT_FOUND",
                    "message": f"Instruction version {body.base_version_id} not found",
                },
            )
    else:
        base_version = await version_repo.get_latest_published(
            body.doc_type_code,
            tenant_id=user.tenant_id,
        )
        if base_version is None:
            return InstructionPreviewResponse(
                valid=False,
                errors=[
                    f"No published instruction version found for doc_type_code='{body.doc_type_code}'"
                ],
            )

    base_payload = base_version.compiled_payload or {}
    effective_payload = dict(base_payload)

    errors: list[str] = []
    warnings: list[str] = []

    # 2. Применяем tenant override
    if body.tenant_override_id is not None:
        tenant_override = await override_repo.get_by_id(body.tenant_override_id)
        if tenant_override is None:
            errors.append(f"Tenant override {body.tenant_override_id} not found")
        elif tenant_override.tenant_id != user.tenant_id and user.global_role != "superadmin":
            errors.append(f"Tenant override {body.tenant_override_id} not accessible")
        elif tenant_override.is_stale:
            warnings.append(
                f"Tenant override {body.tenant_override_id} is stale — rebase recommended"
            )
        else:
            try:
                patch = jsonpatch.JsonPatch(tenant_override.patch_ops or [])
                effective_payload = patch.apply(effective_payload, in_place=False)
            except Exception as e:
                errors.append(f"Tenant override patch conflict: {e}")

    # 3. Применяем deal override
    if body.deal_override_id is not None:
        deal_override = await override_repo.get_by_id(body.deal_override_id)
        if deal_override is None:
            errors.append(f"Deal override {body.deal_override_id} not found")
        elif deal_override.tenant_id != user.tenant_id and user.global_role != "superadmin":
            errors.append(f"Deal override {body.deal_override_id} not accessible")
        elif deal_override.is_stale:
            warnings.append(
                f"Deal override {body.deal_override_id} is stale — rebase recommended"
            )
        else:
            try:
                patch = jsonpatch.JsonPatch(deal_override.patch_ops or [])
                effective_payload = patch.apply(effective_payload, in_place=False)
            except Exception as e:
                errors.append(f"Deal override patch conflict: {e}")

    # 4. Применяем draft_patch_ops (live preview)
    if body.draft_patch_ops:
        try:
            patch = jsonpatch.JsonPatch(body.draft_patch_ops)
            effective_payload = patch.apply(effective_payload, in_place=False)
        except Exception as e:
            errors.append(f"Draft patch ops conflict: {e}")

    # Если были ошибки применения patch — возвращаем без compilation
    if errors:
        return InstructionPreviewResponse(
            valid=False,
            errors=errors,
            warnings=warnings,
            base_version_id=str(base_version.id),
            base_hash=base_version.source_sha256,
        )

    # 5. Компилируем и валидируем effective payload
    try:
        compiled = compiler.compile_doc_type_instruction(
            doc_type_code=body.doc_type_code,
            source=effective_payload,
        )
    except InstructionCompilationError as e:
        return InstructionPreviewResponse(
            valid=False,
            errors=[str(e)],
            warnings=warnings,
            base_version_id=str(base_version.id),
            base_hash=base_version.source_sha256,
        )

    if not compiled.is_valid:
        errors.extend(
            d.message for d in compiled.diagnostics if d.level == "error"
        )
    warnings.extend(
        d.message for d in compiled.diagnostics if d.level == "warning"
    )

    # 6. Считаем effective hash
    effective_hash = hashlib.sha256(
        json.dumps(effective_payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()

    # 7. Diff: base_payload vs effective_payload
    base_lines = json.dumps(
        base_payload, sort_keys=True, indent=2, ensure_ascii=False
    ).splitlines(keepends=True)
    effective_lines = json.dumps(
        effective_payload, sort_keys=True, indent=2, ensure_ascii=False
    ).splitlines(keepends=True)

    unified_diff = list(difflib.unified_diff(
        base_lines,
        effective_lines,
        fromfile=f"base/{base_version.id}",
        tofile="effective",
        lineterm="",
    ))

    # 8. Check ID collisions
    check_ids: list[str] = []
    for check in (effective_payload.get("checks_v8") or []):
        if isinstance(check, dict) and check.get("id"):
            check_ids.append(str(check["id"]))

    from collections import Counter
    collisions = [
        check_id for check_id, count in Counter(check_ids).items()
        if count > 1
    ]

    return InstructionPreviewResponse(
        valid=compiled.is_valid and not errors,
        errors=errors,
        warnings=warnings,
        base_version_id=str(base_version.id),
        base_hash=base_version.source_sha256,
        effective_hash=effective_hash,
        effective_payload=effective_payload,
        checks_count=compiled.checks_count,
        check_id_collisions=collisions,
        diff=unified_diff,
    )


    