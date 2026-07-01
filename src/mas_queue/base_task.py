# src/mas_queue/base_task.py

"""
MASBaseTask — базовый класс для всех Celery-задач в системе.

Назначение:
- единая реализация политики ретраев, DLQ и трекинга Job в БД;
- стандартное логирование с контекстом сделки и документа;
- централизованная обработка TransientError / PermanentError /
  QuarantineError / SoftTimeLimitExceeded.

Что делает этот класс:
- перехватывает выполнение задачи в __call__ и:
    * TransientError и любые неизвестные исключения → self.retry()
      с экспоненциальным backoff + jitter;
    * PermanentError → без ретраев, финальная обработка идёт через
      on_failure(), где задача пишется в DLQ и Job помечается как DLQ;
    * QuarantineError → без ретраев, on_failure() помечает Job как
      COMPLETED с флагом quarantine;
    * SoftTimeLimitExceeded → превращается в PermanentError;
      ретраить бессмысленно, задача уже превысила допустимое время
      выполнения.
- при достижении max_retries для транзиентных ошибок:
    * задача больше не ретраится;
    * __call__ пробрасывает исключение дальше;
    * финальная запись в DLQ выполняется ровно один раз в on_failure().
- в before_start / on_success / on_failure / on_retry:
    * логирует ключевые события жизненного цикла таски;
    * обновляет статус Job (RUNNING, COMPLETED, DLQ) и
      вспомогательные поля (worker_id, started_at, finished_at,
      retry_count, error_details);
    * обновляет document_stage_executions (STARTED / SUCCEEDED / FAILED)
      в отдельной транзакции, независимо от бизнес-транзакции worker'а.
    * инкрементирует Prometheus pipeline metrics (documents_processed_total,
      document_stage_duration_seconds, celery_task_* и т.д.).

Политика stage execution lifecycle:
- before_start  → mark_started  (best-effort, отдельный UoW)
- on_success    → mark_succeeded или mark_failed в зависимости от retval
- on_failure    → mark_failed   (best-effort, отдельный UoW)

Идемпотентность:
- перед каждой записью читается текущий статус execution;
- если execution уже в terminal статусе (succeeded/failed/cancelled),
  повторная запись пропускается — worker-specific lifecycle и base task
  lifecycle могут оба вызываться без конфликта.

Политика ретраев:
TransientError         : до max_retries=3 попыток, экспоненциальный
                         backoff с jitter, потолок retry_backoff_max=300 с.
PermanentError         : 1 попытка, затем сразу DLQ.
SoftTimeLimitExceeded  : трактуется как PermanentError (1 попытка → DLQ).
Неизвестные ошибки     : считаются транзиентными.

Backoff:
retry 0 →  10 с  + jitter [0, 1 с]
retry 1 →  30 с  + jitter [0, 3 с]
retry 2 →  90 с  + jitter [0, 9 с]
retry 3 → 270 с  + jitter [0, 27 с]  (потолок 300 с)

Jitter (±10 % от base) предотвращает thundering herd при массовом
рестарте воркеров.

Архитектурные гарантии:
- запись в DLQ выполняется только в финальной точке отказа — on_failure();
- от повторной записи защищает request-local флаг _dlq_sent;
- source_task_id, retry_count и dedupe_key формируются из self.request
  и kwargs текущей Celery-задачи.

Как использовать:
- наследовать Celery-таски от этого класса через декоратор:
      @celery_app.task(base=MASBaseTask, bind=True, queue="default")
      def my_task(self, document_id: str, job_id: str,
                  deal_id: str | None = None):
          ...
- передавать в kwargs:
    * job_id              — для трекинга статуса в таблице Job;
    * deal_id             — заполняет deal_id_var для логгера;
    * document_id         — заполняет document_id_var для логгера;
    * stage_execution_id  — для трекинга document_stage_executions.

Ограничения:
- все операции с БД (Job / DLQ / stage execution) выполняются асинхронно
  внутри отдельного event loop через run_async и db_uow();
- класс не знает бизнес-логики задач, только управляет их
  жизненным циклом и побочными эффектами;
- если SIGKILL (task_time_limit) срабатывает до on_failure,
  хуки могут не выполниться. Для таких случаев рекомендуется
  периодическая Celery Beat задача, которая переводит Job и
  stage_executions, застрявшие в RUNNING/STARTED дольше task_time_limit,
  в DLQ / FAILED.
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

logger = get_logger(__name__)


class MASBaseTask(Task):
    """
    Базовый класс Celery-тасок с политикой ретраев, DLQ и трекингом Job
    и document_stage_executions.
    """

    autoretry_for = ()
    max_retries = 3
    retry_backoff_max = 300
    track_job = True

    # Статусы, при которых повторная запись в execution пропускается.
    _TERMINAL_EXECUTION_STATUSES: frozenset[str] = frozenset(
        {
            DocumentStageExecutionStatus.SUCCEEDED.value,
            DocumentStageExecutionStatus.FAILED.value,
            DocumentStageExecutionStatus.CANCELLED.value,
        }
    )

    # Бизнес-статусы документа, означающие terminal failure на уровне stage.
    _FAILURE_DOCUMENT_STATUSES: frozenset[str] = frozenset(
        {
            DocumentStatus.FAILED.value,
            DocumentStatus.QUARANTINE.value,
        }
    )

    # ── Core lifecycle hooks ──────────────────────────────────────────────────

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """
        Выполнить задачу внутри единого retry/DLQ envelope.

        Envelope-поля оркестратора читаются из kwargs через get() и
        сохраняются в self, но НЕ удаляются из kwargs. Это гарантирует,
        что worker-функции получают stage_execution_id в своих kwargs/аргументах
        и могут вызывать mark_started/mark_succeeded самостоятельно.
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
        Подготовить контекст перед стартом задачи.

        Вызывается Celery до __call__ и до run(). kwargs здесь полные —
        содержат все поля, включая stage_execution_id.
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

        # Запомнить время старта для расчёта duration в on_success / on_failure.
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
        Обработать успешное завершение задачи.

        «Успешное» с точки зрения Celery означает, что run() не бросил
        исключение. Бизнес-логика worker'а может всё равно вернуть
        status=failed/quarantine — в таком случае execution закрывается
        как FAILED.
        """
        _ = args

        try:
            logger.info("Task completed", task_name=self.name, task_id=task_id)

            # ── Prometheus pipeline metrics ───────────────────────────────
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
                pass  # metrics never break pipeline
            # ─────────────────────────────────────────────────────────────

            # Читаем из kwargs (они полные в хуках on_success/on_failure).
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
        Обработать окончательный провал задачи.

        Это единая финальная точка отказа, где выполняется запись в DLQ
        и перевод Job в статус DLQ. Для QuarantineError вместо этого
        Job помечается как COMPLETED с quarantine-флагом.

        Stage execution закрывается как FAILED безусловно при любом
        типе исключения.
        """
        _ = args

        try:
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
                pass  # metrics never break pipeline
            # ─────────────────────────────────────────────────────────────

            error_info = self._build_error_info(exc, task_id=task_id)
            traceback_text = str(einfo) if einfo is not None else None

            # Закрыть stage execution независимо от типа исключения.
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
        Залогировать событие retry.
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
                pass  # metrics never break pipeline
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
        Обработать retryable-ошибку.

        Если лимит ретраев ещё не исчерпан, задача переводится обратно в QUEUED
        и планируется на повторный запуск через self.retry() с backoff+jitter.

        Если лимит исчерпан, метод только логирует событие и обновляет Job.
        Финальная запись в DLQ выполняется позже в on_failure().
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
        Безопасно извлечь stage_execution_id из kwargs.

        Возвращает непустую строку или None.
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
        Определить, как закрыть stage execution по результату worker-а.

        Возвращает:
          ("failed",    error_details_dict)
          ("succeeded", result_details | None)

        Важно:
        - terminal failure по-прежнему определяется по retval["status"]
          в _FAILURE_DOCUMENT_STATUSES;
        - explainability trace status (succeeded/skipped/partial)
          живёт внутри result_details["status"] и не меняет
          технический terminal status execution row, который остаётся
          SUCCEEDED/FAILED.
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
        Построить error_details для execution FAILED из retval worker-а.
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
        Построить error_details для execution FAILED из исключения.
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

    # ── Best-effort sync wrappers (вызываются из синхронных хуков Celery) ─────

    def _mark_stage_execution_started_best_effort(self, stage_execution_id: str) -> None:
        """Обновить execution как STARTED. Ошибка не прерывает pipeline."""
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
        """Обновить execution как SUCCEEDED. Ошибка не прерывает pipeline."""
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
        """Обновить execution как FAILED. Ошибка не прерывает pipeline."""
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

    # ── Async DB helpers (каждый в своём UoW → отдельный commit) ─────────────

    @classmethod
    async def _async_mark_execution_started(cls, stage_execution_id: str) -> None:
        """
        Пометить execution как STARTED в отдельной транзакции.

        Пропускается если:
        - execution не найден
        - уже в terminal статусе (succeeded/failed/cancelled)
        - уже в STARTED (идемпотентность)
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
        Пометить execution как SUCCEEDED в отдельной транзакции.

        В Explainability flow допускается special-case:
        - если execution уже SUCCEEDED, но у нас появился enriched trace,
          мы обновляем result_details поверх существующей записи.

        Это нужно для hybrid ownership model:
        - некоторые worker'ы сами делают mark_succeeded() ради атомарности;
        - MASBaseTask затем дописывает/нормализует explainability trace.
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

            # Если уже FAILED/CANCELLED — не трогаем.
            if execution.status in {
                DocumentStageExecutionStatus.FAILED.value,
                DocumentStageExecutionStatus.CANCELLED.value,
            }:
                return

            # Если уже SUCCEEDED — допускаем update trace payload.
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
        Пометить execution как FAILED в отдельной транзакции.

        Пропускается если execution уже в terminal статусе.
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

    # ── Общие helpers ─────────────────────────────────────────────────────────

    def _build_error_info(
        self,
        exc: BaseException,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Построить унифицированный словарь с данными об ошибке."""
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
        """Рассчитать exponential backoff с jitter для retry."""
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
        """Отправить запись в DLQ не более одного раза за lifecycle текущего request."""
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
        """Подготовить и записать событие в DLQ."""
        raw_job_id = kwargs.get("job_id")
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

        dedupe_parts = [task_type, failure_type]
        if job_id:
            dedupe_parts.append(str(job_id))
        dedupe_key = ":".join(dedupe_parts)

        try:
            run_async(
                self._async_send_to_dlq(
                    job_id=job_id,
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
        task_type: str,
        failure_type: str,
        error_details: dict[str, Any],
        *,
        source_task_id: str | None = None,
        dedupe_key: str | None = None,
        retry_count: int = 0,
    ) -> None:
        """Асинхронно записать событие в DLQ через Unit of Work."""
        async with db_uow() as uow:
            db: AsyncSession = uow.session
            dlq = DLQManager(db)
            await dlq.send_to_dlq(
                task_type=task_type,
                failure_type=failure_type,
                job_id=job_id,
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
        """Асинхронно обновить статус Job и связанные метаданные."""
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
    """Убрать None-значения из словаря для чистоты JSON payload."""
    return {key: val for key, val in values.items() if val is not None}

