# src/api/endpoints/run_summary.py

"""
Endpoints для executive summary run с поддержкой мультиязычности.

GET  /api/v1/runs/{run_id}/summary            — статус + текст + fallback (с параметром ?locale=)
POST /api/v1/runs/{run_id}/summary/translate  — принудительный запуск/повтор перевода
POST /api/v1/runs/{run_id}/summary/regenerate — принудительная перегенерация резюме

Tenant-изоляция — через get_scoped_run (тот же контракт, что в runs.py).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import get_scoped_run
from db.models.run import Run
from db.session import get_session, transactional_session
from db.repositories.run_summary_repo import RunSummaryRepository
from services.run_summary_service import RunSummaryService

router = APIRouter(prefix="/runs", tags=["run_summary"])


class RunSummaryResponse(BaseModel):
    run_id: str
    status: str  # pending | generating | ready | failed
    text: Optional[str] = None
    claims: Optional[dict[str, Any]] = None
    fallback: Optional[dict[str, Any]] = None
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    error_message: Optional[str] = None
    generated_at: Optional[str] = None
    # i18n metadata
    locale: Optional[str] = None
    supported_locales: Optional[list[str]] = None
    translation_status: Optional[str] = None  # None | pending | ready | failed


@router.get("/{run_id}/summary", response_model=RunSummaryResponse)
async def get_run_summary(
    locale: Optional[str] = Query(
        default=None,
        description="Target locale for translation (e.g. 'en', 'ru')",
    ),
    run: Run = Depends(get_scoped_run),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Вернуть summary для run.

    Если указан locale (например en) и перевод ещё не готов — автоматически
    триггерит фоновый перевод и возвращает translation_status='pending'.
    """
    # === СИСТЕМНЫЙ ФИКС: Мягкий статус ожидания для активных запусков ===
    # Если запуск еще выполняется (статус не completed и не completed_with_errors),
    # возвращаем статус "pending" вместо жесткой ошибки 404, разблокируя UX фронтенда.
    if run.status not in ("completed", "completed_with_errors"):
        return RunSummaryResponse(
            run_id=str(run.id),
            status="pending",
            text="Анализ документов еще выполняется. Резюме будет сгенерировано после завершения.",
            locale=(run.analysis_language or "ru").lower(),
            supported_locales=["ru", "en"],
        )
    # ===================================================================

    async with get_session() as session:
        service = RunSummaryService(session)
        await service.ensure_record(run.id)
        
        # 1. Получаем текущее состояние (RU-оригинал или кэшированный перевод)
        response = await service.get_response(run.id, locale=locale)

    if response is None:
        raise HTTPException(status_code=404, detail="Summary not available")

    # 2. Auto-trigger перевода, если запрошен другой язык и статус None (перевод ещё не запрашивался)
    target_locale = (locale or "").strip().lower()
    analysis_lang = (run.analysis_language or "ru").strip().lower()

    if (
        target_locale
        and target_locale != analysis_lang
        and response.get("status") == "ready"
        and response.get("translation_status") is None
    ):
        # Используем транзакционную сессию для мутирующей операции постановки в очередь
        async with transactional_session() as session:
            service = RunSummaryService(session)
            try:
                await service.request_translation(run.id, target_locale)
            except Exception:
                # В случае любых инфраструктурных сбоев очереди — не роняем GET эндпоинт,
                # отдаем оригинальный язык
                pass

        # Перечитываем актуальный статус после постановки задачи
        async with get_session() as session:
            service = RunSummaryService(session)
            response = await service.get_response(run.id, locale=target_locale)

    return response


@router.post("/{run_id}/summary/translate", response_model=RunSummaryResponse)
async def trigger_summary_translation(
    locale: str = Query(..., description="Target locale code to translate to"),
    run: Run = Depends(get_scoped_run),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Явный запуск перевода на целевую локаль (например, при нажатии Retry Translation).
    """
    if run.status not in ("completed", "completed_with_errors"):
        raise HTTPException(status_code=400, detail="Run is not completed yet")

    async with transactional_session() as session:
        service = RunSummaryService(session)
        summary = await service.ensure_record(run.id)
        if not summary or summary.status != "ready":
            raise HTTPException(
                status_code=400, detail="Master summary must be ready before translating"
            )

        try:
            await service.request_translation(run.id, locale)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    async with get_session() as session:
        service = RunSummaryService(session)
        response = await service.get_response(run.id, locale=locale)

    if response is None:
        raise HTTPException(status_code=404, detail="Summary not available")

    return response


@router.post("/{run_id}/summary/regenerate", response_model=RunSummaryResponse)
async def regenerate_run_summary(
    run: Run = Depends(get_scoped_run),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Принудительная перегенерация: переводит ready/failed в pending,
    сбрасывает все переводы и спавнит генерацию в фоне.
    """
    async with transactional_session() as session:
        repo = RunSummaryRepository(session)
        summary = await repo.get_by_run_id(run.id)
        if summary is None:
            raise HTTPException(status_code=404, detail="Summary not found")

        if summary.status != "generating":
            await repo.update_status(
                run.id,
                "pending",
                translations=None,
                translation_status=None,
            )

    # Фоновая генерация в API-процессе (claim защитит от дублей).
    async def _gen() -> None:
        async with transactional_session() as session:
            await RunSummaryService(session).generate(run.id)

    asyncio.create_task(_gen(), name=f"summary_regen_{run.id}")

    async with get_session() as session:
        response = await RunSummaryService(session).get_response(run.id)

    return response


    