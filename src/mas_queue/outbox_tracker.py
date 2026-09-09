"""
Outbox message status tracker for MASBaseTask.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.models.outbox import OutboxMessage
from db.uow import db_uow

logger = get_logger(__name__)


def _build_aggregate_id_patterns(task_kwargs: dict[str, Any]) -> list[str]:
    """Build aggregate_id patterns to match outbox message from task kwargs."""
    run_id = task_kwargs.get('run_id')
    locale = task_kwargs.get('locale')
    content_version = task_kwargs.get('content_version')
    
    if not run_id:
        return []
    
    patterns = [str(run_id)]
    if locale:
        patterns.append(f"{run_id}:{locale}")
        if content_version:
            patterns.append(f"{run_id}:{locale}:{content_version}")
    return patterns


async def mark_outbox_processed(
    task_name: str,
    task_kwargs: dict[str, Any],
) -> bool:
    """Mark matching outbox message as 'processed' after successful task."""
    patterns = _build_aggregate_id_patterns(task_kwargs)
    if not patterns:
        return False
    
    async with db_uow() as uow:
        db: AsyncSession = uow.session
        for pattern in patterns:
            stmt = (
                select(OutboxMessage)
                .where(
                    OutboxMessage.task_name == task_name,
                    OutboxMessage.aggregate_id.like(f"%{pattern}%"),
                    OutboxMessage.status == "published",
                    OutboxMessage.published_at > datetime.now(UTC) - timedelta(minutes=10),
                )
                .limit(1)
            )
            result = await db.execute(stmt)
            message = result.scalar_one_or_none()
            
            if message:
                message.status = "processed"
                await db.commit()
                logger.info(
                    "Outbox message marked as processed",
                    outbox_message_id=str(message.id),
                    task_name=task_name,
                )
                return True
    return False


async def mark_outbox_failed(
    task_name: str,
    task_kwargs: dict[str, Any],
    error_message: str,
) -> bool:
    """Mark matching outbox message as 'failed' after task failure."""
    patterns = _build_aggregate_id_patterns(task_kwargs)
    if not patterns:
        return False
    
    async with db_uow() as uow:
        db: AsyncSession = uow.session
        for pattern in patterns:
            stmt = (
                select(OutboxMessage)
                .where(
                    OutboxMessage.task_name == task_name,
                    OutboxMessage.aggregate_id.like(f"%{pattern}%"),
                    OutboxMessage.status == "published",
                    OutboxMessage.published_at > datetime.now(UTC) - timedelta(minutes=10),
                )
                .limit(1)
            )
            result = await db.execute(stmt)
            message = result.scalar_one_or_none()
            
            if message:
                message.status = "failed"
                message.last_error = error_message[:4000]
                await db.commit()
                logger.warning(
                    "Outbox message marked as failed",
                    outbox_message_id=str(message.id),
                    task_name=task_name,
                )
                return True
    return False