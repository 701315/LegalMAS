# src/workers/runner.py

"""
Runner — упрощённая версия для вертикального среза, обновлённая до работы с плейбуком.

Назначение:
- Выполнить проверки DD по одному документу в рамках конкретного Run.
- Брать конфигурацию проверок (checks) из PlaybookVersion.compiled_checks,
  привязанного к этому Run.
- На каждый документ ставится отдельная Celery‑задача run_checks.

Архитектура:
- HTTP-эндпоинт создаёт Run и ставит по одной задаче run_checks на каждый документ сделки.
- Внутри задачи:
  1) по run_id находим Run и PlaybookVersion;
  2) извлекаем список checks из compiled_checks["checks"];
  3) загружаем layout и clause_tree документа из ArtifactStore по ссылкам в DocumentVersion;
  4) для каждого check_cfg вызываем простой rules-исполнитель execute_check_for_document;
  5) сохраняем результаты в CheckResult и кладём NDJSON в сторедж;
  6) (экспорт сейчас запускается отдельным эндпоинтом).

Важное ограничение:
- Сейчас используется упрощённый rules-only executor (без LLM и сложного движка Stage 8).
  Позже его можно заменить/расширить, не меняя контракт с Runner'ом.
"""

import json
import uuid
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ops.metrics import METRICS
from core.constants import DocumentStatus
from core.exceptions import PermanentError
from core.logging import get_logger
from db.models.run import Run
from db.repositories import ResultRepository, DocumentRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.repositories.playbook_repo import PlaybookRepository
from db.repositories.run_repo import RunRepository
from db.uow import db_uow, UnitOfWork
from engine.checks.simple_rules import execute_check_for_document
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from mas_queue.async_helpers import run_async
from storage.artifact_store import ArtifactPath, ArtifactStore

logger = get_logger(__name__)


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.run_checks",
    track_job=False,
    queue="default",
)
def run_checks(
    self,
    document_id: str,
    deal_id: str,
    tenant_id: str,
    run_id: str | None = None,
    doctype: str = "Other",
) -> dict:
    """
    Sync Celery entrypoint: обёртка над асинхронным ядром _run_checks_async.

    Паттерн:
    - Celery вызывает синхронную функцию.
    - Внутри один раз передаём управление в async‑мир через run_async.
    """

    logger.info(
        "Starting checks",
        document_id=document_id,
        deal_id=deal_id,
        run_id=run_id,
        doctype=doctype,
    )

    async def _wrapper() -> dict:
        try:
            async with db_uow() as uow:
                return await _run_checks_async(
                    document_id=document_id,
                    deal_id=deal_id,
                    tenant_id=tenant_id,
                    run_id=run_id,
                    doctype=doctype,
                    db=uow.session,
                )
        except Exception as e:
            logger.error(
                "Unhandled error during checks",
                document_id=document_id,
                deal_id=deal_id,
                run_id=run_id,
                error=str(e),
            )
            # Отдельный UoW, чтобы пометить документ FAILED на стадии checks.
            async with db_uow() as uow_status:
                await _mark_checks_failed(
                    uow_status,
                    document_id=document_id,
                    run_id=run_id,
                    message=str(e),
                )
            # Пробрасываем, чтобы таска пометилась как failed в Celery.
            raise

    return run_async(_wrapper())


