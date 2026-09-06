# src/api/endpoints/playbooks.py

"""
Endpoints for working with playbooks (Playbook / PlaybookVersion).

What this file does:
- Exposes global checks and bundles catalog for the playbook builder;
- Manages logical playbooks (PlaybookLine) and their line items;
- Creates, reads, updates, and publishes PlaybookVersions;
- Provides a thin HTTP layer on top of playbook repository/service domain.

Architectural role:
- The API layer does not store compiler domain logic within itself;
- Uses PlaybookRepository for persistence;
- Uses PlaybookPublishingService for publish/archive actions;
- Uses PlaybookVersionDiffService for diff actions;
- Validates instruction_code for canonical wiring of line items
  via services.playbooks.line_items and the global checks catalog.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.concurrency import ensure_if_match, require_if_match, set_response_etag
from api.errors import api_error

from api.schemas.playbooks import (
    BundleInfo,
    GlobalCheckInfo,
    PlaybookCreateRequest,
    PlaybookCreateResponse,
    PlaybookLineCreate,
    PlaybookLineDetail,
    PlaybookLineItemPayload,
    PlaybookLineShort,
    PlaybookTopicInfo,
    PlaybookVersionDetail,
    PlaybookVersionShort,
    PlaybookDraftUpdateRequest,
    PlaybookVersionDiffResponse,
)
from services.playbooks.publishing import (
    PlaybookPublishingService,
    PublishedVersionImmutableError,
)
from core.playbooks.compiler import (
    BUNDLES_DIR,
    BundleConfig,
    build_compiled_checks,
)
from services.global_checks_db_loader import (
    load_global_checks_from_db,
    load_global_checks_with_refs_from_db,
)
from db.repositories.playbook_repo import PlaybookRepository
from db.session import get_db
from services.playbooks.catalog import load_global_checks_catalog_from_db

from core.constants import PlaybookStatus
from services.playbooks.diff import (
    PlaybookVersionDiffService,
    PlaybookDiffError,
)
from services.playbooks.line_items import (
    PlaybookLineItemValidationError,
    extract_unique_instruction_codes_from_items,
    validate_instruction_codes_from_db,
    validate_line_item_payloads_from_db,
)

router = APIRouter(
    prefix="/playbooks",
    tags=["playbooks"],
)

def _playbook_not_found(playbook_id: uuid.UUID):
    return api_error(
        status.HTTP_404_NOT_FOUND,
        "PLAYBOOK_NOT_FOUND",
        f"Playbook not found: {playbook_id}",
    )


def _playbook_version_not_found(version_id: uuid.UUID):
    return api_error(
        status.HTTP_404_NOT_FOUND,
        "PLAYBOOK_VERSION_NOT_FOUND",
        f"Playbook version not found: {version_id}",
    )


def _playbook_line_not_found(line_id: uuid.UUID):
    return api_error(
        status.HTTP_404_NOT_FOUND,
        "PLAYBOOK_LINE_NOT_FOUND",
        f"Playbook line not found: {line_id}",
    )


def _published_version_immutable():
    return api_error(
        status.HTTP_409_CONFLICT,
        "PLAYBOOK_VERSION_IMMUTABLE",
        "Published version cannot be modified.",
    )

async def require_playbook_admin(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """
    Validate permissions to manage playbook templates.

    Allowed: superadmin and tenant_admin.
    Scope isolation is performed at the endpoint level:
    - superadmin works exclusively with platform playbooks
    - tenant_admin works with playbooks of their tenant only
    """
    if user.global_role not in ("superadmin", "tenant_admin"):
        raise api_error(
            status.HTTP_403_FORBIDDEN,
            "PLAYBOOK_ACCESS_DENIED",
            "Not enough permissions to manage playbook templates.",
        )
    return user


def _resolve_write_tenant_id(user: CurrentUser) -> uuid.UUID | None:
    """
    Resolve tenant_id for write operations (create/update/publish/archive/delete).

    Rules:
    - superadmin → works with platform playbooks (tenant_id = None)
    - tenant_admin → works only with their own tenant (tenant_id = user.tenant_id)
    """
    if user.global_role == "superadmin":
        return None
    # tenant_admin
    if user.tenant_id is None:
        raise api_error(
            status.HTTP_403_FORBIDDEN,
            "PLAYBOOK_TENANT_REQUIRED",
            "tenant_admin must have tenant_id to manage playbooks.",
        )
    return uuid.UUID(str(user.tenant_id))


def _check_can_modify_playbook(user: CurrentUser, playbook_tenant_id: uuid.UUID | None) -> None:
    """
    Validate permissions to modify (edit/delete/publish/archive) a specific playbook.

    Rules:
    - superadmin → can modify any playbook
    - tenant_admin → can modify their tenant scope only
    """
    if user.global_role == "superadmin":
        return

    # tenant_admin
    if playbook_tenant_id is None:
        raise api_error(
            status.HTTP_403_FORBIDDEN,
            "PLAYBOOK_PLATFORM_READONLY",
            "Platform playbooks are read-only for tenant admins.",
        )

    if user.tenant_id is None or str(playbook_tenant_id) != str(user.tenant_id):
        raise api_error(
            status.HTTP_403_FORBIDDEN,
            "PLAYBOOK_TENANT_MISMATCH",
            "Playbook belongs to another tenant.",
        )


def _check_can_read_playbook(user: CurrentUser, playbook_tenant_id: uuid.UUID | None) -> None:
    """
    Validate permissions to read a specific playbook.

    Rules:
    - superadmin → can read everything
    - tenant_admin / member → can read platform + their own tenant scope
    """
    if user.global_role == "superadmin":
        return

    if playbook_tenant_id is None:
        # Platform playbook — visible to everyone
        return

    if user.tenant_id is None or str(playbook_tenant_id) != str(user.tenant_id):
        raise api_error(
            status.HTTP_403_FORBIDDEN,
            "PLAYBOOK_TENANT_MISMATCH",
            "Playbook belongs to another tenant.",
        )


@router.get(
    "/catalog",
    response_model=list[PlaybookTopicInfo],
    summary="Global checks catalog (topics and instructions)",
)
async def get_playbooks_catalog(
    db: AsyncSession = Depends(get_db),
):
    return await load_global_checks_catalog_from_db(db)


@router.get(
    "/checks",
    response_model=list[GlobalCheckInfo],
    summary="List of all global checks (global_checks)",
)
async def list_global_checks(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    all_checks, global_refs = await load_global_checks_with_refs_from_db(db)

    return [
        GlobalCheckInfo(
            id=cfg.id,
            name=cfg.name,
            description=cfg.description,
            category=cfg.category,
            group=cfg.group,
            severity=cfg.severity,
            doc_types=cfg.doc_types,
        )
        for cfg in sorted(all_checks.values(), key=lambda item: item.id)
    ]


@router.get(
    "/bundles",
    response_model=list[BundleInfo],
    summary="List of all preconfigured bundles (presets)",
)
async def list_bundles(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    import yaml

    items: list[BundleInfo] = []

    if not BUNDLES_DIR.exists():
        return items

    for path in sorted(BUNDLES_DIR.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            cfg = BundleConfig(**raw)
        except Exception:
            continue

        items.append(
            BundleInfo(
                id=cfg.id,
                name=cfg.name,
                description=cfg.description,
                check_ids=cfg.check_ids,
            )
        )

    return items


@router.get(
    "/lines",
    response_model=list[PlaybookLineShort],
    summary="List of logical playbooks (Playbook templates)",
)
async def list_playbook_lines(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_playbook_admin),
    deal_type: str | None = Query(
        default=None,
        description="Filter by deal type: real_estate, mna, nda, corporate, etc.",
    ),
    jurisdiction: str | None = Query(
        default=None,
        description="Filter by jurisdiction: RU, EN, DE, etc.",
    ),
    language: str | None = Query(
        default=None,
        description="Filter by document language: 'ru', 'en', etc.",
    ),
    scope: str | None = Query(
        default=None,
        description="Optional scope filter: 'platform' | 'tenant' | 'all'",
    ),
):
    """
    Returns playbooks respecting tenant scope:
    - superadmin: sees all platform playbooks (other tenants' playbooks are hidden)
    - tenant_admin / member: sees platform + their own tenant
    - with scope='tenant' → only tenant-owned (own)
    - with scope='platform' → only platform
    """
    repo = PlaybookRepository(db)

    if user.global_role == "superadmin":
        # Superadmin works at the platform level
        if scope == "tenant":
            # Explicitly requested tenant-owned but without tenant_id context, return empty
            return []
        playbooks = await repo.list_playbooks(
            deal_type=deal_type,
            jurisdiction=jurisdiction,
            language=language,
            tenant_id=None,
            include_platform=True,
        )
    else:
        # tenant_admin / member
        user_tenant_id = (
            uuid.UUID(str(user.tenant_id)) if user.tenant_id else None
        )
        if user_tenant_id is None:
            return []

        if scope == "tenant":
            playbooks = await repo.list_playbooks(
                deal_type=deal_type,
                jurisdiction=jurisdiction,
                language=language,
                tenant_id=user_tenant_id,
                only_tenant_owned=True,
            )
        elif scope == "platform":
            playbooks = await repo.list_playbooks(
                deal_type=deal_type,
                jurisdiction=jurisdiction,
                language=language,
                tenant_id=None,
                include_platform=True,
            )
        else:
            playbooks = await repo.list_playbooks(
                deal_type=deal_type,
                jurisdiction=jurisdiction,
                language=language,
                tenant_id=user_tenant_id,
                include_platform=True,
            )

    return [
        PlaybookLineShort(
            id=p.id,
            code=p.code,
            title=p.title,
            description=p.description,
            deal_type=p.deal_type,
            jurisdiction=p.jurisdiction,
            language=p.language,
            risk_profile=p.risk_profile,
        )
        for p in playbooks
    ]


@router.post(
    "",
    response_model=PlaybookCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new playbook version (PlaybookVersion)",
)
async def create_playbook_version(
    payload: PlaybookCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Create a new playbook version.

    Check composition sources:

    1) bundles + include_ids / exclude_ids — direct compile contract.
    2) from_line_id — read PlaybookLine and its items,
       extract instruction_code values and build include_ids directly.
    """

    repo = PlaybookRepository(db)

    # Base include_ids from payload (preserving legacy contract)
    include_ids: list[str] = list(payload.include_ids or [])

    # If from_line_id is set, fetch the line and its items
    if payload.from_line_id:
        line, items = await repo.get_line_with_items(payload.from_line_id)
        if line is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "PLAYBOOK_LINE_NOT_FOUND",
                "Playbook line not found for from_line_id.",
            )

        try:
            line_codes = await validate_instruction_codes_from_db(
                extract_unique_instruction_codes_from_items(items),
                db,
            )
        except PlaybookLineItemValidationError as exc:
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "PLAYBOOK_LINE_INVALID_INSTRUCTION_CODES",
                "Playbook line contains unknown instruction_code values.",
                unknown_instruction_codes=exc.unknown_codes,
            ) from exc

        for code in line_codes:
            if code not in include_ids:
                include_ids.append(code)

        # If playbook_id is not specified, implicitly link version to this line
        if not payload.playbook_id:
            payload.playbook_id = line.id

    try:
        include_ids = await validate_instruction_codes_from_db(include_ids, db)
    except PlaybookLineItemValidationError as exc:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "PLAYBOOK_INVALID_INSTRUCTION_CODES",
            "Request contains unknown instruction_code values.",
            unknown_instruction_codes=exc.unknown_codes,
        ) from exc

    # Validate: must have at least bundles, or include_ids (including those compiled from from_line_id)
    if not payload.bundles and not include_ids:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "PLAYBOOK_SOURCE_REQUIRED",
            "At least one bundle, include_ids, or from_line_id must be provided.",
        )

    # Load all global checks with refs
    all_checks, global_refs = await load_global_checks_with_refs_from_db(db)
    if not all_checks:
        raise api_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "PLAYBOOK_GLOBAL_CHECKS_UNAVAILABLE",
            "No global checks loaded; check server configuration.",
        )

    # Compile the final set of checks using existing compilation logic
    try:
        compiled = build_compiled_checks(
            all_checks=all_checks,
            bundles=payload.bundles,
            include_ids=include_ids,
            exclude_ids=payload.exclude_ids,
            profile=payload.profile,
            primary_bundle_id=payload.bundles[0] if payload.bundles else None,
            global_instruction_refs=global_refs,
        )
    except KeyError as e:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "PLAYBOOK_BUILD_FAILED",
            str(e),
        )
    except ValueError as e:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "PLAYBOOK_BUILD_FAILED",
            str(e),
        )
    except Exception:
        raise api_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "PLAYBOOK_BUILD_FAILED",
            "Failed to build compiled_checks.",
        )

    # Resolve tenant scope for the new version
    if payload.playbook_id is not None:
        parent_playbook = await repo.get_playbook_by_id(payload.playbook_id)
        if parent_playbook is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "PLAYBOOK_NOT_FOUND",
                f"Playbook not found: {payload.playbook_id}",
            )
        _check_can_modify_playbook(user, parent_playbook.tenant_id)
        version_tenant_id = parent_playbook.tenant_id
    else:
        # Version without parent playbook — inherit scope from user
        version_tenant_id = _resolve_write_tenant_id(user)

    # Version name resolution
    if payload.name:
        name = payload.name
    elif payload.bundles:
        name = f"Bundle: {', '.join(payload.bundles)}"
    elif payload.from_line_id:
        name = "Playbook from template"
    else:
        name = "Custom playbook"

    semver = payload.semver or "0.1.0"
    status_value = payload.status or PlaybookStatus.DRAFT.value

    # Build canonical source_payload (edit lifecycle layer)
    source_payload = {
        "schema_version": 1,
        "bundles": payload.bundles or [],
        "include_ids": payload.include_ids or [],
        "exclude_ids": payload.exclude_ids or [],
        "profile": payload.profile,
        "model_config_id": str(payload.model_config_id),
        "playbook_id": str(payload.playbook_id) if payload.playbook_id else None,
        "from_line_id": str(payload.from_line_id) if payload.from_line_id else None,
    }

    pv = await repo.create_version(
        name=name,
        semver=semver,
        model_config_id=payload.model_config_id,
        git_commit=None,
        yaml_sha256=None,
        compiled_checks=compiled,
        status=status_value,
        playbook_id=payload.playbook_id,
        source_payload=source_payload,
        tenant_id=version_tenant_id,
    )

    await db.commit()
    await db.refresh(pv)

    return PlaybookCreateResponse(
        id=pv.id,
        name=pv.name,
        semver=pv.semver,
        status=pv.status,
        playbook_id=pv.playbook_id,
    )


