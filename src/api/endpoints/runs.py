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

from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

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

from mas_queue.celery_app import celery_app

from core.config import settings
from services.run_analytics_service import RunAnalyticsService, RunNotFoundError

from ..schemas.runs import (
    RunCreate,
    RunResponse,
    ClassificationReportResponse,
)
from ..schemas.results import CheckResultResponse
from ..schemas.pagination import PaginatedResponse as PaginatedResponseSchema

router = APIRouter(prefix="/runs", tags=["runs"])


async def _start_run_core(
    deal_uuid: uuid.UUID,
    data: RunCreate,
    db: AsyncSession,
    user: CurrentUser,
) -> RunResponse:
    """
    Общая логика запуска run для сделки.

    1) проверяем существование сделки;
    2) находим playbook для этой сделки (или default);
    3) берём из него model_config_id;
    4) создаём Run с обоими ID;
    5) ставим Celery-задачи classifier/run_checks.
    """
    run_repo = RunRepository(db)
    doc_repo = DocumentRepository(db)
    deal_repo = DealRepository(db)
    playbook_repo = PlaybookRepository(db)

    # 1. Проверяем, что сделка существует
    deal = await deal_repo.get_by_id(deal_uuid)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

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

    # 4. Создаём run с обоими ID
    run = await run_repo.create(
        deal_id=deal_uuid,
        playbook_version_id=playbook_version_id,
        model_config_id=model_config_id,
        bundle_id=None,
        profile=data.profile,
    )

    # обновляем last_run_id у сделки
    await deal_repo.set_last_run_id(deal_id=deal_uuid, run_id=run.id)

    # 5. Загружаем документы сделки
    docs = await doc_repo.get_by_deal(deal_uuid)

    # Ветка: сначала (пере)классифицировать все документы
    if data.force_reclassify and getattr(settings, "API_ALLOW_FORCE_RECLASSIFY", False):
        for d in docs:
            celery_app.send_task(
                "workers.classify_document",  # имя таски из декоратора
                kwargs={
                    "document_id": str(d.id),
                    "deal_id": str(d.deal_id),
                    "tenant_id": str(user.tenant_id),
                    "run_id": str(run.id),
                },
            )
    else:
        for d in docs:
            celery_app.send_task(
                "workers.run_checks",
                kwargs={
                    "document_id": str(d.id),
                    "deal_id": str(d.deal_id),
                    "tenant_id": str(user.tenant_id),
                    "run_id": str(run.id),
                },
            )
  
    
    # фиксируем изменения и обновляем объект run
    await db.commit()
    await db.refresh(run)

    return RunResponse.model_validate(run)


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

    return run_out


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
    export_type: str = "run_full"
    requested_by: str | None = None
    requester_role: str | None = None


class RunExportResponse(BaseModel):
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
    - Если статус run не "completed" — экспорт запрещён (400).
    """
    run_repo = RunRepository(db)
    export_repo = ExportRepository(db)

    # 1. Находим run
    run = await run_repo.get_by_id(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # 2. Проверяем, что пользователь имеет право на экспорт в этой сделке.
    await require_project_role(
        db=db,
        user=user,
        deal_id=run.deal_id,
        allowed_roles=("admin", "editor"),
    )

    # 3. Проверяем статус run
    if run.status not in ("completed",):
        raise HTTPException(
            status_code=400,
            detail=f"Run status must be 'completed' to export, got '{run.status}'",
        )

    # 4. Создаём запись экспорта
    export = await export_repo.create(
        deal_id=run.deal_id,
        run_id=run.id,
        export_type=data.export_type,
        requested_by=data.requested_by or user.id,
        requester_role=data.requester_role or user.global_role,
        status="pending",
    )

    # 5. Ставим задачу на экспорт в Celery
    celery_app.send_task(
        "workers.export_results",
        kwargs={
            "run_id": str(run.id),
            "deal_id": str(run.deal_id),
            "tenant_id": str(user.tenant_id),
        },
    )

    await db.commit()
    await db.refresh(export)

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
    items_orm, total = await result_repo.get_page_for_run(
        run_id=run_id,
        page=page,
        per_page=per_page,
        doc_type=doc_type,
        severity=severity,
        conditional_only=conditional_only,
        has_structured_data=has_structured_data,
    )

    items = [CheckResultResponse.model_validate(r) for r in items_orm]

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
    Краткое резюме последнего run по сделке.

    Здесь уже используется фильтрация по user_id в репозитории,
    так что доступ ограничен участниками проекта.
    """
    deal_repo = DealRepository(db)
    deal = await deal_repo.get_by_id(deal_id, user_id=user.id)

    if not deal or not deal.last_run_id:
        raise HTTPException(status_code=404, detail="Run not found for this deal")

    run_repo = RunRepository(db)
    run = await run_repo.get_by_id(deal.last_run_id, user_id=user.id)

    # здесь run уже должен мапиться в RunResponse через from_attributes
    run_response = RunResponse.model_validate(run)

    if not include_classification_stats:
        run_response.classification_stats = None

    return DealRunSummaryResponse(run=run_response)