async def _run_checks_async(
    document_id: str,
    deal_id: str,
    tenant_id: str,
    run_id: str | None,
    doctype: str,
    db: AsyncSession,
) -> dict:
    """
    Основная асинхронная логика: загрузить артефакты, выполнить checks,
    сохранить результаты и подготовить артефакты для экспорта.

    Все операции с БД выполняются через переданную AsyncSession (db),
    чтобы одна задача Runner'а работала в рамках одного unit of work.
    """

    # 1. Получаем список checks из PlaybookVersion.compiled_checks
    checks_cfg: list[dict] = []

    if run_id:
        run_uuid = UUID(run_id)

        # Находим Run по run_id
        result = await db.execute(select(Run).where(Run.id == run_uuid))
        run_obj = result.scalar_one_or_none()
        if not run_obj:
            raise PermanentError(f"Run {run_id} not found")

        # Находим PlaybookVersion по run.playbook_version_id
        pb_repo = PlaybookRepository(db)
        playbook = await pb_repo.get_by_id(run_obj.playbook_version_id)
        if not playbook or not playbook.compiled_checks:
            raise PermanentError(
                f"PlaybookVersion for run {run_id} has no compiled_checks"
            )

        compiled = playbook.compiled_checks or {}
        checks_cfg = compiled.get("checks") or []

    # 2. Загружаем артефакты документа (layout и clause_tree) по ссылкам версии.
    store = ArtifactStore()

    doc_repo = DocumentRepository(db)
    ver_repo = DocumentVersionRepository(db)

    doc_uuid = UUID(document_id)
    doc = await doc_repo.get_by_id(doc_uuid)
    if not doc:
        raise PermanentError(f"Document {document_id} not found")

    version = await ver_repo.get_latest(doc.id)
    if not version:
        raise PermanentError(f"No version found for document {document_id}")

    if not version.text_layout_raw_ref:
        # Без raw layout проверки выполнить невозможно.
        raise PermanentError(
            f"text_layout_raw_ref missing for document {document_id}"
        )

    text_layout_raw = store.get_json(version.text_layout_raw_ref)
    elements = text_layout_raw.get("elements", [])

    if not version.clause_tree_ref:
        # По договоренности: отсутствие дерева пунктов — фатальная ошибка.
        raise PermanentError(
            f"clause_tree_ref missing for document {document_id}"
        )

    clause_tree = store.get_json(version.clause_tree_ref)

    check_results: list[dict] = []
    evidence_records: list[dict] = []

    # 3. Выполняем все checks из плейбука для этого документа.
    if checks_cfg:
        for check_cfg in checks_cfg:
            result = execute_check_for_document(
                check_cfg=check_cfg,
                document_id=document_id,
                elements=elements,
                clause_tree=clause_tree,
                doc_type=doctype,
            )
            check_results.append(result)

            # Если есть evidence_snippet, добавляем запись в evidence_records.
            snippet = result.get("evidence_snippet")
            page = result.get("evidence_page")
            if snippet:
                evidence_records.append(
                    {
                        "check_id": result["check_id"],
                        "document_id": document_id,
                        "snippet": snippet,
                        "page": page,
                    }
                )
    else:
        logger.warning(
            "No checks_cfg for run/document, skipping checks",
            run_id=run_id,
            document_id=document_id,
        )

    # 4. Метрики выполнения проверок.
    for cr in check_results:
        METRICS.checks_executed.labels(
            detector_type=cr.get("detector_used", "unknown"),
            result=cr.get("result", "unknown"),
        ).inc()

        METRICS.check_duration.labels(
            detector_type=cr.get("detector_used", "unknown"),
        ).observe(0.0)  # TODO: заменить на реальную длительность.

    # 5. Сохраняем результаты в БД и обновляем статус документа / Run.
    await _finalize(
        run_id=run_id,
        document_id=document_id,
        check_results=check_results,
        db=db,
    )

    # 6. Сохраняем результаты в NDJSON для экспорта/отладки.
    if run_id:
        results_path = ArtifactPath.check_results(tenant_id, deal_id, run_id)
        results_ndjson = "\n".join(
            json.dumps(r, ensure_ascii=False) for r in check_results
        )
        store.put_file(
            results_path,
            results_ndjson.encode("utf-8"),
            content_type="application/x-ndjson",
        )

        if evidence_records:
            evidence_path = ArtifactPath.evidence(tenant_id, deal_id, run_id)
            evidence_ndjson = "\n".join(
                json.dumps(e, ensure_ascii=False) for e in evidence_records
            )
            store.put_file(
                evidence_path,
                evidence_ndjson.encode("utf-8"),
                content_type="application/x-ndjson",
            )

    logger.info(
        "Checks complete",
        document_id=document_id,
        results=len(check_results),
        evidence=len(evidence_records),
    )

    # Экспорт теперь запускается отдельным эндпоинтом /runs/{run_id}/export.

    return {
        "document_id": document_id,
        "checks_run": len(check_results),
        "findings": sum(1 for r in check_results if r["result"] == "fail"),
    }


