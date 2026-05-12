# src/services/outbox_service.py

from __future__ import annotations

from datetime import UTC, datetime

from db.repositories.outbox import OutboxRepository


class OutboxService:
    def __init__(self, db) -> None:
        self.repo = OutboxRepository(db)

    async def enqueue_task(
        self,
        *,
        task_name: str,
        payload: dict,
        aggregate_type: str,
        aggregate_id: str,
        dedup_key: str | None = None,
        headers: dict | None = None,
        max_attempts: int = 25,
        available_at: datetime | None = None,
    ) -> str:
        if dedup_key:
            existing = await self.repo.get_by_dedup_key(dedup_key)
            if existing is not None:
                return str(existing.id)

        message = await self.repo.create(
            task_name=task_name,
            payload=payload,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            dedup_key=dedup_key,
            headers=headers or {},
            max_attempts=max_attempts,
            available_at=available_at or datetime.now(UTC),
        )
        return str(message.id)


        