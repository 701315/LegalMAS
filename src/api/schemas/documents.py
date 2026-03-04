"""
Pydantic-схемы для работы с документами в REST API.

Эти классы описывают форму JSON-ответов/запросов:
- краткая информация о документе;
- детальная информация с версией и классификацией;
- запрос и ответ для ручной переклассификации документа.
"""

from uuid import UUID
from datetime import datetime

from pydantic import BaseModel

from core.constants import DocumentStatus, RelationType


class ClassificationMetadata(BaseModel):
    """
    Метаданные классификации документа.

    Используется в детальной карточке документа, чтобы:
    - показать тип документа (doc_type),
    - уровень классификации (L0-L4, L_manual),
    - уверенность (0.0–1.0),
    - список триггеров (applicable_triggers),
    - флаги low_confidence и есть ли YAML-инструкция.
    """
    doc_type: str
    classification_level: str          # "L0", "L1", "L2", "L3", "L4", "L_manual"
    classification_confidence: float
    applicable_triggers: list[str]
    yaml_instruction_available: bool   # True, если есть playbooks/document_types/{doc_type}.yaml
    low_confidence: bool               # True, если confidence < 0.6


class DocumentResponse(BaseModel):
    """
    Краткая информация о документе.

    Используется в списках документов и простых ответах API.
    """
    id: UUID
    deal_id: UUID
    filename: str
    folder_path: str | None
    status: DocumentStatus
    doc_type: str | None
    language: str | None
    jurisdiction_guess: str | None
    page_count: int | None

    # Поля классификации (Stage 6+8)
    classification_level: str | None = None
    classification_confidence: float | None = None
    applicable_triggers: list[str] = []

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentVersionResponse(BaseModel):
    """
    Версия документа с ссылками на артефакты (MinIO, файлы).
    """
    id: UUID
    document_id: UUID
    version_num: int
    original_ref: str | None
    text_layout_raw_ref: str | None
    text_layout_sanitized_ref: str | None
    clause_tree_ref: str | None
    extraction_strategy: str | None
    ocr_confidence: float | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentDetailResponse(BaseModel):
    """
    Детальная карточка документа.

    Содержит:
    - базовую информацию (DocumentResponse),
    - последнюю версию (DocumentVersionResponse),
    - семью документов (family_id),
    - полный блок метаданных классификации (ClassificationMetadata).
    """
    document: DocumentResponse
    latest_version: DocumentVersionResponse | None
    family_id: UUID | None = None
    classification: ClassificationMetadata | None = None


class ReclassifyRequest(BaseModel):
    """
    Запрос на ручную переклассификацию документа.

    Используется в POST /documents/{doc_id}/reclassify.
    """
    doc_type: str
    reason: str                 # обязательное поле, будет записано в аудит-лог
    rerun_checks: bool = False  # если True — повторно запускаем проверки по документу


class ReclassifyResponse(BaseModel):
    """
    Ответ после ручной переклассификации документа.
    """
    document_id: UUID
    previous_doc_type: str | None
    new_doc_type: str
    new_applicable_triggers: list[str]
    yaml_instruction_found: bool
    checks_requeued: bool = False


class ReclassifyBatchRequest(BaseModel):
    """
    Запрос на переклассификацию сразу нескольких документов.
    (можно реализовать позже; схема оставлена на будущее).
    """
    document_ids: list[UUID]
    doc_type: str
    reason: str
    rerun_checks: bool = False


class RelationResponse(BaseModel):
    """
    Отношение между документами (например, "основной" и "приложение").
    """
    id: UUID
    source_doc_id: UUID
    target_doc_id: UUID
    relation_type: RelationType
    confidence: float
    evidence_text: str | None

    model_config = {"from_attributes": True}


class FamilyResponse(BaseModel):
    """
    Семья документов (master + связанные).
    """
    family_id: UUID
    master_document: DocumentResponse
    related_documents: list[DocumentResponse]
    relations: list[RelationResponse]
