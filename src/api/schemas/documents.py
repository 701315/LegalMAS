# src/api/schemas/documents.py

"""
Pydantic‑схемы для документов и связанных сущностей (версии, семьи, связи).

Зачем нужен этот модуль и где он используется:
- формат ответов API для списка документов сделки и карточки документа:
  - DocumentResponse — строка в таблице документов по сделке;
  - DocumentDetailResponse — полная карточка документа (метаданные, артефакты, классификация);
- формат запросов/ответов для ручной переклассификации:
  - ReclassifyRequest / ReclassifyResponse / ReclassifyBatchRequest;
- формат ответов для связей между документами и семей документов:
  - RelationResponse / FamilyResponse;
- формат запроса на пометку документа как просмотренного юристом:
  - DocumentReviewedUpdateRequest.

Важно про статусы и ошибки:
- status: DocumentStatus — статус обработки документа в пайплайне:
  PENDING, EXTRACTING, EXTRACTED, SANITIZED, STRUCTURED, CLASSIFIED,
  ANALYZING, COMPLETED, QUARANTINE, FAILED, DUPLICATE и т.п.;
- processing_error_details: dict | None — единое поле для описания ошибки
  по конкретному документу (если статус FAILED или QUARANTINE).

Формат processing_error_details:
    {
        "stage": "import" | "extract" | "pii" | "structure" | "classify" | "checks" | "export",
        "type": "failed" | "quarantine",
        "reason": "<короткий машинный код причины>" (опционально),
        "message": "<человекочитаемое описание ошибки>",
        "timestamp": "<ISO8601 UTC>",
        "run_id": "<UUID Run, если есть>" (опционально)
    }

Фронт использует эти поля, чтобы:
- показывать юристу, на какой стадии остановился документ;
- выводить понятное текстовое объяснение, что пошло не так;
- подсвечивать документы в QUARANTINE, требующие ручной проверки.

Основные схемы:
- ClassificationMetadata — метаданные классификации для карточки документа
  (doc_type, уровень L0–L4/L_manual, confidence, applicable_triggers, low_confidence,
  наличие YAML‑инструкции);
- DocumentResponse — краткая карточка документа для таблиц, семейств, связей
  (status, doc_type, флаги reviewed_by_person / human_review_status,
  classification_* поля, processing_error_details);
- DocumentVersionResponse — техническая версия документа с ссылками на артефакты
  (original_ref, text_layout_raw_ref/sanitized_ref, clause_tree_ref, pipeline_strategy и т.п.);
- DocumentDetailResponse — объединяет DocumentResponse, последнюю версию,
  метаданные классификации и family_id для полной карточки;
- RelationResponse / FamilyResponse — представление связей и «семей» документов
  (master + связанные + relation_type/confidence/evidence_text);
- ReclassifyRequest / ReclassifyResponse / ReclassifyBatchRequest — контракты
  для ручной переклассификации (смена doc_type, причина, опциональный rerun checks);
- DocumentReviewedUpdateRequest — контракт для отметки документа как
  «просмотренного юристом».
"""

from uuid import UUID
from datetime import datetime
from typing import List

from pydantic import BaseModel, Field

from core.constants import DocumentStatus, RelationType


