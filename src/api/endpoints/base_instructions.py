# src/api/endpoints/base_instructions.py

"""
Read-only facade endpoints для базовых platform instructions.

Доступен любому аутентифицированному пользователю (tenant_admin, member).
Superadmin тоже может использовать эти endpoints.

Используют те же services и repos, что и superadmin-endpoints,
но без write-доступа и с чистым ACL — не ходим в /admin/*.

Endpoints:
    GET /api/v1/instructions/base/global-checks
    GET /api/v1/instructions/base/global-checks/{instruction_code}/versions
    GET /api/v1/instructions/base/global-checks/versions/{version_id}
    GET /api/v1/instructions/base/doc-types
    GET /api/v1/instructions/base/doc-types/{doc_type_code}/versions
    GET /api/v1/instructions/base/doc-types/versions/{version_id}
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.errors import api_error
from api.schemas.global_instruction_versions import (
    GlobalInstructionCatalogItem,
    GlobalInstructionCatalogResponse,
    GlobalInstructionVersionDetailItem,
    GlobalInstructionVersionDetailResponse,
    GlobalInstructionVersionItem,
    GlobalInstructionVersionListResponse,
)
from api.schemas.instruction_versions import (
    InstructionCatalogItem,
    InstructionCatalogResponse,
    InstructionVersionDetailItem,
    InstructionVersionDetailResponse,
    InstructionVersionItem,
    InstructionVersionListResponse,
)
from db.repositories.document_type_instruction_version_repo import (
    DocumentTypeInstructionVersionRepository,
)
from db.repositories.global_instruction_version_repo import (
    GlobalInstructionVersionRepository,
)
from db.session import get_db
from services.global_instruction_catalog_service import GlobalInstructionCatalogService
from services.instruction_catalog_service import InstructionCatalogService
from fastapi import status

router = APIRouter(
    prefix="/instructions/base",
    tags=["base-instructions"],
)


# ── Auth ───────────────────────────────────────────────────────────────────────

def require_authenticated(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Любой аутентифицированный пользователь."""
    return user


# ── DI ─────────────────────────────────────────────────────────────────────────

def get_global_catalog_service(
    db: AsyncSession = Depends(get_db),
) -> GlobalInstructionCatalogService:
    return GlobalInstructionCatalogService(db)


def get_doc_type_catalog_service(
    db: AsyncSession = Depends(get_db),
) -> InstructionCatalogService:
    return InstructionCatalogService(db)


# ── Serializers ────────────────────────────────────────────────────────────────

def _serialize_global_catalog_item(item) -> GlobalInstructionCatalogItem:
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


def _serialize_global_version(version) -> GlobalInstructionVersionItem:
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


def _serialize_global_version_detail(version) -> GlobalInstructionVersionDetailItem:
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


def _serialize_doc_type_catalog_item(item) -> InstructionCatalogItem:
    return InstructionCatalogItem(
        doc_type_code=item.doc_type_code,
        name=item.name,
        category=item.category,
        parent=item.parent,
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
        latest_published_immutable_content_hash=(
            item.latest_published_immutable_content_hash
        ),
        latest_draft_version_id=item.latest_draft_version_id,
        latest_draft_is_valid=item.latest_draft_is_valid,
        latest_draft_updated_at=item.latest_draft_updated_at,
    )


def _serialize_doc_type_version(version) -> InstructionVersionItem:
    return InstructionVersionItem(
        id=str(version.id),
        doc_type_code=version.doc_type_code,
        name=version.name,
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


def _serialize_doc_type_version_detail(version) -> InstructionVersionDetailItem:
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
        checks_count=checks_count,
    )


# ── Global checks endpoints ────────────────────────────────────────────────────

@router.get(
    "/global-checks",
    response_model=GlobalInstructionCatalogResponse,
    summary="Read-only каталог базовых global instructions",
)
async def list_base_global_checks(
    user: CurrentUser = Depends(require_authenticated),
    service: GlobalInstructionCatalogService = Depends(get_global_catalog_service),
) -> GlobalInstructionCatalogResponse:
    """
    Каталог базовых global instructions платформы.
    Read-only. Доступен tenant_admin и member.
    """
    _ = user
    items = await service.list_catalog()
    return GlobalInstructionCatalogResponse(
        items=[_serialize_global_catalog_item(item) for item in items]
    )


