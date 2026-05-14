# src/api/endpoints/runs.py

"""
Эндпоинты для запусков анализа (runs).

- POST /runs                               — запуск анализа по сделке
- GET  /runs/{run_id}                      — статус run + (опционально) stats классификации
- GET  /runs/{run_id}/classification-report — подробный отчёт по классификации
"""

from __future__ import annotations  # сильно упрощает жизнь с аннотациями

import uuid
from uuid import UUID
import json
from typing import Literal

from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from core.constants import RunStatus, LanguageDiscoveryStatus
from fastapi.responses import StreamingResponse
from services.run_progress_service import subscribe_run_progress

from api.schemas.runs import DealRunSummaryResponse
from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role

from db.session import get_db
from db.repositories.deal_repo import DealRepository
from db.repositories.playbook_repo import PlaybookRepository
from db.repositories.run_repo import RunRepository
from db.repositories.document_repo import DocumentRepository
from db.repositories.export_repo import ExportRepository
from db.repositories.result_repo import ResultRepository
from db.repositories.audit_repo import AuditRepository

from mas_queue.celery_app import celery_app
from core.error_catalog import render_error_message

from core.config import settings
from services.run_analytics_service import RunAnalyticsService, RunNotFoundError

from ..schemas.runs import (
    RunCreate,
    RunResponse,
    ClassificationReportResponse,
)
from ..schemas.results import CheckResultResponse
from ..schemas.pagination import PaginatedResponse as PaginatedResponseSchema
from core.logging import get_logger

logger = get_logger(__name__)


router = APIRouter(prefix="/runs", tags=["runs"])


