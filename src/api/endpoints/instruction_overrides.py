# src/api/endpoints/instruction_overrides.py

"""
Endpoints for instruction override lifecycle management.

Tenant-level overrides (doc-type):
    GET  /api/v1/tenants/{tenant_id}/instruction-overrides
    POST /api/v1/tenants/{tenant_id}/instruction-overrides/draft
    POST /api/v1/tenants/{tenant_id}/instruction-overrides/{override_id}/validate
    POST /api/v1/tenants/{tenant_id}/instruction-overrides/{override_id}/activate
    POST /api/v1/tenants/{tenant_id}/instruction-overrides/{override_id}/archive

Tenant-level overrides (global instructions):
    POST /api/v1/tenants/{tenant_id}/global-instruction-overrides/draft
    POST /api/v1/tenants/{tenant_id}/global-instruction-overrides/{override_id}/validate
    POST /api/v1/tenants/{tenant_id}/global-instruction-overrides/{override_id}/activate
    POST /api/v1/tenants/{tenant_id}/global-instruction-overrides/{override_id}/archive

Deal-level overrides (doc-type):
    GET  /api/v1/deals/{deal_id}/instruction-overrides
    POST /api/v1/deals/{deal_id}/instruction-overrides/draft
    POST /api/v1/deals/{deal_id}/instruction-overrides/{override_id}/validate
    POST /api/v1/deals/{deal_id}/instruction-overrides/{override_id}/activate
    POST /api/v1/deals/{deal_id}/instruction-overrides/{override_id}/archive
    POST /api/v1/deals/{deal_id}/instruction-overrides/{override_id}/rebase

Deal-level overrides (global instructions):
    POST /api/v1/deals/{deal_id}/global-instruction-overrides/draft
    POST /api/v1/deals/{deal_id}/global-instruction-overrides/{override_id}/validate
    POST /api/v1/deals/{deal_id}/global-instruction-overrides/{override_id}/activate
    POST /api/v1/deals/{deal_id}/global-instruction-overrides/{override_id}/archive

Access model:
    Tenant endpoints:
        superadmin    → any tenant
        tenant_admin  → own tenant only
        member        → forbidden

    Deal endpoints (read):
        superadmin    → any
        tenant_admin  → any deal within own tenant
        member        → only via deal_members (viewer/editor/admin)

    Deal endpoints (write: draft/validate/activate/archive/rebase):
        superadmin    → yes
        tenant_admin  → yes
        member        → editor/admin only
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import (
    get_scoped_deal,
    require_project_role,
    require_tenant_scope_access,
)
from api.schemas.instruction_overrides import (
    GlobalInstructionOverrideDraftRequest,
    InstructionOverrideDraftRequest,
    InstructionOverrideItem,
    InstructionOverrideListResponse,
    InstructionOverrideRebaseRequest,
    InstructionOverrideResponse,
    InstructionOverrideValidationResponse,
)
from db.models.instruction_override import InstructionOverride
from db.repositories.instruction_override_repo import (
    InvalidLifecycleTransitionError,
    TenantOwnershipError,
)
from db.session import get_db
from engine.instructions.override_service import (
    BaseVersionNotFoundError,
    InstructionOverrideService,
    PatchConflictError,
    StaleBaseError,
)

router = APIRouter(tags=["instruction-overrides"])


# ── Dependency factories ──────────────────────────────────────────────────────

def get_override_service(
    db: AsyncSession = Depends(get_db),
) -> InstructionOverrideService:
    return InstructionOverrideService(db)


# ── Serialization ─────────────────────────────────────────────────────────────

def _serialize_override(override: InstructionOverride) -> InstructionOverrideItem:
    return InstructionOverrideItem(
        id=str(override.id),
        instruction_version_id=(
            str(override.instruction_version_id)
            if override.instruction_version_id is not None
            else None
        ),
        global_instruction_version_id=(
            str(override.global_instruction_version_id)
            if override.global_instruction_version_id is not None
            else None
        ),
        override_scope=override.override_scope,
        tenant_id=str(override.tenant_id),
        deal_id=str(override.deal_id) if override.deal_id else None,
        status=override.status,
        base_content_hash=override.base_content_hash,
        patch_ops=override.patch_ops or [],
        is_stale=override.is_stale,
        change_summary=override.change_summary,
        created_by=str(override.created_by) if override.created_by else None,
        created_at=getattr(override, "created_at", None),
        updated_at=getattr(override, "updated_at", None),
    )


# ── Error mapping ─────────────────────────────────────────────────────────────

def _map_override_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, BaseVersionNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "BASE_VERSION_NOT_FOUND", "message": str(exc)},
        )
    if isinstance(exc, PatchConflictError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "OVERRIDE_PATCH_CONFLICT", "message": str(exc)},
        )
    if isinstance(exc, StaleBaseError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "OVERRIDE_IS_STALE", "message": str(exc)},
        )
    if isinstance(exc, TenantOwnershipError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "TENANT_OWNERSHIP_VIOLATION", "message": str(exc)},
        )
    if isinstance(exc, InvalidLifecycleTransitionError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "INVALID_LIFECYCLE_TRANSITION", "message": str(exc)},
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"code": "INTERNAL_ERROR", "message": "Internal error"},
    )


# ── Tenant-level override endpoints ──────────────────────────────────────────

@router.get(
    "/tenants/{tenant_id}/instruction-overrides",
    response_model=InstructionOverrideListResponse,
    summary="List tenant-level overrides",
)
async def list_tenant_overrides(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    service: InstructionOverrideService = Depends(get_override_service),
) -> InstructionOverrideListResponse:
    """
    Return all tenant-level overrides for the given tenant.

    Access:
    - superadmin → any tenant
    - tenant_admin → own tenant only
    - member → forbidden
    """
    require_tenant_scope_access(user, tenant_id)

    overrides = await service.override_repo.list_for_tenant_scope(tenant_id)
    return InstructionOverrideListResponse(
        items=[_serialize_override(o) for o in overrides]
    )


@router.post(
    "/tenants/{tenant_id}/instruction-overrides/draft",
    response_model=InstructionOverrideResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create draft tenant-level override",
)
async def create_tenant_override_draft(
    tenant_id: uuid.UUID,
    body: InstructionOverrideDraftRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    service: InstructionOverrideService = Depends(get_override_service),
) -> InstructionOverrideResponse:
    """
    Create a draft tenant-level override.

    Dry-run apply before saving — patch is validated for applicability.

    Access:
    - superadmin → any tenant
    - tenant_admin → own tenant only
    - member → forbidden
    """
    require_tenant_scope_access(user, tenant_id)

    try:
        override = await service.create_tenant_override_draft(
            tenant_id=tenant_id,
            instruction_version_id=body.instruction_version_id,
            patch_ops=body.patch_ops,
            change_summary=body.change_summary,
            created_by=uuid.UUID(str(user.id)),
        )
        item = _serialize_override(override)
        await db.commit()
        return InstructionOverrideResponse(item=item)
    except Exception as exc:
        await db.rollback()
        raise _map_override_exception(exc) from exc


@router.post(
    "/tenants/{tenant_id}/instruction-overrides/{override_id}/validate",
    response_model=InstructionOverrideValidationResponse,
    summary="Validate tenant-level override",
)
async def validate_tenant_override(
    tenant_id: uuid.UUID,
    override_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    service: InstructionOverrideService = Depends(get_override_service),
) -> InstructionOverrideValidationResponse:
    """
    Validate override: staleness, patch conflict, effective payload validation.

    Does not change status. Read-only validation.
    """
    require_tenant_scope_access(user, tenant_id)

    try:
        result = await service.validate_override(
            override_id=override_id,
            tenant_id=tenant_id,
        )
        return InstructionOverrideValidationResponse(
            override_id=str(override_id),
            is_valid=result.get("is_valid", False),
            errors=result.get("errors", []),
            warnings=result.get("warnings", []),
            checks_count=result.get("checks_count"),
            effective_payload=result.get("effective_payload"),
            validation_report=result.get("validation_report"),
        )
    except Exception as exc:
        raise _map_override_exception(exc) from exc


@router.post(
    "/tenants/{tenant_id}/instruction-overrides/{override_id}/activate",
    response_model=InstructionOverrideResponse,
    summary="Activate tenant-level override",
)
async def activate_tenant_override(
    tenant_id: uuid.UUID,
    override_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    service: InstructionOverrideService = Depends(get_override_service),
) -> InstructionOverrideResponse:
    """
    Activate tenant-level override: draft → active.

    Cannot activate a stale override.
    """
    require_tenant_scope_access(user, tenant_id)

    try:
        override = await service.activate_override(
            override_id=override_id,
            tenant_id=tenant_id,
        )
        item = _serialize_override(override)
        await db.commit()
        return InstructionOverrideResponse(item=item)
    except Exception as exc:
        await db.rollback()
        raise _map_override_exception(exc) from exc


@router.post(
    "/tenants/{tenant_id}/instruction-overrides/{override_id}/archive",
    response_model=InstructionOverrideResponse,
    summary="Archive tenant-level override",
)
async def archive_tenant_override(
    tenant_id: uuid.UUID,
    override_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    service: InstructionOverrideService = Depends(get_override_service),
) -> InstructionOverrideResponse:
    """
    Archive tenant-level override: active|draft → archived.
    """
    require_tenant_scope_access(user, tenant_id)

    try:
        override = await service.archive_override(
            override_id=override_id,
            tenant_id=tenant_id,
        )
        item = _serialize_override(override)
        await db.commit()
        return InstructionOverrideResponse(item=item)
    except Exception as exc:
        await db.rollback()
        raise _map_override_exception(exc) from exc


# ── Deal-level override endpoints ─────────────────────────────────────────────

@router.get(
    "/deals/{deal_id}/instruction-overrides",
    response_model=InstructionOverrideListResponse,
    summary="List deal-level overrides",
)
async def list_deal_overrides(
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    service: InstructionOverrideService = Depends(get_override_service),
) -> InstructionOverrideListResponse:
    """
    Return all deal-level overrides for the given deal.

    Access: project viewer/editor/admin.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    overrides = await service.override_repo.list_for_deal(deal_id)
    return InstructionOverrideListResponse(
        items=[_serialize_override(o) for o in overrides]
    )


