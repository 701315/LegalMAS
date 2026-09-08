# src/services/auto_translation_dispatcher.py

"""
Auto-translation dispatcher service.

Provides a unified, idempotent helper to trigger locale-specific result
presentation generation post-run or lazily on grid read.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from core.result_presentation_content import PRESENTATION_CONTENT_VERSION_V2
from db.models.deal import Deal
from db.models.run import Run
from db.repositories.audit_repo import AuditRepository
from services.outbox_service import OutboxService
from services.result_presentation_request_service import (
    ResultPresentationRequestService,
)
from services.translation_audit import ACTION_REQUESTED

logger = get_logger(__name__)


async def dispatch_auto_translation_if_needed(
    session: AsyncSession,
    *,
    run: Run,
    target_locale: str = "en",
    actor: str = "system:auto_translation",
) -> bool:
    """
    Idempotently request and queue result presentation translations for a run.

    Returns True if new pending records were created and enqueued into Outbox.
    Safely catches exceptions so execution/read flows never crash.
    """
    normalized_target = target_locale.strip().lower()
    analysis_lang = (run.analysis_language or "ru").strip().lower()

    # Skip translation if target locale matches canonical source analysis language
    if normalized_target == analysis_lang:
        return False

    try:
        deal = await session.get(Deal, run.deal_id)
        source_locale = (
            (deal.primary_language if deal else None)
            or run.analysis_language
            or "ru"
        )

        service = ResultPresentationRequestService(session)
        progress = await service.request_pending_presentations(
            run_id=run.id,
            locale=normalized_target,
            source_locale=source_locale,
            content_version=PRESENTATION_CONTENT_VERSION_V2,
        )

        if progress.created_pending <= 0:
            return False

        # Log audit event for auto-dispatch
        audit_repo = AuditRepository(session)
        await audit_repo.log(
            tenant_id=run.tenant_id,
            deal_id=run.deal_id,
            action=ACTION_REQUESTED,
            actor=actor,
            actor_role="system",
            details={
                "run_id": str(run.id),
                "requested_locale": normalized_target,
                "content_version": progress.content_version,
                "total_results": progress.total,
                "created_pending": progress.created_pending,
                "existing_presentations": progress.existing,
                "dispatch_status": "queued_auto",
            },
        )

        # Enqueue task into Outbox
        outbox_service = OutboxService(session)
        await outbox_service.enqueue_task(
            task_name="workers.process_pending_result_presentations",
            payload={
                "run_id": str(run.id),
                "deal_id": str(run.deal_id),
                "tenant_id": str(run.tenant_id),
                "locale": normalized_target,
                "content_version": progress.content_version,
                "batch_limit": 25,
            },
            aggregate_type="run",
            aggregate_id=str(run.id),
            dedup_key=(
                "result-presentation-batch:"
                f"{run.id}:{normalized_target}:{progress.content_version}"
            ),
            headers={
                "queue": "heavy_llm_checks",
            },
        )

        logger.info(
            "Auto-translation dispatched via Outbox",
            run_id=str(run.id),
            target_locale=normalized_target,
            created_pending=progress.created_pending,
            actor=actor,
        )
        return True

    except Exception as exc:
        logger.error(
            "Failed to auto-dispatch result presentation translation",
            run_id=str(run.id),
            target_locale=normalized_target,
            error=str(exc),
            exc_info=True,
        )
        return False
