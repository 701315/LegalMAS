# src/db/repositories/check_result_anchor_repo.py

"""
Repository for CheckResultAnchor persistence.

Anchors are one-to-many with CheckResult: a single finding may carry
several anchors (multiple evidence chunks, multiple quotes).

Idempotency contract:
- anchors have no logical identity key (unlike presentations);
- a re-run for the same CheckResult must fully replace its anchor set;
- the intended write sequence is delete_for_check_result + create_many,
  optionally followed by set_primary.

This repository owns only the check_result_anchors table. It does NOT
denormalize primary anchor fields onto CheckResult — that is a service-layer
responsibility (B4).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.anchors.models import CheckAnchor
from db.models.check_result_anchor import CheckResultAnchor


def _anchor_to_orm_values(
    *,
    check_result_id: uuid.UUID,
    anchor: CheckAnchor,
) -> dict[str, Any]:
    """
    Map a CheckAnchor Pydantic value object to CheckResultAnchor column values.

    is_primary is always written as False here. The primary flag is owned by
    set_primary(), never by create_many() — this guarantees at most one
    primary per CheckResult under the partial unique index.
    """
    return {
        "check_result_id": check_result_id,
        "clause_uid": anchor.clause_uid,
        "clause_ref": anchor.clause_ref,
        "quoted_text": anchor.quoted_text,
        "span_start": anchor.span_start,
        "span_end": anchor.span_end,
        "source_content_hash": anchor.source_content_hash,
        "page": anchor.page,
        "layout_element_ids": list(anchor.layout_element_ids),
        "bbox_union": anchor.bbox_union,
        "segment_id": anchor.segment_id,
        "anchor_method": anchor.anchor_method.value,
        "anchor_confidence": anchor.anchor_confidence,
        "anchor_validation_passed": anchor.anchor_validation_passed,
        "anchor_diagnostics": dict(anchor.anchor_diagnostics),
        "is_primary": False,
    }


class CheckResultAnchorRepository:
    """Persistence access for CheckResultAnchor records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_many(
        self,
        *,
        check_result_id: uuid.UUID,
        anchors: Sequence[CheckAnchor],
    ) -> list[CheckResultAnchor]:
        """
        Persist N anchors for one CheckResult.

        All created anchors have is_primary=False. Call set_primary() afterwards
        to designate exactly one of them as primary.

        Empty input returns [] without emitting SQL.
        """
        if not anchors:
            return []

        created: list[CheckResultAnchor] = []
        for anchor in anchors:
            row = CheckResultAnchor(
                **_anchor_to_orm_values(
                    check_result_id=check_result_id,
                    anchor=anchor,
                )
            )
            self.session.add(row)
            created.append(row)

        await self.session.flush()
        return created

    async def list_for_check_result(
        self,
        *,
        check_result_id: uuid.UUID,
    ) -> list[CheckResultAnchor]:
        """Return all anchors for a CheckResult, stable-ordered by creation."""
        stmt = (
            select(CheckResultAnchor)
            .where(CheckResultAnchor.check_result_id == check_result_id)
            .order_by(
                CheckResultAnchor.created_at.asc(),
                CheckResultAnchor.id.asc(),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_primary(
        self,
        *,
        check_result_id: uuid.UUID,
    ) -> CheckResultAnchor | None:
        """
        Return the primary anchor, or None if none is set.

        The partial unique index uq_cra_one_primary guarantees at most one row.
        """
        stmt = (
            select(CheckResultAnchor)
            .where(
                CheckResultAnchor.check_result_id == check_result_id,
                CheckResultAnchor.is_primary.is_(True),
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def set_primary(
        self,
        *,
        check_result_id: uuid.UUID,
        anchor_id: uuid.UUID,
    ) -> CheckResultAnchor | None:
        """
        Designate anchor_id as the sole primary anchor for check_result_id.

        Atomically clears the primary flag on every other anchor of the same
        CheckResult, then sets it on the target. Returns the target ORM object,
        or None when anchor_id does not belong to check_result_id.

        Concurrency note: this method assumes the caller serializes concurrent
        writes for the same CheckResult (the check executor processes one
        CheckResult at a time inside a single transaction).
        """
        target = await self._get_by_id_and_result(
            anchor_id=anchor_id,
            check_result_id=check_result_id,
        )
        if target is None:
            return None

        await self.session.execute(
            update(CheckResultAnchor)
            .where(
                CheckResultAnchor.check_result_id == check_result_id,
                CheckResultAnchor.id != anchor_id,
                CheckResultAnchor.is_primary.is_(True),
            )
            .values(is_primary=False)
        )

        target.is_primary = True
        await self.session.flush()
        return target

    async def clear_primary(
        self,
        *,
        check_result_id: uuid.UUID,
    ) -> int:
        """
        Remove the primary flag from any anchor of this CheckResult.

        Returns the number of rows updated (0 or 1 under the partial unique
        index).
        """
        stmt = (
            update(CheckResultAnchor)
            .where(
                CheckResultAnchor.check_result_id == check_result_id,
                CheckResultAnchor.is_primary.is_(True),
            )
            .values(is_primary=False)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return int(result.rowcount or 0)

    async def delete_for_check_result(
        self,
        *,
        check_result_id: uuid.UUID,
    ) -> int:
        """Delete every anchor for a CheckResult. Returns the rowcount."""
        stmt = delete(CheckResultAnchor).where(
            CheckResultAnchor.check_result_id == check_result_id,
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return int(result.rowcount or 0)

    async def replace_for_check_result(
        self,
        *,
        check_result_id: uuid.UUID,
        anchors: Sequence[CheckAnchor],
    ) -> list[CheckResultAnchor]:
        """
        Replace the full anchor set for a CheckResult.

        Deletes existing anchors then creates the provided ones. Does NOT set
        a primary — the caller decides via set_primary() once it has computed
        which anchor is primary (usually via select_primary_anchor()).
        """
        await self.delete_for_check_result(check_result_id=check_result_id)
        return await self.create_many(
            check_result_id=check_result_id,
            anchors=anchors,
        )

    # ── internals ─────────────────────────────────────────────────────────

    async def _get_by_id_and_result(
        self,
        *,
        anchor_id: uuid.UUID,
        check_result_id: uuid.UUID,
    ) -> CheckResultAnchor | None:
        stmt = select(CheckResultAnchor).where(
            CheckResultAnchor.id == anchor_id,
            CheckResultAnchor.check_result_id == check_result_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

        