# src/api/mappers/documents.py

"""
Мапперы для преобразования ORM‑моделей документов в API‑схемы.

Задачи этого модуля:
- разорвать жёсткую связь между слоями хранения (SQLAlchemy‑модели) и REST API;
- нормализовать «сырой» объект Document из БД под стабильный контракт API
  (например, превращать None в [] для applicable_triggers);
- зафиксировать в одном месте бизнес‑логику формирования ответа по документу
  (human_readable статус проверки, прокидка ошибок и т.п.).

Где используется:
- в эндпоинтах deals.py при формировании:
  - списка документов сделки;
  - списка карантинных документов;
  перед отдачей их во внешнее API.

Ключевые особенности:
- _compute_human_review_status:
  - превращает технический статус документа (DocumentStatus + reviewed_by_person)
    в человекочитаемую строку для UI:
    * QUARANTINE → «Требует внимания юриста»;
    * COMPLETED → «Проверен юристом» или «Проверка юриста не требуется»;
    * DUPLICATE → «Дубликат (по необходимости)»;
    * прочие статусы пайплайна → «В обработке».
- map_document_to_response:
  - приводит ORM‑Document к DocumentResponse;
  - нормализует applicable_triggers: None → [];
  - прокидывает processing_error_details как есть, чтобы фронт мог
    показывать детали последней ошибки обработки;
  - прокидывает classification_requires_review, чтобы UI мог подсветить
    документы, требующие ручной проверки;
  - вычисляет human_review_status через _compute_human_review_status.

Таким образом, любые изменения формата ответа по документам для UI
должны сначала вноситься сюда, а не напрямую в ORM‑модели или в контроллеры.
"""

from collections.abc import Iterable

from api.schemas.documents import DocumentResponse
from core.constants import DocumentStatus
from db.models.document import Document


def _compute_human_review_status(doc: Document) -> str:
    """
    Человекочитаемый статус проверки документа юристом.
    """
    status = DocumentStatus(doc.status)

    if status == DocumentStatus.QUARANTINE:
        return "Требует внимания юриста"

    if status == DocumentStatus.LANGUAGE_SELECTION_REQUIRED:
        # Документ технически не в quarantine, но пайплайн остановлен до выбора языка.
        return "Нужно выбрать основной язык"

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
        # Флаг «нужна ручная проверка», выставленный HybridClassifier
        # (low-confidence или зона unknown).
        classification_requires_review=getattr(doc, "classification_requires_review", False),
        # Детали последней ошибки обработки пайплайна.
        processing_error_details=doc.processing_error_details,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def map_documents_to_response(
    docs: Iterable[Document],
) -> list[DocumentResponse]:
    return [map_document_to_response(d) for d in docs]
