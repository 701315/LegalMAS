"""
Repository for AuditLog operations.
AuditLog is immutable — only create and read, no update or delete.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.ops import AuditLog


class AuditRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(
        self,
        tenant_id: uuid.UUID,
        action: str,
        actor: str,
        deal_id: uuid.UUID | None = None,
        actor_role: str | None = None,
        details: dict | None = None,
    ) -> AuditLog:
        """Create an immutable audit log entry."""
        entry = AuditLog(
            tenant_id=tenant_id,
            deal_id=deal_id,
            action=action,
            actor=actor,
            actor_role=actor_role,
            details=details or {},
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def get_by_deal(
        self,
        deal_id: uuid.UUID,
        action: str | None = None,
        limit: int = 100,
    ) -> list[AuditLog]:
        """Get audit logs for a deal, optionally filtered by action."""
        stmt = select(AuditLog).where(AuditLog.deal_id == deal_id)
        if action is not None:
            stmt = stmt.where(AuditLog.action == action)
        stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
