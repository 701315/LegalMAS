"""
Exporter Worker — Stage 9.

Производит полный пакет экспортных файлов по сделке:
  - dd_grid_{run_id}.xlsx      — DD Grid с 4 листами
  - summary_{run_id}.xlsx      — Summary с 5 листами
  - report_{run_id}.docx       — Word-отчёт с 7 разделами
  - aggregated_{run_id}.json   — JSON-дамп агрегации

Архитектура:
  - Celery-таска остаётся точкой входа (как было)
  - Вся логика агрегации и экспорта вынесена в src/services/export/
  - БД-операции выполняются через db_uow / AsyncSession (как было)
  - Файлы сохраняются через ArtifactStore (как было)
"""

#import json
#import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from db.uow import db_uow
from mas_queue.base_task import MASBaseTask
from mas_queue.celery_app import celery_app
from services.export.core import export_core

#from db.models.export import Export
#from db.models.result import CheckResult
#from db.repositories import DealRepository, ResultRepository, RunnerRepository, RunRepository
#from services.export.aggregator import aggregate_results
#from services.export.grid_builder import build_grid_excel
#from services.export.report_builder import build_report_docx
#from services.export.summary_builder import build_summary_excel
#from storage.artifact_store import ArtifactPath, ArtifactStore

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Загрузка данных из БД
# ---------------------------------------------------------------------------


#async def _load_check_results(run_id: str, db: AsyncSession) -> list[dict]:
#    """
#    Загрузить результаты проверок из БД для данного run_id.
#
#    Возвращает список словарей — Aggregator не знает про ORM,
#    работает только со словарями.
#
#    Включает поля Stage 8: structured_data, conditional_check_triggered,
#    trigger_name.
#    """
#    repo = ResultRepository(db)
#    results: list[CheckResult] = await repo.get_by_run(uuid.UUID(run_id))
#
#    return [
#        {
#            # --- Базовые поля ---
#            "check_id": r.check_id,
#            "check_name": r.check_name,
#            "result": r.result,
#            "severity": r.severity,
#            "value_text": r.value_text or "",
#            "confidence": r.confidence or 0.0,
#            "detector_used": getattr(r, "detector_used", "") or "",
#            "quality_flags": getattr(r, "quality_flags", {}) or {},
#            "qc_status": getattr(r, "qc_status", "pending") or "pending",
#            "document_id": str(r.document_id) if r.document_id else "",
#            "page": getattr(r, "page", None),
#            "clause_uid": getattr(r, "clause_uid", "") or "",
#            # --- Поля Stage 8 ---
#            "structured_data": getattr(r, "structured_data", {}) or {},
#            "conditional_check_triggered": getattr(r, "conditional_check_triggered", False)
#            or False,
#            "trigger_name": getattr(r, "trigger_name", "") or "",
#        }
#        for r in results
#    ]


#async def _load_documents_metadata(deal_id: str, db: AsyncSession) -> dict[str, dict]:
#    repo = RunnerRepository(db)
#    documents = await repo.get_non_duplicate_docs(uuid.UUID(deal_id))
#
#    return {
#        str(d.id): {
#            # --- Базовые поля ---
#            "name": d.name,
#            "folder_path": getattr(d, "folder_path", "") or "",
#            "doc_type": getattr(d, "doc_type", "Generic") or "Generic",
#            "status": getattr(d, "status", "active") or "active",
#            # --- Поля Stage 8 ---
#            "classification_level": getattr(d, "classification_level", "") or "",
#            "classification_confidence": getattr(d, "classification_confidence", 0.0) or 0.0,
#            "applicable_triggers": getattr(d, "applicable_triggers", []) or [],
#        }
#        for d in documents
#    }


#async def _load_deal_name(deal_id: str, db: AsyncSession) -> str:
#    """Получить название сделки по deal_id. Возвращает deal_id если не найдено."""
#    try:
#        repo = DealRepository(db)
#        deal = await repo.get_by_id(uuid.UUID(deal_id))
#        return deal.name if deal and deal.name else deal_id
#    except Exception:
#        # Если DealRepository ещё не реализован — не падаем
#        return deal_id


# ---------------------------------------------------------------------------
# Сохранение артефактов
# ---------------------------------------------------------------------------


#async def _save_export_record(
#    run_id: str,
#    export_ref: str | None,
#    db: AsyncSession,
#    format: str = "xlsx",
#) -> None:
#    """Сохранить запись об экспорте и обновить статус run."""
#    run_repo = RunRepository(db)
#    run = await run_repo.get_by_id(uuid.UUID(run_id))
#    if run:
#        export = Export(run_id=run.id, ref=export_ref, format=format)
#        db.add(export)
#        run.status = "completed"
#        await db.flush()


#def _save_artifact(
#    store: ArtifactStore,
#    tenant_id: str,
#    deal_id: str,
#    run_id: str,
#    suffix: str,
#    data: bytes,
#    content_type: str,
#) -> str | None:
#    """Сохранить файл в ArtifactStore. Возвращает ref или None при ошибке."""
#    try:
#        export_path = ArtifactPath.export(tenant_id, deal_id, run_id)
#        return store.put_file(
#            f"{export_path}{suffix}",
#            data,
#            content_type=content_type,
#        )
#    except Exception as e:
#        logger.warning(
#            "Не удалось сохранить артефакт",
#            suffix=suffix,
#            error=str(e),
#        )
#        return None


# ---------------------------------------------------------------------------
# Основная async-логика экспорта
# ---------------------------------------------------------------------------


