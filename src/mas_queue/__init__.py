# src/mas_queue/__init__.py

"""
Queue infrastructure: Celery app, base task, DLQ, helpers.
"""

from .base_task import MASBaseTask
from .celery_app import celery_app

__all__ = ["celery_app", "MASBaseTask"]
