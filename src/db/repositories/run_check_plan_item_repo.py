# src/db/repositories/run_check_plan_item_repo.py

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.run_check_plan_item import RunCheckPlanItem

TERMINAL_STATUSES = {"succeeded", "failed", "skipped", "timeout", "cancelled"}
ERROR_STATUSES = {"failed", "timeout", "cancelled"}


class RunCheckPlanItemRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, item_id: uuid.UUID) -> RunCheckPlanItem | None:
        result = await self.session.execute(
            select(RunCheckPlanItem).where(RunCheckPlanItem.id == item_id)
        )
        return result.scalar_one_or_none()

    async def create_planned(
        self,
        run_id: uuid.UUID,
        deal_id: uuid.UUID,
        document_id: uuid.UUID,
        check_id: str,
        playbook_version_id: uuid.UUID | None = None,
        segment_id: str | None = None,
        doc_type: str | None = None,
        check_name: str | None = None,
        check_origin: str | None = None,
    ) -> RunCheckPlanItem:
        item = RunCheckPlanItem(
            run_id=run_id,
            deal_id=deal_id,
            document_id=document_id,
            segment_id=segment_id,
            doc_type=doc_type,
            check_id=check_id,
            check_name=check_name,
            check_origin=check_origin,
            playbook_version_id=playbook_version_id,
            status="planned",
            attempt_count=0,
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def mark_dispatched(
        self,
        item_id: uuid.UUID,
        dispatch_ref: str,
    ) -> RunCheckPlanItem | None:
        stmt = (
            update(RunCheckPlanItem)
            .where(
                RunCheckPlanItem.id == item_id,
                RunCheckPlanItem.status == "planned",
            )
            .values(
                status="dispatched",
                dispatch_ref=dispatch_ref,
                dispatched_at=datetime.now(UTC),
            )
            .returning(RunCheckPlanItem)
        )
        result = await self.session.execute(stmt)
        item = result.scalar_one_or_none()
        if item:
            await self.session.flush()
        return item

    async def mark_started(self, item_id: uuid.UUID) -> RunCheckPlanItem | None:
        stmt = (
            update(RunCheckPlanItem)
            .where(
                RunCheckPlanItem.id == item_id,
                RunCheckPlanItem.status.in_(["planned", "dispatched"]),
            )
            .values(
                status="started",
                started_at=datetime.now(UTC),
                attempt_count=RunCheckPlanItem.attempt_count + 1,
            )
            .returning(RunCheckPlanItem)
        )
        result = await self.session.execute(stmt)
        item = result.scalar_one_or_none()
        if item:
            await self.session.flush()
        return item

    async def mark_terminal(
        self,
        item_id: uuid.UUID,
        status: str,
        *,
        error_details: dict | None = None,
    ) -> RunCheckPlanItem | None:
        if status not in TERMINAL_STATUSES:
            raise ValueError(f"Status {status} is not terminal")

        stmt = (
            update(RunCheckPlanItem)
            .where(
                RunCheckPlanItem.id == item_id,
                RunCheckPlanItem.status.notin_(TERMINAL_STATUSES),
            )
            .values(
                status=status,
                error_details=error_details,
                finished_at=datetime.now(UTC),
            )
            .returning(RunCheckPlanItem)
        )
        result = await self.session.execute(stmt)
        item = result.scalar_one_or_none()
        if item:
            await self.session.flush()
        return item

    async def count_active_for_run(self, run_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(RunCheckPlanItem).where(
            RunCheckPlanItem.run_id == run_id,
            RunCheckPlanItem.status.notin_(TERMINAL_STATUSES),
        )
        result = await self.session.execute(stmt)
        return int(result.scalar() or 0)

    async def count_total_for_run(self, run_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(RunCheckPlanItem).where(
            RunCheckPlanItem.run_id == run_id,
        )
        result = await self.session.execute(stmt)
        return int(result.scalar() or 0)

    async def count_terminal_for_run(self, run_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(RunCheckPlanItem).where(
            RunCheckPlanItem.run_id == run_id,
            RunCheckPlanItem.status.in_(TERMINAL_STATUSES),
        )
        result = await self.session.execute(stmt)
        return int(result.scalar() or 0)

    async def has_errors_for_run(self, run_id: uuid.UUID) -> bool:
        stmt = select(func.count()).select_from(RunCheckPlanItem).where(
            RunCheckPlanItem.run_id == run_id,
            RunCheckPlanItem.status.in_(ERROR_STATUSES),
        )
        result = await self.session.execute(stmt)
        return int(result.scalar() or 0) > 0

    async def get_run_progress_stats(self, run_id: uuid.UUID) -> dict[str, int | bool]:
        total_items = await self.count_total_for_run(run_id)
        terminal_items = await self.count_terminal_for_run(run_id)
        active_items = max(total_items - terminal_items, 0)
        has_errors = await self.has_errors_for_run(run_id)

        return {
            "total_items": total_items,
            "terminal_items": terminal_items,
            "active_items": active_items,
            "has_errors": has_errors,
        }

    async def list_by_run_id(
        self,
        run_id: uuid.UUID,
        *,
        status: str | None = None,
    ) -> list[RunCheckPlanItem]:
        """
        Read-контракт для GET /runs/{run_id}/check-plan.

        Сортировка по document_id/check_id для стабильного, детерминированного
        порядка в UI (важно для diff-подобных экранов на фронте).
        """
        stmt = select(RunCheckPlanItem).where(RunCheckPlanItem.run_id == run_id)
        if status is not None:
            stmt = stmt.where(RunCheckPlanItem.status == status)
        stmt = stmt.order_by(
            RunCheckPlanItem.document_id,
            RunCheckPlanItem.check_id,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id_scoped(
        self,
        item_id: uuid.UUID,
        run_id: uuid.UUID,
    ) -> RunCheckPlanItem | None:
        """
        Read-контракт для GET /runs/{run_id}/check-plan/{plan_item_id}.

        Scoped по run_id — предотвращает cross-run leakage, если plan_item_id
        валиден, но принадлежит другому run (даже в рамках одного tenant).
        """
        result = await self.session.execute(
            select(RunCheckPlanItem).where(
                RunCheckPlanItem.id == item_id,
                RunCheckPlanItem.run_id == run_id,
            )
        )
        return result.scalar_one_or_none()
    

    