async def _start_run_core(
    deal_uuid: uuid.UUID,
    data: RunCreate,
    db: AsyncSession,
    user: CurrentUser,
) -> RunResponse:
    """
    Общая логика запуска run для сделки.

    Теперь:
    1) проверяем существование сделки;
    2) находим playbook для этой сделки (или default);
    3) берём из него model_config_id;
    4) создаём Run с этими ID;
    5) обновляем last_run_id у сделки;
    6) ставим одну оркестрационную Celery-задачу start_run_pipeline(run_id),
       которая уже сама разберётся, какие документы и какие стадии пайплайна
       нужно пройти (extract → pii → structure → classify → run_deal_checks).
    """
    run_repo = RunRepository(db)
    deal_repo = DealRepository(db)
    playbook_repo = PlaybookRepository(db)
    audit_repo = AuditRepository(db)

    # 1. Проверяем, что сделка существует
    deal = await deal_repo.get_by_id(deal_uuid)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    # 1.1. Для запуска анализа основной язык сделки должен быть выбран заранее.
    #
    # Архитектурное правило системы:
    # - сначала выполняется pre-run language discovery;
    # - затем пользователь выбирает primary_language сделки;
    # - только после этого разрешён запуск Run.
    #
    # Поэтому backend здесь жёстко запрещает запуск анализа,
    # если основной язык сделки ещё не задан.
    if not getattr(deal, "primary_language", None):
        logger.warning(
            "Run start rejected: primary_language is not set",
            extra={
                "deal_id": str(deal_uuid),
                "tenant_id": str(getattr(deal, "tenant_id", "")),
                "requested_by": (
                    str(getattr(user, "id", None))
                    if getattr(user, "id", None)
                    else "unknown"
                ),
            },
        )
        raise HTTPException(
            status_code=400,
            detail=(
                "Primary language must be selected before starting analysis"
            ),
        )

    # 1.2. Пока language discovery ещё выполняется, запуск Run запрещён.
    # Это защита на backend уровне: даже если UI ошибётся или кто-то вызовет
    # API напрямую, analysis нельзя стартовать до завершения pre-run discovery.
    if getattr(deal, "language_discovery_status", None) == LanguageDiscoveryStatus.PROCESSING:
        logger.warning(
            "Run start rejected: language discovery is still in progress",
            extra={
                "deal_id": str(deal_uuid),
                "tenant_id": str(getattr(deal, "tenant_id", "")),
                "requested_by": (
                    str(getattr(user, "id", None))
                    if getattr(user, "id", None)
                    else "unknown"
                ),
                "language_discovery_status": getattr(
                    deal, "language_discovery_status", None
                ),
            },
        )
        raise HTTPException(
            status_code=400,
            detail=(
                "Language discovery is still in progress. "
                "Please wait until it completes before starting analysis."
            ),
        )


    # 2. Берём playbook для сделки (привязанный или default)
    playbook = await playbook_repo.get_for_deal(deal_uuid)
    if not playbook:
        raise HTTPException(
            status_code=400,
            detail="Deal is not configured with a playbook",
        )

    # 3. Проверяем, что у playbook есть model_config
    if not playbook.model_config_id:
        raise HTTPException(
            status_code=400,
            detail="Playbook is not configured with model_config",
        )

    playbook_version_id = playbook.id
    model_config_id = playbook.model_config_id

    # 4. Определяем стратегию пайплайна и создаём run.
    #
    # Сейчас у нас есть два ключевых фактора:
    # - модель (model_config_id), привязанная к playbook;
    # - выбранный playbook_version (playbook_version_id).
    #
    # Идея такая:
    # - если модель изменилась по сравнению с последним Run по этой сделке —
    #   безопаснее пересчитать всё с нуля (FULL_RERUN);
    # - если модель та же, мы можем переиспользовать структуру документов
    #   и только заново прогнать проверки под новым плейбуком (REUSE_STRUCTURE).
    #
    # Отдельно от этого, в будущем сюда можно будет добавить сравнение
    # "технического окружения" через Run.environment_hash и/или
    # конфигурационный fingerprint плейбука, когда появится единый источник
    # этих данных (см. TODO ниже).
    pipeline_strategy = "REUSE_STRUCTURE"

    last_run = await run_repo.get_latest_for_deal(deal_uuid)
    if last_run:
        same_model = (last_run.model_config_id == model_config_id)
        # TODO (env/reproducibility):
        #  - Run.environment_hash сейчас почти всегда None и не заполняется
        #    на уровне инфраструктуры;
        #  - на уровне плейбука/ModelConfig пока нет единого fingerprint'а
        #    конфигурации анализа.
        # Когда появится:
        #  - функция, считающая environment_hash для текущего запуска
        #    (docker + libs + weights),
        #  - и/или config_fingerprint для (playbook + model_config + registry),
        # сюда можно добавить сравнение окружения и конфигурации анализа.
        # Если модель или окружение изменились — лучше прогнать всё с нуля
        # (FULL_RERUN), иначе можно безопасно REUSE_STRUCTURE.
        if not same_model:
            pipeline_strategy = "FULL_RERUN"
        else:
            # Модель та же; структура документа не зависит от набора проверок,
            # поэтому достаточно переиспользовать структуру и заново оценить риски.
            pipeline_strategy = "REUSE_STRUCTURE"

    run = await run_repo.create(
        deal_id=deal_uuid,
        playbook_version_id=playbook_version_id,
        model_config_id=model_config_id,
        bundle_id=None,
        profile=data.profile,
        pipeline_strategy=pipeline_strategy,
        checks_mode=data.checks_mode,
    )

    logger.info(
        "Run created",
        extra={
            "run_id": str(run.id),
            "deal_id": str(deal_uuid),
            "playbook_version_id": str(playbook_version_id),
            "model_config_id": str(model_config_id),
            "pipeline_strategy": pipeline_strategy,
            "created_by": getattr(user, "id", None),
        },
    )

    # 5. Обновляем last_run_id и агрегированные поля по последнему Run у сделки
    await deal_repo.set_last_run_id(
        deal_id=deal_uuid,
        run_id=run.id,
        checks_mode=getattr(run, "checks_mode", None),
        pipeline_strategy=getattr(run, "pipeline_strategy", None),
    )

    # 5.1. Сбрасываем флаг незакрытых ручных переклассификаций:
    # юрист только что запустил новый анализ, значит все текущие
    # переклассификации считаем «учтёнными» этим run.
    await deal_repo.set_has_pending_manual_reclassifications(
        deal_id=deal_uuid,
        value=False,
    )

    # 6. Фиксируем изменения в БД перед постановкой задач
    await db.commit()
    await db.refresh(run)

    # 6.1. Аудит: пользователь запросил запуск анализа по сделке
    try:
        await audit_repo.log(
            tenant_id=getattr(user, "tenant_id", None) or uuid.UUID(int=0),
            deal_id=deal_uuid,
            action="ANALYSIS_REQUESTED",
            actor=str(getattr(user, "id", None)) if getattr(user, "id", None) else "unknown",
            actor_role=getattr(user, "global_role", "user"),
            details={
                "run_id": str(run.id),
                "deal_id": str(deal_uuid),
                "playbook_version_id": str(playbook_version_id),
                "model_config_id": str(model_config_id),
                "profile": data.profile,
                "checks_mode": data.checks_mode,
                "pipeline_strategy": pipeline_strategy,
                "force_reclassify": bool(
                    data.force_reclassify
                    and getattr(settings, "API_ALLOW_FORCE_RECLASSIFY", False)
                ),
            },
        )
        # commit уже был, аудит пойдёт в рамках того же транзакционного контекста
    except Exception as e:
        logger.warning(
            "Failed to write audit log for ANALYSIS_REQUESTED",
            extra={
                "run_id": str(run.id),
                "deal_id": str(deal_uuid),
                "error": str(e),
            },
        )

    # 7. Ставим одну оркестрационную Celery-задачу для run
    # Воркер workers.start_run_pipeline должен:
    # - по run_id найти deal и playbook;
    # - обойти все документы сделки;
    # - с учётом их статусов (PENDING/EXTRACTED/STRUCTURED/CLASSIFIED/COMPLETED)
    #   запустить или дозапустить пайплайн до run_checks.
    tenant_id = getattr(user, "tenant_id", None)

    try:

        logger.info(
            "Scheduling start_run_pipeline",
            extra={
                "run_id": str(run.id),
                "deal_id": str(deal_uuid),
            },
        )

        celery_app.send_task(
            "workers.start_run_pipeline",
            kwargs={
                "run_id": str(run.id),
                "deal_id": str(deal_uuid),
                "tenant_id": (
                    str(tenant_id)
                    if tenant_id
                    and str(tenant_id) != "00000000-0000-0000-0000-000000000000"
                    else None
                ),
                "force_reclassify": bool(
                    data.force_reclassify
                    and getattr(settings, "API_ALLOW_FORCE_RECLASSIFY", False)
                ),
            },
        )

    except Exception as e:
        msg = str(e)
        lower_msg = msg.lower()

        # Простейшая классификация ошибок брокера очередей.
        if any(
            token in lower_msg
            for token in (
                "connection refused",
                "connectionerror",
                "timeout",
                "broker",
                "rabbitmq",
                "redis",
            )
        ):
            reason = "queue_unavailable"
            http_detail = (
                "Не удалось запустить анализ сделки: очередь задач временно "
                "недоступна. Попробуйте ещё раз позже."
            )
        else:
            reason = "infrastructure_error"
            http_detail = (
                "Не удалось запустить анализ сделки: внутренняя ошибка "
                "инфраструктуры."
            )

        await _mark_run_failed_orchestrator(
            run_repo=run_repo,
            run_id=run.id,
            reason=reason,
            message=msg,
        )
        raise HTTPException(
            status_code=503,
            detail=http_detail,
        )

    return RunResponse.model_validate(run)


