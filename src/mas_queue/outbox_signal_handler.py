# src/mas_queue/outbox_signal_handler.py

"""
Celery signal handlers to update Outbox message status after task execution.

This ensures that outbox_messages.status transitions from 'published' to 'processed'
automatically when a Celery task completes successfully or fails.
"""

from __future__ import annotations

import json
from celery import signals
from core.logging import get_logger
from db.uow import db_uow
from db.repositories.outbox import OutboxRepository
from sqlalchemy import select
from db.models.outbox import OutboxMessage

logger = get_logger(__name__)


def _extract_outbox_info_from_task(task_name, task_id, kwargs):
    """
    Try to match a Celery task execution back to its outbox message.
    
    This is heuristic-based since Celery doesn't preserve outbox message ID.
    We match by:
    1. task_name
    2. run_id / deal_id from kwargs
    3. recent published_at timestamp (within last 10 minutes)
    """
    run_id = kwargs.get('run_id')
    deal_id = kwargs.get('deal_id')
    
    if not run_id:
        return None
    
    # Build aggregate_id patterns to search
    # Outbox aggregate_id can be: run_id, or f"{run_id}:{locale}", etc.
    patterns = [
        run_id,
        f"{run_id}:en",
        f"{run_id}:ru",
    ]
    
    return {
        'task_name': task_name,
        'run_id': run_id,
        'deal_id': deal_id,
        'patterns': patterns,
    }


@signals.task_success.connect(weak=False)
def on_task_success(sender=None, result=None, **kwargs):
    """
    Mark outbox message as 'processed' when task succeeds.
    """
    task_name = sender.name if sender else None
    task_id = kwargs.get('task_id')
    task_kwargs = kwargs.get('kwargs', {})
    
    if not task_name:
        return
    
    info = _extract_outbox_info_from_task(task_name, task_id, task_kwargs)
    if not info:
        return
    
    async def _mark_processed():
        async with db_uow() as uow:
            repo = OutboxRepository(uow.session)
            
            # Find matching outbox message
            for pattern in info['patterns']:
                message = await uow.session.execute(
                    select(OutboxMessage).where(
                        OutboxMessage.task_name == task_name,
                        OutboxMessage.aggregate_id.like(f'%{pattern}%'),
                        OutboxMessage.status == 'published',
                    )
                )
                msg = message.scalar_one_or_none()
                
                if msg:
                    msg.status = 'processed'
                    await uow.session.commit()
                    logger.info(
                        "Outbox message marked as processed",
                        outbox_message_id=str(msg.id),
                        task_name=task_name,
                        task_id=task_id,
                    )
                    return
    
    try:
        import asyncio
        asyncio.run(_mark_processed())
    except Exception as e:
        logger.error(
            "Failed to mark outbox message as processed",
            task_name=task_name,
            task_id=task_id,
            error=str(e),
        )


@signals.task_failure.connect(weak=False)
def on_task_failure(sender=None, exception=None, **kwargs):
    """
    Mark outbox message as 'failed' when task fails.
    """
    task_name = sender.name if sender else None
    task_id = kwargs.get('task_id')
    task_kwargs = kwargs.get('kwargs', {})
    
    if not task_name:
        return
    
    info = _extract_outbox_info_from_task(task_name, task_id, task_kwargs)
    if not info:
        return
    
    async def _mark_failed():
        async with db_uow() as uow:
            repo = OutboxRepository(uow.session)
            
            for pattern in info['patterns']:
                message = await uow.session.execute(
                    select(OutboxMessage).where(
                        OutboxMessage.task_name == task_name,
                        OutboxMessage.aggregate_id.like(f'%{pattern}%'),
                        OutboxMessage.status == 'published',
                    )
                )
                msg = message.scalar_one_or_none()
                
                if msg:
                    msg.status = 'failed'
                    msg.last_error = str(exception)
                    await uow.session.commit()
                    logger.warning(
                        "Outbox message marked as failed",
                        outbox_message_id=str(msg.id),
                        task_name=task_name,
                        task_id=task_id,
                        error=str(exception),
                    )
                    return
    
    try:
        import asyncio
        asyncio.run(_mark_failed())
    except Exception as e:
        logger.error(
            "Failed to mark outbox message as failed",
            task_name=task_name,
            task_id=task_id,
            error=str(e),
        )


