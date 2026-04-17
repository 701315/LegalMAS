# src/services/run_checks_auto_starter.py

"""
Run Checks Auto-Starter Service.

Назначение:
- Автоматически запускать воркер run_deal_checks, когда все нужные документы
  для Run дошли до классификации (CLASSIFIED или COMPLETED).

Как это работает:
- Сервис вызывается:
  - после успешной классификации КАЖДОГО документа (если есть run_id);
  - после прохода оркестратора по всем документам сделки.
- Он проверяет:
  1) Run всё ещё в статусе RUNNING.
  2) Для этого Run ещё нет Job с task_type="run_deal_checks"
     (по факту — нет успешной вставки в jobs при уникальном (run_id, task_type)).
  3) Все «участвующие» документы сделки для этого Run уже в статусах
     CLASSIFIED или COMPLETED.
- Если все условия выполняются, ставится один Celery-заказ workers.run_deal_checks.

Важно:
- Документы в FAILED, QUARANTINE и LANGUAGE_SELECTION_REQUIRED
  не участвуют в auto-start checks.
- LANGUAGE_SELECTION_REQUIRED означает, что пайплайн по документу
  остановлен до ручного выбора основного языка, поэтому такой документ
  не должен блокировать checks по остальным документам сделки.

Замечание по транзакциям:
- Внутри функции при конфликте уникального ограничения выполняется rollback()
  на переданном AsyncSession. Поэтому вызывать maybe_start_run_checks нужно
  ПОСЛЕ всех критичных обновлений в текущем UoW, как это уже сделано
  в classifier.py и run_orchestrator.py.
"""

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import DocumentStatus, RunStatus, JobStatus
from core.logging import get_logger
from db.models.run import Run, Job
from db.repositories.document_repo import DocumentRepository
from mas_queue.celery_app import celery_app

logger = get_logger(__name__)


async def maybe_start_run_checks(
    db: AsyncSession,
    run_id: Optional[uuid.UUID],
) -> None:
    """
    Проверить, пора ли запускать checks для Run, и при необходимости
    поставить таску workers.run_deal_checks.

    Для непрофессионального программиста:
    - Эта функция НИЧЕГО не делает, если:
      * run_id не передан;
      * Run не в статусе RUNNING;
      * checks уже запускались для этого Run (есть Job с task_type=run_deal_checks);
      * ещё остались участвующие документы, которые не дошли до CLASSIFIED/COMPLETED.
    - Если всё готово — она один раз поставит Celery-задачу для run_deal_checks.
    """
    if not run_id:
        return

    run_id_str = str(run_id)

    logger.info(
        "maybe_start_run_checks: starting",
        extra={"run_id": run_id_str},
    )

    # 1) Загружаем Run
    result = await db.execute(select(Run).where(Run.id == run_id))
    run_obj: Run | None = result.scalar_one_or_none()
    if not run_obj:
        logger.warning(
            "maybe_start_run_checks: run not found",
            extra={"run_id": run_id_str},
        )
        return

    if run_obj.status != RunStatus.RUNNING.value:
        logger.debug(
            "maybe_start_run_checks: run is not RUNNING, skip",
            extra={
                "run_id": run_id_str,
                "status": run_obj.status,
            },
        )
        return

    # 2) Быстрая проверка на существующий Job.
    job_exists = await _has_run_deal_checks_job(db, run_id)
    if job_exists:
        logger.debug(
            "maybe_start_run_checks: run_deal_checks job already exists, skip",
            extra={"run_id": run_id_str},
        )
        return

    # 3) Читаем документы сделки.
    doc_repo = DocumentRepository(db)
    deal_id = run_obj.deal_id
    deal_id_str = str(deal_id)

    docs = await doc_repo.get_by_deal(deal_id)
    if not docs:
        logger.info(
            "maybe_start_run_checks: no documents for deal, nothing to check",
            extra={
                "run_id": run_id_str,
                "deal_id": deal_id_str,
            },
        )
        return

    ready_statuses = {
        DocumentStatus.CLASSIFIED.value,
        DocumentStatus.COMPLETED.value,
    }

    non_participating_statuses = {
        DocumentStatus.FAILED.value,
        DocumentStatus.QUARANTINE.value,
        DocumentStatus.LANGUAGE_SELECTION_REQUIRED.value,
    }

    participating_docs = [
        d for d in docs if d.status not in non_participating_statuses
    ]

    # Если participating_docs нет, всё равно запускаем run_deal_checks,
    # чтобы корректно отработать zero-check run и финализировать Run.
    if not participating_docs:
        logger.info(
            "maybe_start_run_checks: no participating documents, scheduling zero-check run",
            extra={
                "run_id": run_id_str,
                "deal_id": deal_id_str,
            },
        )
    else:
        all_ready = all(d.status in ready_statuses for d in participating_docs)
        if not all_ready:
            logger.debug(
                "maybe_start_run_checks: not all documents are ready for checks",
                extra={
                    "run_id": run_id_str,
                    "deal_id": deal_id_str,
                    "participating_docs": len(participating_docs),
                    "ready_docs": sum(
                        1 for d in participating_docs if d.status in ready_statuses
                    ),
                    "blocked_docs": sum(
                        1
                        for d in docs
                        if d.status == DocumentStatus.LANGUAGE_SELECTION_REQUIRED.value
                    ),
                },
            )
            return

    # 4) Все условия выполняются — пытаемся атомарно создать Job.
    # Полагаемся на уникальный индекс jobs(run_id, task_type),
    # чтобы защититься от гонок.
    try:
        job = Job(
            run_id=run_id,
            document_id=None,
            task_type="run_deal_checks",
            status=JobStatus.QUEUED.value,
        )
        db.add(job)
        await db.flush()
    except IntegrityError:
        # Кто-то другой уже успел создать Job для run_deal_checks.
        # Считаем, что checks уже запущены или запланированы.
        await db.rollback()
        logger.info(
            "maybe_start_run_checks: run_deal_checks job was created concurrently, skip duplicate",
            extra={"run_id": run_id_str},
        )
        return

    logger.info(
        "maybe_start_run_checks: scheduling run_deal_checks",
        extra={
            "run_id": run_id_str,
            "deal_id": deal_id_str,
            # tenant_id намеренно не подменяем, пусть downstream сам резолвит,
            # как это делает run_orchestrator.
            "checks_planned": None,
            "job_id": str(job.id),
        },
    )

    celery_app.send_task(
        "workers.run_deal_checks",
        kwargs={
            "run_id": run_id_str,
            "deal_id": deal_id_str,
            "tenant_id": None,
        },
    )

    logger.info(
        "maybe_start_run_checks: run_deal_checks task sent",
        extra={
            "run_id": run_id_str,
            "deal_id": deal_id_str,
            "tenant_id": None,
            "job_id": str(job.id),
        },
    )


async def _has_run_deal_checks_job(db: AsyncSession, run_id: uuid.UUID) -> bool:
    """
    Проверить, есть ли уже Job для run_deal_checks по этому run_id.

    Считаем, что наличие хотя бы одной Job (любой статус) означает,
    что checks уже запускались или запланированы.
    """
    result = await db.execute(
        select(Job).where(
            Job.run_id == run_id,
            Job.task_type == "run_deal_checks",
        )
    )
    job = result.scalar_one_or_none()
    return job is not None

