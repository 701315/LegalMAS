"""
Test tasks for verifying Celery + MASBaseTask + DLQ integration.

These tasks are registered ONLY during test runs via conftest.py fixture.
They are NOT part of the production worker registry.
"""

from src.core.exceptions import PermanentError, TransientError
from src.core.logging import get_logger
from src.mas_queue.base_task import MASBaseTask
from src.mas_queue.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(base=MASBaseTask, bind=True, name="test.success_task", track_job=False)
def success_task(self, message: str = "hello") -> dict:
    """A simple task that always succeeds."""
    logger.info("Success task executing", message=message)
    return {"status": "ok", "message": message}


@celery_app.task(base=MASBaseTask, bind=True, name="test.transient_fail_task", track_job=False)
def transient_fail_task(self, fail_until_retry: int = 2) -> dict:
    """
    Fails with TransientError for the first N retries, then succeeds.
    """
    current_retry = self.request.retries
    logger.info(
        "Transient fail task executing",
        retry=current_retry,
        fail_until=fail_until_retry,
    )
    if current_retry < fail_until_retry:
        raise TransientError(
            f"Simulated transient error (retry {current_retry})",
            details={"retry": current_retry},
        )
    return {"status": "ok", "retries_needed": current_retry}


@celery_app.task(base=MASBaseTask, bind=True, name="test.permanent_fail_task", track_job=False)
def permanent_fail_task(self) -> dict:
    """Always fails with PermanentError — goes to DLQ."""
    logger.info("Permanent fail task executing")
    raise PermanentError(
        "Simulated permanent error",
        details={"reason": "test"},
    )


@celery_app.task(base=MASBaseTask, bind=True, name="test.add_numbers", track_job=False)
def add_numbers(self, a: int, b: int) -> dict:
    """Simple addition task for basic verification."""
    return {"result": a + b}
