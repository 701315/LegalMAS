# src/db/repositories/dd_request_repo.py
"""
Repository for DDRequest CRUD operations.

Thin wrapper over SQLAlchemy ORM — no business logic here.
"""

import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.dd_request import DDRequest


class DDRequestRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_for_deal(
        self,
        deal_id: uuid.UUID,
        status: str | None = None,
        priority: str | None = None,
    ) -> list[DDRequest]:
        """
        Return all DD-requests for a deal, optionally filtered by status/priority.
        """
        stmt = select(DDRequest).where(DDRequest.deal_id == deal_id)

        if status is not None:
            stmt = stmt.where(DDRequest.status == status)
        if priority is not None:
            stmt = stmt.where(DDRequest.priority == priority)

        stmt = stmt.order_by(DDRequest.created_at.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, req_id: uuid.UUID) -> DDRequest | None:
        """
        Get a single DD-request by its ID.
        """
        stmt = select(DDRequest).where(DDRequest.id == req_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_for_deal(
        self,
        deal_id: uuid.UUID,
        *,
        title: str | None,
        priority: str,
        text: str,
        status: str,
        addressee: str,
        check_id: str | None,
        structured_values: list[dict] | None,
        source: str,
        document_refs: list[uuid.UUID],
        evidence_refs: list[uuid.UUID],
    ) -> DDRequest:
        if structured_values is None:
            structured_values = []
        """
        Create a new DD-request for a deal.
        """
        req = DDRequest(
            deal_id=deal_id,
            title=title,
            priority=priority,
            text=text,
            status=status,
            addressee=addressee,
            check_id=check_id,
            structured_values=structured_values,
            source=source,
            document_refs=document_refs,
            evidence_refs=evidence_refs,
        )
        self.session.add(req)
        await self.session.flush()
        return req

    async def update(
        self,
        req_id: uuid.UUID,
        data: dict,
    ) -> DDRequest | None:
        """
        Partially update a DD-request. `data` should contain only fields to change.
        """
        if not data:
            return await self.get_by_id(req_id)

        stmt = update(DDRequest).where(DDRequest.id == req_id).values(**data).returning(DDRequest)
        result = await self.session.execute(stmt)
        req = result.scalar_one_or_none()
        if req:
            await self.session.flush()
        return req

    async def delete(self, req_id: uuid.UUID) -> None:
        """
        Delete a DD-request by ID.
        """
        stmt = delete(DDRequest).where(DDRequest.id == req_id)
        await self.session.execute(stmt)
        await self.session.flush()
