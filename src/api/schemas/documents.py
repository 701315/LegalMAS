# src/api/schemas/documents.py

from uuid import UUID
from datetime import datetime
from typing import List
from pydantic import BaseModel, Field

from core.constants import DocumentStatus, RelationType


class ClassificationMetadata(BaseModel):
    """
    Метаданные классификации документа.
    """
    doc_type: str
    classification_level: str          # "L0", "L1", "L2", "L3", "L4", "L_manual"
    classification_confidence: float
    applicable_triggers: list[str] = Field(default_factory=list)
    yaml_instruction_available: bool   # True, если есть playbooks/document_types/{doc_type}.yaml
    low_confidence: bool               # True, если confidence < 0.6


class DocumentResponse(BaseModel):
    """
    Краткая информация о документе.
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

    reviewed_by_person: bool = False
    human_review_status: str | None = None

    classification_level: str | None = None
    classification_confidence: float | None = None
    applicable_triggers: List[str] = Field(default_factory=list)

    # NEW: детали последней ошибки обработки
    processing_error_details: dict | None = None

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
    """
    document: DocumentResponse
    latest_version: DocumentVersionResponse | None
    family_id: UUID | None = None
    classification: ClassificationMetadata | None = None


class ReclassifyRequest(BaseModel):
    """
    Запрос на ручную переклассификацию документа.
    """
    doc_type: str
    reason: str
    rerun_checks: bool = False


class ReclassifyResponse(BaseModel):
    """
    Ответ после ручной переклассификации документа.
    """
    document_id: UUID
    previous_doc_type: str | None
    new_doc_type: str
    new_applicable_triggers: list[str] = Field(default_factory=list)
    yaml_instruction_found: bool
    checks_requeued: bool = False


class ReclassifyBatchRequest(BaseModel):
    """
    Запрос на переклассификацию сразу нескольких документов.
    """
    document_ids: list[UUID] = Field(default_factory=list)
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
    related_documents: list[DocumentResponse] = Field(default_factory=list)
    relations: list[RelationResponse] = Field(default_factory=list)


class DocumentReviewedUpdateRequest(BaseModel):
    """
    Запрос на обновление флага reviewed_by_person.
    """
    reviewed_by_person: bool