async def _mark_run_failed_orchestrator(
    run_repo: RunRepository,
    run_id: uuid.UUID,
    *,
    reason: str,
    message: str,
) -> None:
    """
    Пометить Run как FAILED при ошибке на уровне оркестратора/старта пайплайна.

    Используется, когда мы не смогли даже запустить workers.start_run_pipeline
    (проблема с брокером, Celery, конфигурацией и т.п.).
    """
    await run_repo.update_status(
        run_id,
        RunStatus.FAILED.value,
        error_details={
            "stage": "orchestrator",
            "type": (
                "infrastructure_error"
                if reason in ("infrastructure_error", "queue_unavailable")
                else "config_error"
            ),
            "reason": reason,
            "message": message,
        },
    )


@router.post(
    "",
    response_model=RunResponse,
    summary="Запуск анализа по сделке",
)
async def start_run(
    data: RunCreate,
    deal_id: str = Query(..., description="ID сделки, для которой запускаем анализ"),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Старый эндпоинт запуска: POST /api/v1/runs?deal_id=...

    Теперь:
    - перед вызовом общей логики _start_run_core добавлена проверка ролей;
    - запуск разрешён только для ролей "admin" и "editor".
    """
    deal_uuid = uuid.UUID(deal_id)

    # Проверяем право запускать анализ по этой сделке
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_uuid,
        allowed_roles=("admin", "editor"),
    )

    return await _start_run_core(deal_uuid, data, db, user)


@router.get(
    "/deal/{deal_id}",
    response_model=list[RunResponse],
    summary="Список запусков анализа для сделки",
)
async def list_runs_for_deal(
    deal_id: uuid.UUID,
    include_classification_stats: bool = Query(
        default=False,
        description="Если true — добавить блок classification_stats к каждому run",
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Вернуть все runs для указанной сделки (новые сначала).

    Если include_classification_stats=True — для каждого run
    дополнительно будет подсчитан блок статистики классификации.

    TODO:
    - при необходимости добавить проверку, что пользователь имеет доступ
      к этой сделке (viewer/editor/admin).
    """
    run_repo = RunRepository(db)

    runs = await run_repo.get_by_deal(deal_id)
    result = [RunResponse.model_validate(r) for r in runs]

    if include_classification_stats and runs:
        # Подгружаем статистику классификации для каждого run
        for i, run_obj in enumerate(runs):
            stats = await run_repo.get_classification_stats_for_run(run_obj.id)
            result[i].classification_stats = stats

    return result


@router.get(
    "/{run_id}",
    response_model=RunResponse,
    summary="Получить статус run и статистику классификации",
)
async def get_run(
    run_id: uuid.UUID,
    include_classification_stats: bool = Query(
        default=False,
        description="Если true — добавить блок classification_stats",
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Возвращает состояние run.

    Если include_classification_stats=True — дополнительно возвращает
    блок статистики классификации (L0–L4, low_confidence_count и т.п.).

    Доступ:
    - только участники проекта (viewer/editor/admin) для сделки этого run.
    """
    run_repo = RunRepository(db)
    run = await run_repo.get_by_id(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Проверка доступа по проектной роли (любой участник)
    await require_project_role(
        db=db,
        user=user,
        deal_id=run.deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    run_out = RunResponse.model_validate(run)

    if include_classification_stats:
        stats = await run_repo.get_classification_stats_for_run(run_id)
        # stats должен быть уже в виде ClassificationStats или dict под него
        run_out.classification_stats = stats

    # Человекочитаемое сообщение об ошибке уровня Run (если есть).
    if getattr(run, "error_details", None):
        run_out.error_user_message = render_error_message(run.error_details)

    return run_out


@router.get(
    "/{run_id}/events",
    summary="SSE-стрим прогресса Run (status + completed/total)",
)
async def stream_run_events(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    SSE-эндпоинт для прогресса Run.

    URL: GET /api/v1/runs/{run_id}/events
    Формат событий:
      data: {"run_id": "...", "status": "...", "completed_checks": 10, "total_checks": 100, ...}

    Доступ:
    - только участники проекта (viewer/editor/admin) для сделки этого run.
    """
    run_repo = RunRepository(db)
    run = await run_repo.get_by_id(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Проверка доступа по проектной роли (любой участник)
    await require_project_role(
        db=db,
        user=user,
        deal_id=run.deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    async def event_generator():
        async for event in subscribe_run_progress(db, run_id):
            # by_alias=True и mode="json" -> UUID и datetime станут строками
            payload = event.model_dump(mode="json")
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )


def get_run_analytics_service(
    db: AsyncSession = Depends(get_db),
) -> RunAnalyticsService:
    return RunAnalyticsService(db)


@router.get(
    "/{run_id}/classification-report",
    response_model=ClassificationReportResponse,
    summary="Подробный отчёт о качестве классификации для run",
)
async def get_classification_report(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    service: RunAnalyticsService = Depends(get_run_analytics_service),
):
    """
    Подробный отчёт о качестве классификации для run.

    Доступ:
    - только участники проекта (viewer/editor/admin) для сделки этого run.
    """
    try:
        report = await service.build_classification_report(run_id)
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found")

    # report должен содержать deal_id run'а (как минимум в модели сервиса).
    # Здесь проверяем доступ по проектной роли.
    await require_project_role(
        db=db,
        user=user,
        deal_id=report.deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    return report


class RunExportCreate(BaseModel):
    """
    Тело запроса экспорта.

    Клиент передаёт только тип экспорта.
    requested_by / requester_role вычисляются на сервере
    по текущему пользователю и project role.
    """
    export_type: Literal[
        "grid_xlsx",
        "deal_summary_xlsx",
        "report_docx",
        "aggregated_json",
    ]


class RunExportResponse(BaseModel):
    """
    Краткий ответ об экспорте для UI.
    """
    id: uuid.UUID
    run_id: uuid.UUID
    deal_id: uuid.UUID
    export_type: str
    status: str
    file_ref: str | None = None


@router.post(
    "/{run_id}/export",
    response_model=RunExportResponse,
    summary="Запустить экспорт результатов по run",
)
@router.post(
    "/{run_id}/export",
    response_model=RunExportResponse,
    summary="Запустить экспорт результатов по run",
)
async def start_run_export(
    run_id: uuid.UUID,
    data: RunExportCreate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Запускает экспорт результатов анализа для указанного run.

    ВАЖНО:
    - Экспорт разрешён только для пользователей с ролью "admin" или "editor"
      в проекте (сделке), к которому относится этот run.
    - Экспорт разрешён для run в статусах "completed" и "completed_with_errors".
    """
    run_repo = RunRepository(db)
    export_repo = ExportRepository(db)

    # 1. Находим run
    run = await run_repo.get_by_id(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # 2. Проверяем проектную роль (admin/editor) по deal_id
    await require_project_role(
        db=db,
        user=user,
        deal_id=run.deal_id,
        allowed_roles=("admin", "editor"),
    )

    # 3. Проверяем статус run — допускаем completed и completed_with_errors
    if run.status not in (RunStatus.COMPLETED.value, "completed_with_errors"):
        raise HTTPException(
            status_code=400,
            detail=(
                "Run status must be 'completed' or 'completed_with_errors' "
                f"to export, got '{run.status}'"
            ),
        )

    # 4. Определяем audit-поля: requested_by / requester_role
    requested_by = getattr(user, "id", None)
    requester_role = getattr(user, "global_role", "user")

    # 5. Создаём запись экспорта
    export = await export_repo.create(
        deal_id=run.deal_id,
        run_id=run.id,
        export_type=data.export_type,
        requested_by=requested_by,
        requester_role=requester_role,
        status="pending",
    )

    # ВАЖНО: сначала фиксируем запись в БД, потом ставим задачу в очередь
    await db.commit()
    await db.refresh(export)

    logger.info(
        "Export record created",
        extra={
            "export_id": str(export.id),
            "run_id": str(run.id),
            "deal_id": str(run.deal_id),
            "export_type": export.export_type,
            "status": export.status,
            "requested_by": str(requested_by) if requested_by else None,
            "requester_role": requester_role,
        },
    )

    # 6. Ставим задачу на экспорт в Celery — передаём export_id
    try:
        celery_app.send_task(
            "workers.export_by_id",
            kwargs={
                "export_id": str(export.id),
            },
            queue="default",
        )

        logger.info(
            "Export task queued",
            extra={
                "export_id": str(export.id),
                "run_id": str(run.id),
                "deal_id": str(run.deal_id),
                "export_type": export.export_type,
                "task_name": "workers.export_by_id",
            },
        )

    except Exception as e:
        msg = str(e)
        lower_msg = msg.lower()

        if any(
            token in lower_msg
            for token in (
                "connection refused",
                "connectionerror",
                "timeout",
                "broker",
                "rabbitmq",
                "redis",
            )
        ):
            reason = "queue_unavailable"
            http_detail = (
                "Не удалось запустить экспорт: очередь задач временно "
                "недоступна. Попробуйте ещё раз позже."
            )
        else:
            reason = "infrastructure_error"
            http_detail = (
                "Не удалось запустить экспорт: внутренняя ошибка инфраструктуры."
            )

        logger.error(
            "Failed to queue export task",
            extra={
                "export_id": str(export.id),
                "run_id": str(run.id),
                "deal_id": str(run.deal_id),
                "export_type": export.export_type,
                "reason": reason,
                "error": msg,
            },
        )

        await export_repo.update_status(
            export.id,
            status="failed",
            error_details={
                "stage": "export",
                "type": "infrastructure_error",
                "reason": reason,
                "message": msg,
            },
        )
        await db.commit()

        raise HTTPException(status_code=503, detail=http_detail)

    return RunExportResponse(
        id=export.id,
        run_id=run.id,
        deal_id=run.deal_id,
        export_type=export.export_type,
        status=export.status,
        file_ref=export.file_ref,
    )


@router.get(
    "/{run_id}/results",
    response_model=PaginatedResponseSchema[CheckResultResponse],
    summary="Пагинированный список результатов проверок для run (DD Grid)",
)
async def list_run_results(
    run_id: uuid.UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(200, ge=1, le=1000),
    doc_type: str | None = Query(
        default=None,
        description="Фильтр по типу документа (doc_type)",
    ),
    severity: str | None = Query(
        default=None,
        description="Фильтр по уровню риска (severity: critical/high/medium/pass/unclear)",
    ),
    conditional_only: bool | None = Query(
        default=None,
        description="Если true — только условные проверки",
    ),
    has_structured_data: bool | None = Query(
        default=None,
        description="Если true — только результаты с structured_data",
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Результаты проверок для одного run в формате PaginatedResponse[CheckResultResponse],
    пригодном для DD Grid.

    ВАЖНО:
    - Смотреть результаты могут только участники проекта (viewer/editor/admin)
      для той сделки, к которой относится этот run.
    - Пользователь, не входящий в проект, получит 403 Forbidden.
    """
    run_repo = RunRepository(db)
    run = await run_repo.get_by_id(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Проверяем, что пользователь — участник проекта (любой роли достаточно).
    await require_project_role(
        db=db,
        user=user,
        deal_id=run.deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    result_repo = ResultRepository(db)
    items_raw, total = await result_repo.get_page_for_run(
        run_id=run_id,
        page=page,
        per_page=per_page,
        doc_type=doc_type,
        severity=severity,
        conditional_only=conditional_only,
        has_structured_data=has_structured_data,
    )

    items = [CheckResultResponse.model_validate(r) for r in items_raw]

    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    has_next = page < total_pages
    has_previous = page > 1

    return PaginatedResponseSchema[CheckResultResponse](
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        has_next=has_next,
        has_previous=has_previous,
    )


@router.get(
    "/deal/{deal_id}",
    response_model=DealRunSummaryResponse,
)
async def get_deal_run_summary(
    deal_id: UUID,
    include_classification_stats: bool = False,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Краткое резюме последнего Run по сделке.

    Здесь уже используется фильтрация по user_id в репозитории,
    так что доступ ограничен участниками проекта.
    """
    deal_repo = DealRepository(db)
    deal = await deal_repo.get_by_id(deal_id, user_id=user.id)

    if not deal or not deal.last_run_id:
        raise HTTPException(status_code=404, detail="Run not found for this deal")

    run_repo = RunRepository(db)
    run = await run_repo.get_by_id(deal.last_run_id, user_id=user.id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found for this deal")

    # При необходимости подтягиваем статистику классификации
    classification_stats = None
    if include_classification_stats:
        classification_stats = await run_repo.get_classification_stats_for_run(run.id)

    # Человекочитаемое сообщение об ошибке уровня Run (если есть).
    error_user_message = None
    if getattr(run, "error_details", None):
        error_user_message = render_error_message(run.error_details)

    return DealRunSummaryResponse(
        deal_id=run.deal_id,
        run_id=run.id,
        status=run.status,
        profile=run.profile,
        checks_mode=getattr(run, "checks_mode", "global_and_doc_type"),
        pipeline_strategy=getattr(run, "pipeline_strategy", "REUSE_STRUCTURE"),
        total_checks=run.total_checks,
        completed_checks=run.completed_checks,
        started_at=run.started_at,
        completed_at=run.completed_at,
        error_details=run.error_details,
        error_user_message=error_user_message,
        classification_stats=classification_stats,
    )


