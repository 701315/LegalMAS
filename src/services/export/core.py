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
  pipeline_strategy и environment_hash для трассировки контекста Run.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Mapping

from sqlalchemy.ext.asyncio import AsyncSession
from ops.metrics import METRICS
from sqlalchemy import select
from core.logging import get_logger
from db.models.result import CheckResult
from services.export.aggregator import aggregate_results
from services.export.grid_builder import build_grid_excel
from services.export.report_builder import build_report_docx
from services.export.summary_builder import build_summary_excel
from storage.artifact_store import ArtifactPath, ArtifactStore
from db.repositories import (
    DealRepository,
    ResultRepository,
    RunnerRepository,
    RunRepository,
)
from db.models.playbook import PlaybookVersion

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Загрузка данных из БД
# ---------------------------------------------------------------------------


async def _load_check_results(run_id: str, db: AsyncSession) -> List[Dict[str, Any]]:
    """
    Загрузить результаты проверок из БД для данного run_id и
    вернуть список словарей (core не знает про ORM-модели).
    """
    repo = ResultRepository(db)
    results: List[CheckResult] = await repo.get_by_run(uuid.UUID(run_id))

    rows: List[Dict[str, Any]] = []
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
                "conditional_check_triggered": getattr(
                    r, "conditional_check_triggered", False
                )
                or False,
                "trigger_name": getattr(r, "trigger_name", "") or "",
            }
        )

    return rows


