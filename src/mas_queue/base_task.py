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
      retry_count, error_details).

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
    * job_id       — для трекинга статуса в таблице Job;
    * deal_id      — заполняет deal_id_var для логгера;
    * document_id  — заполняет document_id_var для логгера.

Ограничения:
- все операции с БД (Job / DLQ) выполняются асинхронно внутри
  отдельного event loop через run_async и db_uow();
- класс не знает бизнес-логики задач, только управляет их
  жизненным циклом и побочными эффектами;
- если SIGKILL (task_time_limit) срабатывает до on_failure,
  хуки могут не выполниться. Для таких случаев рекомендуется
  периодическая Celery Beat задача, которая переводит Job,
  застрявшие в статусе RUNNING дольше task_time_limit, в DLQ.
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime
from typing import Any

from celery import Task
from celery.exceptions import Retry, SoftTimeLimitExceeded
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import JobStatus
from core.exceptions import PermanentError, QuarantineError, TransientError
from core.logging import deal_id_var, document_id_var, get_logger
from db.models.run import Job
from db.uow import db_uow
from mas_queue.async_helpers import run_async
from mas_queue.dlq import DLQManager

logger = get_logger(__name__)


class MASBaseTask(Task):
    """
    Базовый класс Celery-тасок с политикой ретраев, DLQ и трекингом Job.
    """

    autoretry_for = ()
    max_retries = 3
    retry_backoff_max = 300
    track_job = True

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """
        Выполнить задачу внутри единого retry/DLQ envelope.

        Envelope-поля оркестратора извлекаются из kwargs и сохраняются в self,
        чтобы сигнатуры worker-функций оставались чистыми.
        """
        self._stage_execution_id: str | None = kwargs.pop("stage_execution_id", None)
        self._orchestration_strategy: str | None = kwargs.pop(
            "orchestration_strategy", None
        )

        try:
            return self.run(*args, **kwargs)
        except Retry:
            raise
        except (PermanentError, QuarantineError):
            raise
        except SoftTimeLimitExceeded as exc:
            raise PermanentError(
                f"Task '{self.name}' exceeded soft time limit"
            ) from exc
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

    def before_start(
        self,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        """
        Подготовить контекст перед стартом задачи.
        """
        if "deal_id" in kwargs:
            deal_id_var.set(kwargs["deal_id"])
        if "document_id" in kwargs:
            document_id_var.set(kwargs["document_id"])
        elif "doc_id" in kwargs:
            document_id_var.set(kwargs["doc_id"])

        setattr(self.request, "_dlq_sent", False)

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
        """
        logger.info("Task completed", task_name=self.name, task_id=task_id)

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
        """
        error_info = self._build_error_info(exc, task_id=task_id)
        traceback_text = str(einfo) if einfo is not None else None

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
        logger.info(
            "Task retrying",
            task_name=self.name,
            task_id=task_id,
            retry_num=self.request.retries,
            error=str(exc),
        )

    def _build_error_info(
        self,
        exc: BaseException,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Построить унифицированный словарь с данными об ошибке.
        """
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
        """
        Рассчитать exponential backoff с jitter для retry.
        """
        base = float(min(10 * (3 ** retry_num), self.retry_backoff_max))
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
        """
        Отправить запись в DLQ не более одного раза за lifecycle текущего request.
        """
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
        """
        Подготовить и записать событие в DLQ.
        """
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
        """
        Асинхронно записать событие в DLQ через Unit of Work.
        """
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
        """
        Асинхронно обновить статус Job и связанные метаданные.
        """
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

            stmt = (
                sa_update(Job)
                .where(Job.id == uuid.UUID(job_id))
                .values(**values)
            )
            await db.execute(stmt)

            