@router.get(
    "",
    response_model=list[PlaybookVersionShort],
    summary="List of playbook versions (PlaybookVersion)",
)
async def list_playbook_versions(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    List versions respecting tenant scope:
    - superadmin: platform only
    - tenant_admin / member: platform + their own tenant
    """
    from sqlalchemy import or_, select
    from db.models.playbook import PlaybookVersion

    stmt = select(PlaybookVersion)

    if user.global_role != "superadmin":
        user_tenant_id = (
            uuid.UUID(str(user.tenant_id)) if user.tenant_id else None
        )
        if user_tenant_id is None:
            return []
        stmt = stmt.where(
            or_(
                PlaybookVersion.tenant_id == user_tenant_id,
                PlaybookVersion.tenant_id.is_(None),
            )
        )

    result = await db.execute(stmt)
    rows = result.scalars().all()

    return [
        PlaybookVersionShort(
            id=row.id,
            name=row.name,
            semver=row.semver,
            status=row.status,
            playbook_id=row.playbook_id,
        )
        for row in rows
    ]


@router.get(
    "/{version_id}",
    response_model=PlaybookVersionDetail,
    summary="Detailed information about a playbook version",
)
async def get_playbook_version_detail(
    response: Response,
    version_id: uuid.UUID = Path(..., description="Playbook version ID"),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Returns a detailed representation of a playbook version.

    Used by frontend to:
    - Inspect playbook composition;
    - Render profiles, sections, and DD requests in the UI.
    """
    repo = PlaybookRepository(db)
    pv = await repo.get_by_id(version_id)
    if pv is None:
        raise _playbook_version_not_found(version_id)

    _check_can_read_playbook(user, pv.tenant_id)

    set_response_etag(response, getattr(pv, "updated_at", None))

    return PlaybookVersionDetail(
        id=pv.id,
        name=pv.name,
        semver=pv.semver,
        status=pv.status,
        playbook_id=pv.playbook_id,
        model_config_id=pv.model_config_id,
        compiled_checks=pv.compiled_checks,
        trigger_definitions=pv.trigger_definitions,
        dd_request_templates=pv.dd_request_templates,
        section_markers=pv.section_markers,
        classification_config=pv.classification_config,
        source_payload=pv.source_payload,
        source_payload_sha256=pv.source_payload_sha256,
    )


@router.get(
    "/lines/{line_id}",
    response_model=PlaybookLineDetail,
    summary="Playbook template details (PlaybookLine)",
)
async def get_playbook_line(
    line_id: uuid.UUID,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_playbook_admin),
):
    repo = PlaybookRepository(db)
    line, items = await repo.get_line_with_items(line_id)
    if not line:
        raise _playbook_line_not_found(line_id)

    _check_can_read_playbook(user, line.tenant_id)

    set_response_etag(response, getattr(line, "updated_at", None))

    return PlaybookLineDetail(
        id=line.id,
        code=line.code,
        title=line.title,
        description=line.description,
        deal_type=line.deal_type,
        jurisdiction=line.jurisdiction,
        language=line.language,
        risk_profile=line.risk_profile,
        items=[
            PlaybookLineItemPayload(
                kind=i.kind,
                instruction_code=i.instruction_code,
                order_index=i.order_index,
            )
            for i in items
        ],
    )


