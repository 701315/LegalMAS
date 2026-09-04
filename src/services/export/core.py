# src/services/export/core.py

"""
Ядро экспорта результатов анализа по сделке/Run.

Отвечает за:
- загрузку данных из БД (результаты проверок, документы, метаданные сделки, Run/Playbook);
- агрегацию результатов (services.export.aggregator);
- генерацию файлов экспорта (DD Grid, Summary, Word‑отчёт, JSON‑дамп);
- сохранение файлов в ArtifactStore и возврат ссылок (refs).

Важно:
- не знает ничего про Celery/FastAPI, работает поверх AsyncSession;
- сам не создаёт/не обновляет записи Export и не меняет статус Run;
- старается быть максимально детерминированным и воспроизводимым:
  в отчёты явно передаются playbook_version, playbook_profile, checks_mode,
  pipeline_strategy и environment_hash для трассировки контекста Run;
- поддерживает presentation_locale для генерации отчётов на языке пользователя.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.i18n.export_translator import normalize_export_locale
from core.logging import get_logger
import db
from db.models.playbook import PlaybookVersion
from db.models.result import CheckResult
from db.repositories import (
    DealRepository,
    ResultRepository,
    RunnerRepository,
    RunRepository,
)
from ops.metrics import METRICS
from services.export.report_builder import build_report_docx
from services.export.summary_builder import build_summary_excel
from services.export.dd_grid_v1_excel_builder import build_dd_grid_v1_excel

from storage.artifact_store import ArtifactStore
from storage.exports import ExportSuffix

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Загрузка данных из БД
# ---------------------------------------------------------------------------


async def _load_check_results(run_id: str, db: AsyncSession) -> list[dict[str, Any]]:
    """
    Загрузить результаты проверок из БД для данного run_id и
    вернуть список словарей (core не знает про ORM-модели).
    """
    repo = ResultRepository(db)
    results: list[CheckResult] = await repo.get_by_run(uuid.UUID(run_id))

    rows: list[dict[str, Any]] = []
    for r in results:
        rows.append(
            {
                # Базовые поля
                "check_id": r.check_id,
                "check_name": r.check_name,
                "result": r.result,
                "severity": r.severity,
                "value_text": r.value_text or "",
                "confidence": r.confidence or 0.0,
                "detector_used": getattr(r, "detector_used", "") or "",
                "quality_flags": getattr(r, "quality_flags", {}) or {},
                "qc_status": getattr(r, "qc_status", "pending") or "pending",
                "document_id": str(r.document_id) if r.document_id else "",
                "page": getattr(r, "page", None),
                "clause_uid": getattr(r, "clause_uid", "") or "",
                # Stage 8
                "structured_data": getattr(r, "structured_data", {}) or {},
                "conditional_check_triggered": getattr(r, "conditional_check_triggered", False)
                or False,
                "trigger_name": getattr(r, "trigger_name", "") or "",
            }
        )

    return rows


async def _load_documents_metadata(run_id: str, db: AsyncSession) -> dict[str, dict[str, Any]]:
    """
    Загрузить метаданные документов, реально участвовавших в указанном run_id.

    Это корректнее, чем смотреть на "текущие non-duplicate документы сделки":
    export должен быть привязан к фактическому составу документов данного run.
    """
    repo = RunnerRepository(db)
    documents = await repo.load_documents_for_run(uuid.UUID(run_id))

    logger.info(
        "Export: loading documents metadata for run",
        extra={
            "run_id": str(run_id),
            "documents_count": len(documents),
        },
    )

    docs: dict[str, dict[str, Any]] = {}
    for document_id, payload in documents.items():
        docs[document_id] = {
            "name": payload.get("name") or "",
            "folder_path": payload.get("folder_path") or "",
            "doc_type": payload.get("doc_type") or "Generic",
            "status": payload.get("status") or "active",
            "classification_level": payload.get("classification_level") or "",
            "classification_confidence": payload.get("classification_confidence") or 0.0,
            "applicable_triggers": payload.get("applicable_triggers") or [],
            "classification_requires_review": bool(
                payload.get("classification_requires_review") or False
            ),
        }

    return docs


async def _load_deal_name(deal_id: str, db: AsyncSession) -> str:
    """
    Получить название сделки по deal_id.
    Возвращает deal_id в строковом виде, если имя не найдено.
    """
    try:
        repo = DealRepository(db)
        deal = await repo.get_by_id(uuid.UUID(deal_id))
        if deal and deal.name:
            return deal.name
    except Exception:
        # Не хотим ломать экспорт, если репозиторий/модель ещё не готовы.
        logger.warning("Не удалось получить имя сделки", deal_id=deal_id)

    return deal_id


# ---------------------------------------------------------------------------
# Публичный core-API: export_core
# ---------------------------------------------------------------------------


async def export_core(
    *,
    run_id: str,
    deal_id: str,
    tenant_id: str,
    db: AsyncSession,
    presentation_locale: str = "en",
) -> dict[str, Any]:
    """
    Общий core экспорта.

    Делает следующее:
      - загружает данные из БД,
      - агрегирует их,
      - генерирует файлы (grid, summary, report, aggregated JSON),
      - сохраняет файлы через ArtifactStore,
      - возвращает структурированную информацию о результатах.

    ВАЖНО:
      - НЕ создаёт и НЕ обновляет записи Export в БД;
      - НЕ меняет статус Run;
      - НЕ зависит от Celery / FastAPI.
    """
    locale = normalize_export_locale(presentation_locale)

    logger.info(
        "Export core starting",
        extra={"deal_id": deal_id, "run_id": run_id, "locale": locale},
    )

    store = ArtifactStore()

    # 1. Загрузка данных
    logger.info("Загрузка данных для экспорта", run_id=run_id, deal_id=deal_id)

    check_results = await _load_check_results(run_id, db)
    documents = await _load_documents_metadata(run_id, db)
    deal_name = await _load_deal_name(deal_id, db)

    # 1.1. Загружаем Run и Playbook для целей воспроизводимости отчёта.
    run_repo = RunRepository(db)
    run_obj = await run_repo.get_by_id(uuid.UUID(run_id))

    playbook_version_str = "1.0.0"
    playbook_profile_str = "M&A Russia DD"
    env_hash_str = ""

    # Режим проверок и стратегия пайплайна текущего Run.
    checks_mode_str = ""
    pipeline_strategy_str = ""

    if run_obj is not None:
        env_hash_str = run_obj.environment_hash or ""
        checks_mode_str = getattr(run_obj, "checks_mode", "") or ""
        pipeline_strategy_str = getattr(run_obj, "pipeline_strategy", "") or ""

        try:
            pb_result = await db.execute(
                select(PlaybookVersion).where(PlaybookVersion.id == run_obj.playbook_version_id)
            )
            pb_obj = pb_result.scalar_one_or_none()
        except Exception:
            pb_obj = None

        if pb_obj is not None:
            playbook_version_str = pb_obj.semver or playbook_version_str
            if pb_obj.name:
                playbook_profile_str = pb_obj.name

    # 1.2. Загружаем CheckDefinition для нового Excel builder
    from db.repositories.playbook_repo import PlaybookRepository
    from engine.playbook.loader import load_playbook_from_version

    pb_repo = PlaybookRepository(db)
    checks_by_id: dict[str, Any] = {}

    if run_obj and run_obj.playbook_version_id:
        try:
            pb_version = await pb_repo.get_by_id(run_obj.playbook_version_id)
            if pb_version:
                playbook = load_playbook_from_version(pb_version)
                checks_by_id = {check.id: check for check in playbook.checks}
                logger.info(
                    "Loaded CheckDefinitions for Excel export",
                    run_id=run_id,
                    checks_count=len(checks_by_id),
                )
        except Exception as e:
            logger.warning(
                "Failed to load CheckDefinitions for Excel export",
                run_id=run_id,
                error=str(e),
            )

    logger.info(
        "Данные для экспорта загружены",
        run_id=run_id,
        check_results=len(check_results),
        documents=len(documents),
    )

    aggregated = None

    refs: dict[str, str | None] = {
        "dd_grid": None,
        "summary": None,
        "report": None,
        "json": None,
    }

    # 3. DD Grid Excel — новый путь через DDGridV1Data
    try:
        from db.repositories.runner_repo import RunnerRepository
        from db.repositories.run_check_plan_item_repo import RunCheckPlanItemRepository
        from classifiers.yaml_registry import YAMLRegistry
        from services.dd_grid_v1_builder import build_dd_grid_v1

        runner_repo = RunnerRepository(db)
        plan_item_repo = RunCheckPlanItemRepository(db)

        check_results_for_grid = await runner_repo.load_check_results_for_run(uuid.UUID(run_id))
        documents_for_grid = await runner_repo.load_documents_for_run(uuid.UUID(run_id))
        plan_items = await plan_item_repo.list_by_run_id(uuid.UUID(run_id))

        registry = YAMLRegistry.get_instance()

        grid_data = build_dd_grid_v1(
            checks=list(checks_by_id.values()),
            check_results=check_results_for_grid,
            documents=documents_for_grid,
            registry=registry,
            plan_items=plan_items,
            checks_mode=checks_mode_str,
        )

        grid_bytes = build_dd_grid_v1_excel(
            grid_data=grid_data,
            check_results=check_results_for_grid,
            documents=documents_for_grid,
            checks_by_id=checks_by_id,
            deal_name=deal_name,
            run_id=run_id,
            checks_mode=checks_mode_str,
            pipeline_strategy=pipeline_strategy_str,
            locale=locale,
        )

        refs["dd_grid"] = store.save_export_artifact(
            tenant_id=tenant_id,
            deal_id=deal_id,
            run_id=run_id,
            suffix=ExportSuffix.DD_GRID,
            data=grid_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        METRICS.export_duration.labels(export_type="grid_xlsx").observe(0.0)
        logger.info("DD Grid V1 Excel сохранён", ref=refs["dd_grid"], locale=locale)
    except Exception as e:  # noqa: BLE001
        logger.error("Ошибка генерации DD Grid V1 Excel", error=str(e), exc_info=True)
        refs["dd_grid"] = None

    # 4. Summary Excel — новый путь через прямое чтение
    try:
        summary_bytes = build_summary_excel(
            check_results=check_results,
            documents=documents,
            checks_by_id=checks_by_id,
            deal_name=deal_name,
            checks_mode=checks_mode_str,
            pipeline_strategy=pipeline_strategy_str,
            locale=locale,  # <-- ПЕРЕДАЕМ LOCALE СЮДА
        )
        refs["summary"] = store.save_export_artifact(
            tenant_id=tenant_id,
            deal_id=deal_id,
            run_id=run_id,
            suffix=ExportSuffix.DEAL_SUMMARY,
            data=summary_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        METRICS.export_duration.labels(export_type="summary_xlsx").observe(0.0)
        logger.info("Summary Excel V1 сохранён", ref=refs["summary"])
    except Exception as e:  # noqa: BLE001
        logger.error("Ошибка генерации Summary Excel V1", error=str(e), exc_info=True)
        refs["summary"] = None

    # 5. Word report — новый путь через прямое чтение check_results
    try:
        report_bytes = build_report_docx(
            check_results=check_results,
            documents=documents,
            checks_by_id=checks_by_id,
            deal_name=deal_name,
            run_id=run_id,
            playbook_version=playbook_version_str,
            playbook_profile=playbook_profile_str,
            environment_hash=env_hash_str,
            checks_mode=checks_mode_str,
            pipeline_strategy=pipeline_strategy_str,
            locale=locale,  # <-- ПЕРЕДАЕМ LOCALE СЮДА
        )
        refs["report"] = store.save_export_artifact(
            tenant_id=tenant_id,
            deal_id=deal_id,
            run_id=run_id,
            suffix=ExportSuffix.REPORT,
            data=report_bytes,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        METRICS.export_duration.labels(export_type="report_docx").observe(0.0)
        logger.info("Word Report V1 сохранён", ref=refs["report"])
    except Exception as e:  # noqa: BLE001
        logger.error("Ошибка генерации Word Report V1", error=str(e), exc_info=True)
        refs["report"] = None

    # 6. JSON dump
    try:
        json_payload = {
            "deal_id": deal_id,
            "deal_name": deal_name,
            "run_id": run_id,
            "playbook_version": playbook_version_str,
            "playbook_profile": playbook_profile_str,
            "checks_mode": checks_mode_str,
            "pipeline_strategy": pipeline_strategy_str,
            "environment_hash": env_hash_str,
            "total_documents": len(documents),
            "total_checks": len(check_results),
            "check_results_count": len(check_results),
        }
        json_bytes = json.dumps(
            json_payload,
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        refs["json"] = store.save_export_artifact(
            tenant_id=tenant_id,
            deal_id=deal_id,
            run_id=run_id,
            suffix=ExportSuffix.AGGREGATED,
            data=json_bytes,
            content_type="application/json",
        )
        METRICS.export_duration.labels(export_type="aggregated_json").observe(0.0)
        logger.info("JSON dump V1 сохранён", ref=refs["json"])
    except Exception as e:  # noqa: BLE001
        logger.error("Ошибка генерации JSON dump V1", error=str(e), exc_info=True)
        refs["json"] = None

    export_ref = refs.get("dd_grid")

    logger.info(
        "Export core completed",
        extra={"deal_id": deal_id, "run_id": run_id, "locale": locale},
    )

    return {
        "run_id": run_id,
        "deal_id": deal_id,
        "rows": len(check_results),
        "top_risks": len(getattr(aggregated, "top_risks", [])) if aggregated else 0,
        "dd_requests": len(getattr(aggregated, "dd_requests", [])) if aggregated else 0,
        "severity": getattr(aggregated, "severity_counts", {}),
        "export_ref": export_ref,
        "refs": {k: v for k, v in refs.items() if v is not None},
        "all_refs": refs,
    }


    