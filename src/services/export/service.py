# src/services/export/service.py

"""
Export service for processing Export records and generating output files.

The service executes export tasks for created `Export` database records,
handles lifecycle status transitions, and persists storage references to generated artifacts.

Key functions:
- run_export_for_record(export, db, tenant_id, presentation_locale):
  - transitions the Export record into `processing` status;
  - invokes `export_core(...)`, which builds the target export artifacts and returns refs;
  - updates target Export fields:
    `status`, `file_ref`, `file_refs` (and optionally `file_size_bytes`);
  - sets `status="completed"` on success;
  - logs exceptions, updates `status="failed"`, and returns an empty dict on error;
  - does not commit transaction — this is delegated to the caller.

- process_one_pending_export(db, tenant_id):
  - claims the earliest pending Export record;
  - executes generation via `run_export_for_record(...)`;
  - commits database transaction;
  - returns `True` if a record was discovered and processed, otherwise `False`.

Purpose:
- Thin orchestration layer wrapping `export_core` to track Export lifecycles
  and persist MinIO references to the database;
- Utilized by background task workers pulling pending items from the mas_queue.

Audit trail:
- EXPORT_COMPLETED — successful generation of an Export record.
- EXPORT_FAILED — execution error during run_export_for_record.
- Best-effort audit logging: telemetry failures do not disrupt file generation workflows.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.models.export import Export
from db.repositories import AuditRepository
from services.export.core import export_core

logger = get_logger(__name__)


async def run_export_for_record(
    export: Export,
    db: AsyncSession,
    tenant_id: str,
    presentation_locale: str | None = None,
) -> dict[str, Any]:
    """
    Execute export for an existing Export record.

    Expectations:
      - export.status is currently 'pending' (or 'queued');
      - export.run_id and export.deal_id are populated.

    Workflow:
      - transitions Export status to 'processing';
      - invokes export_core(...), generating files and returning refs;
      - updates Export fields:
          - status: 'completed' or 'failed',
          - file_ref: primary output file reference,
          - file_refs: dictionary of all generated artifact references,
          - file_size_bytes: optional total size computation.
      - does NOT commit the transaction (caller responsibility).

    Additional:
      - records EXPORT_COMPLETED / EXPORT_FAILED in audit trail (best-effort).
    """
    # Resolve presentation locale: explicit param -> model attribute -> "en"
    locale = (
        presentation_locale
        or getattr(export, "presentation_locale", None)
        or getattr(export, "locale", None)
        or "en"
    )

    logger.info(
        "Starting run_export_for_record",
        export_id=str(export.id),
        run_id=str(export.run_id),
        deal_id=str(export.deal_id),
        tenant_id=str(export.tenant_id),
        status=export.status,
        locale=locale,
    )

    audit_repo = AuditRepository(db)

    export.status = "processing"
    await db.flush()

    try:
        result = await export_core(
            run_id=str(export.run_id),
            deal_id=str(export.deal_id),
            tenant_id=tenant_id,
            db=db,
            presentation_locale=locale,
        )

        export.file_ref = result.get("export_ref")
        export.file_refs = result.get("all_refs") or result.get("refs")
        export.status = "completed"

        logger.info(
            "Export record processing completed",
            export_id=str(export.id),
            tenant_id=str(export.tenant_id),
            status=export.status,
            locale=locale,
        )

        try:
            await audit_repo.log(
                tenant_id=export.tenant_id,
                deal_id=export.deal_id,
                action="EXPORT_COMPLETED",
                actor="system",
                actor_role="worker",
                details={
                    "export_id": str(export.id),
                    "run_id": str(export.run_id),
                    "deal_id": str(export.deal_id),
                    "tenant_id": str(export.tenant_id),
                    "status": export.status,
                    "file_ref": export.file_ref,
                    "file_refs": export.file_refs,
                    "locale": locale,
                },
            )
        except Exception:
            logger.warning(
                "Export service: failed to write audit log for EXPORT_COMPLETED",
                export_id=str(export.id),
            )

        return result

    except Exception as e:  # noqa: BLE001
        logger.exception(
            "Error executing run_export_for_record",
            export_id=str(export.id),
            tenant_id=str(export.tenant_id),
            error=str(e),
        )
        export.status = "failed"
        await db.flush()

        try:
            await audit_repo.log(
                tenant_id=export.tenant_id,
                deal_id=export.deal_id,
                action="EXPORT_FAILED",
                actor="system",
                actor_role="worker",
                details={
                    "export_id": str(export.id),
                    "run_id": str(export.run_id),
                    "deal_id": str(export.deal_id),
                    "tenant_id": str(export.tenant_id),
                    "status": export.status,
                    "error": str(e),
                    "locale": locale,
                },
            )
        except Exception:
            logger.warning(
                "Export service: failed to write audit log for EXPORT_FAILED",
                export_id=str(export.id),
            )

        return {}


async def process_one_pending_export(
    db: AsyncSession,
    tenant_id: str,
) -> bool:
    """
    Claim a single pending Export record and process it atomically.

    Uses FOR UPDATE SKIP LOCKED to prevent race conditions across
    concurrent worker processes: each worker claims a unique record.

    Returns:
      - True if a record was claimed and processed (success or failure);
      - False if no pending records were available.
    """
    stmt = (
        select(Export)
        .where(Export.status == "pending")
        .where(Export.tenant_id == tenant_id)
        .order_by(Export.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )

    try:
        result = await db.execute(stmt)
        export: Export | None = result.scalars().first()

        if export is None:
            logger.debug(
                "process_one_pending_export: no pending exports available",
                tenant_id=tenant_id,
            )
            return False

        logger.info(
            "process_one_pending_export: claimed pending export",
            export_id=str(export.id),
            tenant_id=tenant_id,
            status=export.status,
        )

        # Pass presentation locale from export record if present
        record_locale = getattr(export, "presentation_locale", None) or getattr(export, "locale", None)

        await run_export_for_record(export, db=db, tenant_id=tenant_id, presentation_locale=record_locale)
        await db.commit()
        return True

    except Exception as e:  # noqa: BLE001
        await db.rollback()
        logger.exception(
            "process_one_pending_export failed",
            tenant_id=tenant_id,
            error=str(e),
        )
        raise


        