@router.post(
    "/lines",
    response_model=PlaybookLineDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create playbook template (PlaybookLine)",
)
async def create_playbook_line(
    payload: PlaybookLineCreate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_playbook_admin),
):
    repo = PlaybookRepository(db)

    try:
        await validate_line_item_payloads_from_db(payload.items, db)
    except PlaybookLineItemValidationError as exc:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "PLAYBOOK_LINE_INVALID_INSTRUCTION_CODES",
            "Playbook line contains unknown instruction_code values.",
            unknown_instruction_codes=exc.unknown_codes,
        ) from exc

    write_tenant_id = _resolve_write_tenant_id(user)

    # Convert Pydantic objects to dicts so repository does not depend on Pydantic directly
    items_payload = [item.model_dump() for item in payload.items]

    line, items = await repo.create_line_with_items(
        title=payload.title,
        description=payload.description,
        deal_type=payload.deal_type,
        jurisdiction=payload.jurisdiction,
        language=payload.language,
        items=items_payload,
        tenant_id=write_tenant_id,
    )
    await db.commit()
    await db.refresh(line)

    return PlaybookLineDetail(
        id=line.id,
        code=line.code,
        title=line.title,
        description=line.description,
        deal_type=line.deal_type,
        jurisdiction=line.jurisdiction,
        language=line.language,
        risk_profile=line.risk_profile,
        items=[
            PlaybookLineItemPayload(
                kind=i.kind,
                instruction_code=i.instruction_code,
                order_index=i.order_index,
            )
            for i in items
        ],
    )