@router.post(
    "/deals/{deal_id}/instruction-overrides/draft",
    response_model=InstructionOverrideResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create draft deal-level override",
)
async def create_deal_override_draft(
    deal_id: uuid.UUID,
    body: InstructionOverrideDraftRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    service: InstructionOverrideService = Depends(get_override_service),
) -> InstructionOverrideResponse:
    """
    Create a draft deal-level override.

    Dry-run apply before saving.

    Access: project editor/admin.
    """
    deal = await get_scoped_deal(deal_id=deal_id, user=user, db=db)
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor"),
    )

    try:
        override = await service.create_deal_override_draft(
            tenant_id=deal.tenant_id,
            deal_id=deal_id,
            instruction_version_id=body.instruction_version_id,
            patch_ops=body.patch_ops,
            change_summary=body.change_summary,
            created_by=uuid.UUID(str(user.id)),
        )
        item = _serialize_override(override)
        await db.commit()
        return InstructionOverrideResponse(item=item)
    except Exception as exc:
        await db.rollback()
        raise _map_override_exception(exc) from exc


@router.post(
    "/deals/{deal_id}/instruction-overrides/{override_id}/validate",
    response_model=InstructionOverrideValidationResponse,
    summary="Validate deal-level override",
)
async def validate_deal_override(
    deal_id: uuid.UUID,
    override_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    service: InstructionOverrideService = Depends(get_override_service),
) -> InstructionOverrideValidationResponse:
    """
    Validate deal-level override without changing its status.

    Access: project viewer/editor/admin.
    """
    deal = await get_scoped_deal(deal_id=deal_id, user=user, db=db)
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    try:
        result = await service.validate_override(
            override_id=override_id,
            tenant_id=deal.tenant_id,
        )
        return InstructionOverrideValidationResponse(
            override_id=str(override_id),
            is_valid=result.get("is_valid", False),
            errors=result.get("errors", []),
            warnings=result.get("warnings", []),
            checks_count=result.get("checks_count"),
            effective_payload=result.get("effective_payload"),
            validation_report=result.get("validation_report"),
        )
    except Exception as exc:
        raise _map_override_exception(exc) from exc


