# src/api/endpoints/instruction_versions.py

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.schemas.instruction_versions import (
    CloneDraftRequest,
    CreateInstructionDraftRequest,
    InstructionCatalogItem,
    InstructionCatalogResponse,
    InstructionDiffResponse,
    InstructionVersionDetailItem,
    InstructionVersionDetailResponse,
    InstructionVersionItem,
    InstructionVersionListResponse,
    InstructionVersionResponse,
    InstructionVersionValidationResponse,
    PreviewInstructionRequest,
    PreviewInstructionResponse,
    UpdateInstructionDraftRequest,
)
from db.repositories.document_type_instruction_version_repo import (
    DocumentTypeInstructionVersionRepository,
)
from db.session import get_db
from services.instruction_catalog_service import InstructionCatalogService
from services.instruction_editor_service import InstructionEditorService
from services.instruction_compiler import InstructionCompilationError
from services.instruction_publishing_service import (
    DraftValidationError,
    DuplicateInstructionContentError,
    ImmutableVersionError,
    InstructionLifecycleError,
    InstructionPublishingService,
    InstructionVersionNotFoundError,
    InvalidLifecycleTransitionError,
)

from api.concurrency import ensure_if_match, require_if_match, set_response_etag
from api.errors import api_error

router = APIRouter(prefix="/admin", tags=["instruction-versions"])


