# src/api/endpoints/runs.py

"""
Эндпоинты для запусков анализа (runs).

- POST /runs                       — запуск анализа по сделке
- GET  /runs/{run_id}             — статус run + (опционально) stats классификации
- GET  /runs/{run_id}/classification-report — подробный отчёт по классификации
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.runs import (
    RunCreate,
    RunResponse,
    ClassificationReportResponse,
)
from src.db.session import get_db
from src.db.repositories.run_repo import RunRepository
from src.db.repositories.document_repo import DocumentRepository
from src.core.config import settings
from src.services.run_analytics_service import RunAnalyticsService, RunNotFoundError
# from src.api.dependencies.deals import check_deal_access  # когда перейдёшь на реальную auth-модель

# Заглушка пользователя — аналогично documents.py
class CurrentUser:
    id: str = "system"
    role: str = "system"
    tenant_id: uuid.UUID = uuid.UUID(int=0)


def get_current_user() -> CurrentUser:
    return CurrentUser()


router = APIRouter(prefix="/runs", tags=["runs"])


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
    Запускает новый run для указанной сделки.

    Логика:
    - создаём запись run в БД;
    - если force_reclassify и API_ALLOW_FORCE_RECLASSIFY=True:
        ставим задачи classifier_worker.classify_document для всех документов
        (переклассификация перед проверками);
    - иначе — запускаем обычные проверки (run_checks) как в Stage 8.
    """
    run_repo = RunRepository(db)
    doc_repo = DocumentRepository(db)

    deal_uuid = uuid.UUID(deal_id)

    # Создаём запись run в БД
    run = await run_repo.create_run(
        deal_id=deal_uuid,
        playbook_version_id=data.playbook_version_id,
        profile=data.profile,
        created_by=str(user.id),
    )

    # Загружаем документы сделки
    docs = await doc_repo.get_by_deal(deal_uuid)

    # Ветка: сначала (пере)классифицировать все документы
    if data.force_reclassify and getattr(settings, "API_ALLOW_FORCE_RECLASSIFY", False):
        try:
            # Используем уже существующую Celery-таску классификатора
            from src.workers.classifier import classify_document

            for d in docs:
                classify_document.delay(
                    document_id=str(d.id),
                    deal_id=str(d.deal_id),
                    tenant_id=str(user.tenant_id),
                    run_id=str(run.id),
                )
        except Exception:
            # В проде стоит залогировать ошибку
            pass
    else:
        # Обычная постановка задач на проверки (Stage 8 Runner)
        try:
            from src.workers.runner import run_checks

            for d in docs:
                run_checks.delay(
                    document_id=str(d.id),
                    deal_id=str(d.deal_id),
                    tenant_id=str(user.tenant_id),
                    run_id=str(run.id),
                )
        except Exception:
            pass

    return RunResponse.model_validate(run)


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
    """
    run_repo = RunRepository(db)
    run = await run_repo.get_by_id(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

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
    try:
        report = await service.build_classification_report(run_id)
    except RunNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found")

    # TODO: when real auth is wired in, use deal_id from report for access check
    # await check_deal_access(report.deal_id, user, db)

    return report