@router.post(
    "/deals/{deal_id}/instruction-overrides/{override_id}/activate",
    response_model=InstructionOverrideResponse,
    summary="Activate deal-level override",
)
async def activate_deal_override(
    deal_id: uuid.UUID,
    override_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    service: InstructionOverrideService = Depends(get_override_service),
) -> InstructionOverrideResponse:
    """
    Activate deal-level override: draft → active.

    Cannot activate a stale override.

    Access: project editor/admin.
    """
    deal = await get_scoped_deal(deal_id=deal_id, user=user, db=db)
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor"),
    )

    try:
        override = await service.activate_override(
            override_id=override_id,
            tenant_id=deal.tenant_id,
        )
        item = _serialize_override(override)
        await db.commit()
        return InstructionOverrideResponse(item=item)
    except Exception as exc:
        await db.rollback()
        raise _map_override_exception(exc) from exc


@router.post(
    "/deals/{deal_id}/instruction-overrides/{override_id}/archive",
    response_model=InstructionOverrideResponse,
    summary="Archive deal-level override",
)
async def archive_deal_override(
    deal_id: uuid.UUID,
    override_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    service: InstructionOverrideService = Depends(get_override_service),
) -> InstructionOverrideResponse:
    """
    Archive deal-level override.

    Access: project editor/admin.
    """
    deal = await get_scoped_deal(deal_id=deal_id, user=user, db=db)
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor"),
    )

    try:
        override = await service.archive_override(
            override_id=override_id,
            tenant_id=deal.tenant_id,
        )
        item = _serialize_override(override)
        await db.commit()
        return InstructionOverrideResponse(item=item)
    except Exception as exc:
        await db.rollback()
        raise _map_override_exception(exc) from exc