def require_instruction_admin(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """
    Verify platform-level access to base instruction version management.

    Only users with the superadmin global role can create, edit, publish,
    archive, validate, and diff base instruction versions.
    """
    if user.global_role != "superadmin":
        raise api_error(
            status.HTTP_403_FORBIDDEN,
            "INSTRUCTION_ACCESS_DENIED",
            "Only superadmin can manage base instruction versions.",
        )
    return user


def get_instruction_publishing_service(
    db: AsyncSession = Depends(get_db),
) -> InstructionPublishingService:
    """
    Build the canonical instruction publishing service for the current request.
    """
    return InstructionPublishingService(db)


def get_instruction_catalog_service(
    db: AsyncSession = Depends(get_db),
) -> InstructionCatalogService:
    """
    Build the canonical instruction catalog service for the current request.
    """
    return InstructionCatalogService(db)

def get_instruction_editor_service(
    db: AsyncSession = Depends(get_db),
) -> InstructionEditorService:
    """
    Build the canonical instruction editor service for the current request.
    """
    return InstructionEditorService(db)

def _instruction_version_not_found(version_id: uuid.UUID):
    """
    Build a structured 404 error for a missing instruction version.
    """
    return api_error(
        status.HTTP_404_NOT_FOUND,
        "INSTRUCTION_VERSION_NOT_FOUND",
        f"Instruction version not found: {version_id}",
    )


def _instruction_version_immutable():
    """
    Build a structured 409 error for immutable instruction versions.
    """
    return api_error(
        status.HTTP_409_CONFLICT,
        "INSTRUCTION_VERSION_IMMUTABLE",
        "Published or archived instruction versions cannot be modified.",
    )


def _serialize_version(version) -> InstructionVersionItem:
    return InstructionVersionItem(
        id=str(version.id),
        doc_type_code=version.doc_type_code,
        name=version.name,
        source_format=version.source_format,
        source_sha256=version.source_sha256,
        version_status=version.version_status,
        immutable_content_hash=version.immutable_content_hash,
        validation_report=version.validation_report,
        parent_version_id=str(version.parent_version_id) if version.parent_version_id else None,
        published_at=version.published_at,
        created_by=str(version.created_by) if version.created_by else None,
        change_summary=version.change_summary,
        created_at=getattr(version, "created_at", None),
        updated_at=getattr(version, "updated_at", None),
    )


def _serialize_version_detail(version) -> InstructionVersionDetailItem:
    checks_count = None
    report = getattr(version, "validation_report", None)
    if isinstance(report, dict):
        raw_count = report.get("checks_count")
        if raw_count is not None:
            try:
                checks_count = int(raw_count)
            except (TypeError, ValueError):
                checks_count = None

    return InstructionVersionDetailItem(
        id=str(version.id),
        doc_type_code=version.doc_type_code,
        name=version.name,
        source_format=version.source_format,
        source_sha256=version.source_sha256,
        version_status=version.version_status,
        immutable_content_hash=version.immutable_content_hash,
        validation_report=version.validation_report,
        parent_version_id=str(version.parent_version_id) if version.parent_version_id else None,
        published_at=version.published_at,
        created_by=str(version.created_by) if version.created_by else None,
        change_summary=version.change_summary,
        created_at=getattr(version, "created_at", None),
        updated_at=getattr(version, "updated_at", None),
        source_yaml=version.source_yaml,
        source_path=version.source_path,
        git_commit=version.git_commit,
        semver=version.semver,
        compiled_payload=version.compiled_payload,
        checks_count=checks_count,
    )


def _serialize_catalog_item(item) -> InstructionCatalogItem:
    return InstructionCatalogItem(
        doc_type_code=item.doc_type_code,
        name=item.name,
        category=item.category,
        risk_level=item.risk_level,
        language=item.language,
        jurisdiction=item.jurisdiction,
        is_registry_available=item.is_registry_available,
        total_versions_count=item.total_versions_count,
        draft_versions_count=item.draft_versions_count,
        has_published=item.has_published,
        latest_version_id=item.latest_version_id,
        latest_version_status=item.latest_version_status,
        latest_version_updated_at=item.latest_version_updated_at,
        latest_published_version_id=item.latest_published_version_id,
        latest_published_at=item.latest_published_at,
        latest_published_immutable_content_hash=item.latest_published_immutable_content_hash,
        latest_draft_version_id=item.latest_draft_version_id,
        latest_draft_is_valid=item.latest_draft_is_valid,
        latest_draft_updated_at=item.latest_draft_updated_at,
    )


def _map_lifecycle_exception(exc: Exception):
    """
    Map domain and lifecycle exceptions to a structured API error envelope.

    This keeps the endpoint layer thin and ensures that all lifecycle-related
    errors use the same HTTP contract and response shape.
    """
    if isinstance(exc, InstructionVersionNotFoundError):
        return api_error(
            status.HTTP_404_NOT_FOUND,
            "INSTRUCTION_VERSION_NOT_FOUND",
            str(exc),
        )

    if isinstance(exc, DuplicateInstructionContentError):
        return api_error(
            status.HTTP_409_CONFLICT,
            "INSTRUCTION_DUPLICATE_CONTENT",
            str(exc),
        )

    if isinstance(exc, ImmutableVersionError):
        return api_error(
            status.HTTP_409_CONFLICT,
            "INSTRUCTION_VERSION_IMMUTABLE",
            str(exc),
        )

    if isinstance(exc, InvalidLifecycleTransitionError):
        return api_error(
            status.HTTP_409_CONFLICT,
            "INSTRUCTION_INVALID_LIFECYCLE_TRANSITION",
            str(exc),
        )

    if isinstance(exc, DraftValidationError):
        return api_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "INSTRUCTION_DRAFT_VALIDATION_FAILED",
            str(exc),
        )

    if isinstance(exc, InstructionCompilationError):
        return api_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "INSTRUCTION_COMPILATION_FAILED",
            str(exc),
        )

    if isinstance(exc, InstructionLifecycleError):
        return api_error(
            status.HTTP_409_CONFLICT,
            "INSTRUCTION_LIFECYCLE_ERROR",
            str(exc),
        )

    return api_error(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "INSTRUCTION_INTERNAL_ERROR",
        "Internal error.",
    )


@router.get(
    "/instructions/doc-types",
    response_model=InstructionCatalogResponse,
)
async def list_instruction_catalog(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_instruction_admin),
    service: InstructionCatalogService = Depends(get_instruction_catalog_service),
) -> InstructionCatalogResponse:
    """
    Return the catalog of document-type instruction families available to admins.
    """
    _ = db
    _ = user
    items = await service.list_doc_type_catalog()
    return InstructionCatalogResponse(
        items=[_serialize_catalog_item(x) for x in items]
    )


@router.get(
    "/instructions/doc-types/{doc_type_code}/versions",
    response_model=InstructionVersionListResponse,
)
async def list_instruction_versions_for_doc_type(
    doc_type_code: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_instruction_admin),
) -> InstructionVersionListResponse:
    """
    Return all instruction versions for a single document type code.
    """
    _ = user
    repo = DocumentTypeInstructionVersionRepository(db)
    versions = await repo.list_by_doc_type_code(doc_type_code)
    return InstructionVersionListResponse(
        doc_type_code=doc_type_code,
        items=[_serialize_version(v) for v in versions],
    )