@router.put(
    "/lines/{line_id}",
    response_model=PlaybookLineDetail,
    summary="Update playbook template (PlaybookLine)",
)
async def update_playbook_line(
    line_id: uuid.UUID,
    payload: PlaybookLineCreate,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_playbook_admin),
):
    repo = PlaybookRepository(db)

    existing_line, _ = await repo.get_line_with_items(line_id)
    if not existing_line:
        raise _playbook_line_not_found(line_id)

    _check_can_modify_playbook(user, existing_line.tenant_id)

    if_match = require_if_match(request)
    ensure_if_match(getattr(existing_line, "updated_at", None), if_match)

    try:
        await validate_line_item_payloads_from_db(payload.items, db)
    except PlaybookLineItemValidationError as exc:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "PLAYBOOK_LINE_INVALID_INSTRUCTION_CODES",
            "Playbook line contains unknown instruction_code values.",
            unknown_instruction_codes=exc.unknown_codes,
        ) from exc

    items_payload = [item.model_dump() for item in payload.items]
    
    line, items = await repo.update_line_with_items(
        line_id=line_id,
        title=payload.title,
        description=payload.description,
        deal_type=payload.deal_type,
        jurisdiction=payload.jurisdiction,
        language=payload.language,
        items=items_payload,
    )
    if not line:
        raise _playbook_line_not_found(line_id)

    await db.commit()
    await db.refresh(line)

    set_response_etag(response, getattr(line, "updated_at", None))

    return PlaybookLineDetail(
        id=line.id,
        code=line.code,
        title=line.title,
        description=line.description,
        deal_type=line.deal_type,
        jurisdiction=line.jurisdiction,
        language=line.language,
        risk_profile=line.risk_profile,
        items=[
            PlaybookLineItemPayload(
                kind=i.kind,
                instruction_code=i.instruction_code,
                order_index=i.order_index,
            )
            for i in items
        ],
    )


