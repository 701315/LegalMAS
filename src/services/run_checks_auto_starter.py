# src/services/run_checks_auto_starter.py

"""
Run Checks Auto-Starter Service.

Назначение:
- Автоматически запускать воркер run_deal_checks, когда все нужные документы
  для Run дошли до классификации (ENRICHED или COMPLETED).

Как это работает:
- Сервис вызывается:
  - после успешной классификации КАЖДОГО документа (если есть run_id);
  - после прохода оркестратора по всем документам сделки.
- Он проверяет:
  1) Run всё ещё в статусе RUNNING.
  2) Для этого Run ещё нет Job с task_type="run_deal_checks"
     (по факту — нет успешной вставки в jobs при уникальном (run_id, task_type)).
  3) Все «участвующие» документы сделки для этого Run уже в статусах
     ENRICHED или COMPLETED.
- Если все условия выполняются, ставится один Celery-заказ workers.run_deal_checks.

Важно:
- Документы в FAILED, QUARANTINE и LANGUAGE_SELECTION_REQUIRED
  не участвуют в auto-start checks.
- LANGUAGE_SELECTION_REQUIRED означает, что пайплайн по документу
  остановлен до ручного выбора основного языка, поэтому такой документ
  не должен блокировать checks по остальным документам сделки.

Замечание по транзакциям:
- Внутри функции при конфликте уникального ограничения используется savepoint
  (session.begin_nested()), а не полный rollback().
- Это гарантирует, что основная транзакция сессии остаётся живой после конфликта.
- Вызывать maybe_start_run_checks нужно ПОСЛЕ всех критичных обновлений
  в текущем UoW, как это уже сделано в classifier.py и run_orchestrator.py.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import DocumentStatus, JobStatus, RunStatus
from core.logging import get_logger
from db.models.run import Job, Run
from db.repositories.document_repo import DocumentRepository
from mas_queue.task_dispatcher import send_task_with_context

logger = get_logger(__name__)


async def maybe_start_run_checks(
    db: AsyncSession,
    run_id: uuid.UUID | None,
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

    Важно про savepoint:
    - При конкурентной гонке (два воркера пытаются создать Job одновременно)
      мы используем savepoint (begin_nested), а не полный rollback сессии.
    - Это позволяет основной транзакции остаться живой после конфликта.
    - Все ORM-объекты, загруженные до этого вызова, остаются валидными.
    """
    if not run_id:
        return

    run_id_str = str(run_id)

    logger.info(
        "maybe_start_run_checks: starting",
        run_id=run_id_str,
    )

    # 1) Загружаем Run
    result = await db.execute(select(Run).where(Run.id == run_id))
    run_obj: Run | None = result.scalar_one_or_none()
    if not run_obj:
        logger.warning(
            "maybe_start_run_checks: run not found",
            run_id=run_id_str,
        )
        return

    # Снимаем нужные поля в примитивы сразу после загрузки
    run_status: str = run_obj.status
    run_deal_id: uuid.UUID = run_obj.deal_id
    deal_id_str: str = str(run_deal_id)

    if run_status != RunStatus.RUNNING.value:
        logger.debug(
            "maybe_start_run_checks: run is not RUNNING, skip",
            run_id=run_id_str,
            status=run_status,
        )
        return

    # 2) Быстрая проверка на существующий Job.
    job_exists = await _has_run_deal_checks_job(db, run_id)
    if job_exists:
        logger.debug(
            "maybe_start_run_checks: run_deal_checks job already exists, skip",
            run_id=run_id_str,
        )
        return

    # 3) Читаем документы сделки.
    doc_repo = DocumentRepository(db)

    docs = await doc_repo.get_by_deal(run_deal_id)
    if not docs:
        logger.info(
            "maybe_start_run_checks: no documents for deal, nothing to check",
            run_id=run_id_str,
            deal_id=deal_id_str,
        )
        return

    ready_statuses = {
        DocumentStatus.ENRICHED.value,
        DocumentStatus.COMPLETED.value,
    }

    non_participating_statuses = {
        DocumentStatus.FAILED.value,
        DocumentStatus.QUARANTINE.value,
        DocumentStatus.LANGUAGE_SELECTION_REQUIRED.value,
    }

    # Снимаем статусы документов в примитивы сразу после загрузки,
    # до любого следующего await. Это предотвращает MissingGreenlet
    # при обращении к doc.status после возможного savepoint rollback.
    doc_statuses: list[str] = [str(d.status or "") for d in docs]

    participating_statuses = [s for s in doc_statuses if s not in non_participating_statuses]

    # Если participating_docs нет, всё равно запускаем run_deal_checks,
    # чтобы корректно отработать zero-check run и финализировать Run.
    if not participating_statuses:
        logger.info(
            "maybe_start_run_checks: no participating documents, scheduling zero-check run",
            run_id=run_id_str,
            deal_id=deal_id_str,
        )
    else:
        all_ready = all(s in ready_statuses for s in participating_statuses)
        if not all_ready:
            logger.debug(
                "maybe_start_run_checks: not all documents are ready for checks",
                run_id=run_id_str,
                deal_id=deal_id_str,
                participating_docs=len(participating_statuses),
                ready_docs=sum(1 for s in participating_statuses if s in ready_statuses),
                blocked_docs=sum(
                    1
                    for s in doc_statuses
                    if s == DocumentStatus.LANGUAGE_SELECTION_REQUIRED.value
                ),
            )
            return

    # 4) Все условия выполняются — пытаемся атомарно создать Job.
    # Используем savepoint (begin_nested) вместо полного rollback сессии.
    # При конкурентном конфликте (IntegrityError) откатывается только savepoint,
    # основная транзакция и все загруженные ORM-объекты остаются валидными.
    job_id_str: str | None = None
    try:
        async with db.begin_nested():
            job = Job(
                run_id=run_id,
                document_id=None,
                task_type="run_deal_checks",
                status=JobStatus.QUEUED.value,
            )
            db.add(job)
            await db.flush()
            # Снимаем job.id в примитив внутри savepoint,
            # пока объект гарантированно валиден
            job_id_str = str(job.id)
    except IntegrityError:
        # Кто-то другой уже успел создать Job для run_deal_checks.
        # Savepoint откатился сам, основная транзакция цела.
        logger.info(
            "maybe_start_run_checks: run_deal_checks job was created concurrently, skip duplicate",
            run_id=run_id_str,
        )
        return

    logger.info(
        "maybe_start_run_checks: scheduling run_deal_checks",
        run_id=run_id_str,
        deal_id=deal_id_str,
        checks_planned=None,
        job_id=job_id_str,
    )

    # tenant_id передаём явно из Run.tenant_id — первичный источник истины.
    # Не полагаемся на implicit logging context:
    # он может отсутствовать в worker-triggered paths.
    run_tenant_id_str: str | None = (
        str(run_obj.tenant_id) if getattr(run_obj, "tenant_id", None) is not None else None
    )

    if run_tenant_id_str is None:
        logger.error(
            "maybe_start_run_checks: run has no tenant_id, "
            "run_deal_checks will run without tenant context",
            run_id=run_id_str,
            deal_id=deal_id_str,
        )

    send_task_with_context(
        "workers.run_deal_checks",
        kwargs={
            "run_id": run_id_str,
            "deal_id": deal_id_str,
            "job_id": job_id_str,
            "tenant_id": run_tenant_id_str,
        },
    )

    logger.info(
        "maybe_start_run_checks: run_deal_checks task sent",
        run_id=run_id_str,
        deal_id=deal_id_str,
        job_id=job_id_str,
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