@router.get(
    "/instruction-versions/{version_id}",
    response_model=InstructionVersionDetailResponse,
)
async def get_instruction_version(
    response: Response,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_instruction_admin),
) -> InstructionVersionDetailResponse:
    """
    Return a single instruction version with a concurrency ETag header.

    The ETag is derived from the current version state and is intended to be
    reused by the frontend in subsequent draft update requests via If-Match.
    """
    _ = user
    repo = DocumentTypeInstructionVersionRepository(db)
    version = await repo.get_by_id(version_id)
    if version is None:
        raise _instruction_version_not_found(version_id)

    set_response_etag(response, getattr(version, "updated_at", None))
    return InstructionVersionDetailResponse(item=_serialize_version_detail(version))


@router.post(
    "/instructions/doc-types/{doc_type_code}/drafts",
    response_model=InstructionVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_instruction_draft(
    doc_type_code: str,
    body: CreateInstructionDraftRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_instruction_admin),
    service: InstructionPublishingService = Depends(get_instruction_publishing_service),
) -> InstructionVersionResponse:
    """
    Create a new draft instruction version for the given document type.
    """
    try:
        version = await service.create_draft(
            doc_type_code=doc_type_code,
            source=body.source_yaml,
            name=body.name,
            source_path=body.source_path,
            git_commit=body.git_commit,
            semver=body.semver,
            created_by=uuid.UUID(user.id),
            change_summary=body.change_summary,
            parent_version_id=body.parent_version_id,
        )
        await db.commit()
        await db.refresh(version)
        item = _serialize_version(version)
        return InstructionVersionResponse(item=item)
    except Exception as exc:
        await db.rollback()
        raise _map_lifecycle_exception(exc) from exc


@router.patch(
    "/instruction-versions/{version_id}",
    response_model=InstructionVersionResponse,
)
async def update_instruction_draft(
    request: Request,
    response: Response,
    version_id: uuid.UUID,
    body: UpdateInstructionDraftRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_instruction_admin),
    service: InstructionPublishingService = Depends(get_instruction_publishing_service),
) -> InstructionVersionResponse:
    """
    Update an existing draft instruction version using optimistic concurrency.

    The client must provide If-Match with the ETag previously returned by the
    detail endpoint. Missing preconditions fail with 428, and stale ETags fail
    with 412.
    """
    _ = user
    repo = DocumentTypeInstructionVersionRepository(db)
    current_version = await repo.get_by_id(version_id)
    if current_version is None:
        raise _instruction_version_not_found(version_id)

    if_match = require_if_match(request)
    ensure_if_match(getattr(current_version, "updated_at", None), if_match)

    try:
        version = await service.update_draft(
            version_id=version_id,
            source=body.source_yaml,
            name=body.name,
            source_path=body.source_path,
            git_commit=body.git_commit,
            semver=body.semver,
            change_summary=body.change_summary,
        )
        await db.commit()
        await db.refresh(version)
        set_response_etag(response, getattr(version, "updated_at", None))
        item = _serialize_version(version)
        return InstructionVersionResponse(item=item)
    except Exception as exc:
        await db.rollback()
        raise _map_lifecycle_exception(exc) from exc


@router.post(
    "/instruction-versions/{version_id}/validate",
    response_model=InstructionVersionValidationResponse,
)
async def validate_instruction_draft(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_instruction_admin),
    service: InstructionPublishingService = Depends(get_instruction_publishing_service),
) -> InstructionVersionValidationResponse:
    """
    Validate a draft instruction version and persist its validation artifacts.
    """
    _ = user
    repo = DocumentTypeInstructionVersionRepository(db)

    try:
        compiled = await service.validate_draft(version_id=version_id)
        version = await repo.get_by_id(version_id)
        if version is None:
            raise InstructionVersionNotFoundError(
                f"Instruction version not found after validation: {version_id}"
            )

        item = _serialize_version(version)
        response = InstructionVersionValidationResponse(
            item=item,
            is_valid=compiled.is_valid,
            checks_count=compiled.checks_count,
            validation_report=compiled.validation_report,
        )
        await db.commit()
        return response
    except Exception as exc:
        await db.rollback()
        raise _map_lifecycle_exception(exc) from exc


