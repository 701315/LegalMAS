# src/api/schemas/__init__.py

"""
Пакет со схемами (Pydantic-моделями) для API.

Этот __init__ удобно использовать, чтобы централизованно
экспортировать основные схемы, которые нужны в нескольких модулях.
"""

from .documents import (
    ClassificationMetadata,
    DocumentResponse,
    DocumentVersionResponse,
    DocumentDetailResponse,
    ReclassifyRequest,
    ReclassifyResponse,
    ReclassifyBatchRequest,
    FamilyResponse,
    RelationResponse,
)
from .runs import (
    RunCreate,
    RunResponse,
    ClassificationStats,
    ClassificationReportResponse,
)
from .results import (
    CheckResultResponse,
    EvidenceResponse,
    StructuredDataResponse,
)
from .requests import (
    DDRequestCreate,
    DDRequestUpdate,
    DDRequestResponse,
)
from .deal_review import (
    DocumentSummaryDTO,
    DocumentDetailDTO,
    CheckItemDTO,
    DDRequestDTO,
    ConditionalCheckDTO,
    ExtractedValueDTO,
)

from .admin import YamlInstructionDTO

__all__ = [
    # documents
    "ClassificationMetadata",
    "DocumentResponse",
    "DocumentVersionResponse",
    "DocumentDetailResponse",
    "ReclassifyRequest",
    "ReclassifyResponse",
    "ReclassifyBatchRequest",
    "FamilyResponse",
    "RelationResponse",
    # runs
    "RunCreate",
    "RunResponse",
    "ClassificationStats",
    "ClassificationReportResponse",
    # results
    "CheckResultResponse",
    "EvidenceResponse",
    "StructuredDataResponse",
    # requests
    "DDRequestCreate",
    "DDRequestUpdate",
    "DDRequestResponse",
    # deal_review DTO
    "DocumentSummaryDTO",
    "DocumentDetailDTO",
    "CheckItemDTO",
    "DDRequestDTO",
    "ConditionalCheckDTO",
    "ExtractedValueDTO",
    "YamlInstructionDTO",
]
