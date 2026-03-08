# src/api/endpoints/deal_review.py

import uuid

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role

from services.deal_review_service import (
    load_aggregated_results,
    build_document_summaries,
    build_document_detail,
    build_dd_requests,
    build_conditional_checks,
    build_extracted_values,
)

from db.session import get_db
from db.repositories.run_repo import RunRepository
from ..schemas.deal_review import (
    DocumentSummaryDTO,
    DocumentDetailDTO,
    DDRequestDTO,
    ConditionalCheckDTO,
    ExtractedValueDTO,
    DocumentStructuredDataDTO,
)

router = APIRouter(prefix="/deals", tags=["deal_review"])


@router.get(
    "/{deal_id}/runs/{run_id}/documents",
    response_model=list[DocumentSummaryDTO],
    summary="Список документов и рисков для run",
)
async def get_documents_for_run(
    deal_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Список документов и рисков по конкретному run.

    ВАЖНО:
    - Доступ разрешён только участникам проекта (viewer/editor/admin)
      для этой сделки.
    """
    # Проверяем, что пользователь имеет доступ к этой сделке
    await require_project_role(
        db=db,
        user=user,
        deal_id=uuid.UUID(deal_id),
        allowed_roles=("admin", "editor", "viewer"),
    )

    agg, documents = await load_aggregated_results(deal_id, run_id)
    return build_document_summaries(agg, documents)


@router.get(
    "/{deal_id}/runs/{run_id}/documents/{document_id}",
    response_model=DocumentDetailDTO,
    summary="Детальная карточка документа для run",
)
async def get_document_detail_for_run(
    deal_id: str,
    run_id: str,
    document_id: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Детальная карточка одного документа в контексте run.

    Доступ — только участникам проекта (viewer/editor/admin).
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=uuid.UUID(deal_id),
        allowed_roles=("admin", "editor", "viewer"),
    )

    agg, documents = await load_aggregated_results(deal_id, run_id)
    if document_id not in documents:
        raise HTTPException(status_code=404, detail="Document not found")
    return build_document_detail(agg, documents, document_id)


@router.get(
    "/{deal_id}/runs/{run_id}/documents/{document_id}/structured-data",
    response_model=DocumentStructuredDataDTO,
    summary="Структурированные значения по документу в рамках run",
)
async def get_document_structured_data_for_run(
    deal_id: str,
    run_id: str,
    document_id: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Структурированные значения по документу для указанного run.

    Доступ — только участникам проекта (viewer/editor/admin) сделки.
    """
    # 1. Проверяем и загружаем run
    run_repo = RunRepository(db)
    run = await run_repo.get_by_id(uuid.UUID(run_id))
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Дополнительная проверка: run действительно относится к переданной сделке
    if str(run.deal_id) != deal_id:
        raise HTTPException(status_code=400, detail="Run does not belong to this deal")

    # Проверяем роль пользователя по deal_id run'а
    await require_project_role(
        db=db,
        user=user,
        deal_id=run.deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )

    # 2. Загружаем AggregatedResults и метаданные документов
    agg, documents = await load_aggregated_results(deal_id, run_id)

    # 3. Проверяем, что документ есть в этом run
    doc_meta = documents.get(document_id)
    if not doc_meta:
        raise HTTPException(status_code=404, detail="Document not found in this run")

    document_name = doc_meta["name"]
    doc_type = doc_meta["doc_type"]

    # 4. Строим все извлечённые значения по run и фильтруем по документу
    all_values: list[ExtractedValueDTO] = build_extracted_values(agg)
    doc_values = [v for v in all_values if v.document_name == document_name]

    # 5. Собираем DTO с шапкой + значениями
    return DocumentStructuredDataDTO(
        deal_id=str(run.deal_id),
        run_id=str(run.id),
        document_id=document_id,
        document_name=document_name,
        doc_type=doc_type,
        playbook_version_id=str(getattr(run, "playbook_version_id", "")) or None,
        playbook_name=None,  # можно заполнять позже, когда появится таблица плейбуков
        profile=getattr(run, "profile", None),
        total_values=len(doc_values),
        values=doc_values,
    )


@router.get(
    "/{deal_id}/runs/{run_id}/dd-requests",
    response_model=list[DDRequestDTO],
    summary="DD-запросы по результатам run",
)
async def get_dd_requests(
    deal_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    DD-запросы по результатам run.

    Доступ — только участникам проекта (viewer/editor/admin).
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=uuid.UUID(deal_id),
        allowed_roles=("admin", "editor", "viewer"),
    )

    agg, _ = await load_aggregated_results(deal_id, run_id)
    return build_dd_requests(agg)


@router.get(
    "/{deal_id}/runs/{run_id}/conditional-checks",
    response_model=list[ConditionalCheckDTO],
    summary="Список сработавших условных проверок",
)
async def get_conditional_checks(
    deal_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Список сработавших условных проверок для run.

    Доступ — только участникам проекта (viewer/editor/admin).
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=uuid.UUID(deal_id),
        allowed_roles=("admin", "editor", "viewer"),
    )

    agg, _ = await load_aggregated_results(deal_id, run_id)
    return build_conditional_checks(agg)


@router.get(
    "/{deal_id}/runs/{run_id}/extracted-values",
    response_model=list[ExtractedValueDTO],
    summary="Список извлечённых значений (structured values)",
)
async def get_extracted_values(
    deal_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Список извлечённых значений (structured values) по run.

    Доступ — только участникам проекта (viewer/editor/admin).
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=uuid.UUID(deal_id),
        allowed_roles=("admin", "editor", "viewer"),
    )

    agg, _ = await load_aggregated_results(deal_id, run_id)
    return build_extracted_values(agg)
