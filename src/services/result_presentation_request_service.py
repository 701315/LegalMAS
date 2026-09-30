"""
Write-side request and progress service for result presentations.

D3 responsibilities:
- create idempotent pending CheckResultPresentation records;
- calculate Run + locale + content-version progress;
- detect source-hash drift as stale without overwriting prior records.

This service does not call an LLM, enqueue Celery work, or mutate canonical
CheckResult rows. D4 will consume pending presentation records.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.result_presentation_content import (
    PRESENTATION_CONTENT_VERSION_V1,
    PRESENTATION_CONTENT_VERSION_V2,
    build_presentation_source_hash,
)
from db.models.result import CheckResult
from db.repositories.check_result_presentation_repo import (
    CheckResultPresentationRepository,
)
from db.repositories.result_repo import ResultRepository
from core.logging import get_logger
from services.translation_audit import (
    ACTION_REQUESTED,
    ACTION_RESET,
    log_translation_event,
)

logger = get_logger(__name__)


_PRESENTATION_STATUSES = (
    "pending",
    "processing",
    "ready",
    "reviewed",
    "approved",
    "rejected",
    "failed",
    "stale",
)


@dataclass(frozen=True)
class ResultPresentationProgress:
    """Derived lifecycle summary for one Run, locale, and content version."""

    run_id: str
    locale: str
    content_version: str
    total: int
    missing: int
    pending: int
    processing: int
    ready: int
    reviewed: int
    approved: int
    failed: int
    stale: int
    created_pending: int = 0
    existing: int = 0
    reset_pending: int = 0

    @property
    def is_complete(self) -> bool:
        """A batch is complete when no records are missing or actively pending."""
        return (
            self.missing == 0
            and self.pending == 0
            and self.processing == 0
        )


def _normalize_locale(locale: str) -> str:
    """Normalize a required locale value for persistence operations."""
    normalized = locale.strip().lower()
    if not normalized:
        raise ValueError("locale must be a non-empty string")
    return normalized


def _normalize_source_locale(source_locale: str | None) -> str | None:
    """Normalize an optional canonical source locale."""
    if source_locale is None:
        return None

    normalized = str(source_locale).strip().lower()
    return normalized or None


def _canonical_source_hash(
    check_result: CheckResult,
    *,
    content_version: str,
) -> str:
    """Build the exact same source fingerprint used by D2 read-side selection."""
    return build_presentation_source_hash(
        check_name=check_result.check_name,
        display_text=check_result.display_text,
        review_message=check_result.review_message,
        structured_data=check_result.structured_data if content_version == PRESENTATION_CONTENT_VERSION_V2 else None,
        content_version=content_version,
    )


def _presentation_value(
    presentation: Any,
    field_name: str,
) -> Any:
    """Read a field from either an ORM presentation object or a mapping."""
    if isinstance(presentation, Mapping):
        return presentation.get(field_name)

    return getattr(presentation, field_name, None)


def build_result_presentation_progress(
    *,
    check_results: Sequence[CheckResult],
    presentations_by_result_id: Mapping[str, Any],
    locale: str,
    content_version: str = PRESENTATION_CONTENT_VERSION_V2,
    created_pending: int = 0,
    existing: int = 0,
    reset_pending: int = 0,
) -> ResultPresentationProgress:
    """
    Build derived progress for one Run/locale/version.

    A record with an outdated source_content_hash is counted as stale even if
    its stored database status is ready, reviewed, or approved. D3 does not
    overwrite it: immutable source-version handling remains explicit.
    """
    normalized_locale = _normalize_locale(locale)
    normalized_version = content_version.strip()

    if not normalized_version:
        raise ValueError("content_version must be a non-empty string")

    counts = {
        "missing": 0,
        "pending": 0,
        "processing": 0,
        "ready": 0,
        "reviewed": 0,
        "approved": 0,
        "failed": 0,
        "stale": 0,
    }

    for check_result in check_results:
        result_id = str(check_result.id)
        presentation = presentations_by_result_id.get(result_id)

        if presentation is None:
            counts["missing"] += 1
            continue

        presentation_locale = _presentation_value(presentation, "locale")
        presentation_version = _presentation_value(
            presentation,
            "content_version",
        )
        presentation_hash = _presentation_value(
            presentation,
            "source_content_hash",
        )
        presentation_status = str(
            _presentation_value(presentation, "translation_status") or ""
        ).strip().lower()

        current_hash = _canonical_source_hash(
            check_result,
            content_version=normalized_version,
        )

        if (
            presentation_locale != normalized_locale
            or presentation_version != normalized_version
            or presentation_hash != current_hash
        ):
            counts["stale"] += 1
            continue

        if presentation_status in _PRESENTATION_STATUSES:
            counts[presentation_status] += 1
        else:
            counts["failed"] += 1

    return ResultPresentationProgress(
        run_id=(
            str(check_results[0].run_id)
            if check_results
            else ""
        ),
        locale=normalized_locale,
        content_version=normalized_version,
        total=len(check_results),
        missing=counts["missing"],
        pending=counts["pending"],
        processing=counts["processing"],
        ready=counts["ready"],
        reviewed=counts["reviewed"],
        approved=counts["approved"],
        failed=counts["failed"],
        stale=counts["stale"],
        created_pending=created_pending,
        existing=existing,
        reset_pending=reset_pending,
    )


class ResultPresentationRequestService:
    """
    Application service for D3 presentation request and progress operations.

    All writes are idempotent through the presentation repository's unique
    logical identity and ON CONFLICT DO NOTHING behavior.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.result_repo = ResultRepository(session)
        self.presentation_repo = CheckResultPresentationRepository(session)

    async def get_progress(
        self,
        *,
        run_id: uuid.UUID,
        locale: str,
        content_version: str = PRESENTATION_CONTENT_VERSION_V2,
    ) -> ResultPresentationProgress:
        """Return current derived progress without creating any records."""
        normalized_locale = _normalize_locale(locale)
        check_results = await self.result_repo.get_by_run(run_id)

        presentations_by_uuid = (
            await self.presentation_repo.list_by_result_ids_and_locale(
                check_result_ids=[
                    check_result.id
                    for check_result in check_results
                ],
                locale=normalized_locale,
                content_version=content_version,
            )
        )

        presentations_by_result_id = {
            str(result_id): presentation
            for result_id, presentation in presentations_by_uuid.items()
        }

        progress = build_result_presentation_progress(
            check_results=check_results,
            presentations_by_result_id=presentations_by_result_id,
            locale=normalized_locale,
            content_version=content_version,
        )

        return ResultPresentationProgress(
            run_id=str(run_id),
            locale=progress.locale,
            content_version=progress.content_version,
            total=progress.total,
            missing=progress.missing,
            pending=progress.pending,
            processing=progress.processing,
            ready=progress.ready,
            reviewed=progress.reviewed,
            approved=progress.approved,
            failed=progress.failed,
            stale=progress.stale,
            created_pending=0,
            existing=0,
            reset_pending=0,
        )

    async def request_pending_presentations(
        self,
        *,
        run_id: uuid.UUID,
        locale: str,
        source_locale: str | None,
        content_version: str = PRESENTATION_CONTENT_VERSION_V2,
        actor: str | None = None,
        tenant_id: uuid.UUID | None = None,
        deal_id: uuid.UUID | None = None,
    ) -> ResultPresentationProgress:
        """
        Create missing pending presentation rows and return final progress.

        Existing rows are never updated or overwritten. Existing stale records
        remain stale because the logical identity already belongs to the older
        immutable source version.
        """
        normalized_locale = _normalize_locale(locale)
        normalized_source_locale = _normalize_source_locale(source_locale)
        normalized_version = content_version.strip()

        if not normalized_version:
            raise ValueError("content_version must be a non-empty string")

        check_results = await self.result_repo.get_by_run(run_id)

        presentations_by_uuid = (
            await self.presentation_repo.list_by_result_ids_and_locale(
                check_result_ids=[
                    check_result.id
                    for check_result in check_results
                ],
                locale=normalized_locale,
                content_version=normalized_version,
            )
        )

        presentations_by_result_id = {
            str(result_id): presentation
            for result_id, presentation in presentations_by_uuid.items()
        }

        created_pending = 0
        existing = 0
        reset_pending = 0
        reset_details: list[dict[str, Any]] = []

        for check_result in check_results:
            result_id = str(check_result.id)
            current_hash = _canonical_source_hash(
                check_result,
                content_version=normalized_version,
            )

            existing_presentation = presentations_by_result_id.get(result_id)

            if existing_presentation is None:
                presentation = await self.presentation_repo.create_pending_if_absent(
                    check_result_id=check_result.id,
                    locale=normalized_locale,
                    content_version=normalized_version,
                    source_content_hash=current_hash,
                    source_locale=normalized_source_locale,
                )
                presentations_by_result_id[result_id] = presentation
                created_pending += 1
                continue

            stored_hash = _presentation_value(
                existing_presentation, "source_content_hash"
            )
            stored_status = str(
                _presentation_value(
                    existing_presentation, "translation_status"
                )
                or ""
            ).strip().lower()

            # Content unchanged — trust the existing presentation.
            if stored_hash == current_hash:
                existing += 1
                continue

            # Content changed but a worker currently owns the row.
            # Do not race the worker; it will finish and the next
            # request_pending_presentations call will reset it.
            if stored_status == "processing":
                existing += 1
                continue

            had_human_override = bool(
                _presentation_value(existing_presentation, "human_override_text")
            )

            reset_row = await self.presentation_repo.reset_to_pending_for_rehash(
                presentation_id=existing_presentation.id,
                new_source_hash=current_hash,
                source_locale=normalized_source_locale,
            )

            if reset_row is None:
                # Raced with a worker claim between read and update.
                existing += 1
                continue

            presentations_by_result_id[result_id] = reset_row
            reset_pending += 1
            reset_details.append(
                {
                    "check_id": check_result.check_id,
                    "old_status": stored_status,
                    "old_hash": stored_hash,
                    "new_hash": current_hash,
                    "human_override_discarded": had_human_override,
                }
            )

        progress = build_result_presentation_progress(
            check_results=check_results,
            presentations_by_result_id=presentations_by_result_id,
            locale=normalized_locale,
            content_version=normalized_version,
            created_pending=created_pending,
            existing=existing,
            reset_pending=reset_pending,
        )

        # Audit — source-content-changed resets (before the created-pending
        # audit so the reasons are recorded even if the second one is
        # skipped). Uses ACTION_RESET with an explicit reason to
        # distinguish from QC-reviewer-triggered resets.
        if reset_pending > 0 and actor and tenant_id and deal_id:
            try:
                await log_translation_event(
                    self.session,
                    tenant_id=tenant_id,
                    deal_id=deal_id,
                    action=ACTION_RESET,
                    actor=actor,
                    details={
                        "run_id": str(run_id),
                        "locale": normalized_locale,
                        "content_version": normalized_version,
                        "reason": "source_content_changed",
                        "reset_pending": reset_pending,
                        "events": reset_details,
                    },
                )
            except Exception:
                logger.warning(
                    "Failed to audit source-content-changed reset",
                    run_id=str(run_id),
                    exc_info=True,
                )

        # Sprint 6.4: Audit — write log when new presentations are requested
        if created_pending > 0 and actor and tenant_id and deal_id:
            try:
                await log_translation_event(
                    self.session,
                    tenant_id=tenant_id,
                    deal_id=deal_id,
                    action=ACTION_REQUESTED,
                    actor=actor,
                    details={
                        "run_id": str(run_id),
                        "locale": normalized_locale,
                        "content_version": normalized_version,
                        "created_pending": created_pending,
                    },
                )
            except Exception:
                pass  # Audit logging is best-effort and must not fail the execution

        return ResultPresentationProgress(
            run_id=str(run_id),
            locale=progress.locale,
            content_version=progress.content_version,
            total=progress.total,
            missing=progress.missing,
            pending=progress.pending,
            processing=progress.processing,
            ready=progress.ready,
            reviewed=progress.reviewed,
            approved=progress.approved,
            failed=progress.failed,
            stale=progress.stale,
            created_pending=progress.created_pending,
            existing=progress.existing,
            reset_pending=progress.reset_pending,
        )