@router.post(
    "/instruction-versions/{version_id}/publish",
    response_model=InstructionVersionResponse,
)
async def publish_instruction_draft(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_instruction_admin),
    service: InstructionPublishingService = Depends(get_instruction_publishing_service),
) -> InstructionVersionResponse:
    """
    Publish a validated draft instruction version.
    """
    _ = user
    try:
        version = await service.publish_draft(version_id=version_id)
        item = _serialize_version(version)
        await db.commit()
        return InstructionVersionResponse(item=item)
    except Exception as exc:
        await db.rollback()
        raise _map_lifecycle_exception(exc) from exc


@router.post(
    "/instruction-versions/{version_id}/archive",
    response_model=InstructionVersionResponse,
)
async def archive_instruction_version(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_instruction_admin),
    service: InstructionPublishingService = Depends(get_instruction_publishing_service),
) -> InstructionVersionResponse:
    """
    Archive an existing instruction version through the canonical lifecycle service.
    """
    _ = user
    try:
        version = await service.archive_version(version_id=version_id)
        item = _serialize_version(version)
        await db.commit()
        return InstructionVersionResponse(item=item)
    except Exception as exc:
        await db.rollback()
        raise _map_lifecycle_exception(exc) from exc

  
@router.post(
    "/instruction-versions/{version_id}/clone-draft",
    response_model=InstructionVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def clone_instruction_draft(
    version_id: uuid.UUID,
    body: CloneDraftRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_instruction_admin),
    service: InstructionEditorService = Depends(get_instruction_editor_service),
) -> InstructionVersionResponse:
    """
    Create a new editable draft cloned from an existing instruction version.

    This is the canonical endpoint for the "edit published" flow, where the UI
    requests a new mutable draft derived from an immutable published version.
    """
    _ = user
    try:
        version = await service.clone_draft(
            source_version_id=version_id,
            change_summary=body.change_summary,
            created_by=uuid.UUID(user.id),
        )
        await db.commit()
        await db.refresh(version)
        item = _serialize_version(version)
        return InstructionVersionResponse(item=item)
    except Exception as exc:
        await db.rollback()
        raise _map_lifecycle_exception(exc) from exc


@router.post(
    "/instructions/doc-types/{doc_type_code}/preview",
    response_model=PreviewInstructionResponse,
)
async def preview_instruction(
    doc_type_code: str,
    body: PreviewInstructionRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_instruction_admin),
    service: InstructionEditorService = Depends(get_instruction_editor_service),
) -> PreviewInstructionResponse:
    """
    Compile and validate instruction YAML without persisting a draft version.

    The endpoint returns validation diagnostics, compiled payload metadata,
    trigger usage, source hash, and duplicate-content hints for the editor UI.
    """
    _ = db
    _ = user
    try:
        result = await service.preview(
            doc_type_code=doc_type_code,
            source_yaml=body.source_yaml,
        )
        return PreviewInstructionResponse(
            is_valid=result.is_valid,
            checks_count=result.checks_count,
            triggers_used=result.triggers_used,
            diagnostics=result.diagnostics,
            validation_report=result.validation_report,
            compiled_payload=result.compiled_payload,
            source_sha256=result.source_sha256,
            already_exists=result.already_exists,
            existing_version_id=result.existing_version_id,
        )
    except Exception as exc:
        raise _map_lifecycle_exception(exc) from exc


@router.get(
    "/instruction-versions/{version_id}/diff",
    response_model=InstructionDiffResponse,
)
async def diff_instruction_versions(
    version_id: uuid.UUID,
    against: uuid.UUID = Query(..., description="ID instruction version to compare against"),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_instruction_admin),
    service: InstructionEditorService = Depends(get_instruction_editor_service),
) -> InstructionDiffResponse:
    """
    Return a unified diff between the source YAML of two instruction versions.

    The response includes unified diff text, equality status, and source hashes
    for both compared versions.
    """
    _ = db
    _ = user
    try:
        result = await service.diff(
            from_version_id=version_id,
            to_version_id=against,
        )
        return InstructionDiffResponse(
            from_version_id=result.from_version_id,
            to_version_id=result.to_version_id,
            from_source_sha256=result.from_source_sha256,
            to_source_sha256=result.to_source_sha256,
            are_identical=result.are_identical,
            unified_diff=result.unified_diff,
        )
    except Exception as exc:
        raise _map_lifecycle_exception(exc) from exc
    
    
