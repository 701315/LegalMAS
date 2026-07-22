"""
Sync API для платформенных инструкций.

Позволяет superadmin запустить re-import инструкций из YAML-источников в БД.

Endpoints:
    POST /api/v1/admin/instructions/sync/global-checks
    POST /api/v1/admin/instructions/sync/doc-types

Доступ: только superadmin.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.deps.auth import CurrentUser, get_current_user
from core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/admin/instructions/sync",
    tags=["admin", "instructions-sync"],
)


# ── Guards ────────────────────────────────────────────────────────────────


def _require_superadmin(user: CurrentUser) -> None:
    if user.global_role != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin access required",
        )


# ── Response schemas ──────────────────────────────────────────────────────


class GlobalChecksSyncResult(BaseModel):
    created: int = Field(ge=0)
    repaired: int = Field(ge=0)
    skipped: int = Field(ge=0)
    errors: int = Field(ge=0)
    total: int = Field(ge=0)
    dry_run: bool = False


class DocTypesSyncResult(BaseModel):
    created: int = Field(ge=0)
    promoted: int = Field(ge=0)
    skipped: int = Field(ge=0)
    errors: int = Field(ge=0)
    total: int = Field(ge=0)
    dry_run: bool = False


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.post(
    "/global-checks",
    response_model=GlobalChecksSyncResult,
    status_code=status.HTTP_200_OK,
    summary="Синхронизировать global checks из YAML в БД (только superadmin)",
)
async def sync_global_checks(
    dry_run: bool = Query(default=False),
    user: CurrentUser = Depends(get_current_user),
) -> GlobalChecksSyncResult:
    _require_superadmin(user)

    logger.info("sync_global_checks: started", actor=user.id, dry_run=dry_run)

    try:
        # Lazy import — выполняется уже после полной инициализации sys.path
        from scripts.import_global_instructions import (
            import_global_instructions,
        )
        counts = await import_global_instructions(dry_run=dry_run)
    except Exception as exc:
        logger.exception(
            "sync_global_checks: unexpected error",
            actor=user.id,
            dry_run=dry_run,
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync failed: {exc}",
        ) from exc

    logger.info(
        "sync_global_checks: completed",
        actor=user.id,
        dry_run=dry_run,
        created=counts.get("created", 0),
        repaired=counts.get("repaired", 0),
        skipped=counts.get("skipped", 0),
        errors=counts.get("errors", 0),
        total=counts.get("total", 0),
    )

    return GlobalChecksSyncResult(
        created=counts.get("created", 0),
        repaired=counts.get("repaired", 0),
        skipped=counts.get("skipped", 0),
        errors=counts.get("errors", 0),
        total=counts.get("total", 0),
        dry_run=dry_run,
    )


@router.post(
    "/doc-types",
    response_model=DocTypesSyncResult,
    status_code=status.HTTP_200_OK,
    summary="Синхронизировать doc-type инструкции из YAMLRegistry в БД (только superadmin)",
)
async def sync_doc_types(
    dry_run: bool = Query(default=False),
    only_doc_type: str | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
) -> DocTypesSyncResult:
    _require_superadmin(user)

    logger.info(
        "sync_doc_types: started",
        actor=user.id,
        dry_run=dry_run,
        only_doc_type=only_doc_type,
    )

    try:
        # Lazy import — выполняется уже после полной инициализации sys.path
        from scripts.import_doc_type_instructions import (
            import_doc_type_instructions,
        )
        counts = await import_doc_type_instructions(
            dry_run=dry_run,
            only_doc_type=only_doc_type,
        )
    except Exception as exc:
        logger.exception(
            "sync_doc_types: unexpected error",
            actor=user.id,
            dry_run=dry_run,
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync failed: {exc}",
        ) from exc

    logger.info(
        "sync_doc_types: completed",
        actor=user.id,
        dry_run=dry_run,
        only_doc_type=only_doc_type,
        created=counts.get("created", 0),
        promoted=counts.get("promoted", 0),
        skipped=counts.get("skipped", 0),
        errors=counts.get("errors", 0),
        total=counts.get("total", 0),
    )

    return DocTypesSyncResult(
        created=counts.get("created", 0),
        promoted=counts.get("promoted", 0),
        skipped=counts.get("skipped", 0),
        errors=counts.get("errors", 0),
        total=counts.get("total", 0),
        dry_run=dry_run,
    )


