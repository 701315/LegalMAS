# src/mas_queue/base_task.py

"""
MASBaseTask — Base class for all Celery tasks in the system.

Purpose:
- Unified implementation of retry policies, DLQ mapping, and Job tracking in DB;
- Standardized logging enriched with deal and document contexts;
- Centralized interception of TransientError / PermanentError /
  QuarantineError / SoftTimeLimitExceeded.

What this class does:
- Intercepts task execution in __call__ and:
    * TransientError and any unexpected exceptions → trigger self.retry()
      with exponential backoff + jitter;
    * PermanentError → skip retries, route to final handling inside
      on_failure(), writing the task to DLQ and marking the Job as DLQ;
    * QuarantineError → skip retries, on_failure() flags the Job as
      COMPLETED with a quarantine flag;
    * SoftTimeLimitExceeded → translated into a PermanentError;
      retrying is skipped as the task has already exceeded its allocated execution time.
- Upon reaching max_retries for transient errors:
    * Task is no longer retried;
    * __call__ propagates the exception upward;
    * Final DLQ record persistence is executed exactly once in on_failure().
- In before_start / on_success / on_failure / on_retry hooks:
    * Logs key task lifecycle events;
    * Updates Job status (RUNNING, COMPLETED, DLQ) and auxiliary metadata
      (worker_id, started_at, finished_at, retry_count, error_details);
    * Updates document_stage_executions (STARTED / SUCCEEDED / FAILED)
      within an independent transaction, detached from the worker's business transaction;
    * Increments Prometheus pipeline metrics (documents_processed_total,
      document_stage_duration_seconds, celery_task_*, etc.).

Stage execution lifecycle policy:
- before_start  → mark_started  (best-effort, independent UoW)
- on_success    → mark_succeeded or mark_failed based on retval status
- on_failure    → mark_failed   (best-effort, independent UoW)

Idempotency guarantees:
- Current execution status is verified before every persistence operation;
- If execution is already in a terminal status (succeeded/failed/cancelled),
  writing is skipped — allowing worker-specific and base task lifecycles to coexist safely.

Retry policy parameters:
TransientError         : up to max_retries=3 attempts, exponential
                         backoff with jitter, capped at retry_backoff_max=300s.
PermanentError         : 1 attempt, routed immediately to DLQ.
SoftTimeLimitExceeded  : handled as PermanentError (1 attempt → DLQ).
Unexpected exceptions  : classified as transient by default.

Backoff progression:
retry 0 →  10s  + jitter [0, 1s]
retry 1 →  30s  + jitter [0, 3s]
retry 2 →  90s  + jitter [0, 9s]
retry 3 → 270s  + jitter [0, 27s]  (capped at 300s)

Jitter (±10% of base value) prevents thundering herd situations during
mass worker restarts.

Architectural guarantees:
- DLQ writing is triggered only at the ultimate failure terminal point — on_failure();
- Re-writing is prevented by a request-local `_dlq_sent` guard flag;
- source_task_id, retry_count, and dedupe_key parameters are resolved from self.request
  and kwargs of the current Celery task execution.

Usage:
- Inherit Celery tasks from this class using the decorator:
      @celery_app.task(base=MASBaseTask, bind=True, queue="default")
      def my_task(self, document_id: str, job_id: str,
                  deal_id: str | None = None):
          ...
- Ensure kwargs contain:
    * job_id              — for status tracking inside the Job table;
    * deal_id             — populates deal_id_var for contextual logging;
    * document_id         — populates document_id_var for contextual logging;
    * stage_execution_id  — for tracking document_stage_executions progress.

Limitations:
- DB operations (Job / DLQ / stage execution updates) execute asynchronously
  inside an isolated event loop using run_async and db_uow();
- This class is business-logic agnostic, tracking task lifecycle state transitions only;
- If SIGKILL (task_time_limit) occurs before on_failure, hooks might be bypassed.
  A background Celery Beat cleaner task should recover Jobs and stage_executions
  stranded in RUNNING/STARTED beyond task_time_limit threshold.
"""

from __future__ import annotations

