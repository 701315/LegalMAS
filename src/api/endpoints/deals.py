# src/api/endpoints/deals.py
print("### LOADING DEALS ROUTER FROM", __file__)

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from .runs import _start_run_core, CurrentUser, get_current_user

from ..schemas.runs import RunCreate, RunResponse
from ..schemas.deals import DealResponse
from ..schemas.pagination import PaginatedResponse
from ..schemas.documents import DocumentResponse
from db.session import get_db
from db.repositories.deal_repo import DealRepository
from db.repositories.document_repo import DocumentRepository
from db.repositories.run_repo import RunRepository

router = APIRouter(
    prefix="/deals",
    tags=["deals"],
)

@router.get(
    "",
    response_model=PaginatedResponse[DealResponse],
    summary="Список сделок",
)
async def list_deals(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = Query(
        None,
        description="Фильтр по статусу сделки (created, draft, ...)",
    ),
    tenant_id: UUID | None = Query(
        None,
        description="Фильтр по tenant_id (UUID арендатора)",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Список сделок с пагинацией.

    Сейчас без фильтрации по tenant_id и статусу:
    возвращаются все сделки, отсортированные по created_at DESC.
    """
    repo = DealRepository(db)

    items, total = await repo.get_page(
        page=page,
        per_page=per_page,
        status=status,
        tenant_id=tenant_id,
    )
    
    # считаем метаданные пагинации
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    has_next = page < total_pages
    has_previous = page > 1

    # маппим ORM-модели Deal → DealResponse
    deal_items = [DealResponse.model_validate(deal) for deal in items]

    return PaginatedResponse[DealResponse](
        items=deal_items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        has_next=has_next,
        has_previous=has_previous,
    )

@router.get(
    "/{deal_id}",
    response_model=DealResponse,
    summary="Детали одной сделки",
)
async def get_deal(
    deal_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    repo = DealRepository(db)
    deal = await repo.get_by_id(deal_id)

    if deal is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Deal not found")

    return DealResponse.model_validate(deal)


@router.get(
    "/{deal_id}/documents",
    response_model=PaginatedResponse[DocumentResponse],
    summary="Список документов сделки",
)
async def list_deal_documents(
    deal_id: UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    include_classification: bool = Query(
        False,
        description="Включить сортировку/данные по классификации",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Список документов для сделки с пагинацией.
    """
    doc_repo = DocumentRepository(db)

    items, total = await doc_repo.get_page_for_deal(
        deal_id=deal_id,
        page=page,
        per_page=per_page,
        include_classification=include_classification,
    )

    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    has_next = page < total_pages
    has_previous = page > 1

    doc_items = [DocumentResponse.model_validate(doc) for doc in items]

    return PaginatedResponse[DocumentResponse](
        items=doc_items,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        has_next=has_next,
        has_previous=has_previous,
    )


@router.get(
    "/{deal_id}/quarantine",
    response_model=list[DocumentResponse],
    summary="Get quarantined documents for a deal",
)
async def get_quarantine_docs(
    deal_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Returns all documents in quarantine status for a deal.
    """
    doc_repo = DocumentRepository(db)
    docs = await doc_repo.get_quarantined(deal_id)
    return [DocumentResponse.model_validate(d) for d in docs]


@router.post(
    "/{deal_id}/run",
    response_model=RunResponse,
    summary="Запустить анализ по сделке",
)
async def start_deal_run(
    deal_id: UUID,
    payload: RunCreate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Старт нового run для сделки через общую логику запуска.

    URL удобен для фронта: POST /api/v1/deals/{deal_id}/run.
    Вся бизнес-логика (reclassify / run_checks, Celery и пр.) находится
    в _start_run_core из endpoints/runs.py.
    """
    return await _start_run_core(deal_id, payload, db, user)
