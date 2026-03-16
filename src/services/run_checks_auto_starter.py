# src/services/run_checks_auto_starter.py

"""
Run Checks Auto-Starter Service.

Назначение:
- Автоматически запускать воркер run_deal_checks, когда все нужные документы
  для Run дошли до классификации (CLASSIFIED или COMPLETED).

Как это работает:
- Сервис вызывается после успешной классификации КАЖДОГО документа (если есть run_id).
- Он проверяет:
  1) Run всё ещё в статусе RUNNING.
  2) Для этого Run ещё нет Job с task_type="run_deal_checks".
  3) Все «живые» документы сделки для этого Run уже в статусах CLASSIFIED или COMPLETED.
- Если все условия выполняются, ставится один Celery-заказ workers.run_deal_checks.
"""

import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

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
      * checks уже запускались для этого Run;
      * ещё остались документы, которые не дошли до CLASSIFIED/COMPLETED.
    - Если всё готово — она один раз поставит Celery-задачу для run_deal_checks.
    """
    if not run_id:
        return

    # 1. Загружаем Run
    result = await db.execute(select(Run).where(Run.id == run_id))
    run_obj: Run | None = result.scalar_one_or_none()
    if not run_obj:
        logger.warning(
            "maybe_start_run_checks: run not found",
            run_id=str(run_id),
        )
        return

    # Checks запускаем только для живого RUNNING.
    if run_obj.status != RunStatus.RUNNING.value:
        logger.debug(
            "maybe_start_run_checks: run is not RUNNING, skip",
            run_id=str(run_id),
            status=run_obj.status,
        )
        return

    # 2. Проверяем, не запускались ли уже checks (Job с task_type='run_deal_checks').
    job_exists = await _has_run_deal_checks_job(db, run_id)
    if job_exists:
        logger.debug(
            "maybe_start_run_checks: run_deal_checks job already exists, skip",
            run_id=str(run_id),
        )
        return

    # 3. Проверяем статусы документов сделки.
    doc_repo = DocumentRepository(db)
    deal_id = run_obj.deal_id

    docs = await doc_repo.get_by_deal(deal_id)

    if not docs:
        # Нет документов — логируем и не запускаем checks.
        logger.info(
            "maybe_start_run_checks: no documents for deal, nothing to check",
            run_id=str(run_id),
            deal_id=str(deal_id),
        )
        return

    # Документ считается "готовым для checks", если он:
    # - не в FAILED/QUARANTINE;
    # - и уже CLASSIFIED или COMPLETED.
    ready_statuses = {DocumentStatus.CLASSIFIED.value, DocumentStatus.COMPLETED.value}
    error_statuses = {DocumentStatus.FAILED.value, DocumentStatus.QUARANTINE.value}

    participating_docs = [
        d for d in docs if d.status not in error_statuses
    ]

    if not participating_docs:
        # Все документы либо упали/в карантине, либо их нет — checks запускать бессмысленно.
        logger.info(
            "maybe_start_run_checks: no participating documents, skip checks",
            run_id=str(run_id),
            deal_id=str(deal_id),
        )
        return

    all_ready = all(d.status in ready_statuses for d in participating_docs)

    if not all_ready:
        # Есть ещё документы, которые не дошли до классификации.
        logger.debug(
            "maybe_start_run_checks: not all documents are ready for checks",
            run_id=str(run_id),
            deal_id=str(deal_id),
        )
        return

    # 4. Все нужные документы готовы, checks ещё не запускались — ставим задачу.
    tenant_id = None
    if hasattr(run_obj, "deal") and run_obj.deal and hasattr(run_obj.deal, "tenant_id"):
        tenant_id = str(run_obj.deal.tenant_id)
    else:
        # Простейший fallback: используем deal_id как tenant_id (как в оркестраторе).
        tenant_id = str(deal_id)

    # Создаём Job-запись, чтобы второй раз не запустить checks.
    job = Job(
        run_id=run_id,
        document_id=None,
        task_type="run_deal_checks",
        status=JobStatus.QUEUED.value,
    )
    db.add(job)
    await db.flush()

    logger.info(
        "maybe_start_run_checks: scheduling run_deal_checks",
        run_id=str(run_id),
        deal_id=str(deal_id),
        tenant_id=tenant_id,
    )

    celery_app.send_task(
        "workers.run_deal_checks",
        kwargs={
            "run_id": str(run_id),
            "deal_id": str(deal_id),
            "tenant_id": tenant_id,
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
