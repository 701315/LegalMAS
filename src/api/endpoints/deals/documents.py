# src/api/endpoints/deals/documents.py

import logging
import os
import tempfile
import zipfile
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from api.mappers.documents import map_document_to_response
from api.schemas.documents import DocumentResponse
from api.schemas.pagination import PaginatedResponse
from db.repositories.deal_repo import DealRepository
from db.repositories.document_repo import DocumentRepository
from db.session import get_db
from mas_queue.celery_app import celery_app
from services.document_composition_query import DocumentCompositionQueryService

logger = logging.getLogger(__name__)

router = APIRouter()


def _attach_composition_to_response(
    response: DocumentResponse,
    composition,
) -> DocumentResponse:
    """
    Вернуть новый DocumentResponse с подставленным composition.

    Для непрофессионального программиста:
    - map_document_to_response(...) уже умеет превращать ORM Document
      в стабильный API-ответ;
    - composition строится отдельно, потому что для него нужны
      DocumentVersion + DocumentSegment;
    - чтобы не ломать mapper, мы просто берём готовый response и
      копируем его с новым полем composition.

    Почему так правильно:
    - mapper остаётся простым и отвечает только за Document;
    - composition остаётся отдельным read-model слоем;
    - endpoint аккуратно склеивает оба источника данных в финальный API-ответ.
    """
    return response.model_copy(update={"composition": composition})


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
    user: CurrentUser = Depends(get_current_user),
):
    """
    Вернуть страницу документов по сделке.

    Что делает endpoint:
    - проверяет, что пользователь имеет доступ к сделке;
    - загружает страницу документов из таблицы documents;
    - отдельно строит composition по latest version + segment'ам;
    - возвращает единый ответ для UI.

    Для непрофессионального программиста:
    - composition не хранится прямо в Document;
    - composition — это вычисляемое summary-представление:
      один или несколько логических документов внутри файла,
      сколько их и какой сегмент является основным.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("viewer", "editor", "admin"),
    )

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

    # Строим composition только один раз на всю страницу документов.
    composition_service = DocumentCompositionQueryService(db)
    composition_by_doc_id = await composition_service.build_for_documents(items)

    doc_items: list[DocumentResponse] = []
    for doc in items:
        base_response = map_document_to_response(doc)
        enriched_response = _attach_composition_to_response(
            response=base_response,
            composition=composition_by_doc_id.get(doc.id),
        )
        doc_items.append(enriched_response)

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
    user: CurrentUser = Depends(get_current_user),
):
    """
    Вернуть документы сделки со статусом QUARANTINE.

    Здесь мы используем ту же схему, что и в основном списке:
    - сначала берём документы;
    - затем отдельно достраиваем composition;
    - потом отдаём DocumentResponse с composition.

    Это важно для консистентности:
    - одинаковый формат ответа в обычной таблице и в quarantine view;
    - фронт не должен по-разному обрабатывать DocumentResponse
      в зависимости от endpoint'а.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("viewer", "editor", "admin"),
    )

    doc_repo = DocumentRepository(db)
    docs = await doc_repo.get_quarantined(deal_id)

    composition_service = DocumentCompositionQueryService(db)
    composition_by_doc_id = await composition_service.build_for_documents(docs)

    responses: list[DocumentResponse] = []
    for doc in docs:
        base_response = map_document_to_response(doc)
        enriched_response = _attach_composition_to_response(
            response=base_response,
            composition=composition_by_doc_id.get(doc.id),
        )
        responses.append(enriched_response)

    return responses


@router.post(
    "/{deal_id}/documents/upload",
    summary="Загрузить новые документы в сделку (через импорт-пайплайн)",
    response_model=dict,
)
async def upload_deal_documents(
    deal_id: UUID,
    files: list[UploadFile] = File(
        ...,
        description="Один или несколько файлов документов",
    ),
    folder_path: str | None = Query(
        default=None,
        description=(
            "Опциональный путь в Data Room, например '01. Corporate/Charter Docs'. "
            "Сейчас это поле используется только для UX; "
            "структура внутри ZIP для import_worker задаётся автоматически."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Загрузить один или несколько документов в сделку и поставить импорт в очередь.

    Для непрофессионального программиста:
    - frontend отправляет файлы;
    - backend упаковывает их во временный ZIP;
    - затем ставит Celery-задачу import_bundle;
    - сама тяжёлая обработка файла идёт уже асинхронно в воркерах.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_id,
        allowed_roles=("admin", "editor"),
    )

    deal_repo = DealRepository(db)
    deal = await deal_repo.get_by_id(deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="Deal not found")

    tenant_id = str(deal.tenant_id)

    tmp_dir = tempfile.mkdtemp(prefix="mas_upload_")
    zip_path = os.path.join(tmp_dir, "upload_bundle.zip")

    try:
        with zipfile.ZipFile(
            zip_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as zf:
            for upload in files:
                file_bytes = await upload.read()
                arcname = upload.filename or "document"
                tmp_file_path = os.path.join(tmp_dir, arcname)
                with open(tmp_file_path, "wb") as f:
                    f.write(file_bytes)
                zf.write(tmp_file_path, arcname=arcname)

        celery_app.send_task(
            "workers.import_bundle",
            kwargs={
                "deal_id": str(deal_id),
                "tenant_id": tenant_id,
                "source_path": zip_path,
                "idempotency_key": None,
                "run_id": None,
            },
        )

    except Exception as e:
        try:
            for root, dirs, fnames in os.walk(tmp_dir, topdown=False):
                for name in fnames:
                    try:
                        os.remove(os.path.join(root, name))
                    except Exception:
                        pass
                for name in dirs:
                    try:
                        os.rmdir(os.path.join(root, name))
                    except Exception:
                        pass
            os.rmdir(tmp_dir)
        except Exception:
            pass

        logger.error(
            "Failed to enqueue import_bundle from upload",
            extra={
                "deal_id": str(deal_id),
                "tenant_id": tenant_id,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to enqueue import job",
        )

    return {
        "status": "queued",
        "files_uploaded": len(files),
    }
