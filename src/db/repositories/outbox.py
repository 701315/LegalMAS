from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.outbox import OutboxMessage


class OutboxRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        *,
        task_name: str,
        payload: dict,
        aggregate_type: str,
        aggregate_id: str,
        headers: dict | None = None,
        dedup_key: str | None = None,
        max_attempts: int = 25,
        available_at: datetime | None = None,
    ) -> OutboxMessage:
        message = OutboxMessage(
            id=uuid.uuid4(),
            task_name=task_name,
            payload=payload,
            headers=headers or {},
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            dedup_key=dedup_key,
            status="pending",
            attempts=0,
            max_attempts=max_attempts,
            available_at=available_at or datetime.now(UTC),
        )
        self.db.add(message)
        await self.db.flush()
        return message

    async def get_by_dedup_key(self, dedup_key: str) -> OutboxMessage | None:
        stmt = select(OutboxMessage).where(OutboxMessage.dedup_key == dedup_key)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def claim_batch(self, batch_size: int) -> Sequence[OutboxMessage]:
        now = datetime.now(UTC)

        stmt: Select[tuple[OutboxMessage]] = (
            select(OutboxMessage)
            .where(OutboxMessage.status == "pending")
            .where(OutboxMessage.available_at <= now)
            .order_by(OutboxMessage.created_at.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )

        result = await self.db.execute(stmt)
        messages = list(result.scalars().all())

        for message in messages:
            message.status = "processing"
            message.updated_at = now

        await self.db.flush()
        return messages

    async def mark_published(self, message_id: uuid.UUID) -> None:
        message = await self.db.get(OutboxMessage, message_id)
        if message is None:
            return
        now = datetime.now(UTC)
        message.status = "published"
        message.published_at = now
        message.updated_at = now
        message.last_error = None
        await self.db.flush()

    async def mark_failed(
        self,
        message_id: uuid.UUID,
        *,
        error: str,
        retry_delay_seconds: int,
    ) -> None:
        message = await self.db.get(OutboxMessage, message_id)
        if message is None:
            return

        now = datetime.now(UTC)
        message.attempts += 1
        message.last_error = error[:4000]

        if message.attempts >= message.max_attempts:
            message.status = "dead"
            message.available_at = now
        else:
            message.status = "pending"
            message.available_at = now + timedelta(seconds=retry_delay_seconds)

        message.updated_at = now
        await self.db.flush()

    async def requeue_stuck_processing(
        self,
        *,
        older_than_seconds: int = 300,
        limit: int = 100,
    ) -> int:
        threshold = datetime.now(UTC) - timedelta(seconds=older_than_seconds)

        stmt = (
            select(OutboxMessage)
            .where(OutboxMessage.status == "processing")
            .where(OutboxMessage.updated_at < threshold)
            .order_by(OutboxMessage.updated_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self.db.execute(stmt)
        messages = list(result.scalars().all())

        now = datetime.now(UTC)
        for message in messages:
            message.status = "pending"
            message.available_at = now
            message.updated_at = now

        await self.db.flush()
        return len(messages)
