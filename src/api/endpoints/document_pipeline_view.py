# src/api/endpoints/document_pipeline_view.py

"""
API endpoint for document pipeline view.

Модуль предоставляет эндпоинт для получения агрегированного представления
стадий обработки документа в пайплайне:
SOURCE -> PRIMARY -> EXTRACT -> PII -> STRUCTURE -> CHUNKS.

Эндпоинт:
- GET /documents/{doc_id}/pipeline-view

Поведение:
- загружает документ по `doc_id`;
- проверяет, что пользователь имеет доступ к сделке документа
  с ролью viewer/editor/admin;
- вызывает `DocumentPipelineViewService` для сборки pipeline view;
- возвращает DTO с объединённой картиной по стадиям обработки.

Ошибки:
- 404, если документ не найден;
- 404, если pipeline-артефакт отсутствует;
- 503, если хранилище временно недоступно или представление
  временно не может быть построено.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from api.schemas.document_pipeline_view import (
    DocumentPipelineViewResponseDTO,
    StageViewMode,
)
from core.exceptions import PermanentError, TransientError
from db.repositories.document_repo import DocumentRepository
from db.session import get_db
from services.document_pipeline_view_service import DocumentPipelineViewService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/documents",
    tags=["documents"],
)


@router.get(
    "/{doc_id}/pipeline-view",
    response_model=DocumentPipelineViewResponseDTO,
    summary="Get pipeline view for document",
)
async def get_document_pipeline_view(
    doc_id: UUID,
    view_mode: StageViewMode = Query(
        StageViewMode.canonical,
        description=(
            "Режим представления стадий пайплайна:\n"
            "- canonical — показывается точный результат этапов;\n"
            "- friendly — показывается более удобный для чтения вид "
            "(может использовать данные соседних этапов)."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Вернуть агрегированное представление стадий обработки документа:
    SOURCE → PRIMARY → EXTRACT → PII → STRUCTURE → CHUNKS.

    Параметр `view_mode` управляет тем, как будут отображены отдельные стадии
    для UI. По умолчанию используется режим canonical.
    """
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    await require_project_role(
        db=db,
        user=user,
        deal_id=doc.deal_id,
        allowed_roles=("viewer", "editor", "admin"),
    )

    service = DocumentPipelineViewService(db)

    try:
        return await service.build(
            document_id=doc_id,
            view_mode=view_mode,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except PermanentError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline artifact not found",
        )
    except TransientError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Storage temporarily unavailable",
        )
    except Exception as e:
        logger.exception(
            "Failed to build document pipeline view",
            extra={
                "doc_id": str(doc_id),
                "deal_id": str(doc.deal_id),
                "user_id": str(user.id),
                "view_mode": view_mode.value,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pipeline view temporarily unavailable",
        )
    
