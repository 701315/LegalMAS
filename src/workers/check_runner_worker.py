# src/workers/check_runner_worker.py

"""
CheckRunner Worker — запуск playbook-checks по уже классифицированным документам сделки.

Позиция в пайплайне:
- import → extract → pii → structure → classify → run_deal_checks → export_results.

Что делает:
- Для одного Run по deal_id:
  - вытаскивает все non-duplicate документы сделки;
  - прогоняет их через CheckRunner (playbook + CheckExecutor);
  - пишет CheckResult'ы в БД;
  - агрегирует статистику (processed_docs, total_checks, failed_checks, errors);
  - обновляет Run.total_checks / Run.completed_checks и финальный статус Run.

Архитектура:
- Снаружи — синхронная Celery-таска run_deal_checks (def), чтобы Celery мог её вызывать.
- Внутри — один переход sync → async через run_async.
- Вся работа с БД и CheckRunner — под db_uow() / AsyncSession.
- Этот воркер запускается ОДИН раз на весь Run (по сделке), а не по каждому документу отдельно.
"""

import time
import uuid

from ops.metrics import get_metrics
from core.logging import get_logger
from core.constants import RunStatus
from db.uow import db_uow
from db.repositories.run_repo import RunRepository
from engine.checks_runner import CheckRunner
from engine.llm.client import LLMClient
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from mas_queue.async_helpers import run_async

logger = get_logger(__name__)


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.run_deal_checks",
    track_job=False,
    queue="default",
)
def run_deal_checks(
    self,
    run_id: str,
    deal_id: str,
    tenant_id: str | None = None,
) -> dict:
    """
    Синхронная Celery‑таска: запускает CheckRunner по сделке для указанного Run.

    Внутри:
      - создаёт LLMClient;
      - переходит в async‑ядро через run_async;
      - внутри async‑ядра открывает db_uow(), запускает CheckRunner.run_deal_checks;
      - по результату обновляет Run (total_checks, completed_checks, статус);
      - возвращает summary от CheckRunner + финальный статус Run.

    Для непрофессионального программиста:
    - Здесь просто «обёртка» для Celery.
    - Основная логика находится во внутренней async‑функции _run().
    """
    logger.info(
        "Run deal checks started",
        run_id=run_id,
        deal_id=deal_id,
        tenant_id=tenant_id,
    )

    started_at = time.time()
    metrics = get_metrics()
    llm_client = LLMClient()
    run_uuid = uuid.UUID(run_id)
    deal_uuid = uuid.UUID(deal_id)

    async def _run() -> dict:
        async with db_uow() as uow:
            run_repo = RunRepository(uow.session)

            try:
                runner = CheckRunner(llm_client=llm_client)

                # Основной запуск checks по сделке
                summary = await runner.run_deal_checks(
                    deal_id=deal_uuid,
                    run_id=run_uuid,
                )

                # Обновляем total_checks / completed_checks по фактическим данным
                total_checks = int(summary.get("total_checks", 0) or 0)
                failed_checks = int(summary.get("failed_checks", 0) or 0)
                errors = int(summary.get("errors", 0) or 0)

                # Прогресс: считаем, что completed_checks == total_checks
                # для run_deal_checks, т.к. все проверки выполняются в этом воркере.
                completed_checks = total_checks

                # Определяем финальный статус Run:
                # - если были ошибки на уровне документов/чеков → COMPLETED_WITH_ERRORS;
                # - иначе → COMPLETED.
                if errors > 0:
                    final_status = RunStatus.COMPLETED_WITH_ERRORS.value
                else:
                    final_status = RunStatus.COMPLETED.value

                await run_repo.update_status(
                    run_uuid,
                    final_status,
                    total_checks=total_checks,
                    completed_checks=completed_checks,
                )

                duration = time.time() - started_at
                metrics.checks_duration.labels(stage="deal_checks").observe(duration)

                logger.info(
                    "Run deal checks completed",
                    run_id=run_id,
                    deal_id=deal_id,
                    duration_sec=round(duration, 2),
                    processed_docs=summary.get("processed_docs"),
                    total_checks=total_checks,
                    failed_checks=failed_checks,
                    errors=errors,
                    status=final_status,
                )

                return {
                    **summary,
                    "status": final_status,
                    "duration_sec": round(duration, 2),
                }

            except Exception as e:
                logger.error(
                    "Run deal checks failed",
                    run_id=run_id,
                    deal_id=deal_id,
                    error=str(e),
                )
                # Помечаем Run как failed и сохраняем детали ошибки
                await run_repo.update_status(
                    run_uuid,
                    RunStatus.FAILED.value,
                    error_details={
                        "stage": "run_deal_checks",
                        "type": "failed",
                        "reason": "checks_error",
                        "message": str(e),
                    },
                )
                # Пробрасываем, чтобы Celery видел failure
                raise

    # Запуск async‑ядра через общий helper run_async.
    return run_async(_run())