import random
import time
import uuid
from datetime import UTC, datetime
from typing import Any
from celery import Task
from celery.exceptions import Retry, SoftTimeLimitExceeded
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from core.stage_trace import enrich_trace_with_base_envelope
from core.constants import DocumentStageExecutionStatus, DocumentStatus, JobStatus
from core.exceptions import PermanentError, QuarantineError, TransientError
from core.logging import clear_log_context, get_logger, set_task_context
from db.models.run import Job
from db.repositories.document_stage_execution_repo import DocumentStageExecutionRepository
from db.uow import db_uow
from mas_queue.async_helpers import run_async
from mas_queue.dlq import DLQManager
from mas_queue.outbox_tracker import mark_outbox_processed, mark_outbox_failed


logger = get_logger(__name__)


class MASBaseTask(Task):
    """
    Base Celery task class with retries, DLQ mapping, Job tracking,
    and document_stage_executions state management.
    """

    autoretry_for = ()
    max_retries = 3
    retry_backoff_max = 300
    track_job = True

    # Execution statuses where redundant persistence operations are skipped.
    _TERMINAL_EXECUTION_STATUSES: frozenset[str] = frozenset(
        {
            DocumentStageExecutionStatus.SUCCEEDED.value,
            DocumentStageExecutionStatus.FAILED.value,
            DocumentStageExecutionStatus.CANCELLED.value,
        }
    )

    # Document terminal business statuses representing stage failures.
    _FAILURE_DOCUMENT_STATUSES: frozenset[str] = frozenset(
        {
            DocumentStatus.FAILED.value,
            DocumentStatus.QUARANTINE.value,
        }
    )

    # ── Core lifecycle hooks ──────────────────────────────────────────────────

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """
        Execute task inside the centralized retry/DLQ envelope.

        Orchestrator envelope properties are resolved from kwargs using get() and
        assigned to the class instance, but are NOT popped from kwargs. This ensures
        worker implementations receive stage_execution_id in their own kwargs
        and can invoke mark_started/mark_succeeded manually if necessary.
        """
        self._stage_execution_id: str | None = self._extract_stage_execution_id(kwargs)
        self._orchestration_strategy: str | None = kwargs.get("orchestration_strategy")

        try:
            return self.run(*args, **kwargs)
        except Retry:
            raise
        except (PermanentError, QuarantineError):
            raise
        except SoftTimeLimitExceeded as exc:
            raise PermanentError(f"Task '{self.name}' exceeded soft time limit") from exc
        except (AttributeError, TypeError, NotImplementedError, AssertionError) as exc:
            raise PermanentError(
                f"Task '{self.name}' failed with programming error: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        except TransientError as exc:
            self._handle_transient(exc, kwargs, error_kind="transient")
            raise
        except Exception as exc:
            self._handle_transient(exc, kwargs, error_kind="unexpected")
            raise

    def before_start(
        self,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        """
        Prepare task logging and transactional context before execution starts.

        Triggered by Celery before __call__ and run(). kwargs are complete —
        containing all dispatch context fields, including stage_execution_id.
        """
        delivery_info = getattr(self.request, "delivery_info", None) or {}
        queue: str | None = None
        if isinstance(delivery_info, dict):
            queue = (
                delivery_info.get("routing_key")
                or delivery_info.get("queue")
                or delivery_info.get("exchange")
            )

        set_task_context(
            request_id=kwargs.get("request_id"),
            task_id=task_id,
            tenant_id=kwargs.get("tenant_id"),
            deal_id=kwargs.get("deal_id"),
            run_id=kwargs.get("run_id"),
            document_id=kwargs.get("document_id") or kwargs.get("doc_id"),
            stage=self.name,
            actor_role=kwargs.get("actor_role"),
            worker_hostname=getattr(self.request, "hostname", None),
            queue=queue,
        )

        # Store start performance counter to compute execution duration later
        self._task_started_at: float = time.perf_counter()

        self._stage_execution_id = self._extract_stage_execution_id(kwargs)
        self._orchestration_strategy = kwargs.get("orchestration_strategy")

        setattr(self.request, "_dlq_sent", False)

        logger.info(
            "Task starting",
            task_name=self.name,
            task_id=task_id,
            retry=self.request.retries,
            stage_execution_id=self._stage_execution_id,
        )

        if self._stage_execution_id:
            self._mark_stage_execution_started_best_effort(self._stage_execution_id)

        if self.track_job and "job_id" in kwargs:
            try:
                run_async(
                    self._update_job_status(
                        kwargs["job_id"],
                        JobStatus.RUNNING.value,
                        worker_id=self.request.hostname,
                    )
                )
            except Exception as job_exc:
                logger.warning(
                    "Failed to update job status on start",
                    error=str(job_exc),
                    task_name=self.name,
                )


    def on_success(
        self,
        retval: Any,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        """
        Handle successful task completion.

        'Success' in Celery context indicates run() finished without throwing exceptions.
        However, the worker's business outcome might still be status=failed/quarantine —
        requiring the stage execution to close as FAILED.
        """
        _ = args

        try:
            logger.info("Task completed", task_name=self.name, task_id=task_id)

            # ── Outbox status update ────────────────────────────────────
            try:
                run_async(mark_outbox_processed(self.name, kwargs))
            except Exception as outbox_exc:
                logger.warning(
                    "Failed to update outbox status on success",
                    error=str(outbox_exc),
                    task_name=self.name,
                )
            # ─────────────────────────────────────────────────────────────

            # ─ Prometheus pipeline metrics ───────────────────────────────
            try:
                from ops.metrics import get_metrics  # noqa: PLC0415
                _duration = time.perf_counter() - getattr(self, "_task_started_at", 0.0)
                _m = get_metrics()
                _m.documents_processed_total.labels(
                    stage=self.name, status="succeeded"
                ).inc()
                _m.document_stage_duration_seconds.labels(
                    stage=self.name, status="succeeded"
                ).observe(_duration)
                _m.celery_task_duration_seconds.labels(
                    task_name=self.name, status="succeeded"
                ).observe(_duration)
            except Exception:
                pass  # metrics failure should never interrupt processing
            # ─────────────────────────────────────────────────────────────

            # Read from complete kwargs context supplied to the hook
            stage_execution_id = self._extract_stage_execution_id(kwargs)
            if stage_execution_id:
                terminal_action, payload = self._resolve_stage_execution_completion(
                    retval=retval,
                    kwargs=kwargs,
                )
                if terminal_action == "failed":
                    self._mark_stage_execution_failed_best_effort(
                        stage_execution_id,
                        error_details=payload or {},
                    )
                else:
                    self._mark_stage_execution_succeeded_best_effort(
                        stage_execution_id,
                        result_details=payload,
                    )

            if self.track_job and "job_id" in kwargs:
                try:
                    run_async(
                        self._update_job_status(
                            kwargs["job_id"],
                            JobStatus.COMPLETED.value,
                        )
                    )
                except Exception as job_exc:
                    logger.warning(
                        "Failed to update job status on success",
                        error=str(job_exc),
                        task_name=self.name,
                    )
        finally:
            clear_log_context()



    def on_failure(
        self,
        exc: BaseException,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        einfo: Any,
    ) -> None:
        """
        Handle ultimate task failure.

        This acts as the single terminal failure callback where DLQ routing
        and Job DLQ status updates are performed. For QuarantineError scenarios,
        the Job is resolved as COMPLETED with a quarantine marker.

        The stage execution is closed as FAILED unconditionally.
        """
        _ = args

        try:
            # ── Outbox status update ─────────────────────────────────────
            try:
                error_msg = f"{type(exc).__name__}: {str(exc)}"
                run_async(mark_outbox_failed(self.name, kwargs, error_msg))
            except Exception as outbox_exc:
                logger.warning(
                    "Failed to update outbox status on failure",
                    error=str(outbox_exc),
                    task_name=self.name,
                )
            # ─────────────────────────────────────────────────────────────

            # ── Prometheus pipeline metrics ───────────────────────────────
            try:
                from ops.metrics import get_metrics  # noqa: PLC0415
                _duration = time.perf_counter() - getattr(self, "_task_started_at", 0.0)
                _failure_type = "permanent" if isinstance(exc, PermanentError) else "transient"
                _m = get_metrics()
                _m.documents_processed_total.labels(
                    stage=self.name, status="failed"
                ).inc()
                _m.document_stage_duration_seconds.labels(
                    stage=self.name, status="failed"
                ).observe(_duration)
                _m.celery_task_failures_total.labels(
                    task_name=self.name, failure_type=_failure_type
                ).inc()
                _m.celery_task_duration_seconds.labels(
                    task_name=self.name, status="failed"
                ).observe(_duration)
            except Exception:
                pass  # metrics failure should never interrupt processing
            # ─────────────────────────────────────────────────────────────

            error_info = self._build_error_info(exc, task_id=task_id)
            traceback_text = str(einfo) if einfo is not None else None

            # Always resolve the stage execution as failed on exception
            stage_execution_id = self._extract_stage_execution_id(kwargs)
            if stage_execution_id:
                self._mark_stage_execution_failed_best_effort(
                    stage_execution_id,
                    error_details=self._build_execution_error_details_from_exc(
                        exc=exc,
                        task_id=task_id,
                        kwargs=kwargs,
                    ),
                )

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
                    except Exception as job_exc:
                        logger.warning(
                            "Failed to update job for quarantine",
                            error=str(job_exc),
                            task_name=self.name,
                        )
                return

            failure_type = "permanent" if isinstance(exc, PermanentError) else "transient"

            logger.error(
                "Task failed permanently — sending to DLQ",
                failure_type=failure_type,
                **error_info,
            )

            self._send_to_dlq_once(
                kwargs=kwargs,
                task_type=self.name,
                failure_type=failure_type,
                error_details={**error_info, "traceback": traceback_text},
            )

            if self.track_job and "job_id" in kwargs:
                try:
                    run_async(
                        self._update_job_status(
                            kwargs["job_id"],
                            JobStatus.DLQ.value,
                            error_details={**error_info, "traceback": traceback_text},
                        )
                    )
                except Exception as job_exc:
                    logger.warning(
                        "Failed to update job status for DLQ",
                        error=str(job_exc),
                        task_name=self.name,
                    )
        finally:
            clear_log_context()

    def on_retry(
        self,
        exc: BaseException,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        einfo: Any,
    ) -> None:
        """
        Log Celery task retry event.
        """
        _ = args, kwargs, einfo

        try:
            logger.info(
                "Task retrying",
                task_name=self.name,
                task_id=task_id,
                retry_num=self.request.retries,
                error=str(exc),
            )

            # ── Prometheus pipeline metrics ───────────────────────────────
            try:
                from ops.metrics import get_metrics  # noqa: PLC0415
                get_metrics().celery_task_retries_total.labels(
                    task_name=self.name
                ).inc()
            except Exception:
                pass  # metrics failure should never interrupt processing
            # ─────────────────────────────────────────────────────────────

        finally:
            clear_log_context()

    # ── _handle_transient ─────────────────────────────────────────────────────

    def _handle_transient(
        self,
        exc: Exception,
        kwargs: dict[str, Any],
        *,
        error_kind: str,
    ) -> None:
        """
        Process a retryable failure.

        If retry limits are not exceeded, the task is re-queued and rescheduled
        via self.retry() with calculated exponential backoff + jitter countdown.

        If retry limits are reached, logs the terminal failure.
        Actual DLQ persistence is delegated to on_failure().
        """
        if self.request.retries < self.max_retries:
            delay = self._calculate_backoff(self.request.retries)
            logger.warning(
                "Task failed with retryable error — retrying",
                task_name=self.name,
                retry_num=self.request.retries,
                next_retry_in=delay,
                error_kind=error_kind,
                error=str(exc),
            )

            if self.track_job and "job_id" in kwargs:
                try:
                    run_async(
                        self._update_job_status(
                            kwargs["job_id"],
                            JobStatus.QUEUED.value,
                            retry_count=self.request.retries + 1,
                            error_details={
                                "error_kind": error_kind,
                                "error_type": type(exc).__name__,
                                "error_message": str(exc),
                            },
                        )
                    )
                except Exception as job_exc:
                    logger.warning(
                        "Failed to update job status for retry",
                        error=str(job_exc),
                        task_name=self.name,
                    )

            raise self.retry(exc=exc, countdown=delay)

        error_info = self._build_error_info(exc)
        logger.error(
            "Task failed — max retries exceeded",
            error_kind=error_kind,
            **error_info,
        )

        if self.track_job and "job_id" in kwargs:
            try:
                run_async(
                    self._update_job_status(
                        kwargs["job_id"],
                        JobStatus.DLQ.value,
                        error_details={
                            **error_info,
                            "reason": "max_retries_exceeded",
                            "error_kind": error_kind,
                        },
                    )
                )
            except Exception as job_exc:
                logger.warning(
                    "Failed to update job for DLQ after max retries exceeded",
                    error=str(job_exc),
                    task_name=self.name,
                )

        raise exc

    # ── Stage execution lifecycle helpers ─────────────────────────────────────

    @staticmethod
    def _extract_stage_execution_id(kwargs: dict[str, Any] | None) -> str | None:
        """
        Safely extract stage_execution_id from kwargs.

        Returns a valid non-empty string or None.
        """
        if not kwargs:
            return None
        raw = kwargs.get("stage_execution_id")
        if not isinstance(raw, str):
            return None
        value = raw.strip()
        return value if value else None

    def _resolve_stage_execution_completion(
        self,
        *,
        retval: Any,
        kwargs: dict[str, Any],
    ) -> tuple[str, dict[str, Any] | None]:
        """
        Evaluate how to resolve the stage execution based on the worker return value.

        Returns:
          ("failed",    error_details_dict)
          ("succeeded", result_details | None)

        Rules:
        - Terminal business outcomes are determined by matching retval["status"]
          against self._FAILURE_DOCUMENT_STATUSES;
        - Explainability trace properties (succeeded/skipped/partial) map to
          result_details["status"] and do not affect the row's technical execution status,
          which remains SUCCEEDED/FAILED.
        """
        raw_status: str | None = None
        if isinstance(retval, dict):
            raw = retval.get("status")
            if isinstance(raw, str):
                raw_status = raw.strip().lower()

        if raw_status in self._FAILURE_DOCUMENT_STATUSES:
            return (
                "failed",
                self._build_execution_error_details_from_result(
                    retval=retval,
                    kwargs=kwargs,
                ),
            )

        raw_fragment: dict[str, Any] | None = None
        trace_status = "succeeded"

        if isinstance(retval, dict):
            candidate = retval.get("stage_execution_result_details")
            if isinstance(candidate, dict):
                raw_fragment = candidate

            explicit_trace_status = retval.get("stage_execution_trace_status")
            if isinstance(explicit_trace_status, str):
                explicit_trace_status = explicit_trace_status.strip().lower()
                if explicit_trace_status in {"succeeded", "skipped", "partial"}:
                    trace_status = explicit_trace_status
            elif retval.get("skipped") is True or raw_status == "skipped":
                trace_status = "skipped"
            elif retval.get("partial") is True:
                trace_status = "partial"

        try:
            result_details = enrich_trace_with_base_envelope(
                raw_fragment,
                stage=self.name,
                status=trace_status,
                started_at=getattr(self, "_task_started_at", None),
                task_id=getattr(self.request, "id", None),
            )
        except Exception:
            result_details = raw_fragment

        return "succeeded", result_details

    def _build_execution_error_details_from_result(
        self,
        *,
        retval: Any,
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build error_details for FAILED execution updates from worker output values.
        """
        if isinstance(retval, dict):
            status = retval.get("status")
            reason = (
                retval.get("reason_code")
                or retval.get("quarantine_reason")
                or retval.get("reason")
                or status
                or "stage_terminal_failure"
            )
            message = (
                retval.get("error")
                or retval.get("message")
                or f"Task '{self.name}' completed with terminal status '{status}'"
            )
        else:
            status = None
            reason = "stage_terminal_failure"
            message = f"Task '{self.name}' completed with terminal failure"

        return _compact_dict(
            {
                "stage": self.name,
                "type": "stage_terminal_failure",
                "reason": str(reason),
                "message": str(message),
                "status": status,
                "task_name": self.name,
                "document_id": kwargs.get("document_id"),
                "document_version_id": kwargs.get("document_version_id"),
                "run_id": kwargs.get("run_id"),
            }
        )

    def _build_execution_error_details_from_exc(
        self,
        *,
        exc: BaseException,
        task_id: str,
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build error_details for FAILED execution updates from an exception.
        """
        exc_details = getattr(exc, "details", None)
        exc_details_dict: dict[str, Any] = exc_details if isinstance(exc_details, dict) else {}

        return _compact_dict(
            {
                "stage": exc_details_dict.get("stage") or self.name,
                "type": exc_details_dict.get("type") or type(exc).__name__,
                "reason": exc_details_dict.get("reason") or "task_exception",
                "message": str(exc),
                "task_name": self.name,
                "task_id": task_id,
                "document_id": kwargs.get("document_id"),
                "document_version_id": kwargs.get("document_version_id"),
                "run_id": kwargs.get("run_id"),
            }
        )

    # ── Best-effort sync wrappers (called inside synchronous Celery hooks) ──

    def _mark_stage_execution_started_best_effort(self, stage_execution_id: str) -> None:
        """Update execution record to STARTED state. Non-blocking to the pipeline."""
        try:
            run_async(self._async_mark_execution_started(stage_execution_id))
        except Exception as exc:
            logger.warning(
                "Failed to persist stage execution STARTED",
                task_name=self.name,
                stage_execution_id=stage_execution_id,
                error=str(exc),
            )

    def _mark_stage_execution_succeeded_best_effort(
        self,
        stage_execution_id: str,
        *,
        result_details: dict[str, Any] | None,
    ) -> None:
        """Update execution record to SUCCEEDED state. Non-blocking to the pipeline."""
        try:
            run_async(
                self._async_mark_execution_succeeded(
                    stage_execution_id,
                    result_details=result_details,
                )
            )
        except Exception as exc:
            logger.warning(
                "Failed to persist stage execution SUCCEEDED",
                task_name=self.name,
                stage_execution_id=stage_execution_id,
                error=str(exc),
            )

    def _mark_stage_execution_failed_best_effort(
        self,
        stage_execution_id: str,
        *,
        error_details: dict[str, Any],
    ) -> None:
        """Update execution record to FAILED state. Non-blocking to the pipeline."""
        try:
            run_async(
                self._async_mark_execution_failed(
                    stage_execution_id,
                    error_details=error_details,
                )
            )
        except Exception as exc:
            logger.warning(
                "Failed to persist stage execution FAILED",
                task_name=self.name,
                stage_execution_id=stage_execution_id,
                error=str(exc),
            )

    # ── Async DB helpers (each executed in an isolated UoW transaction) ───

    @classmethod
    async def _async_mark_execution_started(cls, stage_execution_id: str) -> None:
        """
        Mark stage execution record as STARTED in an isolated transaction.

        Skipped if:
        - Record does not exist;
        - Record is already in a terminal state (succeeded/failed/cancelled);
        - Record is already STARTED (idempotent guard).
        """
        execution_uuid = uuid.UUID(stage_execution_id)
        async with db_uow() as uow:
            repo = DocumentStageExecutionRepository(uow.session)
            execution = await repo.get_by_id(execution_uuid)
            if execution is None:
                logger.warning(
                    "Stage execution not found for STARTED update",
                    stage_execution_id=stage_execution_id,
                )
                return
            if execution.status in cls._TERMINAL_EXECUTION_STATUSES:
                return
            if execution.status == DocumentStageExecutionStatus.STARTED.value:
                return
            await repo.mark_started(execution_uuid)

    @classmethod
    async def _async_mark_execution_succeeded(
        cls,
        stage_execution_id: str,
        *,
        result_details: dict[str, Any] | None,
    ) -> None:
        """
        Mark stage execution record as SUCCEEDED in an isolated transaction.

        Explainability special case handling:
        - If execution state is already SUCCEEDED but an enriched trace payload is supplied,
          updates result_details on the existing record.

        This supports our hybrid ownership model:
        - Certain workers trigger mark_succeeded() directly for atomic persistence;
        - MASBaseTask then appends and normalizes the explainability trace.
        """
        execution_uuid = uuid.UUID(stage_execution_id)
        async with db_uow() as uow:
            repo = DocumentStageExecutionRepository(uow.session)
            execution = await repo.get_by_id(execution_uuid)
            if execution is None:
                logger.warning(
                    "Stage execution not found for SUCCEEDED update",
                    stage_execution_id=stage_execution_id,
                )
                return

            # Cancel updates if already FAILED or CANCELLED
            if execution.status in {
                DocumentStageExecutionStatus.FAILED.value,
                DocumentStageExecutionStatus.CANCELLED.value,
            }:
                return

            # Allow updating details if state is already SUCCEEDED
            if execution.status == DocumentStageExecutionStatus.SUCCEEDED.value:
                if result_details is not None:
                    await repo.update_result_details(
                        execution_uuid,
                        result_details=result_details,
                    )
                return

            await repo.mark_succeeded(execution_uuid, result_details=result_details)

    @classmethod
    async def _async_mark_execution_failed(
        cls,
        stage_execution_id: str,
        *,
        error_details: dict[str, Any],
    ) -> None:
        """
        Mark stage execution record as FAILED in an isolated transaction.

        Skipped if record is already in a terminal state.
        """
        execution_uuid = uuid.UUID(stage_execution_id)
        async with db_uow() as uow:
            repo = DocumentStageExecutionRepository(uow.session)
            execution = await repo.get_by_id(execution_uuid)
            if execution is None:
                logger.warning(
                    "Stage execution not found for FAILED update",
                    stage_execution_id=stage_execution_id,
                )
                return
            if execution.status in cls._TERMINAL_EXECUTION_STATUSES:
                return
            await repo.mark_failed(execution_uuid, error_details=error_details)

    # ── Miscellaneous helpers ─────────────────────────────────────────────────

    def _build_error_info(
        self,
        exc: BaseException,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Build a unified dictionary containing failure metadata."""
        info: dict[str, Any] = {
            "task_name": self.name,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "retry_num": self.request.retries,
        }
        if task_id:
            info["task_id"] = task_id
        return info

    def _calculate_backoff(self, retry_num: int) -> float:
        """Calculate exponential backoff with random jitter for retry interval."""
        base = float(min(10 * (3**retry_num), self.retry_backoff_max))
        jitter = random.uniform(0, base * 0.1)
        return base + jitter

    def _send_to_dlq_once(
        self,
        *,
        kwargs: dict[str, Any],
        task_type: str,
        failure_type: str,
        error_details: dict[str, Any],
    ) -> None:
        """Ensure task is written to DLQ at most once during the current request lifecycle."""
        if getattr(self.request, "_dlq_sent", False):
            logger.warning(
                "Duplicate DLQ send skipped",
                task_name=self.name,
                task_id=getattr(self.request, "id", None),
                failure_type=failure_type,
            )
            return

        setattr(self.request, "_dlq_sent", True)
        self._send_to_dlq(
            kwargs=kwargs,
            task_type=task_type,
            failure_type=failure_type,
            error_details=error_details,
        )

    def _send_to_dlq(
        self,
        kwargs: dict[str, Any],
        task_type: str,
        failure_type: str,
        error_details: dict[str, Any],
    ) -> None:
        """Prepare and write a terminal task failure record to DLQ."""
        raw_job_id = kwargs.get("job_id")
        raw_tenant_id = kwargs.get("tenant_id")
        source_task_id = getattr(self.request, "id", None)
        retry_count = int(getattr(self.request, "retries", 0) or 0)

        job_id: uuid.UUID | None = None
        if raw_job_id:
            try:
                job_id = (
                    raw_job_id
                    if isinstance(raw_job_id, uuid.UUID)
                    else uuid.UUID(str(raw_job_id))
                )
            except (ValueError, TypeError) as parse_exc:
                logger.warning(
                    "Failed to parse job_id for DLQ",
                    task_name=self.name,
                    raw_job_id=str(raw_job_id),
                    error=str(parse_exc),
                )

        tenant_id: uuid.UUID | None = None
        if raw_tenant_id is not None:
            try:
                tenant_id = (
                    raw_tenant_id
                    if isinstance(raw_tenant_id, uuid.UUID)
                    else uuid.UUID(str(raw_tenant_id))
                )
            except (ValueError, TypeError) as parse_exc:
                logger.warning(
                    "Failed to parse tenant_id for DLQ",
                    task_name=self.name,
                    raw_tenant_id=str(raw_tenant_id),
                    error=str(parse_exc),
                )

        if tenant_id is None:
            logger.critical(
                "DLQ write skipped: tenant_id could not be resolved from task kwargs",
                task_name=self.name,
                source_task_id=source_task_id,
                task_kwargs_keys=sorted(kwargs.keys()),
            )
            return

        dedupe_parts = [task_type, failure_type]
        if job_id:
            dedupe_parts.append(str(job_id))
        dedupe_key = ":".join(dedupe_parts)

        try:
            run_async(
                self._async_send_to_dlq(
                    job_id=job_id,
                    tenant_id=tenant_id,
                    task_type=task_type,
                    failure_type=failure_type,
                    error_details=error_details,
                    source_task_id=source_task_id,
                    dedupe_key=dedupe_key,
                    retry_count=retry_count,
                )
            )
        except Exception as dlq_exc:
            logger.critical(
                "CRITICAL: Failed to write to DLQ",
                task_name=self.name,
                source_task_id=source_task_id,
                dedupe_key=dedupe_key,
                retry_count=retry_count,
                error=str(dlq_exc),
                original_error=error_details,
            )

    @staticmethod
    async def _async_send_to_dlq(
        job_id: uuid.UUID | None,
        tenant_id: uuid.UUID,
        task_type: str,
        failure_type: str,
        error_details: dict[str, Any],
        *,
        source_task_id: str | None = None,
        dedupe_key: str | None = None,
        retry_count: int = 0,
    ) -> None:
        """Asynchronously persist failure details to DLQ using a dedicated Unit of Work transaction."""
        async with db_uow() as uow:
            db: AsyncSession = uow.session
            dlq = DLQManager(db)
            await dlq.send_to_dlq(
                task_type=task_type,
                failure_type=failure_type,
                job_id=job_id,
                tenant_id=tenant_id,
                source_task_id=source_task_id,
                dedupe_key=dedupe_key,
                error_details=error_details,
                retry_count=retry_count,
            )

    @staticmethod
    async def _update_job_status(
        job_id: str,
        status: str,
        worker_id: str | None = None,
        error_details: dict[str, Any] | None = None,
        retry_count: int | None = None,
    ) -> None:
        """Asynchronously update Job status metrics and executing worker metadata."""
        async with db_uow() as uow:
            db: AsyncSession = uow.session

            values: dict[str, Any] = {"status": status}
            if worker_id:
                values["worker_id"] = worker_id
            if status == JobStatus.RUNNING.value:
                values["started_at"] = datetime.now(UTC)
            if status in (
                JobStatus.COMPLETED.value,
                JobStatus.FAILED.value,
                JobStatus.DLQ.value,
            ):
                values["finished_at"] = datetime.now(UTC)
            if error_details:
                values["error_details"] = error_details
            if retry_count is not None:
                values["retry_count"] = retry_count

            stmt = sa_update(Job).where(Job.id == uuid.UUID(job_id)).values(**values)
            await db.execute(stmt)


# ── Module-level helpers ──────────────────────────────────────────────────────

def _compact_dict(values: dict[str, Any]) -> dict[str, Any]:
    """Purge None values from a dictionary to keep JSON payload clean."""
    return {key: val for key, val in values.items() if val is not None}
