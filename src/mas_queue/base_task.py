# src/mas_queue/base_task.py


"""
MASBaseTask — базовый класс для всех Celery‑задач в системе.

Назначение:
  - единая реализация политики ретраев, DLQ и трекинга Job в БД;
  - стандартное логирование с контекстом сделки и документа;
  - централизованная обработка TransientError / PermanentError / QuarantineError.

Что делает этот класс:
  - перехватывает выполнение задачи в __call__ и:
      * TransientError и любые неизвестные исключения → self.retry() с экспоненциальным backoff;
      * PermanentError → без ретраев, on_failure пишет в DLQ и помечает Job как DLQ;
      * QuarantineError → без ретраев, on_failure помечает Job как COMPLETED с флагом quarantine;
  - при достижении max_retries для транзиентных ошибок:
      * пишет запись в DLQ через DLQManager;
      * обновляет статус Job в PostgreSQL на DLQ;
  - в before_start / on_success / on_failure / on_retry:
      * логирует ключевые события жизненного цикла таски;
      * обновляет статус Job (RUNNING, COMPLETED, DLQ) и вспомогательные поля
        (worker_id, started_at, finished_at, retry_count, error_details).

Как использовать:
  - наследовать Celery‑таски от этого класса через декоратор:
        @celery_app.task(base=MASBaseTask, bind=True, queue="default")
        def my_task(self, document_id: str, job_id: str, deal_id: str | None = None):
            ...
  - передавать в kwargs:
      * job_id  — для трекинга статуса в таблице Job;
      * deal_id / document_id — для логгера (контекст deal_id_var / document_id_var).

Ограничения:
  - все операции с БД (Job / DLQ) выполняются асинхронно внутри отдельного event loop
    через asyncio.run и db_uow();
  - класс не знает бизнес‑логики задач, только управляет их жизненным циклом и побочными эффектами.
"""


import asyncio
import traceback
import uuid
from datetime import UTC, datetime

from celery import Task
from celery.exceptions import Retry
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import JobStatus
from core.exceptions import PermanentError, QuarantineError, TransientError
from core.logging import deal_id_var, document_id_var, get_logger
from db.models.run import Job
from db.uow import db_uow
from mas_queue.dlq import DLQManager


logger = get_logger(__name__)


