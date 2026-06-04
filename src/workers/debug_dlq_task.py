# src/workers/debug_dlq_task.py

from __future__ import annotations

from core.exceptions import PermanentError, TransientError
from core.logging import get_logger
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from typing import Any


logger = get_logger(__name__)


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="debug.always_fail_transient",
    track_job=False,
)
def always_fail_transient(
    self,
    *,
    job_id: str | None = None,
    stage_execution_id: str | None = None,
    orchestration_strategy: str | None = None,
    **kwargs: Any,
) -> dict:
    retry_num = int(getattr(self.request, "retries", 0) or 0)

    logger.warning(
        "debug.always_fail_transient: about to fail",
        extra={
            "retry_num": retry_num,
            "job_id": job_id,
            "task_id": self.request.id,
        },
    )

    raise TransientError(
        f"Debug transient failure for DLQ test, retry_num={retry_num}, job_id={job_id}"
    )


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="debug.always_fail_permanent",
    track_job=False,
)
def always_fail_permanent(
    self,
    *,
    job_id: str | None = None,
    stage_execution_id: str | None = None,
    orchestration_strategy: str | None = None,
    **kwargs: Any,
) -> dict:
    """
    Тестовая задача для проверки DLQ при PermanentError:
    без ретраев, сразу один проход через on_failure и запись в DLQ.
    """
    logger.warning(
        "debug.always_fail_permanent: about to fail",
        extra={
            "job_id": job_id,
            "task_id": self.request.id,
        },
    )

    raise PermanentError(
        f"Debug permanent failure for DLQ test, job_id={job_id}",
        details={"job_id": job_id},
    )
