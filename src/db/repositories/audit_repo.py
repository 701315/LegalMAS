# src/db/repositories/audit_repo.py

"""
Repository for AuditLog operations.
AuditLog is immutable — only create and read, no update or delete.
"""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.ops import AuditLog


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

    async def get_page_by_deal(
        self,
        deal_id: uuid.UUID,
        page: int = 1,
        per_page: int = 50,
        action: str | None = None,
        actor: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> tuple[list[AuditLog], int]:
        """
        Вернуть одну страницу записей аудита по сделке + общий count.

        Поддерживает фильтры:
        - action  — тип действия (точное совпадение)
        - actor   — пользователь (точное совпадение)
        - from_date / to_date — временной диапазон по created_at

        Возвращает кортеж (записи, общий_count).
        """
        # Базовый фильтр: только записи этой сделки
        base_stmt = select(AuditLog).where(AuditLog.deal_id == deal_id)

        # Необязательные фильтры
        if action:
            base_stmt = base_stmt.where(AuditLog.action == action)
        if actor:
            base_stmt = base_stmt.where(AuditLog.actor == actor)
        if from_date:
            base_stmt = base_stmt.where(AuditLog.created_at >= from_date)
        if to_date:
            base_stmt = base_stmt.where(AuditLog.created_at <= to_date)

        # Считаем общее количество строк, попадающих под фильтры
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total: int = (await self.session.execute(count_stmt)).scalar_one()

        if total == 0:
            return [], 0

        # Пагинация: смещение = (номер_страницы - 1) * размер_страницы
        offset = (page - 1) * per_page

        rows_stmt = (
            base_stmt
            .order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        result = await self.session.execute(rows_stmt)
        return list(result.scalars().all()), total
    
    