@router.get(
    "/global-checks/{instruction_code}/versions",
    response_model=GlobalInstructionVersionListResponse,
    summary="Read-only список версий базовой global instruction",
)
async def list_base_global_check_versions(
    instruction_code: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_authenticated),
) -> GlobalInstructionVersionListResponse:
    """
    Список версий одной базовой global instruction.
    Read-only. Tenant admin видит их при просмотре инструкции.
    """
    _ = user
    repo = GlobalInstructionVersionRepository(db)
    versions = await repo.list_by_instruction_code(instruction_code)
    return GlobalInstructionVersionListResponse(
        instruction_code=instruction_code,
        items=[_serialize_global_version(v) for v in versions],
    )


@router.get(
    "/global-checks/versions/{version_id}",
    response_model=GlobalInstructionVersionDetailResponse,
    summary="Read-only детали версии базовой global instruction",
)
async def get_base_global_check_version_detail(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_authenticated),
) -> GlobalInstructionVersionDetailResponse:
    """
    Детали конкретной версии global instruction включая source_yaml
    и compiled_payload. Read-only — без ETag, без write-доступа.
    """
    _ = user
    repo = GlobalInstructionVersionRepository(db)
    version = await repo.get_by_id(version_id)
    if version is None:
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            "BASE_GLOBAL_VERSION_NOT_FOUND",
            f"Global instruction version not found: {version_id}",
        )
    return GlobalInstructionVersionDetailResponse(
        item=_serialize_global_version_detail(version)
    )


# ── Doc-type endpoints ─────────────────────────────────────────────────────────

@router.get(
    "/doc-types",
    response_model=InstructionCatalogResponse,
    summary="Read-only каталог базовых doc-type instructions",
)
async def list_base_doc_types(
    user: CurrentUser = Depends(require_authenticated),
    service: InstructionCatalogService = Depends(get_doc_type_catalog_service),
) -> InstructionCatalogResponse:
    """
    Каталог базовых doc-type instructions платформы.
    Read-only. Доступен tenant_admin и member.
    """
    _ = user
    items = await service.list_doc_type_catalog()
    return InstructionCatalogResponse(
        items=[_serialize_doc_type_catalog_item(item) for item in items]
    )


@router.get(
    "/doc-types/{doc_type_code}/versions",
    response_model=InstructionVersionListResponse,
    summary="Read-only список версий базовой doc-type instruction",
)
async def list_base_doc_type_versions(
    doc_type_code: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_authenticated),
) -> InstructionVersionListResponse:
    """
    Список версий одной базовой doc-type instruction.
    Read-only. Tenant admin видит их при просмотре инструкции.
    """
    _ = user
    repo = DocumentTypeInstructionVersionRepository(db)
    versions = await repo.list_by_doc_type_code(doc_type_code)
    return InstructionVersionListResponse(
        doc_type_code=doc_type_code,
        items=[_serialize_doc_type_version(v) for v in versions],
    )


@router.get(
    "/doc-types/versions/{version_id}",
    response_model=InstructionVersionDetailResponse,
    summary="Read-only детали версии базовой doc-type instruction",
)
async def get_base_doc_type_version_detail(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_authenticated),
) -> InstructionVersionDetailResponse:
    """
    Детали конкретной версии doc-type instruction включая source_yaml
    и compiled_payload. Read-only — без ETag, без write-доступа.
    """
    _ = user
    repo = DocumentTypeInstructionVersionRepository(db)
    version = await repo.get_by_id(version_id)
    if version is None:
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            "BASE_DOC_TYPE_VERSION_NOT_FOUND",
            f"Doc-type instruction version not found: {version_id}",
        )
    return InstructionVersionDetailResponse(
        item=_serialize_doc_type_version_detail(version)
    )