@router.post(
    "/deals/{deal_id}/instruction-overrides/{override_id}/rebase",
    response_model=InstructionOverrideResponse,
    summary="Rebase deal-level override onto a new base version",
)
async def rebase_deal_override(
    deal_id: uuid.UUID,
    override_id: uuid.UUID,
    body: InstructionOverrideRebaseRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    service: InstructionOverrideService = Depends(get_override_service),
) -> InstructionOverrideResponse:
    """
    Rebase deal-level override onto a new base instruction version.

    Explicit operation — always user-initiated, never automatic.
    After rebase, is_stale is reset to False.

    Access: project editor/admin.
    """
    deal = await get_scoped_deal(deal_id=deal_id, user=user, db=db)
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor"),
    )

    try:
        override = await service.rebase_override(
            override_id=override_id,
            new_base_version_id=body.new_base_version_id,
            new_patch_ops=body.new_patch_ops,
            tenant_id=deal.tenant_id,
        )
        item = _serialize_override(override)
        await db.commit()
        return InstructionOverrideResponse(item=item)
    except Exception as exc:
        await db.rollback()
        raise _map_override_exception(exc) from exc


# ── Tenant-level global instruction override endpoints ─────────────────────────

@router.post(
    "/tenants/{tenant_id}/global-instruction-overrides/draft",
    response_model=InstructionOverrideResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create draft tenant-level override (global instruction)",
)
async def create_tenant_global_override_draft(
    tenant_id: uuid.UUID,
    body: GlobalInstructionOverrideDraftRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    service: InstructionOverrideService = Depends(get_override_service),
) -> InstructionOverrideResponse:
    """
    Create a draft tenant-level override for a global instruction.

    Global instructions are universal checks (confidentiality, governing_law,
    term_and_renewal, etc.) not tied to a specific doc_type.

    Dry-run apply before saving — patch is validated for applicability to
    the compiled_payload of the base global instruction version.

    Access:
    - superadmin → any tenant
    - tenant_admin → own tenant only
    - member → forbidden
    """
    require_tenant_scope_access(user, tenant_id)

    try:
        override = await service.create_tenant_global_override_draft(
            tenant_id=tenant_id,
            global_instruction_version_id=body.global_instruction_version_id,
            patch_ops=body.patch_ops,
            change_summary=body.change_summary,
            created_by=uuid.UUID(str(user.id)),
        )
        item = _serialize_override(override)
        await db.commit()
        return InstructionOverrideResponse(item=item)
    except Exception as exc:
        await db.rollback()
        raise _map_override_exception(exc) from exc