class MASBaseTask(Task):
    """
    Базовый класс Celery‑тасок с политикой ретраев, DLQ и трекингом Job.

    Политика ретраев:
        TransientError : до 3 попыток, экспоненциальный backoff, максимум 300 сек;
        PermanentError : 1 попытка, затем сразу DLQ;
        Неизвестные ошибки : считаются транзиентными.

    Пример использования:
        @celery_app.task(base=MASBaseTask, bind=True, queue="default")
        def my_task(self, document_id: str, job_id: str):
            ...  # бросаем TransientError / PermanentError по необходимости
    """

    # Автоматические ретраи Celery не используем, всё управляется вручную.
    autoretry_for = ()
    max_retries = 3
    retry_backoff_max = 300  # секунды

    # Если False — обновления Job в БД не выполняются.
    track_job = True

    # ------------------------------------------------------------------
    # Основной жизненный цикл
    # ------------------------------------------------------------------

    def __call__(self, *args, **kwargs):
        """
        Обёртка вокруг выполнения задачи.

        Перехватывает исключения и маршрутизирует их:
        - TransientError / неизвестные → self.retry() с задержкой;
        - PermanentError               → даём дойти до on_failure (DLQ);
        - QuarantineError              → даём дойти до on_failure (quarantine);
        - Retry                        → перекидываем как есть (Celery уже расписал ретрай).
        """
        try:
            return self.run(*args, **kwargs)
        except Retry:
            # Celery уже спланировал повторный запуск — просто перекидываем.
            raise
        except (PermanentError, QuarantineError):
            # Финальные ошибки без ретраев — обрабатываются в on_failure.
            raise
        except TransientError as exc:
            self._handle_transient(exc, kwargs)
        except Exception as exc:
            # Любые неожиданные ошибки считаем транзиентными.
            self._handle_transient(exc, kwargs)

    def _handle_transient(self, exc: Exception, kwargs: dict) -> None:
        """Обработка транзиентной ошибки: либо ретрай с backoff, либо DLQ при исчерпании попыток."""
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
                    asyncio.run(
                        self._update_job_status(
                            kwargs["job_id"],
                            JobStatus.QUEUED.value,
                            retry_count=self.request.retries + 1,
                        )
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to update job status for retry",
                        error=str(e),
                    )

            # Просим Celery запланировать повторный запуск с задержкой.
            raise self.retry(exc=exc, countdown=delay)
        else:
            # Ретраи исчерпаны — отправляем в DLQ.
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
                    asyncio.run(
                        self._update_job_status(
                            kwargs["job_id"],
                            JobStatus.DLQ.value,
                            error_details=error_info,
                        )
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to update job for DLQ",
                        error=str(e),
                    )

            raise

    # ------------------------------------------------------------------
    # Хуки Celery
    # ------------------------------------------------------------------

    def before_start(self, task_id, args, kwargs):
        """
        Хук, вызываемый перед запуском задачи на воркере.

        Заполняет контекст логгера (deal_id, document_id) и помечает Job как RUNNING.
        """
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
                asyncio.run(
                    self._update_job_status(
                        kwargs["job_id"],
                        JobStatus.RUNNING.value,
                        worker_id=self.request.hostname,
                    )
                )
            except Exception as e:
                logger.warning(
                    "Failed to update job status on start",
                    error=str(e),
                )

    def on_success(self, retval, task_id, args, kwargs):
        """
        Хук успешного завершения задачи.

        Логирует успех и помечает Job как COMPLETED.
        """
        logger.info("Task completed", task_name=self.name, task_id=task_id)

        if self.track_job and "job_id" in kwargs:
            try:
                asyncio.run(
                    self._update_job_status(
                        kwargs["job_id"],
                        JobStatus.COMPLETED.value,
                    )
                )
            except Exception as e:
                logger.warning(
                    "Failed to update job status on success",
                    error=str(e),
                )

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """
        Вызывается ТОЛЬКО при окончательной неудаче (когда ретраи исчерпаны).

        Здесь нет логики ретраев — только запись в DLQ (кроме quarantine)
        и финальное обновление статуса Job.
        """
        error_info = self._build_error_info(exc, task_id=task_id)

        if isinstance(exc, QuarantineError):
            # Специальный случай: документ уходит в карантин, Job считаем COMPLETED.
            logger.warning("Task resulted in quarantine", **error_info)
            if self.track_job and "job_id" in kwargs:
                try:
                    asyncio.run(
                        self._update_job_status(
                            kwargs["job_id"],
                            JobStatus.COMPLETED.value,
                            error_details={"quarantine": True, **error_info},
                        )
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to update job for quarantine",
                        error=str(e),
                    )
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
                asyncio.run(
                    self._update_job_status(
                        kwargs["job_id"],
                        JobStatus.DLQ.value,
                        error_details=error_info,
                    )
                )
            except Exception as e:
                logger.warning(
                    "Failed to update job status for DLQ",
                    error=str(e),
                )

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """
        Хук, вызываемый Celery при каждом ретрае задачи.
        """
        logger.info(
            "Task retrying",
            task_name=self.name,
            task_id=task_id,
            retry_num=self.request.retries,
            error=str(exc),
        )

    # ------------------------------------------------------------------
    # Вспомогательные методы
    # ------------------------------------------------------------------

    def _build_error_info(self, exc: Exception, task_id: str | None = None) -> dict:
        """Собирает структуру с базовой информацией об ошибке для логов и DLQ."""
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
        Расчёт задержки перед следующим ретраем.

        retry 0 →  10 сек
        retry 1 →  30 сек
        retry 2 →  90 сек
        retry 3 → 270 сек (максимум 300)
        """
        return float(min(10 * (3**retry_num), self.retry_backoff_max))

    def _send_to_dlq(
        self,
        kwargs: dict,
        task_type: str,
        failure_type: str,
        error_details: dict,
    ) -> None:
        """
        Синхронная обёртка, отправляющая запись о неуспешной задаче в DLQ (через async‑метод).
        """
        job_id = kwargs.get("job_id")
        try:
            asyncio.run(
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
        """
        Асинхронная запись события о проваленной задаче в таблицу DLQ.
        """
        async with db_uow() as uow:
            db: AsyncSession = uow.session
            dlq = DLQManager(db)
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
        """
        Асинхронное обновление статуса записи Job в БД.

        Обновляет статус, временные метки, счётчик ретраев и детали ошибки.
        """
        async with db_uow() as uow:
            db: AsyncSession = uow.session

            values: dict = {"status": status}
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
