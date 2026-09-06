# src/workers/export_pending.py

"""
Export Pending Worker.

This module contains a Celery worker that processes pending export
tasks from the database one by one.

Purpose:
  - Periodically check for export tasks in 'pending' state;
  - Claim a single task and process it to completion;
  - Ensure atomicity of single export updates via db_uow;
  - Encapsulate processing business logic inside
    services.export.service.process_one_pending_export.

Behavior:
  - If at least one export in 'pending' status exists in DB,
    worker claims it, runs all processing steps, and returns True;
  - If no eligible tasks exist, worker does nothing and returns False;
  - If a transient error occurs (DB, network, etc.),
    MASBaseTask marks it as transient and initiates a retry.

Architecture:
  - External layer: synchronous Celery task export_process_pending (def),
    registered in mas_queue.celery_app.celery_app;
  - Internal layer: sync-to-async transition via run_async(), invoking
    async function _export_process_pending_async(...);
  - _export_process_pending_async opens a Unit of Work via db_uow(),
    calls process_one_pending_export(db=uow.session, tenant_id=...),
    and returns a boolean indicating whether work was performed.

Audit trail:
  - If pending export is processed, records EXPORT_PENDING_PROCESSED.
  - If pending export is not found, records EXPORT_PENDING_IDLE.
  - If an error occurs, records EXPORT_PENDING_FAILED.
  - Best-effort audit logging: audit failures must not crash the worker.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from core.logging import get_logger
from db.repositories import AuditRepository
from db.uow import db_uow
from mas_queue.async_helpers import run_async
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.export.service import process_one_pending_export

logger = get_logger(__name__)


async def _export_process_pending_async(tenant_id: str) -> bool:
    """
    Async implementation of processing a single pending export task.

    Encapsulates database operations and business logic execution.
    """
    start = time.time()
    tenant_uuid: uuid.UUID | None = None

    try:
        try:
            tenant_uuid = uuid.UUID(tenant_id)
        except Exception:
            tenant_uuid = None

        async with db_uow() as uow:
            processed = await process_one_pending_export(
                db=uow.session,
                tenant_id=tenant_id,
            )

            duration_ms = int((time.time() - start) * 1000)

            try:
                if tenant_uuid is not None:
                    audit_repo = AuditRepository(uow.session)
                    await audit_repo.log(
                        tenant_id=tenant_uuid,
                        deal_id=None,
                        action=("EXPORT_PENDING_PROCESSED" if processed else "EXPORT_PENDING_IDLE"),
                        actor="system",
                        actor_role="worker",
                        details={
                            "tenant_id": tenant_id,
                            "processed": bool(processed),
                            "duration_ms": duration_ms,
                        },
                    )
            except Exception:
                logger.warning(
                    "Export pending worker: failed to write audit log",
                    tenant_id=tenant_id,
                    processed=bool(processed),
                )

            logger.info(
                "Export pending worker finished",
                tenant_id=tenant_id,
                processed=bool(processed),
                duration_ms=duration_ms,
            )

            return processed

    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)

        logger.exception(
            "Export pending worker failed",
            tenant_id=tenant_id,
            duration_ms=duration_ms,
            error=str(e),
        )

        if tenant_uuid is not None:
            try:
                async with db_uow() as uow_status:
                    audit_repo = AuditRepository(uow_status.session)
                    await audit_repo.log(
                        tenant_id=tenant_uuid,
                        deal_id=None,
                        action="EXPORT_PENDING_FAILED",
                        actor="system",
                        actor_role="worker",
                        details={
                            "tenant_id": tenant_id,
                            "duration_ms": duration_ms,
                            "error": str(e),
                        },
                    )
            except Exception:
                logger.warning(
                    "Export pending worker: failed to write failure audit log",
                    tenant_id=tenant_id,
                )

        raise


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="export.process_pending",
    track_job=False,
    queue="default",
)
def export_process_pending(
    self,
    tenant_id: str = "default",
    stage_execution_id: str | None = None,
    orchestration_strategy: str | None = None,
    **kwargs: Any,
) -> bool:
    """
    Synchronous Celery task for processing a single pending export task.

    Workflow:
      - Executes async function _export_process_pending_async(...)
        via the run_async() bridge;
      - Returns True if an export was claimed and processed, otherwise False.
    """
    _ = self
    return run_async(_export_process_pending_async(tenant_id))
