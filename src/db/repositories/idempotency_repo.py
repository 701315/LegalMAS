"""
Repository for IdempotencyKey operations.
"""

import uuid
from datetime import UTC, datetime  # ← изменено

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.ops import IdempotencyKey


class IdempotencyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create(
        self,
        tenant_id: uuid.UUID,
        endpoint: str,
        key: str,
        expires_at: datetime | None = None,
    ) -> tuple[IdempotencyKey, bool]:
        """
        Get existing key or create new one.
        Returns (record, is_new). is_new=True means it was just created.
        """
        # Try to find existing
        result = await self.session.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.tenant_id == tenant_id,
                IdempotencyKey.endpoint == endpoint,
                IdempotencyKey.idempotency_key == key,
            )
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            return existing, False

        # Create new
        record = IdempotencyKey(
            tenant_id=tenant_id,
            endpoint=endpoint,
            idempotency_key=key,
            status="processing",
            expires_at=expires_at,
        )
        self.session.add(record)
        await self.session.flush()
        return record, True

    async def mark_completed(
        self,
        key_id: uuid.UUID,
        response_hash: str | None = None,
        result: dict | None = None,
    ) -> None:
        """Mark key as completed with cached response."""
        await self.session.execute(
            update(IdempotencyKey)
            .where(IdempotencyKey.id == key_id)
            .values(
                status="completed",
                response_hash=response_hash,
                result=result,
            )
        )
        await self.session.flush()

    async def mark_failed(self, key_id: uuid.UUID) -> None:
        """Mark key as failed."""
        await self.session.execute(
            update(IdempotencyKey).where(IdempotencyKey.id == key_id).values(status="failed")
        )
        await self.session.flush()

    async def cleanup_expired(self) -> int:
        """Delete expired keys. Returns count of deleted rows."""
        stmt = delete(IdempotencyKey).where(
            IdempotencyKey.expires_at < datetime.now(UTC)
        )  # ← изменено
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount
