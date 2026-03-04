"""
Queue infrastructure: Celery app, base task, DLQ, helpers.
"""

from .base_task import MASBaseTask
from mas_queue.celery_app import celery_app

__all__ = ["celery_app", "MASBaseTask"]
