# src/api/endpoints/global_instruction_versions.py

"""
Global instruction version endpoints.
Зеркало instruction_versions.py под prefix /admin/instructions/global-checks.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.concurrency import ensure_if_match, require_if_match, set_response_etag
from api.deps.auth import CurrentUser, get_current_user
from api.errors import api_error
from api.schemas.global_instruction_versions import (
    CloneGlobalDraftRequest,
    CreateGlobalInstructionDraftRequest,
    GlobalInstructionCatalogItem,
    GlobalInstructionCatalogResponse,
    GlobalInstructionDiffResponse,
    GlobalInstructionVersionDetailItem,
    GlobalInstructionVersionDetailResponse,
    GlobalInstructionVersionItem,
    GlobalInstructionVersionListResponse,
    GlobalInstructionVersionResponse,
    GlobalInstructionVersionValidationResponse,
    PreviewGlobalInstructionRequest,
    PreviewGlobalInstructionResponse,
    UpdateGlobalInstructionDraftRequest,
)
from db.repositories.global_instruction_version_repo import (
    GlobalInstructionVersionRepository,
)
from db.session import get_db
from services.global_instruction_catalog_service import GlobalInstructionCatalogService
from services.global_instruction_editor_service import GlobalInstructionEditorService
from services.global_instruction_publishing_service import (
    GlobalInstructionDraftValidationError,
    GlobalInstructionDuplicateContentError,
    GlobalInstructionImmutableError,
    GlobalInstructionInvalidTransitionError,
    GlobalInstructionLifecycleError,
    GlobalInstructionNotFoundError,
    GlobalInstructionPublishingService,
)
from services.instruction_compiler import InstructionCompilationError

router = APIRouter(prefix="/admin", tags=["global-instruction-versions"])


# ── Auth ───────────────────────────────────────────────────────────

def require_global_instruction_admin(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    if user.global_role != "superadmin":
        raise api_error(
            status.HTTP_403_FORBIDDEN,
            "GLOBAL_INSTRUCTION_ACCESS_DENIED",
            "Only superadmin can manage global instruction versions.",
        )
    return user


# ── DI ─────────────────────────────────────────────────────────────

def get_publishing_service(
    db: AsyncSession = Depends(get_db),
) -> GlobalInstructionPublishingService:
    return GlobalInstructionPublishingService(db)


def get_catalog_service(
    db: AsyncSession = Depends(get_db),
) -> GlobalInstructionCatalogService:
    return GlobalInstructionCatalogService(db)


def get_editor_service(
    db: AsyncSession = Depends(get_db),
) -> GlobalInstructionEditorService:
    return GlobalInstructionEditorService(db)


# ── Serializers ────────────────────────────────────────────────────

def _serialize_version(version) -> GlobalInstructionVersionItem:
    return GlobalInstructionVersionItem(
        id=str(version.id),
        instruction_code=version.instruction_code,
        name=version.name,
        group=version.group,
        source_format=version.source_format,
        source_sha256=version.source_sha256,
        version_status=version.version_status,
        immutable_content_hash=version.immutable_content_hash,
        validation_report=version.validation_report,
        parent_version_id=(
            str(version.parent_version_id) if version.parent_version_id else None
        ),
        published_at=version.published_at,
        created_by=str(version.created_by) if version.created_by else None,
        change_summary=version.change_summary,
        created_at=getattr(version, "created_at", None),
        updated_at=getattr(version, "updated_at", None),
    )


def _serialize_version_detail(version) -> GlobalInstructionVersionDetailItem:
    return GlobalInstructionVersionDetailItem(
        id=str(version.id),
        instruction_code=version.instruction_code,
        name=version.name,
        group=version.group,
        source_format=version.source_format,
        source_sha256=version.source_sha256,
        version_status=version.version_status,
        immutable_content_hash=version.immutable_content_hash,
        validation_report=version.validation_report,
        parent_version_id=(
            str(version.parent_version_id) if version.parent_version_id else None
        ),
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
    )


def _serialize_catalog_item(item) -> GlobalInstructionCatalogItem:
    return GlobalInstructionCatalogItem(
        instruction_code=item.instruction_code,
        name=item.name,
        group=item.group,
        total_versions_count=item.total_versions_count,
        draft_versions_count=item.draft_versions_count,
        has_published=item.has_published,
        latest_version_id=item.latest_version_id,
        latest_version_status=item.latest_version_status,
        latest_version_updated_at=item.latest_version_updated_at,
        latest_published_version_id=item.latest_published_version_id,
        latest_published_at=item.latest_published_at,
        latest_published_immutable_content_hash=(
            item.latest_published_immutable_content_hash
        ),
        latest_draft_version_id=item.latest_draft_version_id,
        latest_draft_is_valid=item.latest_draft_is_valid,
        latest_draft_updated_at=item.latest_draft_updated_at,
    )


def _map_exception(exc: Exception):
    if isinstance(exc, GlobalInstructionNotFoundError):
        return api_error(
            status.HTTP_404_NOT_FOUND,
            "GLOBAL_INSTRUCTION_VERSION_NOT_FOUND",
            str(exc),
        )
    if isinstance(exc, GlobalInstructionDuplicateContentError):
        return api_error(
            status.HTTP_409_CONFLICT,
            "GLOBAL_INSTRUCTION_DUPLICATE_CONTENT",
            str(exc),
        )
    if isinstance(exc, GlobalInstructionImmutableError):
        return api_error(
            status.HTTP_409_CONFLICT,
            "GLOBAL_INSTRUCTION_VERSION_IMMUTABLE",
            str(exc),
        )
    if isinstance(exc, GlobalInstructionInvalidTransitionError):
        return api_error(
            status.HTTP_409_CONFLICT,
            "GLOBAL_INSTRUCTION_INVALID_LIFECYCLE_TRANSITION",
            str(exc),
        )
    if isinstance(exc, GlobalInstructionDraftValidationError):
        return api_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "GLOBAL_INSTRUCTION_DRAFT_VALIDATION_FAILED",
            str(exc),
        )
    if isinstance(exc, InstructionCompilationError):
        return api_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "GLOBAL_INSTRUCTION_COMPILATION_FAILED",
            str(exc),
        )
    if isinstance(exc, GlobalInstructionLifecycleError):
        return api_error(
            status.HTTP_409_CONFLICT,
            "GLOBAL_INSTRUCTION_LIFECYCLE_ERROR",
            str(exc),
        )
    return api_error(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "GLOBAL_INSTRUCTION_INTERNAL_ERROR",
        "Internal error.",
    )


# ── Endpoints ──────────────────────────────────────────────────────

@router.get(
    "/instructions/global-checks",
    response_model=GlobalInstructionCatalogResponse,
)
async def list_global_instruction_catalog(
    user: CurrentUser = Depends(require_global_instruction_admin),
    service: GlobalInstructionCatalogService = Depends(get_catalog_service),
) -> GlobalInstructionCatalogResponse:
    """Каталог global instruction families, сгруппированных по group."""
    _ = user
    items = await service.list_catalog()
    return GlobalInstructionCatalogResponse(
        items=[_serialize_catalog_item(x) for x in items]
    )


@router.get(
    "/instructions/global-checks/{instruction_code}/versions",
    response_model=GlobalInstructionVersionListResponse,
)
async def list_global_instruction_versions(
    instruction_code: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_global_instruction_admin),
) -> GlobalInstructionVersionListResponse:
    """Все версии для одного instruction_code."""
    _ = user
    repo = GlobalInstructionVersionRepository(db)
    versions = await repo.list_by_instruction_code(instruction_code)
    return GlobalInstructionVersionListResponse(
        instruction_code=instruction_code,
        items=[_serialize_version(v) for v in versions],
    )


@router.get(
    "/global-instruction-versions/{version_id}",
    response_model=GlobalInstructionVersionDetailResponse,
)
async def get_global_instruction_version(
    response: Response,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_global_instruction_admin),
) -> GlobalInstructionVersionDetailResponse:
    """
    Детали версии + ETag header для optimistic concurrency.
    ETag передаётся в If-Match при последующих PATCH.
    """
    _ = user
    repo = GlobalInstructionVersionRepository(db)
    version = await repo.get_by_id(version_id)
    if version is None:
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            "GLOBAL_INSTRUCTION_VERSION_NOT_FOUND",
            f"Global instruction version not found: {version_id}",
        )
    set_response_etag(response, getattr(version, "updated_at", None))
    return GlobalInstructionVersionDetailResponse(
        item=_serialize_version_detail(version)
    )


@router.post(
    "/instructions/global-checks/{instruction_code}/drafts",
    response_model=GlobalInstructionVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_global_instruction_draft(
    instruction_code: str,
    body: CreateGlobalInstructionDraftRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_global_instruction_admin),
    service: GlobalInstructionPublishingService = Depends(get_publishing_service),
) -> GlobalInstructionVersionResponse:
    """Создать новый draft global instruction."""
    try:
        version = await service.create_draft(
            instruction_code=instruction_code,
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
        return GlobalInstructionVersionResponse(item=_serialize_version(version))
    except Exception as exc:
        await db.rollback()
        raise _map_exception(exc) from exc


@router.patch(
    "/global-instruction-versions/{version_id}",
    response_model=GlobalInstructionVersionResponse,
)
async def update_global_instruction_draft(
    request: Request,
    response: Response,
    version_id: uuid.UUID,
    body: UpdateGlobalInstructionDraftRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_global_instruction_admin),
    service: GlobalInstructionPublishingService = Depends(get_publishing_service),
) -> GlobalInstructionVersionResponse:
    """
    Обновить draft. Требует If-Match header.
    428 если нет If-Match, 412 если ETag устарел.
    """
    _ = user
    repo = GlobalInstructionVersionRepository(db)
    current = await repo.get_by_id(version_id)
    if current is None:
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            "GLOBAL_INSTRUCTION_VERSION_NOT_FOUND",
            f"Global instruction version not found: {version_id}",
        )

    if_match = require_if_match(request)
    ensure_if_match(getattr(current, "updated_at", None), if_match)

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
        return GlobalInstructionVersionResponse(item=_serialize_version(version))
    except Exception as exc:
        await db.rollback()
        raise _map_exception(exc) from exc


@router.post(
    "/global-instruction-versions/{version_id}/validate",
    response_model=GlobalInstructionVersionValidationResponse,
)
async def validate_global_instruction_draft(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_global_instruction_admin),
    service: GlobalInstructionPublishingService = Depends(get_publishing_service),
) -> GlobalInstructionVersionValidationResponse:
    """Валидировать draft и сохранить validation artifacts."""
    _ = user
    repo = GlobalInstructionVersionRepository(db)
    try:
        compiled = await service.validate_draft(version_id=version_id)
        version = await repo.get_by_id(version_id)
        if version is None:
            raise GlobalInstructionNotFoundError(
                f"Version not found after validation: {version_id}"
            )
        await db.commit()
        return GlobalInstructionVersionValidationResponse(
            item=_serialize_version(version),
            is_valid=compiled.is_valid,
            validation_report=compiled.validation_report,
        )
    except Exception as exc:
        await db.rollback()
        raise _map_exception(exc) from exc


@router.post(
    "/global-instruction-versions/{version_id}/publish",
    response_model=GlobalInstructionVersionResponse,
)
async def publish_global_instruction_draft(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_global_instruction_admin),
    service: GlobalInstructionPublishingService = Depends(get_publishing_service),
) -> GlobalInstructionVersionResponse:
    """Опубликовать validated draft."""
    _ = user
    try:
        version = await service.publish_draft(version_id=version_id)
        await db.commit()
        return GlobalInstructionVersionResponse(item=_serialize_version(version))
    except Exception as exc:
        await db.rollback()
        raise _map_exception(exc) from exc


@router.post(
    "/global-instruction-versions/{version_id}/archive",
    response_model=GlobalInstructionVersionResponse,
)
async def archive_global_instruction_version(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_global_instruction_admin),
    service: GlobalInstructionPublishingService = Depends(get_publishing_service),
) -> GlobalInstructionVersionResponse:
    """Архивировать версию."""
    _ = user
    try:
        version = await service.archive_version(version_id=version_id)
        await db.commit()
        return GlobalInstructionVersionResponse(item=_serialize_version(version))
    except Exception as exc:
        await db.rollback()
        raise _map_exception(exc) from exc


@router.post(
    "/global-instruction-versions/{version_id}/clone-draft",
    response_model=GlobalInstructionVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def clone_global_instruction_draft(
    version_id: uuid.UUID,
    body: CloneGlobalDraftRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_global_instruction_admin),
    service: GlobalInstructionEditorService = Depends(get_editor_service),
) -> GlobalInstructionVersionResponse:
    """
    Создать новый draft на основе существующей версии.
    Canonical "edit published" flow.
    """
    try:
        version = await service.clone_draft(
            source_version_id=version_id,
            change_summary=body.change_summary,
            created_by=uuid.UUID(user.id),
        )
        await db.commit()
        await db.refresh(version)
        return GlobalInstructionVersionResponse(item=_serialize_version(version))
    except Exception as exc:
        await db.rollback()
        raise _map_exception(exc) from exc


@router.post(
    "/instructions/global-checks/{instruction_code}/preview",
    response_model=PreviewGlobalInstructionResponse,
)
async def preview_global_instruction(
    instruction_code: str,
    body: PreviewGlobalInstructionRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_global_instruction_admin),
    service: GlobalInstructionEditorService = Depends(get_editor_service),
) -> PreviewGlobalInstructionResponse:
    """Preview YAML без сохранения в БД."""
    _ = db
    _ = user
    try:
        result = await service.preview(
            instruction_code=instruction_code,
            source_yaml=body.source_yaml,
        )
        return PreviewGlobalInstructionResponse(
            is_valid=result.is_valid,
            instruction_code=result.instruction_code,
            group=result.group,
            diagnostics=result.diagnostics,
            validation_report=result.validation_report,
            compiled_payload=result.compiled_payload,
            source_sha256=result.source_sha256,
            already_exists=result.already_exists,
            existing_version_id=result.existing_version_id,
        )
    except Exception as exc:
        raise _map_exception(exc) from exc


@router.get(
    "/global-instruction-versions/{version_id}/diff",
    response_model=GlobalInstructionDiffResponse,
)
async def diff_global_instruction_versions(
    version_id: uuid.UUID,
    against: uuid.UUID = Query(
        ...,
        description="ID версии для сравнения"
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_global_instruction_admin),
    service: GlobalInstructionEditorService = Depends(get_editor_service),
) -> GlobalInstructionDiffResponse:
    """Unified diff между source YAML двух версий."""
    _ = db
    _ = user
    try:
        result = await service.diff(
            from_version_id=version_id,
            to_version_id=against,
        )
        return GlobalInstructionDiffResponse(
            from_version_id=result.from_version_id,
            to_version_id=result.to_version_id,
            from_source_sha256=result.from_source_sha256,
            to_source_sha256=result.to_source_sha256,
            are_identical=result.are_identical,
            unified_diff=result.unified_diff,
        )
    except Exception as exc:
        raise _map_exception(exc) from exc


    