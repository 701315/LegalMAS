# src/db/repositories/check_result_presentation_repo.py

"""
Repository for locale-specific CheckResult presentation records.

This repository owns only CheckResultPresentation persistence. It does not
create, update, or duplicate canonical CheckResult records.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.result import CheckResultPresentation


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