#async def _export_results_async(
#    run_id: str,
#    deal_id: str,
#    tenant_id: str,
#    db: AsyncSession,
#) -> dict:
#    """
#    Async core: загружает данные из БД, агрегирует, генерирует файлы,
#    сохраняет артефакты.#
#
#    Все операции с БД выполняются через переданную AsyncSession (db),
#    чтобы одна задача worker'а работала в рамках одного unit of work.
#    """
#    store = ArtifactStore()
#
#    # 1. Загрузить данные из БД
#    logger.info("Загрузка данных для экспорта", run_id=run_id, deal_id=deal_id)
#
#    check_results = await _load_check_results(run_id, db)
#    documents = await _load_documents_metadata(deal_id, db)
#    deal_name = await _load_deal_name(deal_id, db)
#
#    logger.info(
#        "Данные загружены",
#        run_id=run_id,
#        check_results=len(check_results),
#        documents=len(documents),
#    )
#
#    # 2. Агрегировать результаты (Stage 9 Aggregator)
#    aggregated = aggregate_results(
#        deal_id=deal_id,
#        deal_name=deal_name,
#        run_id=run_id,
#        check_results=check_results,
#        documents=documents,
#    )
#
#    refs: dict[str, str | None] = {}
#
#    # 3. DD Grid Excel (.xlsx)
#    try:
#        grid_bytes = build_grid_excel(aggregated)
#        refs["dd_grid"] = _save_artifact(
#            store,
#            tenant_id,
#            deal_id,
#            run_id,
#            suffix="_dd_grid.xlsx",
#            data=grid_bytes,
#            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
#        )
#        logger.info("DD Grid Excel сохранён", ref=refs["dd_grid"])
#    except Exception as e:
#        logger.error("Ошибка генерации DD Grid Excel", error=str(e))
#        refs["dd_grid"] = None
#
#    # 4. Summary Excel (.xlsx)
#    try:
#        summary_bytes = build_summary_excel(aggregated)
#        refs["summary"] = _save_artifact(
#            store,
#            tenant_id,
#            deal_id,
#            run_id,
#            suffix="_summary.xlsx",
#            data=summary_bytes,
#            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
#        )
#        logger.info("Summary Excel сохранён", ref=refs["summary"])
#    except Exception as e:
#        logger.error("Ошибка генерации Summary Excel", error=str(e))
#        refs["summary"] = None
#
#    # 5. Word Report (.docx)
#    try:
#        report_bytes = build_report_docx(aggregated)
#        refs["report"] = _save_artifact(
#            store,
#            tenant_id,
#            deal_id,
#            run_id,
#            suffix="_report.docx",
#            data=report_bytes,
#            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
#        )
#        logger.info("Word Report сохранён", ref=refs["report"])
#    except Exception as e:
#        logger.error("Ошибка генерации Word Report", error=str(e))
#        refs["report"] = None
#
#    # 6. JSON-дамп агрегации
#    try:
#        json_bytes = json.dumps(aggregated.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")
#        refs["json"] = _save_artifact(
#            store,
#            tenant_id,
#            deal_id,
#            run_id,
#            suffix="_aggregated.json",
#            data=json_bytes,
#            content_type="application/json",
#        )
#        logger.info("JSON-дамп сохранён", ref=refs["json"])
#    except Exception as e:
#        logger.error("Ошибка генерации JSON-дампа", error=str(e))
#        refs["json"] = None
#
#    # 7. Сохранить запись об экспорте (основной ref = dd_grid для обратной совместимости)
#    await _save_export_record(run_id, refs.get("dd_grid"), db)
#
#    logger.info(
#        "Экспорт завершён",
#        run_id=run_id,
#        check_results=len(check_results),
#        severity=aggregated.severity_counts.to_dict(),
#        top_risks=len(aggregated.top_risks),
#        dd_requests=len(aggregated.dd_requests),
#        conditional_rows=len(aggregated.conditional_rows),
#        structured_values=len(aggregated.structured_value_rows),
#        refs=list(refs.keys()),
#    )
#
#    return {
#        "run_id": run_id,
#        "deal_id": deal_id,
#        "rows": len(check_results),
#        "top_risks": len(aggregated.top_risks),
#        "dd_requests": len(aggregated.dd_requests),
#        "severity": aggregated.severity_counts.to_dict(),
#        # Ссылки на сгенерированные файлы
#        "export_ref": refs.get("dd_grid"),  # обратная совместимость
#        "refs": {k: v for k, v in refs.items() if v is not None},
#    }


# ---------------------------------------------------------------------------
# Celery task (точка входа — не изменилась по сигнатуре)
# ---------------------------------------------------------------------------


@celery_app.task(
    base=MASBaseTask,
    bind=True,
    name="workers.export_results",
    track_job=False,
    queue="default",
)
async def export_results(
    self,
    run_id: str,
    deal_id: str,
    tenant_id: str,
) -> dict:
    """
    Celery entrypoint: async оболочка вокруг export_core.

    Снаружи сигнатура и формат возвращаемого значения остаются прежними,
    чтобы не ломать существующих потребителей.

    Внутри:
      - создаём UnitOfWork / AsyncSession через db_uow();
      - вызываем services.export.core.export_core(...);
      - возвращаем результат export_core.
    """
    logger.info("Запуск экспорта", run_id=run_id, deal_id=deal_id)

    async with db_uow() as uow:
        result = await export_core(
            run_id=run_id,
            deal_id=deal_id,
            tenant_id=tenant_id,
            db=uow.session,
        )
        return result