@router.delete(
    "/lines/{line_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete playbook template (PlaybookLine) if not in use",
)
async def delete_playbook_line(
    line_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_playbook_admin),
):
    """
    Deletes logical playbook template (PlaybookLine) only if it is not in use.

    Steps:
    - Validate template existence.
    - Validate if there are associated versions which are:
      * assigned to deals (Deal.playbook_version_id),
      * or used in a analysis run (Run.playbook_version_id).
    - If in use, raise 409 Conflict with meaningful message.
    - Otherwise, perform delete of line and its line_items, return 204.
    """
    repo = PlaybookRepository(db)

    existing_line, _ = await repo.get_line_with_items(line_id)
    if not existing_line:
        raise _playbook_line_not_found(line_id)

    _check_can_modify_playbook(user, existing_line.tenant_id)

    if_match = require_if_match(request)
    ensure_if_match(getattr(existing_line, "updated_at", None), if_match)

    usage = await repo.get_line_usage(line_id)

    # 1. Template not found - 404
    if not usage.line_exists:
        raise _playbook_line_not_found(line_id)

    # 2. Used in deals or runs - 409
    if usage.used_in_deals > 0 or usage.used_in_runs > 0:
        parts: list[str] = []

        if usage.used_in_deals > 0:
            if usage.deal_names:
                deals_str = ", ".join(usage.deal_names)
                parts.append(
                    f"used in {usage.used_in_deals} deal(s): {deals_str}"
                )
            else:
                parts.append(f"used in {usage.used_in_deals} deal(s)")

        if usage.used_in_runs > 0:
            parts.append(
                f"used in {usage.used_in_runs} analysis run(s)"
            )

        detail = (
            "Playbook template cannot be deleted: "
            + "; ".join(parts)
            + "."
        )

        raise api_error(
            status.HTTP_409_CONFLICT,
            "PLAYBOOK_LINE_IN_USE",
            detail,
        )

    deleted = await repo.delete_line_with_items(line_id)
    if not deleted:
        # Race condition safeguard: template was deleted by another request
        raise _playbook_line_not_found(line_id)

    await db.commit()


