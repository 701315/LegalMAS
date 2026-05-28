# src/api/schemas/__init__.py

"""
Пакет со схемами (Pydantic-моделями) для API.

Этот __init__ удобно использовать, чтобы централизованно
экспортировать основные схемы, которые нужны в нескольких модулях.
"""

from .admin import YamlInstructionDTO
from .deal_review import (
    CheckItemDTO,
    ConditionalCheckDTO,
    DDRequestDTO,
    DocumentDetailDTO,
    DocumentSummaryDTO,
    ExtractedValueDTO,
)
from .documents import (
    ClassificationMetadata,
    DocumentDetailResponse,
    DocumentResponse,
    DocumentVersionResponse,
    FamilyResponse,
    ReclassifyBatchRequest,
    ReclassifyRequest,
    ReclassifyResponse,
    RelationResponse,
)
from .requests import (
    DDRequestCreate,
    DDRequestResponse,
    DDRequestUpdate,
)
from .results import (
    CheckResultResponse,
    EvidenceResponse,
    StructuredDataResponse,
)
from .runs import (
    ClassificationReportResponse,
    ClassificationStats,
    RunCreate,
    RunResponse,
)

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
