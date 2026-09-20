"""
Translation Review Service — Sprint 6.1

Handles QC approval, rejection, and human edits (overrides) for localized result
presentations. Ensures canonical CheckResult is NEVER altered (Invariants #1, #3).
Logs all review milestones to the immutable audit trail.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.result import CheckResult, CheckResultPresentation
from db.models.run import Run
from db.models.deal import Deal
from db.repositories.audit_repo import AuditRepository
from ops.metrics import get_metrics

logger = logging.getLogger(__name__)

# Allowed status transitions for translation review:
# ready -> approved (Approve text)
# ready -> reviewed (Edit text, stores snapshot + override)
# ready -> rejected (Reject text, requires comment)
# reviewed -> approved (Approve edited text)
# reviewed -> rejected (Reject edited text)
# approved -> reviewed (Re-edit approved text)
# approved -> rejected (Reject approved text)
# rejected -> pending (Optionally reset back to pending for worker re-translation)

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "ready": {"approved", "reviewed", "rejected"},
    "reviewed": {"approved", "rejected", "reviewed"},
    "approved": {"reviewed", "rejected"},
    "rejected": {"pending"},
}


class ReviewStateError(ValueError):
    """Raised when a review transition violates the state machine."""
    pass


async def get_presentation_audit_context(
    session: AsyncSession,
    presentation_id: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID]:
    """
    Fetch tenant_id and deal_id linked to the presentation for audit logs.
    """
    stmt = (
        select(Deal.tenant_id, Deal.id)
        .select_from(CheckResultPresentation)
        .join(CheckResult, CheckResult.id == CheckResultPresentation.check_result_id)
        .join(Run, Run.id == CheckResult.run_id)
        .join(Deal, Deal.id == Run.deal_id)
        .where(CheckResultPresentation.id == presentation_id)
    )
    result = await session.execute(stmt)
    row = result.fetchone()
    if not row:
        raise ValueError(f"Could not find audit context for presentation {presentation_id}")
    return row[0], row[1]


class ResultLocalizationReviewService:
    """
    Enterprise-grade service controlling localized translation review workflows.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit_repo = AuditRepository(session)

    async def _get_and_lock_presentation(
        self,
        presentation_id: uuid.UUID,
    ) -> CheckResultPresentation:
        """Fetch and lock presentation row for updates."""
        stmt = (
            select(CheckResultPresentation)
            .where(CheckResultPresentation.id == presentation_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        presentation = result.scalar_one_or_none()
        if not presentation:
            raise ValueError(f"CheckResultPresentation {presentation_id} not found")
        return presentation

    def _validate_transition(self, current_status: str, target_status: str) -> None:
        """Validate state machine constraints."""
        allowed = _ALLOWED_TRANSITIONS.get(current_status, set())
        if target_status not in allowed:
            raise ReviewStateError(
                f"Cannot transition presentation status from '{current_status}' to '{target_status}'. "
                f"Allowed transitions: {sorted(list(allowed))}"
            )

    async def approve_translation(
        self,
        *,
        presentation_id: uuid.UUID,
        user_id: uuid.UUID,
        user_email: str,
        comment: str | None = None,
    ) -> CheckResultPresentation:
        """
        Approve the localized presentation translation without human edits.
        """
        presentation = await self._get_and_lock_presentation(presentation_id)
        current_status = presentation.translation_status
        
        self._validate_transition(current_status, "approved")

        now = datetime.now(timezone.utc)
        presentation.translation_status = "approved"
        presentation.approved_by = user_id
        presentation.approved_at = now
        presentation.review_comment = comment.strip() if comment else None

        # Sprint 6.5: Emit approved metric to Prometheus
        try:
            get_metrics().translation_review_approved_total.labels(locale=presentation.locale).inc()
        except Exception:
            pass

        # Resolve context for audit logs
        tenant_id, deal_id = await get_presentation_audit_context(self.session, presentation_id)
        await self.audit_repo.log(
            tenant_id=tenant_id,
            deal_id=deal_id,
            action="result_presentation.approved",
            actor=user_email,
            details={
                "presentation_id": str(presentation_id),
                "locale": presentation.locale,
                "previous_status": current_status,
                "comment": comment,
            }
        )

        await self.session.flush()
        logger.info("Presentation %s approved by user %s", presentation_id, user_id)
        return presentation

    async def reject_translation(
        self,
        *,
        presentation_id: uuid.UUID,
        user_id: uuid.UUID,
        user_email: str,
        comment: str,
    ) -> CheckResultPresentation:
        """
        Reject translation. Rejection strictly requires a non-empty comment.
        """
        if not comment or not comment.strip():
            raise ValueError("Rejection comment is mandatory and cannot be empty")

        presentation = await self._get_and_lock_presentation(presentation_id)
        current_status = presentation.translation_status

        self._validate_transition(current_status, "rejected")

        now = datetime.now(timezone.utc)
        presentation.translation_status = "rejected"
        presentation.reviewed_by = user_id
        presentation.reviewed_at = now
        presentation.review_comment = comment.strip()

        # Sprint 6.5: Emit rejected metric to Prometheus
        try:
            get_metrics().translation_review_rejected_total.labels(locale=presentation.locale).inc()
        except Exception:
            pass

        # Resolve context for audit logs
        tenant_id, deal_id = await get_presentation_audit_context(self.session, presentation_id)
        await self.audit_repo.log(
            tenant_id=tenant_id,
            deal_id=deal_id,
            action="result_presentation.rejected",
            actor=user_email,
            details={
                "presentation_id": str(presentation_id),
                "locale": presentation.locale,
                "previous_status": current_status,
                "comment": comment.strip(),
            }
        )

        await self.session.flush()
        logger.info("Presentation %s rejected by user %s", presentation_id, user_id)
        return presentation

    async def edit_translation_override(
        self,
        *,
        presentation_id: uuid.UUID,
        user_id: uuid.UUID,
        user_email: str,
        localized_check_name: str | None = None,
        display_text: str | None = None,
        review_message: str | None = None,
        dd_request_text: str | None = None,
        comment: str | None = None,
    ) -> CheckResultPresentation:
        """
        Apply a human override edit to the translation fields.
        Saves original LLM values inside `original_translation_snapshot` during the first edit.
        Overridden text is stored directly in fields for transparent zero-cost read overlays.
        """
        presentation = await self._get_and_lock_presentation(presentation_id)
        current_status = presentation.translation_status

        self._validate_transition(current_status, "reviewed")

        # Snapshot original LLM values if this is the first edit
        if not presentation.original_translation_snapshot:
            presentation.original_translation_snapshot = {
                "localized_check_name": presentation.localized_check_name,
                "display_text": presentation.display_text,
                "review_message": presentation.review_message,
                "dd_request_text": presentation.dd_request_text,
            }

        # Keep track of changes for the audit log
        changes: dict[str, Any] = {}
        
        if localized_check_name is not None and localized_check_name != presentation.localized_check_name:
            changes["localized_check_name"] = {
                "old": presentation.localized_check_name,
                "new": localized_check_name,
            }
            presentation.localized_check_name = localized_check_name

        if display_text is not None and display_text != presentation.display_text:
            changes["display_text"] = {
                "old": presentation.display_text,
                "new": display_text,
            }
            presentation.display_text = display_text

        if review_message is not None and review_message != presentation.review_message:
            changes["review_message"] = {
                "old": presentation.review_message,
                "new": review_message,
            }
            presentation.review_message = review_message

        if dd_request_text is not None and dd_request_text != presentation.dd_request_text:
            changes["dd_request_text"] = {
                "old": presentation.dd_request_text,
                "new": dd_request_text,
            }
            presentation.dd_request_text = dd_request_text

        now = datetime.now(timezone.utc)
        
        # Save human override summary explicitly
        presentation.human_override_text = {
            "localized_check_name": presentation.localized_check_name,
            "display_text": presentation.display_text,
            "review_message": presentation.review_message,
            "dd_request_text": presentation.dd_request_text,
        }
        
        presentation.translation_status = "reviewed"
        presentation.reviewed_by = user_id
        presentation.reviewed_at = now
        presentation.review_comment = comment.strip() if comment else presentation.review_comment

        # Sprint 6.5: Emit edited metric to Prometheus
        try:
            get_metrics().translation_review_edited_total.labels(locale=presentation.locale).inc()
        except Exception:
            pass

        # Resolve context for audit logs
        tenant_id, deal_id = await get_presentation_audit_context(self.session, presentation_id)
        await self.audit_repo.log(
            tenant_id=tenant_id,
            deal_id=deal_id,
            action="result_presentation.edited",
            actor=user_email,
            details={
                "presentation_id": str(presentation_id),
                "locale": presentation.locale,
                "changes": changes,
                "comment": comment,
            }
        )

        await self.session.flush()
        logger.info("Presentation %s edited by user %s", presentation_id, user_id)
        return presentation

    async def reset_to_pending(
        self,
        *,
        presentation_id: uuid.UUID,
        user_email: str,
    ) -> CheckResultPresentation:
        """
        Reset a rejected or stale presentation back to pending status.
        Allows workers to safely schedule translation retry.
        """
        presentation = await self._get_and_lock_presentation(presentation_id)
        current_status = presentation.translation_status

        self._validate_transition(current_status, "pending")

        presentation.translation_status = "pending"
        presentation.error_message = None

        # Sprint 6.5: Emit reset metric to Prometheus
        try:
            get_metrics().translation_review_reset_total.labels(locale=presentation.locale).inc()
        except Exception:
            pass

        # Resolve context for audit logs
        tenant_id, deal_id = await get_presentation_audit_context(self.session, presentation_id)
        await self.audit_repo.log(
            tenant_id=tenant_id,
            deal_id=deal_id,
            action="result_presentation.reset",
            actor=user_email,
            details={
                "presentation_id": str(presentation_id),
                "locale": presentation.locale,
                "previous_status": current_status,
            }
        )

        await self.session.flush()
        logger.info("Presentation %s reset to pending", presentation_id)
        return presentation