# -------------------------------------------------------------------
# ModelConfig migration endpoint for PlaybookVersion
# -------------------------------------------------------------------


class PlaybookVersionModelConfigUpdate(BaseModel):
    """
    Request body for updating ModelConfig link of a playbook version.

    If model_config_id is null, the version will no longer point to a
    specific model profile.
    """

    model_config_id: uuid.UUID | None


@router.patch(
    "/{version_id}/model-config",
    response_model=PlaybookVersionDetail,
    summary="Update model configuration (ModelConfig) for a playbook version",
)
async def set_playbook_version_model_config(
    request: Request,
    response: Response,
    version_id: uuid.UUID,
    payload: PlaybookVersionModelConfigUpdate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_playbook_admin),
):
    """
    Updates model_config_id on PlaybookVersion.

    Used inside playbook admin workspace to:
    - Re-link playbook version to a new model profile;
    - Clear old linkage (model_config_id = null) to allow deleting obsolete model configs.
    """
    repo = PlaybookRepository(db)

    pv = await repo.get_by_id(version_id)
    if pv is None:
        raise _playbook_version_not_found(version_id)

    _check_can_modify_playbook(user, pv.tenant_id)

    if_match = require_if_match(request)
    ensure_if_match(getattr(pv, "updated_at", None), if_match)

    if pv.status == PlaybookStatus.PUBLISHED.value:
        raise _published_version_immutable()

    # If configuration is identical, return early with current state
    if pv.model_config_id == payload.model_config_id:

        set_response_etag(response, getattr(pv, "updated_at", None))

        return PlaybookVersionDetail(
            id=pv.id,
            name=pv.name,
            semver=pv.semver,
            status=pv.status,
            playbook_id=pv.playbook_id,
            model_config_id=pv.model_config_id,
            compiled_checks=pv.compiled_checks,
            trigger_definitions=pv.trigger_definitions,
            dd_request_templates=pv.dd_request_templates,
            section_markers=pv.section_markers,
            classification_config=pv.classification_config,
        )

    # If new profile specified, validate its existence in the database
    if payload.model_config_id is not None:
        mc = await repo.get_model_config(payload.model_config_id)
        if mc is None:
            raise api_error(
                status.HTTP_404_NOT_FOUND,
                "MODEL_CONFIG_NOT_FOUND",
                "ModelConfig not found.",
            )

    pv.model_config_id = payload.model_config_id

    await db.commit()
    await db.refresh(pv)

    set_response_etag(response, getattr(pv, "updated_at", None))

    return PlaybookVersionDetail(
        id=pv.id,
        name=pv.name,
        semver=pv.semver,
        status=pv.status,
        playbook_id=pv.playbook_id,
        model_config_id=pv.model_config_id,
        compiled_checks=pv.compiled_checks,
        trigger_definitions=pv.trigger_definitions,
        dd_request_templates=pv.dd_request_templates,
        section_markers=pv.section_markers,
        classification_config=pv.classification_config,
    )


