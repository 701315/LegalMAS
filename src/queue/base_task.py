"""
MASBaseTask — base class for all Celery tasks in the system.

Provides:
- Typed retry: TransientError -> retry with backoff, PermanentError -> DLQ
- Job status tracking in PostgreSQL
- Structured logging with context
- DLQ integration for permanently failed tasks

Retry lifecycle:
    __call__() intercepts exceptions BEFORE Celery sees them.
    - TransientError / unknown  → self.retry() with exponential backoff
    - PermanentError            → re-raise, on_failure → DLQ
    - QuarantineError           → re-raise, on_failure → COMPLETED + quarantine
    on_failure() is called ONLY for the final failure (retries exhausted).
    on_retry()   is called by Celery each time self.retry() is raised.
"""

import traceback
import uuid
from datetime import UTC, datetime

from celery import Task
from celery.exceptions import Retry

from src.core.constants import JobStatus
from src.core.exceptions import PermanentError, QuarantineError, TransientError
from src.core.logging import deal_id_var, document_id_var, get_logger
from src.db.models.run import Job
from src.db.session import get_session
from src.queue.async_helpers import run_async
from src.queue.dlq import DLQManager

logger = get_logger(__name__)


class MASBaseTask(Task):
    """
    Base task class with retry policy, DLQ, and job tracking.

    Retry policy:
        TransientError : max 3 attempts, exponential backoff, max 300 sec
        PermanentError : 1 attempt, immediately to DLQ
        Unknown errors : treated as transient

    Usage:
        @celery_app.task(base=MASBaseTask, bind=True, queue="default")
        def my_task(self, document_id: str, job_id: str):
            ...  # raise TransientError / PermanentError as needed
    """

    autoretry_for = ()
    max_retries = 3
    retry_backoff_max = 300  # seconds

    track_job = True

    # ------------------------------------------------------------------
    # Core lifecycle
    # ------------------------------------------------------------------

    def __call__(self, *args, **kwargs):
        """
        Wraps task execution. Intercepts exceptions and routes them:
        - TransientError / unknown → self.retry() with backoff
        - PermanentError           → on_failure → DLQ
        - QuarantineError          → on_failure → quarantine
        - Retry                    → re-raise as-is (already scheduled)
        """
        try:
            return self.run(*args, **kwargs)
        except Retry:
            raise
        except (PermanentError, QuarantineError):
            raise
        except TransientError as exc:
            self._handle_transient(exc, kwargs)
        except Exception as exc:
            self._handle_transient(exc, kwargs)

    def _handle_transient(self, exc: Exception, kwargs: dict) -> None:
        """Retry with backoff, or DLQ if retries exhausted."""
        if self.request.retries < self.max_retries:
            delay = self._calculate_backoff(self.request.retries)
            logger.warning(
                "Task failed with transient error — retrying",
                task_name=self.name,
                retry_num=self.request.retries,
                next_retry_in=delay,
                error=str(exc),
            )
            if self.track_job and "job_id" in kwargs:
                try:
                    run_async(
                        self._update_job_status(
                            kwargs["job_id"],
                            JobStatus.QUEUED.value,
                            retry_count=self.request.retries + 1,
                        )
                    )
                except Exception as e:
                    logger.warning("Failed to update job status for retry", error=str(e))

            raise self.retry(exc=exc, countdown=delay)
        else:
            error_info = self._build_error_info(exc)
            logger.error(
                "Task failed — max retries exceeded — sending to DLQ",
                **error_info,
            )
            self._send_to_dlq(
                kwargs=kwargs,
                task_type=self.name,
                failure_type="transient",
                error_details={**error_info, "reason": "max_retries_exceeded"},
            )
            if self.track_job and "job_id" in kwargs:
                try:
                    run_async(
                        self._update_job_status(
                            kwargs["job_id"],
                            JobStatus.DLQ.value,
                            error_details=error_info,
                        )
                    )
                except Exception as e:
                    logger.warning("Failed to update job for DLQ", error=str(e))
            raise

    # ------------------------------------------------------------------
    # Celery hooks
    # ------------------------------------------------------------------

    def before_start(self, task_id, args, kwargs):
        if "deal_id" in kwargs:
            deal_id_var.set(kwargs["deal_id"])
        if "document_id" in kwargs:
            document_id_var.set(kwargs["document_id"])

        logger.info(
            "Task starting",
            task_name=self.name,
            task_id=task_id,
            retry=self.request.retries,
        )

        if self.track_job and "job_id" in kwargs:
            try:
                run_async(
                    self._update_job_status(
                        kwargs["job_id"],
                        JobStatus.RUNNING.value,
                        worker_id=self.request.hostname,
                    )
                )
            except Exception as e:
                logger.warning("Failed to update job status on start", error=str(e))

    def on_success(self, retval, task_id, args, kwargs):
        logger.info("Task completed", task_name=self.name, task_id=task_id)

        if self.track_job and "job_id" in kwargs:
            try:
                run_async(
                    self._update_job_status(
                        kwargs["job_id"],
                        JobStatus.COMPLETED.value,
                    )
                )
            except Exception as e:
                logger.warning("Failed to update job status on success", error=str(e))

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """
        Called ONLY for final failure.
        No retry logic here — only DLQ write and Job status update.
        """
        error_info = self._build_error_info(exc, task_id=task_id)

        if isinstance(exc, QuarantineError):
            logger.warning("Task resulted in quarantine", **error_info)
            if self.track_job and "job_id" in kwargs:
                try:
                    run_async(
                        self._update_job_status(
                            kwargs["job_id"],
                            JobStatus.COMPLETED.value,
                            error_details={"quarantine": True, **error_info},
                        )
                    )
                except Exception as e:
                    logger.warning("Failed to update job for quarantine", error=str(e))
            return

        failure_type = "permanent" if isinstance(exc, PermanentError) else "transient"
        logger.error(
            "Task failed permanently — sending to DLQ",
            failure_type=failure_type,
            **error_info,
        )
        self._send_to_dlq(
            kwargs=kwargs,
            task_type=self.name,
            failure_type=failure_type,
            error_details={**error_info, "traceback": traceback.format_exc()},
        )
        if self.track_job and "job_id" in kwargs:
            try:
                run_async(
                    self._update_job_status(
                        kwargs["job_id"],
                        JobStatus.DLQ.value,
                        error_details=error_info,
                    )
                )
            except Exception as e:
                logger.warning("Failed to update job status for DLQ", error=str(e))

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        logger.info(
            "Task retrying",
            task_name=self.name,
            task_id=task_id,
            retry_num=self.request.retries,
            error=str(exc),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_error_info(self, exc: Exception, task_id: str | None = None) -> dict:
        info = {
            "task_name": self.name,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "retry_num": self.request.retries,
        }
        if task_id:
            info["task_id"] = task_id
        return info

    def _calculate_backoff(self, retry_num: int) -> float:
        """
        retry 0 →  10 sec
        retry 1 →  30 sec
        retry 2 →  90 sec
        retry 3 → 270 sec  (max 300)
        """
        return float(min(10 * (3**retry_num), self.retry_backoff_max))

    def _send_to_dlq(
        self,
        kwargs: dict,
        task_type: str,
        failure_type: str,
        error_details: dict,
    ) -> None:
        job_id = kwargs.get("job_id")
        try:
            run_async(
                self._async_send_to_dlq(
                    job_id=uuid.UUID(job_id) if job_id else None,
                    task_type=task_type,
                    failure_type=failure_type,
                    error_details=error_details,
                )
            )
        except Exception as e:
            logger.critical(
                "CRITICAL: Failed to write to DLQ",
                error=str(e),
                original_error=error_details,
            )

    @staticmethod
    async def _async_send_to_dlq(
        job_id: uuid.UUID | None,
        task_type: str,
        failure_type: str,
        error_details: dict,
    ) -> None:
        async with get_session() as session:
            dlq = DLQManager(session)
            await dlq.send_to_dlq(
                task_type=task_type,
                failure_type=failure_type,
                job_id=job_id,
                error_details=error_details,
            )

    @staticmethod
    async def _update_job_status(
        job_id: str,
        status: str,
        worker_id: str | None = None,
        error_details: dict | None = None,
        retry_count: int | None = None,
    ) -> None:
        from sqlalchemy import update as sa_update

        async with get_session() as session:
            values: dict = {"status": status}
            if worker_id:
                values["worker_id"] = worker_id
            if status == JobStatus.RUNNING.value:
                values["started_at"] = datetime.now(UTC)
            if status in (JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.DLQ.value):
                values["finished_at"] = datetime.now(UTC)
            if error_details:
                values["error_details"] = error_details
            if retry_count is not None:
                values["retry_count"] = retry_count

            stmt = sa_update(Job).where(Job.id == uuid.UUID(job_id)).values(**values)
            await session.execute(stmt)
