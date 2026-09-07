# src/db/repositories/check_result_presentation_repo.py

"""
Repository for locale-specific CheckResult presentation records.

This repository owns only CheckResultPresentation persistence. It does not
create, update, or duplicate canonical CheckResult records.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.result import CheckResult, CheckResultPresentation


_READY_PRESENTATION_STATUSES = (
    "ready",
    "reviewed",
    "approved",
)


class CheckResultPresentationRepository:
    """Persistence access for locale-specific result presentations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_identity(
        self,
        *,
        check_result_id: uuid.UUID,
        locale: str,
        content_version: str,
    ) -> CheckResultPresentation | None:
        """Return one presentation by its immutable logical identity."""
        stmt = select(CheckResultPresentation).where(
            CheckResultPresentation.check_result_id == check_result_id,
            CheckResultPresentation.locale == locale,
            CheckResultPresentation.content_version == content_version,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_ready_by_result_and_locale(
        self,
        *,
        check_result_id: uuid.UUID,
        locale: str,
        content_version: str,
    ) -> CheckResultPresentation | None:
        """
        Return a presentation usable for normal review rendering.

        `pending`, `processing`, `failed`, and `stale` records are intentionally
        excluded. The caller must use canonical CheckResult content as fallback.
        """
        stmt = select(CheckResultPresentation).where(
            CheckResultPresentation.check_result_id == check_result_id,
            CheckResultPresentation.locale == locale,
            CheckResultPresentation.content_version == content_version,
            CheckResultPresentation.translation_status.in_(
                _READY_PRESENTATION_STATUSES
            ),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_ready_by_result_ids_and_locale(
        self,
        *,
        check_result_ids: Iterable[uuid.UUID],
        locale: str,
        content_version: str,
    ) -> dict[uuid.UUID, CheckResultPresentation]:
        """
        Return ready/reviewed/approved presentations keyed by canonical result ID.

        Empty input returns an empty mapping without emitting SQL.
        """
        normalized_ids = list(dict.fromkeys(check_result_ids))

        if not normalized_ids:
            return {}

        stmt = select(CheckResultPresentation).where(
            CheckResultPresentation.check_result_id.in_(normalized_ids),
            CheckResultPresentation.locale == locale,
            CheckResultPresentation.content_version == content_version,
            CheckResultPresentation.translation_status.in_(
                _READY_PRESENTATION_STATUSES
            ),
        )
        result = await self.session.execute(stmt)

        return {
            presentation.check_result_id: presentation
            for presentation in result.scalars().all()
        }


    async def list_by_result_ids_and_locale(
        self,
        *,
        check_result_ids: Iterable[uuid.UUID],
        locale: str,
        content_version: str,
    ) -> dict[uuid.UUID, CheckResultPresentation]:
        """
        Return all presentation states for one locale/content version, keyed by
        canonical CheckResult ID.

        Unlike list_ready_by_result_ids_and_locale(), this method intentionally
        includes pending, processing, failed, and stale records. The read-side
        selection service remains responsible for deciding whether a record is
        safe to render as localized content.

        Empty input returns an empty mapping without emitting SQL.
        """
        normalized_ids = list(dict.fromkeys(check_result_ids))

        if not normalized_ids:
            return {}

        stmt = select(CheckResultPresentation).where(
            CheckResultPresentation.check_result_id.in_(normalized_ids),
            CheckResultPresentation.locale == locale,
            CheckResultPresentation.content_version == content_version,
        )
        result = await self.session.execute(stmt)

        return {
            presentation.check_result_id: presentation
            for presentation in result.scalars().all()
        }

    async def create_pending_if_absent(
        self,
        *,
        check_result_id: uuid.UUID,
        locale: str,
        content_version: str,
        source_content_hash: str,
        source_locale: str | None,
    ) -> CheckResultPresentation:
        """
        Create an idempotent pending presentation request.

        The PostgreSQL ON CONFLICT guard protects concurrent review requests.
        Existing records are never overwritten here: future worker/state-machine
        code owns controlled status transitions and generated content updates.
        """
        normalized_locale = locale.strip()

        if not normalized_locale:
            raise ValueError("locale must be a non-empty string")

        normalized_version = content_version.strip()

        if not normalized_version:
            raise ValueError("content_version must be a non-empty string")

        normalized_hash = source_content_hash.strip().lower()

        if len(normalized_hash) != 64:
            raise ValueError("source_content_hash must be a SHA-256 hex digest")

        stmt = (
            insert(CheckResultPresentation)
            .values(
                check_result_id=check_result_id,
                locale=normalized_locale,
                content_version=normalized_version,
                source_content_hash=normalized_hash,
                source_locale=source_locale,
                translation_status="pending",
            )
            .on_conflict_do_nothing(
                constraint="uq_check_result_presentations_identity"
            )
        )

        await self.session.execute(stmt)
        await self.session.flush()

        presentation = await self.get_by_identity(
            check_result_id=check_result_id,
            locale=normalized_locale,
            content_version=normalized_version,
        )

        if presentation is None:
            raise RuntimeError(
                "CheckResultPresentation was not found after idempotent insert"
            )

        return presentation


    async def claim_pending_for_run(
        self,
        *,
        run_id: uuid.UUID,
        locale: str,
        content_version: str,
        limit: int = 25,
    ) -> list[CheckResultPresentation]:
        """
        Atomically claim pending presentation records for one Run and locale.

        PostgreSQL row locking with SKIP LOCKED prevents parallel workers from
        processing the same presentation row. Only pending rows can be claimed;
        ready/reviewed/approved/failed/stale rows are never reopened here.
        """
        normalized_locale = locale.strip().lower()
        normalized_version = content_version.strip()

        if not normalized_locale:
            raise ValueError("locale must be a non-empty string")

        if not normalized_version:
            raise ValueError("content_version must be a non-empty string")

        if limit <= 0:
            raise ValueError("limit must be greater than zero")

        stmt = (
            select(CheckResultPresentation)
            .join(
                CheckResult,
                CheckResult.id == CheckResultPresentation.check_result_id,
            )
            .where(
                CheckResult.run_id == run_id,
                CheckResultPresentation.locale == normalized_locale,
                CheckResultPresentation.content_version == normalized_version,
                CheckResultPresentation.translation_status == "pending",
            )
            .order_by(
                CheckResultPresentation.created_at.asc(),
                CheckResultPresentation.id.asc(),
            )
            .limit(limit)
            .with_for_update(skip_locked=True)
        )

        result = await self.session.execute(stmt)
        presentations = list(result.scalars().all())

        for presentation in presentations:
            presentation.translation_status = "processing"
            presentation.error_message = None

        if presentations:
            await self.session.flush()

        return presentations

    async def mark_ready(
        self,
        *,
        presentation_id: uuid.UUID,
        localized_check_name: str,
        display_text: str | None,
        review_message: str | None,
        translation_provider: str,
        translation_model: str,
        translation_metadata: dict,
    ) -> CheckResultPresentation | None:
        """
        Persist a successfully generated localized presentation.

        The transition is guarded by translation_status == processing. A worker
        retry or duplicate delivery cannot overwrite an already terminal record.
        """
        stmt = (
            update(CheckResultPresentation)
            .where(
                CheckResultPresentation.id == presentation_id,
                CheckResultPresentation.translation_status == "processing",
            )
            .values(
                localized_check_name=localized_check_name,
                display_text=display_text,
                review_message=review_message,
                translation_status="ready",
                translation_provider=translation_provider,
                translation_model=translation_model,
                translation_metadata=translation_metadata,
                error_message=None,
            )
            .returning(CheckResultPresentation)
        )

        result = await self.session.execute(stmt)
        presentation = result.scalar_one_or_none()

        if presentation is not None:
            await self.session.flush()

        return presentation

    async def mark_failed(
        self,
        *,
        presentation_id: uuid.UUID,
        error_message: str,
        translation_metadata: dict,
    ) -> CheckResultPresentation | None:
        """
        Persist a terminal presentation-generation failure.

        Only currently processing rows can transition to failed. Existing
        terminal rows remain unchanged.
        """
        normalized_error = error_message.strip()[:4000]

        if not normalized_error:
            normalized_error = "Presentation translation failed"

        stmt = (
            update(CheckResultPresentation)
            .where(
                CheckResultPresentation.id == presentation_id,
                CheckResultPresentation.translation_status == "processing",
            )
            .values(
                translation_status="failed",
                translation_metadata=translation_metadata,
                error_message=normalized_error,
            )
            .returning(CheckResultPresentation)
        )

        result = await self.session.execute(stmt)
        presentation = result.scalar_one_or_none()

        if presentation is not None:
            await self.session.flush()

        return presentation

    async def mark_stale(
        self,
        *,
        presentation_id: uuid.UUID,
        translation_metadata: dict,
    ) -> CheckResultPresentation | None:
        """
        Mark a claimed presentation stale when canonical source content changed.

        The row is not translated and existing localized content is preserved for
        audit. D3/D4 never overwrite older source-version presentation content.
        """
        stmt = (
            update(CheckResultPresentation)
            .where(
                CheckResultPresentation.id == presentation_id,
                CheckResultPresentation.translation_status == "processing",
            )
            .values(
                translation_status="stale",
                translation_metadata=translation_metadata,
                error_message=None,
            )
            .returning(CheckResultPresentation)
        )

        result = await self.session.execute(stmt)
        presentation = result.scalar_one_or_none()

        if presentation is not None:
            await self.session.flush()

        return presentation

    async def reset_processing_to_pending(
        self,
        *,
        presentation_id: uuid.UUID,
    ) -> CheckResultPresentation | None:
        """
        Reset a presentation's status from processing back to pending.

        Used during transient failures/retries so the SKIP LOCKED claim query
        can pick up the row again in subsequent worker attempts.
        """
        stmt = (
            update(CheckResultPresentation)
            .where(
                CheckResultPresentation.id == presentation_id,
                CheckResultPresentation.translation_status == "processing",
            )
            .values(
                translation_status="pending",
                error_message=None,
            )
            .returning(CheckResultPresentation)
        )

        result = await self.session.execute(stmt)
        presentation = result.scalar_one_or_none()

        if presentation is not None:
            await self.session.flush()

        return presentation

        