@router.post(
    "/{version_id}/publish",
    response_model=PlaybookVersionDetail,
)
async def publish_playbook_version(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_playbook_admin),
):
    repo = PlaybookRepository(db)
    pv = await repo.get_by_id(version_id)
    if not pv:
        raise _playbook_version_not_found(version_id)

    _check_can_modify_playbook(user, pv.tenant_id)

    service = PlaybookPublishingService(db)

    try:
        pv = await service.publish(pv)
    except PublishedVersionImmutableError:
        raise _published_version_immutable()
    except Exception as e:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "PLAYBOOK_PUBLISH_FAILED",
            str(e),
        )

    await db.commit()
    await db.refresh(pv)

    return pv

@router.patch(
    "/{version_id}",
    response_model=PlaybookVersionDetail,
    summary="Update draft playbook version",
)
async def update_playbook_draft(
    request: Request,
    response: Response,
    version_id: uuid.UUID,
    payload: PlaybookDraftUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_playbook_admin),
):
    from core.constants import PlaybookStatus

    repo = PlaybookRepository(db)
    pv = await repo.get_by_id(version_id)
    if not pv:
        raise _playbook_version_not_found(version_id)

    _check_can_modify_playbook(user, pv.tenant_id)

    if_match = require_if_match(request)
    ensure_if_match(getattr(pv, "updated_at", None), if_match)

    if pv.status != PlaybookStatus.DRAFT.value:
        raise _published_version_immutable()

    # Update source_payload metadata
    source = dict(pv.source_payload or {})
    if payload.bundles is not None:
        source["bundles"] = payload.bundles
    source["include_ids"] = payload.include_ids or source.get("include_ids", [])
    source["exclude_ids"] = payload.exclude_ids or source.get("exclude_ids", [])
    source["profile"] = payload.profile or source.get("profile")

    pv.source_payload = source

    # Re-compile compiled_checks using compiler logic
    all_checks, global_refs = await load_global_checks_with_refs_from_db(db)
    
    compiled = build_compiled_checks(
        all_checks=all_checks,
        bundles=source.get("bundles"),
        include_ids=source.get("include_ids"),
        exclude_ids=source.get("exclude_ids"),
        profile=source.get("profile"),
        primary_bundle_id=(
            source.get("bundles")[0]
            if source.get("bundles")
            else None
        ),
        global_instruction_refs=global_refs,
    )

    pv.compiled_checks = compiled

    # Recompute payload SHA256 checksum
    from db.repositories.playbook_repo import compute_source_payload_hash
    pv.source_payload_sha256 = compute_source_payload_hash(source)

    if payload.name:
        pv.name = payload.name

    await db.commit()
    await db.refresh(pv)

    set_response_etag(response, getattr(pv, "updated_at", None))

    return pv