async def _load_documents_metadata(
    deal_id: str, db: AsyncSession
) -> Dict[str, Dict[str, Any]]:
    """
    Загрузить метаданные документов по сделке.
    Ключ словаря — document_id в строковом виде.
    """
    repo = RunnerRepository(db)
    documents = await repo.get_non_duplicate_docs(uuid.UUID(deal_id))

    logger.info(
        "Export: loading documents metadata",
        extra={
            "deal_id": str(deal_id),
            "documents_count": len(documents),
        },
    )

    docs: Dict[str, Dict[str, Any]] = {}

    for d in documents:
        docs[str(d.id)] = {
            "name": getattr(d, "filename", None) or getattr(d, "name", ""),
            "folder_path": getattr(d, "folder_path", "") or "",
            "doc_type": getattr(d, "doc_type", "Generic") or "Generic",
            "status": getattr(d, "status", "active") or "active",
            "classification_level": getattr(d, "classification_level", "") or "",
            "classification_confidence": getattr(
                d, "classification_confidence", 0.0
            )
            or 0.0,
            "applicable_triggers": getattr(d, "applicable_triggers", []) or [],
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
# Сохранение артефактов
# ---------------------------------------------------------------------------


def _save_artifact(
    store: ArtifactStore,
    tenant_id: str,
    deal_id: str,
    run_id: str,
    suffix: str,
    data: bytes,
    content_type: str,
) -> str | None:
    """
    Сохранить файл в ArtifactStore. Возвращает ref (путь/URI) или None при ошибке.
    """
    try:
        export_path = ArtifactPath.export(tenant_id, deal_id, run_id)
        return store.put_file(
            f"{export_path}{suffix}",
            data,
            content_type=content_type,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "Не удалось сохранить артефакт",
            suffix=suffix,
            error=str(e),
        )
        return None


# ---------------------------------------------------------------------------
# Публичный core-API: export_core
# ---------------------------------------------------------------------------


async def export_core(
    *,
    run_id: str,
    deal_id: str,
    tenant_id: str,
    db: AsyncSession,
) -> Dict[str, Any]:
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

    Возвращает словарь вида:
    {
        "run_id": ...,
        "deal_id": ...,
        "rows": <int>,
        "top_risks": <int>,
        "dd_requests": <int>,
        "severity": {...},
        "export_ref": <str | None>,         # основной файл (для обратной совместимости)
        "refs": {                           # ключ -> ref (только не-None)
            "dd_grid": <str>,
            "summary": <str>,
            "report": <str>,
            "json": <str>,
        },
        "all_refs": {                       # ключ -> ref (включая None)
            "dd_grid": <str | None>,
            "summary": <str | None>,
            "report": <str | None>,
            "json": <str | None>,
        },
    }
    """

    logger.info(
        "Export core starting",
        extra={"deal_id": deal_id, "run_id": run_id},
    )

    store = ArtifactStore()

    # 1. Загрузка данных
    logger.info("Загрузка данных для экспорта", run_id=run_id, deal_id=deal_id)

    check_results = await _load_check_results(run_id, db)
    documents = await _load_documents_metadata(deal_id, db)
    deal_name = await _load_deal_name(deal_id, db)

    # 1.1. Загружаем Run и Playbook для целей воспроизводимости отчёта.
    run_repo = RunRepository(db)
    run_obj = await run_repo.get_by_id(uuid.UUID(run_id))

    playbook_version_str = "1.0.0"
    playbook_profile_str = "M&A Russia DD"
    env_hash_str = ""

    # НОВОЕ: режим проверок и стратегия пайплайна текущего Run.
    checks_mode_str = ""
    pipeline_strategy_str = ""

    if run_obj is not None:
        # Берём хэш окружения из Run, если он есть.
        env_hash_str = run_obj.environment_hash or ""

        # Режим проверок и стратегия пайплайна — передадим в экспорт,
        # чтобы добавить их в шапку файлов.
        checks_mode_str = getattr(run_obj, "checks_mode", "") or ""
        pipeline_strategy_str = getattr(run_obj, "pipeline_strategy", "") or ""

        # Пытаемся подтянуть PlaybookVersion, чтобы взять реальную версию.
        try:
            pb_result = await db.execute(
                select(PlaybookVersion).where(
                    PlaybookVersion.id == run_obj.playbook_version_id
                )
            )
            pb_obj = pb_result.scalar_one_or_none()
        except Exception:
            pb_obj = None

        if pb_obj is not None:
            # Используем реальную semver плейбука.
            playbook_version_str = pb_obj.semver or playbook_version_str

            # В качестве "профиля анализа" логично показать name плейбука,
            # если он задан; иначе оставляем дефолт.
            if pb_obj.name:
                playbook_profile_str = pb_obj.name

    logger.info(
        "Данные для экспорта загружены",
        run_id=run_id,
        check_results=len(check_results),
        documents=len(documents),
    )

    # 2. Агрегация
    aggregated = aggregate_results(
        deal_id=deal_id,
        deal_name=deal_name,
        run_id=run_id,
        check_results=check_results,
        documents=documents,
    )

    refs: Dict[str, str | None] = {
        "dd_grid": None,
        "summary": None,
        "report": None,
        "json": None,
    }

    # 3. DD Grid Excel
    try:
        # НОВОЕ: передаём метаданные Run в билдера таблицы.
        grid_bytes = build_grid_excel(
            aggregated,
            checks_mode=checks_mode_str,
            pipeline_strategy=pipeline_strategy_str,
        )
        refs["dd_grid"] = _save_artifact(
            store,
            tenant_id,
            deal_id,
            run_id,
            suffix="_dd_grid.xlsx",
            data=grid_bytes,
            content_type=(
                "application/"
                "vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        METRICS.export_duration.labels(export_type="grid_xlsx").observe(0.0)
        logger.info("DD Grid Excel сохранён", ref=refs["dd_grid"])
    except Exception as e:  # noqa: BLE001
        logger.error("Ошибка генерации DD Grid Excel", error=str(e))
        refs["dd_grid"] = None

    # 4. Summary Excel
    try:
        summary_bytes = build_summary_excel(
            aggregated,
            checks_mode=checks_mode_str,
            pipeline_strategy=pipeline_strategy_str,
        )
        refs["summary"] = _save_artifact(
            store,
            tenant_id,
            deal_id,
            run_id,
            suffix="_summary.xlsx",
            data=summary_bytes,
            content_type=(
                "application/"
                "vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
        METRICS.export_duration.labels(export_type="summary_xlsx").observe(0.0)
        logger.info("Summary Excel сохранён", ref=refs["summary"])
    except Exception as e:  # noqa: BLE001
        logger.error("Ошибка генерации Summary Excel", error=str(e))
        refs["summary"] = None

    # 5. Word report
    try:
        report_bytes = build_report_docx(
            aggregated,
            playbook_version=playbook_version_str,
            playbook_profile=playbook_profile_str,
            environment_hash=env_hash_str,
            # НОВОЕ: режим и стратегия текущего Run в шапке отчёта.
            checks_mode=checks_mode_str,
            pipeline_strategy=pipeline_strategy_str,
        )
        refs["report"] = _save_artifact(
            store,
            tenant_id,
            deal_id,
            run_id,
            suffix="_report.docx",
            data=report_bytes,
            content_type=(
                "application/"
                "vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
        )
        METRICS.export_duration.labels(export_type="report_docx").observe(0.0)
        logger.info("Word Report сохранён", ref=refs["report"])
    except Exception as e:  # noqa: BLE001
        logger.error("Ошибка генерации Word Report", error=str(e))
        refs["report"] = None

    # 6. JSON aggregated
    try:
        json_bytes = json.dumps(
            aggregated.to_dict(),
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        refs["json"] = _save_artifact(
            store,
            tenant_id,
            deal_id,
            run_id,
            suffix="_aggregated.json",
            data=json_bytes,
            content_type="application/json",
        )
        METRICS.export_duration.labels(export_type="aggregated_json").observe(0.0)
        logger.info("JSON-дамп сохранён", ref=refs["json"])
    except Exception as e:  # noqa: BLE001
        logger.error("Ошибка генерации JSON-дампа", error=str(e))
        refs["json"] = None

    # Основной ref для обратной совместимости — dd_grid
    export_ref = refs.get("dd_grid")

    logger.info(
        "Export core completed",
        extra={"deal_id": deal_id, "run_id": run_id},
    )

    return {
        "run_id": run_id,
        "deal_id": deal_id,
        "rows": len(check_results),
        "top_risks": len(aggregated.top_risks),
        "dd_requests": len(aggregated.dd_requests),
        "severity": aggregated.severity_counts.to_dict(),
        "export_ref": export_ref,
        "refs": {k: v for k, v in refs.items() if v is not None},
        "all_refs": refs,
    }