@router.post(
    "/tenants/{tenant_id}/global-instruction-overrides/{override_id}/validate",
    response_model=InstructionOverrideValidationResponse,
    summary="Validate tenant-level override (global instruction)",
)
async def validate_tenant_global_override(
    tenant_id: uuid.UUID,
    override_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    service: InstructionOverrideService = Depends(get_override_service),
) -> InstructionOverrideValidationResponse:
    """
    Validate global instruction override without changing its status.

    Checks: staleness, patch conflict, effective payload structure.

    Access:
    - superadmin → any tenant
    - tenant_admin → own tenant only
    - member → forbidden
    """
    require_tenant_scope_access(user, tenant_id)

    try:
        result = await service.validate_global_override(
            override_id=override_id,
            tenant_id=tenant_id,
        )
        return InstructionOverrideValidationResponse(
            override_id=str(override_id),
            is_valid=result.get("is_valid", False),
            errors=result.get("errors", []),
            warnings=result.get("warnings", []),
            checks_count=result.get("checks_count"),
            effective_payload=result.get("effective_payload"),
            validation_report=result.get("validation_report"),
        )
    except Exception as exc:
        raise _map_override_exception(exc) from exc


@router.post(
    "/tenants/{tenant_id}/global-instruction-overrides/{override_id}/activate",
    response_model=InstructionOverrideResponse,
    summary="Activate tenant-level override (global instruction)",
)
async def activate_tenant_global_override(
    tenant_id: uuid.UUID,
    override_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    service: InstructionOverrideService = Depends(get_override_service),
) -> InstructionOverrideResponse:
    """
    Activate tenant-level global instruction override: draft → active.

    Cannot activate a stale override.

    Access:
    - superadmin → any tenant
    - tenant_admin → own tenant only
    - member → forbidden
    """
    require_tenant_scope_access(user, tenant_id)

    try:
        override = await service.activate_override(
            override_id=override_id,
            tenant_id=tenant_id,
        )
        item = _serialize_override(override)
        await db.commit()
        return InstructionOverrideResponse(item=item)
    except Exception as exc:
        await db.rollback()
        raise _map_override_exception(exc) from exc


@router.post(
    "/tenants/{tenant_id}/global-instruction-overrides/{override_id}/archive",
    response_model=InstructionOverrideResponse,
    summary="Archive tenant-level override (global instruction)",
)
async def archive_tenant_global_override(
    tenant_id: uuid.UUID,
    override_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    service: InstructionOverrideService = Depends(get_override_service),
) -> InstructionOverrideResponse:
    """
    Archive tenant-level global instruction override.

    Access:
    - superadmin → any tenant
    - tenant_admin → own tenant only
    - member → forbidden
    """
    require_tenant_scope_access(user, tenant_id)

    try:
        override = await service.archive_override(
            override_id=override_id,
            tenant_id=tenant_id,
        )
        item = _serialize_override(override)
        await db.commit()
        return InstructionOverrideResponse(item=item)
    except Exception as exc:
        await db.rollback()
        raise _map_override_exception(exc) from exc


# ── Deal-level global instruction override endpoints ───────────────────────────