class ClassificationMetadata(BaseModel):
    """
    Метаданные классификации документа.

    Используется в карточке документа, чтобы показать:
    - к какому типу договора он отнесён;
    - на каком уровне (L0-L4, L_manual) с какой уверенностью;
    - какие триггеры/разделы риска к нему применимы;
    - есть ли YAML‑инструкция для этого типа документа;
    - низкая ли уверенность (low_confidence).
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

    Используется в:
    - списке документов по сделке (таблица в UI);
    - списках внутри семей, связей и т.п.

    Основные поля для фронта:

    - status — текущий статус пайплайна по документу
      (PENDING / EXTRACTED / SANITIZED / STRUCTURED / CLASSIFIED /
       COMPLETED / QUARANTINE / FAILED / DUPLICATE и др.);
    - processing_error_details — детали последней ошибки обработки, если есть;
    - classification_* поля — результат классификации (если она выполнялась);
    - reviewed_by_person / human_review_status — флаги ручной проверки юристом.
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

    # Детали последней ошибки обработки (если статус FAILED/QUARANTINE и т.п.).
    # Структура описана в модуле repositories/document_repo.py.
    processing_error_details: dict | None = None

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentVersionResponse(BaseModel):
    """
    Версия документа с ссылками на артефакты (MinIO, файлы).

    Используется в карточке документа, чтобы:
    - показать, где лежит исходник и результаты пайплайна;
    - диагностировать проблемы (например, отсутствует text_layout_raw_ref).
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
    origin_filetype: str | None = None
    origin_extension: str | None = None
    pipeline_strategy: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentDetailResponse(BaseModel):
    """
    Детальная карточка документа.

    Объединяет:
    - базовую информацию о документе (DocumentResponse);
    - последнюю версию и её артефакты (DocumentVersionResponse);
    - метаданные классификации (ClassificationMetadata);
    - family_id — идентификатор семьи документов (если реализовано).
    """
    document: DocumentResponse
    latest_version: DocumentVersionResponse | None
    family_id: UUID | None = None
    classification: ClassificationMetadata | None = None


class ReclassifyRequest(BaseModel):
    """
    Запрос на ручную переклассификацию документа.

    Используется, когда:
    - юрист считает, что тип документа определён неверно;
    - нужно задать новый doc_type и (опционально) пересчитать checks.

    Поля:
    - doc_type — новый тип документа (из справочника);
    - reason — текстовое объяснение, почему меняем тип;
    - rerun_checks — если True, система поставит задачи на повторный run_checks.
    """
    doc_type: str
    reason: str
    rerun_checks: bool = False


class ReclassifyResponse(BaseModel):
    """
    Ответ после ручной переклассификации документа.

    Используется UI для:
    - подтверждения нового типа документа;
    - показания, были ли перезапущены проверки.
    """
    document_id: UUID
    previous_doc_type: str | None
    new_doc_type: str
    new_applicable_triggers: list[UUID] | list[str] = Field(default_factory=list)
    yaml_instruction_found: bool
    checks_requeued: bool = False


class ReclassifyBatchRequest(BaseModel):
    """
    Запрос на переклассификацию сразу нескольких документов.

    Удобно для сценария:
    - выделить несколько документов в таблице;
    - задать новый тип и причину;
    - по желанию перезапустить checks для всех этих документов.
    """
    document_ids: list[UUID] = Field(default_factory=list)
    doc_type: str
    reason: str
    rerun_checks: bool = False


class RelationResponse(BaseModel):
    """
    Отношение между документами (например, "основной" и "приложение").

    Используется в UI для:
    - отображения связей между договором и приложениями;
    - показа уверенности и краткого текста‑доказательства.
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

    Пример:
    - master_document — основной договор;
    - related_documents — приложения, допсоглашения и т.п.;
    - relations — детальное описание связей.

    Используется в UI для показа связанной группы документов в одном блоке.
    """
    family_id: UUID
    master_document: DocumentResponse
    related_documents: list[DocumentResponse] = Field(default_factory=list)
    relations: list[RelationResponse] = Field(default_factory=list)


class DocumentReviewedUpdateRequest(BaseModel):
    """
    Запрос на обновление флага reviewed_by_person.

    Для чего это нужно:

    - юрист может отметить документ как «просмотренный»;
    - фронт может подсвечивать, какие документы уже были проверены вручную;
    - система может строить отчёты по прогрессу ручной валидации.

    Обычно этот запрос отправляется при клике «Отметить как проверенный»
    в карточке документа или в таблице.
    """
    reviewed_by_person: bool
