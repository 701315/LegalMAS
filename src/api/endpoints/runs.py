# src/api/endpoints/runs.py

"""
Эндпоинты для запусков анализа (runs).

Основные маршруты:
- POST /runs                               — запуск анализа по сделке
- GET  /runs/{run_id}                      — статус run + (опционально) stats классификации
- GET  /runs/{run_id}/classification-report — подробный отчёт по классификации
- GET  /runs/{run_id}/events               — SSE-стрим прогресса Run (status + completed/total)
"""

from __future__ import annotations  # сильно упрощает жизнь с аннотациями

import json
import uuid
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import get_scoped_run, get_scoped_deal, require_project_role
from api.schemas.runs import (
    ClassificationReportResponse,
    DealRunSummaryResponse,
    RunCreate,
    RunPipelineProgressResponse,
    RunResponse,
)
from api.schemas.instructions import EffectiveInstructionResponse

from db.models.run import Run
from db.models.deal import Deal
from db.repositories.run_repo import RunRepository

from api.schemas.pagination import PaginatedResponse as PaginatedResponseSchema
from api.schemas.results import CheckResultResponse
from core.config import settings
from core.constants import LanguageDiscoveryStatus, RunCheckPlanItemStatus, RunStatus
from core.error_catalog import render_error_message
from core.logging import get_logger
from db.repositories.audit_repo import AuditRepository
from db.repositories.deal_repo import DealRepository
from db.repositories.export_repo import ExportRepository
from db.repositories.playbook_repo import PlaybookRepository
from db.repositories.result_repo import ResultRepository
from db.session import get_db
from mas_queue.task_dispatcher import send_task_with_context
from services.effective_instruction_service import (
    EffectiveInstructionNotFoundError,
    EffectiveInstructionService,
)
from services.run_analytics_service import RunAnalyticsService, RunNotFoundError
from services.run_pipeline_progress_service import RunPipelineProgressService
from services.run_progress_service import subscribe_run_progress
from api.schemas.instruction_overrides import RunInstructionSnapshotResponse
from engine.checks.snapshot_policy import check_snapshot_integrity
from api.schemas.run_check_plan import RunCheckPlanItemResponse, RunCheckPlanResponse
from db.repositories.run_check_plan_item_repo import RunCheckPlanItemRepository

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

    # 1. Проверяем, что сделка существует в рамках tenant пользователя
    deal = await deal_repo.get_by_id(
        deal_uuid,
        tenant_id=user.tenant_id,
    )
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
                    str(getattr(user, "id", None)) if getattr(user, "id", None) else "unknown"
                ),
            },
        )
        raise HTTPException(
            status_code=400,
            detail=("Primary language must be selected before starting analysis"),
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
                    str(getattr(user, "id", None)) if getattr(user, "id", None) else "unknown"
                ),
                "language_discovery_status": getattr(deal, "language_discovery_status", None),
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
        same_model = last_run.model_config_id == model_config_id
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
        tenant_id=deal.tenant_id,
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
            "tenant_id": str(deal.tenant_id),
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

    # 6.1. Аудит: пользователь запросил запуск анализа.
    # Tenant берётся из deal — canonical source of truth ownership.
    try:
        await audit_repo.log(
            tenant_id=deal.tenant_id,
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
    except Exception as e:
        logger.warning(
            "Failed to write audit log for ANALYSIS_REQUESTED",
            extra={
                "run_id": str(run.id),
                "deal_id": str(deal_uuid),
                "error": str(e),
            },
        )

    # 7. Ставим Celery-задачу.
    # tenant_id берётся из run — он уже зафиксирован в БД из deal.tenant_id.
    try:
        logger.info(
            "Scheduling start_run_pipeline",
            extra={
                "run_id": str(run.id),
                "deal_id": str(deal_uuid),
                "tenant_id": str(run.tenant_id),
            },
        )

        send_task_with_context(
            "workers.start_run_pipeline",
            kwargs={
                "run_id": str(run.id),
                "deal_id": str(deal_uuid),
                "tenant_id": str(run.tenant_id),
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
                "Failed to start deal analysis: task queue is temporarily unavailable. "
                "Please try again later."
            )
        else:
            reason = "infrastructure_error"
            http_detail = "Failed to start deal analysis: internal infrastructure error."

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


@router.get("/deal/{deal_id}", response_model=list[RunResponse])
async def list_runs_for_deal(
    # СИСТЕМНЫЙ ФИКС: Проверка тенанта через scoped зависимость
    deal: Deal = Depends(get_scoped_deal),
    include_classification_stats: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    run_repo = RunRepository(db)
    runs = await run_repo.get_by_deal(deal.id)
    result = [RunResponse.model_validate(r) for r in runs]
    if include_classification_stats and runs:
        for i, run_obj in enumerate(runs):
            stats = await run_repo.get_classification_stats_for_run(run_obj.id)
            result[i].classification_stats = stats
    return result


# --- Раньше был ручной поиск, теперь одной строкой ---

@router.get("/{run_id}", response_model=RunResponse)
async def get_run(
    run: Run = Depends(get_scoped_run), # СИСТЕМНЫЙ ФИКС: Изоляция тенанта автоматом
    include_classification_stats: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    # Теперь нам не нужен if not run и manual require_project_role для базового просмотра
    run_out = RunResponse.model_validate(run)

    if include_classification_stats:
        stats = await RunRepository(db).get_classification_stats_for_run(run.id)
        run_out.classification_stats = stats

    if getattr(run, "error_details", None):
        run_out.error_user_message = render_error_message(run.error_details)

    return run_out

@router.get("/{run_id}/progress", response_model=RunPipelineProgressResponse)
async def get_run_pipeline_progress(
    run: Run = Depends(get_scoped_run), # СИСТЕМНЫЙ ФИКС
    db: AsyncSession = Depends(get_db),
):
    service = RunPipelineProgressService(db)
    return await service.build_progress(run)

@router.get("/{run_id}/events")
async def stream_run_events(
    request: Request,
    run: Run = Depends(get_scoped_run), # СИСТЕМНЫЙ ФИКС
    db: AsyncSession = Depends(get_db),
):
    # Логика SSE остается прежней, но проверка прав теперь в одной строке параметров
    async def event_generator():
        async for event in subscribe_run_progress(run.id):
            if await request.is_disconnected():
                break
            yield f"data: {json.dumps(event.model_dump(mode='json'), ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def get_run_analytics_service(
    db: AsyncSession = Depends(get_db),
) -> RunAnalyticsService:
    return RunAnalyticsService(db)

def get_effective_instruction_service(
    db: AsyncSession = Depends(get_db),
) -> EffectiveInstructionService:
    return EffectiveInstructionService(db)


@router.get(
    "/{run_id}/documents/{document_id}/effective-instruction",
    response_model=EffectiveInstructionResponse,
    summary="Единая инструкция (global + doc-type checks), применённая к документу в этом Run",
)
async def get_effective_instruction(
    document_id: uuid.UUID,
    run: Run = Depends(get_scoped_run),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    service: EffectiveInstructionService = Depends(get_effective_instruction_service),
):
    """
    Вернуть единую инструкцию, реально применённую к документу в данном Run.

    Доступ: любой участник проекта (admin/editor/viewer) — read-only.

    is_frozen_snapshot=True означает, что doc_type_checks взяты из
    зафиксированного в момент запуска Run snapshot (гарантированная
    воспроизводимость). False — fallback на текущий live YAML
    (для Run, созданных до введения snapshot-логики).
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=run.deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    try:
        result = await service.get_for_document(run_id=run.id, document_id=document_id)
    except EffectiveInstructionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return EffectiveInstructionResponse(**result)

@router.get(
    "/{run_id}/classification-report",
    response_model=ClassificationReportResponse,
    summary="Подробный отчёт о качестве классификации для run",
)
async def get_classification_report(
    # СИСТЕМНЫЙ ФИКС: Используем защищенную зависимость для автоматической изоляции тенанта
    run: Run = Depends(get_scoped_run), 
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
    service: RunAnalyticsService = Depends(get_run_analytics_service),
):
    # 1. Проверяем проектную роль (внутри require_project_role теперь есть проверка тенанта)
    await require_project_role(
        db=db,
        user=user,
        deal_id=run.deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    # 2. Вызываем сервис, используя ID из уже проверенного объекта 'run'
    try:
        return await service.build_classification_report(run.id)
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail="Classification report not found")


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
async def start_run_export(
    data: RunExportCreate,
    # СИСТЕМНЫЙ ФИКС: Автоматическая проверка тенанта и существования рана
    run: Run = Depends(get_scoped_run), 
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Запускает экспорт результатов анализа.
    Доступ: только admin/editor текущего тенанта.
    """
    export_repo = ExportRepository(db)

    # 1. Проверяем проектную роль (admin/editor) по deal_id из уже проверенного объекта run
    await require_project_role(
        db=db,
        user=user,
        deal_id=run.deal_id,
        allowed_roles=("admin", "editor"),
    )

    # 2. Проверяем статус run — допускаем только завершенные
    if run.status not in (RunStatus.COMPLETED.value, "completed_with_errors"):
        raise HTTPException(
            status_code=400,
            detail=f"Run status must be completed to export, got '{run.status}'",
        )

    # 3. Определяем данные для аудита и текущую локаль пользователя
    requested_by = getattr(user, "id", None)
    requester_role = getattr(user, "global_role", "user")
    user_locale = getattr(user, "ui_locale", "en") or "en"

    # 4. Создаём запись экспорта
    export = await export_repo.create(
        deal_id=run.deal_id,
        run_id=run.id,
        export_type=data.export_type,
        requested_by=requested_by,
        requester_role=requester_role,
        status="pending",
    )

    # Фиксируем в БД перед постановкой задачи
    await db.commit()
    await db.refresh(export)

    # 5. Ставим задачу в Celery с указанием ясного языка пользователя
    try:
        send_task_with_context(
            "workers.export_by_id",
            kwargs={
                "export_id": str(export.id),
                "presentation_locale": user_locale,
            },
            queue="default",
        )
        
        logger.info(
            "Export task queued",
            extra={
                "export_id": str(export.id),
                "run_id": str(run.id),
                "presentation_locale": user_locale,
            },
        )

    except Exception as e:
        # Если очередь упала - помечаем экспорт как failed
        await export_repo.update_status(
            export.id,
            status="failed",
            error_details={"stage": "export", "type": "infrastructure_error", "message": str(e)},
        )
        await db.commit()
        raise HTTPException(status_code=503, detail="Queue unavailable, try again later")

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
    "/deal/{deal_id}/summary",
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

    Источник истины:
    - Deal.last_run_id указывает на последний запущенный run для сделки.
    - Доступ проверяется через require_project_role, а не через repo-level user_id.

    Это endpoint для status/progress блока фронта.
    """
    deal_repo = DealRepository(db)
    deal = await deal_repo.get_by_id(
        deal_id,
        tenant_id=user.tenant_id,
    )

    if not deal or not deal.last_run_id:
        raise HTTPException(status_code=404, detail="Run not found for this deal")

    # Проверяем, что пользователь — участник проекта.
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal.id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    run_repo = RunRepository(db)
    run = await run_repo.get_by_id(deal.last_run_id)
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

    
@router.get(
    "/{run_id}/instruction-snapshot",
    response_model=RunInstructionSnapshotResponse,
    summary="Frozen instruction snapshot для исторического Run",
)
async def get_run_instruction_snapshot(
    run: Run = Depends(get_scoped_run),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> RunInstructionSnapshotResponse:
    """
    Вернуть frozen instruction snapshot для Run.

    Показывает:
    - exact instruction versions, зафиксированные на момент запуска;
    - snapshot manifest с hashes;
    - execution manifest;
    - is_reproducible — можно ли воспроизвести Run.

    Доступ: viewer/editor/admin проекта.
    is_reproducible=False для legacy runs (до введения strict snapshot).
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=run.deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    snapshot_schema_version = getattr(run, "snapshot_schema_version", None)
    instruction_versions = getattr(run, "instruction_versions", None) or {}
    instruction_snapshot_manifest = getattr(run, "instruction_snapshot_manifest", None)
    execution_manifest = getattr(run, "execution_manifest", None)

    is_valid, warning = check_snapshot_integrity(
        run_id=str(run.id),
        snapshot_schema_version=snapshot_schema_version,
        instruction_snapshot_payload=getattr(run, "instruction_snapshot_payload", None),
    )

    is_reproducible = (snapshot_schema_version is not None and is_valid)

    return RunInstructionSnapshotResponse(
        run_id=str(run.id),
        deal_id=str(run.deal_id),
        snapshot_schema_version=snapshot_schema_version,
        is_reproducible=is_reproducible,
        instruction_versions=instruction_versions,
        instruction_snapshot_manifest=instruction_snapshot_manifest,
        execution_manifest=execution_manifest,
        doc_types_count=len(instruction_versions),
        warning=warning,
    )

@router.get(
    "/{run_id}/check-plan",
    response_model=RunCheckPlanResponse,
    summary="Execution ledger проверок для Run (check-plan)",
)
async def get_run_check_plan(
    run: Run = Depends(get_scoped_run),
    status: RunCheckPlanItemStatus | None = Query(
        default=None,
        description=(
            "Фильтр по статусу execution ledger. Применяется только к items; "
            "summary всегда отражает overall состояние Run независимо от фильтра."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> RunCheckPlanResponse:
    """
    Вернуть execution ledger (source-of-truth прогресса) для Run.

    items фильтруются по status (если передан).
    summary — overall статистика по всему Run, независимо от фильтра.

    Невалидное значение status приводит к 422 Unprocessable Entity
    (валидация на уровне FastAPI/Pydantic до входа в repository).

    Доступ: viewer/editor/admin проекта, read-only.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=run.deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    repo = RunCheckPlanItemRepository(db)
    items = await repo.list_by_run_id(run.id, status=status)
    stats = await repo.get_run_progress_stats(run.id)

    return RunCheckPlanResponse(
        run_id=run.id,
        items=[RunCheckPlanItemResponse.model_validate(i) for i in items],
        summary=stats,
    )


@router.get(
    "/{run_id}/check-plan/{plan_item_id}",
    response_model=RunCheckPlanItemResponse,
    summary="Один элемент execution ledger по ID",
)
async def get_run_check_plan_item(
    plan_item_id: uuid.UUID,
    run: Run = Depends(get_scoped_run),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> RunCheckPlanItemResponse:
    """
    Вернуть один check-plan item, scoped по run_id (защита от cross-run leakage).

    Доступ: viewer/editor/admin проекта, read-only.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=run.deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    repo = RunCheckPlanItemRepository(db)
    item = await repo.get_by_id_scoped(plan_item_id, run.id)
    if not item:
        raise HTTPException(status_code=404, detail="Check plan item not found")

    return RunCheckPlanItemResponse.model_validate(item)


    