@router.post(
    "/deals/{deal_id}/global-instruction-overrides/draft",
    response_model=InstructionOverrideResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create draft deal-level override (global instruction)",
)
async def create_deal_global_override_draft(
    deal_id: uuid.UUID,
    body: GlobalInstructionOverrideDraftRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    service: InstructionOverrideService = Depends(get_override_service),
) -> InstructionOverrideResponse:
    """
    Create a draft deal-level override for a global instruction.

    Global instructions are universal checks applicable to any
    doc_type within this deal.

    Dry-run apply before saving — patch is validated for applicability to
    the compiled_payload of the base global instruction version.

    Access: project editor/admin.
    """
    deal = await get_scoped_deal(deal_id=deal_id, user=user, db=db)
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor"),
    )

    try:
        override = await service.create_deal_global_override_draft(
            tenant_id=deal.tenant_id,
            deal_id=deal_id,
            global_instruction_version_id=body.global_instruction_version_id,
            patch_ops=body.patch_ops,
            change_summary=body.change_summary,
            created_by=uuid.UUID(str(user.id)),
        )
        item = _serialize_override(override)
        await db.commit()
        return InstructionOverrideResponse(item=item)
    except Exception as exc:
        await db.rollback()
        raise _map_override_exception(exc) from exc


@router.post(
    "/deals/{deal_id}/global-instruction-overrides/{override_id}/validate",
    response_model=InstructionOverrideValidationResponse,
    summary="Validate deal-level override (global instruction)",
)
async def validate_deal_global_override(
    deal_id: uuid.UUID,
    override_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    service: InstructionOverrideService = Depends(get_override_service),
) -> InstructionOverrideValidationResponse:
    """
    Validate global instruction deal override without changing its status.

    Access: project viewer/editor/admin.
    """
    deal = await get_scoped_deal(deal_id=deal_id, user=user, db=db)
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    try:
        result = await service.validate_global_override(
            override_id=override_id,
            tenant_id=deal.tenant_id,
        )
        return InstructionOverrideValidationResponse(
            override_id=str(override_id),
            is_valid=result.get("is_valid", False),
            errors=result.get("errors", []),
            warnings=result.get("warnings", []),
            checks_count=result.get("checks_count"),
            effective_payload=result.get("effective_payload"),
            validation_report=result.get("validation_report"),
        )
    except Exception as exc:
        raise _map_override_exception(exc) from exc


@router.post(
    "/deals/{deal_id}/global-instruction-overrides/{override_id}/activate",
    response_model=InstructionOverrideResponse,
    summary="Activate deal-level override (global instruction)",
)
async def activate_deal_global_override(
    deal_id: uuid.UUID,
    override_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    service: InstructionOverrideService = Depends(get_override_service),
) -> InstructionOverrideResponse:
    """
    Activate deal-level global instruction override: draft → active.

    Cannot activate a stale override.

    Access: project editor/admin.
    """
    deal = await get_scoped_deal(deal_id=deal_id, user=user, db=db)
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor"),
    )

    try:
        override = await service.activate_override(
            override_id=override_id,
            tenant_id=deal.tenant_id,
        )
        item = _serialize_override(override)
        await db.commit()
        return InstructionOverrideResponse(item=item)
    except Exception as exc:
        await db.rollback()
        raise _map_override_exception(exc) from exc


@router.post(
    "/deals/{deal_id}/global-instruction-overrides/{override_id}/archive",
    response_model=InstructionOverrideResponse,
    summary="Archive deal-level override (global instruction)",
)
async def archive_deal_global_override(
    deal_id: uuid.UUID,
    override_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    service: InstructionOverrideService = Depends(get_override_service),
) -> InstructionOverrideResponse:
    """
    Archive deal-level global instruction override.

    Access: project editor/admin.
    """
    deal = await get_scoped_deal(deal_id=deal_id, user=user, db=db)
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor"),
    )

    try:
        override = await service.archive_override(
            override_id=override_id,
            tenant_id=deal.tenant_id,
        )
        item = _serialize_override(override)
        await db.commit()
        return InstructionOverrideResponse(item=item)
    except Exception as exc:
        await db.rollback()
        raise _map_override_exception(exc) from exc


        