@router.get(
    "/{version_id}/diff",
    response_model=PlaybookVersionDiffResponse,
    summary="Diff between two playbook versions",
)
async def diff_playbook_versions(
    version_id: uuid.UUID,
    against: uuid.UUID = Query(..., description="Version ID for comparison"),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_playbook_admin),
):
    repo = PlaybookRepository(db)

    base = await repo.get_by_id(version_id)
    other = await repo.get_by_id(against)

    if not base:
        raise _playbook_version_not_found(version_id)
    if not other:
        raise _playbook_version_not_found(against)

    _check_can_read_playbook(user, base.tenant_id)
    _check_can_read_playbook(user, other.tenant_id)

    service = PlaybookVersionDiffService()

    try:
        changes = service.diff(base, other)
    except PlaybookDiffError as e:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "PLAYBOOK_DIFF_FAILED",
            str(e),
        )

    return PlaybookVersionDiffResponse(
        base_version_id=base.id,
        compare_version_id=other.id,
        has_changes=len(changes) > 0,
        diff=changes,
    )


@router.post(
    "/{version_id}/archive",
    response_model=PlaybookVersionDetail,
)
async def archive_playbook_version(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_playbook_admin),
):
    repo = PlaybookRepository(db)
    pv = await repo.get_by_id(version_id)
    if not pv:
        raise _playbook_version_not_found(version_id)

    _check_can_modify_playbook(user, pv.tenant_id)

    service = PlaybookPublishingService(db)

    try:
        pv = await service.archive(pv)
    except Exception as e:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "PLAYBOOK_ARCHIVE_FAILED",
            str(e),
        )

    await db.commit()
    await db.refresh(pv)

    return pv

@router.post(
    "/{version_id}/clone",
    response_model=PlaybookVersionDetail,
)
async def clone_playbook_version(
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_playbook_admin),
):
    repo = PlaybookRepository(db)
    pv = await repo.get_by_id(version_id)
    if not pv:
        raise _playbook_version_not_found(version_id)

    _check_can_read_playbook(user, pv.tenant_id)

    service = PlaybookPublishingService(db)

    new_version = await service.clone_to_draft(pv)

    await db.commit()
    await db.refresh(new_version)

    return new_version


# ─── Tenant-owned playbooks catalog ───────────────────────────────────

_tenant_router = APIRouter(
    prefix="/tenants",
    tags=["playbooks"],
)


@_tenant_router.get(
    "/{tenant_id}/playbooks",
    response_model=list[PlaybookLineShort],
    summary="Catalog of organization's tenant-owned playbooks",
)
async def list_tenant_owned_playbooks(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    deal_type: str | None = Query(default=None),
    jurisdiction: str | None = Query(default=None),
    language: str | None = Query(default=None),
):
    """
    Returns only tenant-owned playbooks (excluding platform).

    Access:
    - superadmin: any tenant context
    - tenant_admin / member: only matching own tenant
    """
    if user.global_role != "superadmin":
        if user.tenant_id is None or str(user.tenant_id) != str(tenant_id):
            raise api_error(
                status.HTTP_403_FORBIDDEN,
                "PLAYBOOK_TENANT_MISMATCH",
                "Cannot list playbooks of another tenant.",
            )

    repo = PlaybookRepository(db)
    playbooks = await repo.list_playbooks(
        deal_type=deal_type,
        jurisdiction=jurisdiction,
        language=language,
        tenant_id=tenant_id,
        only_tenant_owned=True,
    )

    return [
        PlaybookLineShort(
            id=p.id,
            code=p.code,
            title=p.title,
            description=p.description,
            deal_type=p.deal_type,
            jurisdiction=p.jurisdiction,
            language=p.language,
            risk_profile=p.risk_profile,
        )
        for p in playbooks
    ]


# Export second router to be registered inside main.py
router_tenant = _tenant_router



