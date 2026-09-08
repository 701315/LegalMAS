"""
Centralized audit action constants and helper for translation lifecycle events.

All 8 translation audit event types are defined here as the single source of
truth. Services import these constants instead of hardcoding action strings.

Sprint 6.4 — covers the full translation lifecycle:
  1. requested   — user triggered presentation creation
  2. claimed     — worker claimed pending rows for processing
  3. translated  — LLM translation completed successfully
  4. failed      — LLM translation failed permanently
  5. approved    — QC reviewer approved translation (S6.1)
  6. rejected    — QC reviewer rejected translation (S6.1)
  7. edited      — QC reviewer edited translation (S6.1)
  8. reset       — rejected presentation reset to pending (S6.1)
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from db.repositories.audit_repo import AuditRepository


# ── Action constants (single source of truth) ────────────────────────

ACTION_REQUESTED = "result_presentation.requested"
ACTION_CLAIMED = "result_presentation.claimed"
ACTION_TRANSLATED = "result_presentation.translated"
ACTION_FAILED = "result_presentation.failed"
ACTION_APPROVED = "result_presentation.approved"
ACTION_REJECTED = "result_presentation.rejected"
ACTION_EDITED = "result_presentation.edited"
ACTION_RESET = "result_presentation.reset"

ALL_ACTIONS = frozenset({
    ACTION_REQUESTED,
    ACTION_CLAIMED,
    ACTION_TRANSLATED,
    ACTION_FAILED,
    ACTION_APPROVED,
    ACTION_REJECTED,
    ACTION_EDITED,
    ACTION_RESET,
})

# Actor identifier for automated worker processes
ACTOR_WORKER = "system:translation_worker"


async def log_translation_event(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    deal_id: uuid.UUID,
    action: str,
    actor: str,
    details: dict,
) -> None:
    """
    Write an immutable audit log entry for a translation lifecycle event.

    Thin convenience wrapper around AuditRepository.log() that ensures
    consistent structure across all translation audit events.
    """
    if action not in ALL_ACTIONS:
        raise ValueError(f"Unknown translation audit action: {action}")

    repo = AuditRepository(session)
    await repo.log(
        tenant_id=tenant_id,
        deal_id=deal_id,
        action=action,
        actor=actor,
        actor_role="system" if actor.startswith("system:") else "user",
        details=details,
    )
