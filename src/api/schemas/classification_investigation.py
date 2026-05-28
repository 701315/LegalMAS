# src/api/schemas/classification_investigation.py

"""
Pydantic-схемы для explainability / investigation API классификации документов.

Зачем нужен этот модуль:
- отделяет forensic/read-model API классификации от обычных document DTO;
- даёт стабильный контракт для Audit → Classification Investigation;
- позволяет UI получать:
  - deal-level summary и paginated list документов;
  - document-level explainability detail;
  - normalized classification reasoning + raw persisted payload.

Что важно:
- эти схемы НЕ заменяют DocumentResponse и НЕ расширяют его;
- это отдельный bounded read model только для investigation UX;
- часть explainability payload хранится в evolving JSON, поэтому некоторые поля
  intentionally оставлены гибкими (dict / list[dict] / Any).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from api.schemas.documents import DocumentCompositionSummary


class ClassificationInvestigationSummary(BaseModel):
    """
    Агрегированная сводка по классификации документов в сделке.

    Используется в верхних counters investigation-экрана.
    """

    total_documents: int
    classified_count: int
    manual_review_count: int
    unknown_count: int
    l4_count: int
    contradiction_count: int


class ClassificationCandidateResponse(BaseModel):
    """
    Один кандидат типа документа из explainability payload.

    Для непрофессионального программиста:
    - это возможный вариант типа документа, который рассматривался системой;
    - level показывает, на каком уровне каскада этот кандидат появился;
    - extra содержит дополнительные сигналы, которые могут меняться со временем.
    """

    doctype: str
    confidence: float
    level: str
    method: str | None = None
    evidence: str | None = None
    language: str | None = None
    jurisdiction: str | None = None
    extra: dict[str, Any] | None = None


class ClassificationLevelResultResponse(BaseModel):
    """
    Нормализованный результат одного уровня классификации.

    Примеры уровней:
    - L1
    - L2
    - L3
    - L4
    - MASTERCOPY
    """

    level: str
    type: str | None = None
    confidence: float | None = None
    method: str | None = None
    evidence: str | None = None
    extra: dict[str, Any] | None = None


class ClassificationVotingResponse(BaseModel):
    """
    Нормализованный блок explainability по voting / override / ranking.

    Важно:
    - strategy и reason нужны для краткого объяснения финального решения;
    - ranking intentionally остаётся гибким, потому что структура может
      эволюционировать вместе с voting logic;
    - override хранит информацию о special-case переопределении результата.
    """

    strategy: str | None = None
    reason: str | None = None
    type: str | None = None
    confidence: float | None = None
    margin: float | None = None
    ranking: list[dict[str, Any]] = Field(default_factory=list)
    override: dict[str, Any] | None = None


class ClassificationSegmentSummaryResponse(BaseModel):
    """
    Лёгкая segment-aware summary для composite file.

    Это НЕ полный segment explainability contract.
    Его задача — лишь показать, что файл сегментирован и что у сегментов
    потенциально есть своя классификация.
    """

    segment_count: int | None = None
    primary_segment_id: str | None = None
    primary_segment_label: str | None = None
    has_segment_classification: bool | None = None


class ClassificationInvestigationRow(BaseModel):
    """
    Одна строка deal-level investigation list.

    Это компактная read-model запись для таблицы:
    - основные classification поля;
    - несколько derived explainability badges;
    - composition / segment summary для UX.
    """

    document_id: UUID
    filename: str
    folder_path: str | None = None
    status: str

    doc_type: str | None = None
    classification_level: str | None = None
    classification_confidence: float | None = None
    applicable_triggers: list[str] = Field(default_factory=list)
    classification_requires_review: bool = False

    decided_by: str | None = None
    confidence_zone: str | None = None
    contradiction_detected: bool = False
    l4_triggered: bool = False

    composition: DocumentCompositionSummary | None = None
    segment_summary: ClassificationSegmentSummaryResponse | None = None

    updated_at: datetime


class ClassificationInvestigationListResponse(BaseModel):
    """
    Полный ответ deal-level investigation endpoint.

    Содержит:
    - summary counters;
    - paginated items;
    - метаданные пагинации.
    """

    summary: ClassificationInvestigationSummary
    items: list[ClassificationInvestigationRow] = Field(default_factory=list)

    total: int
    page: int
    per_page: int
    total_pages: int
    has_next: bool
    has_previous: bool


class ClassificationInvestigationDetailResponse(BaseModel):
    """
    Полный explainability detail по одному документу.

    Структура разделена на несколько слоёв:
    - summary: финальные classification поля документа;
    - derived explainability: краткие вычисленные признаки;
    - normalized detail: уровни, кандидаты, voting;
    - raw debug payload: сохранённые JSON-данные без потерь.
    """

    document_id: UUID
    filename: str
    folder_path: str | None = None
    status: str

    doc_type: str | None = None
    classification_level: str | None = None
    classification_confidence: float | None = None
    applicable_triggers: list[str] = Field(default_factory=list)
    classification_requires_review: bool = False

    language: str | None = None
    jurisdiction_guess: str | None = None

    decided_by: str | None = None
    confidence_zone: str | None = None
    contradiction_detected: bool = False
    l4_triggered: bool = False

    levels_tried: list[str] = Field(default_factory=list)
    candidates: list[ClassificationCandidateResponse] = Field(default_factory=list)
    level_results: list[ClassificationLevelResultResponse] = Field(default_factory=list)
    voting: ClassificationVotingResponse | None = None
    decision_summary: dict[str, Any] = Field(default_factory=dict)

    composition: DocumentCompositionSummary | None = None
    segment_summary: ClassificationSegmentSummaryResponse | None = None

    raw_result: dict[str, Any] = Field(default_factory=dict)
    raw_details: dict[str, Any] = Field(default_factory=dict)
