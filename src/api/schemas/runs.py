"""
Pydantic-схемы для запусков анализа (runs) и их статуса.
"""

from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field


class RunCreate(BaseModel):
    """
    Запрос на запуск анализа по сделке.

    profile:
      - "core"  — минимальный набор проверок
      - "full"  — полный набор
      - "max"   — максимум, что умеет система
    """
    playbook_version_id: UUID | None = None
    profile: str = Field(default="core", description="core / full / max")

    # Новый флаг: перед запуском проверок заново классифицировать документы
    force_reclassify: bool = Field(
        default=False,
        description="Re-run HybridClassifier on all documents before checks",
    )


class ClassificationStats(BaseModel):
    """
    Статистика качества классификации для одного run.

    Показывает, сколько документов попало на каждый уровень L0-L4,
    сколько низкоуверенных и сколько с неизвестным типом.
    """
    total_documents: int = 0
    l0_no_match: int = 0
    l1_filename: int = 0
    l2_keyword: int = 0
    l3_semantic: int = 0
    l4_llm: int = 0
    low_confidence_count: int = 0    # confidence < 0.6
    unknown_doc_type_count: int = 0  # doc_type = "Generic" или None


class RunResponse(BaseModel):
    """
    Краткий статус запуска анализа.

    Используется в UI для отображения прогресса и качества классификации.
    """
    id: UUID
    deal_id: UUID
    status: str
    profile: str
    total_checks: int
    completed_checks: int
    started_at: datetime | None
    completed_at: datetime | None
    error_details: dict | None
    classification_stats: ClassificationStats | None = None

    model_config = {"from_attributes": True}


class RunProgressResponse(BaseModel):
    """
    Упрощённая схема прогресса (можно использовать в SSE/поллинге).
    """
    status: str
    completed_checks: int
    total_checks: int
    percent: float


class ClassificationReportResponse(BaseModel):
    """
    Полный отчёт о качестве классификации для run.

    Используется в GET /runs/{run_id}/classification-report.
    Позволяет найти документы с низкой уверенностью и неизвестным типом.
    """
    run_id: UUID
    deal_id: UUID
    total_documents: int
    stats: ClassificationStats
    low_confidence_docs: list[dict]   # [{doc_id, filename, doc_type, confidence, classification_level}]
    unknown_type_docs: list[dict]     # [{doc_id, filename, detected_type}]
    trigger_coverage: dict[str, int]  # {trigger_name: doc_count}
