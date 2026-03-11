# src/api/mappers/documents.py

"""
Мапперы для преобразования ORM-моделей документов в API-схемы.

Задачи этого модуля:
- разорвать жёсткую связь между слоями хранения (SQLAlchemy-модели) и REST API;
- нормализовать «сырой» объект Document из БД под стабильный контракт API
  (например, превращать None в [] для applicable_triggers);
- зафиксировать в одном месте бизнес-логику формирования ответа по документу.

Где используется:
- в эндпоинтах deals.py при формировании списка документов сделки
  и карантинных документов, перед отдачей их во внешнее API.
"""

from db.models.document import Document
from api.schemas.documents import DocumentResponse
from core.constants import DocumentStatus
from typing import Iterable, List


def _compute_human_review_status(doc: Document) -> str:
    """
    Человекочитаемый статус проверки документа юристом.
    """
    status = DocumentStatus(doc.status)

    if status == DocumentStatus.QUARANTINE:
        return "Требует внимания юриста"

    if status == DocumentStatus.COMPLETED:
        if doc.reviewed_by_person:
            return "Проверен юристом"
        return "Проверка юриста не требуется"

    if status == DocumentStatus.DUPLICATE:
        return "Дубликат (по необходимости)"

    # PENDING / EXTRACTING / EXTRACTED / SANITIZED / STRUCTURED / CLASSIFIED / ANALYZING
    return "В обработке"


def map_document_to_response(doc: Document) -> DocumentResponse:
    return DocumentResponse(
        id=doc.id,
        deal_id=doc.deal_id,
        filename=doc.filename,
        folder_path=doc.folder_path,
        status=doc.status,
        doc_type=doc.doc_type,
        language=doc.language,
        jurisdiction_guess=doc.jurisdiction_guess,
        page_count=doc.page_count,
        reviewed_by_person=doc.reviewed_by_person,
        human_review_status=_compute_human_review_status(doc),
        classification_level=doc.classification_level,
        classification_confidence=doc.classification_confidence,
        applicable_triggers=doc.applicable_triggers or [],  # ключевая нормализация
        processing_error_details=doc.processing_error_details,  # NEW
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def map_documents_to_response(
    docs: Iterable[Document],
) -> List[DocumentResponse]:
    return [map_document_to_response(d) for d in docs]