def _find_clause_for_element(clause_tree, element_id) -> str | None:
    """
    Вспомогательная функция: найти clause_uid по element_id в clause_tree.

    Сейчас не используется в simple_rules, но может пригодиться позже,
    когда будем привязывать evidence к конкретным пунктам договора.
    """

    def search(nodes):
        for node in nodes:
            if element_id in node.get("element_ids", []):
                return node["clause_uid"]
            found = search(node.get("children", []))
            if found:
                return found
        return None

    root_children = clause_tree.get("root", {}).get("children", [])
    return search(root_children)


async def _save_results(
    run_id: str | None,
    document_id: str,
    check_results: list[dict],
    db: AsyncSession,
) -> None:
    """Сохранить результаты проверок в БД (таблица check_results)."""
    if not run_id:
        return

    repo = ResultRepository(db)
    for cr in check_results:
        await repo.create(
            run_id=uuid.UUID(run_id),
            document_id=uuid.UUID(document_id),
            check_id=cr["check_id"],
            check_name=cr["check_name"],
            result=cr["result"],
            severity=cr["severity"],
            value_text=cr.get("value_text"),
            confidence=cr.get("confidence"),
            detector_used=cr.get("detector_used"),
            quality_flags=cr.get("quality_flags"),
            structured_data=cr.get("structured_data"),
            conditional_check_triggered=cr.get(
                "conditional_check_triggered", False
            ),
            trigger_name=cr.get("trigger_name"),
        )


async def _finalize(
    run_id: str | None,
    document_id: str,
    check_results: list[dict],
    db: AsyncSession,
) -> None:
    """
    Финализация задачи Runner'а:
    - сохранение результатов в CheckResult;
    - обновление статуса документа;
    - инкремент completed_checks для Run (если run_id задан);
    - автозавершение Run, если все документы обработаны.
    """
    await _save_results(run_id, document_id, check_results, db)
    await _update_document_status(document_id, db)

    if not run_id:
        return

    run_repo = RunRepository(db)
    run_uuid = uuid.UUID(run_id)

    # Увеличиваем счётчик обработанных документов для этого Run.
    await run_repo.increment_completed_checks(run_uuid)

    # Проверяем, все ли документы для Run обработаны.
    total, completed = await run_repo.get_counts(run_uuid)
    if total and completed >= total:
        # Все документы, запланированные на этот Run, прошли run_checks.
        await run_repo.update_status(run_uuid, "completed")


async def _update_document_status(
    document_id: str,
    db: AsyncSession,
) -> None:
    """Обновить статус документа после выполнения проверок."""
    repo = DocumentRepository(db)
    await repo.update_status(
        uuid.UUID(document_id),
        DocumentStatus.COMPLETED.value,
        processing_error_details=None,
    )


async def _mark_checks_failed(
    uow: UnitOfWork,
    document_id: str,
    run_id: str | None,
    *,
    message: str,
) -> None:
    """
    Отдельный простой UoW для перевода документа в FAILED
    с деталями ошибки на стадии checks.
    """
    repo = DocumentRepository(uow.session)
    run_uuid = uuid.UUID(run_id) if run_id else None
    await repo.set_failed(
        uuid.UUID(document_id),
        stage="checks",
        message=message,
        reason="checks_error",
        run_id=run_uuid,
    )
