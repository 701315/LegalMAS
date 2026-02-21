"""
All enumerations and constants used across the system.
Every Enum inherits from (str, Enum) for JSON/DB serialization.
"""

from enum import Enum


class DocumentStatus(str, Enum):
    """Status of a document in the processing pipeline."""

    PENDING = "pending"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    SANITIZED = "sanitized"
    STRUCTURED = "structured"
    CLASSIFIED = "classified"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    QUARANTINE = "quarantine"


class Severity(str, Enum):
    """Risk severity level for a check result."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    PASS = "pass"
    UNCLEAR = "unclear"


class CheckResultStatus(str, Enum):
    """Result of a single DD check."""

    FAIL = "fail"
    PASS = "pass"
    UNCLEAR = "unclear"


class PlaybookStatus(str, Enum):
    """Lifecycle status of a playbook version."""

    DRAFT = "draft"
    STABLE = "stable"
    DEFAULT = "default"


class RelationType(str, Enum):
    """Type of relationship between two documents."""

    MASTER = "master"
    APPENDIX = "appendix"
    AMENDMENT = "amendment"
    DISCLOSURE = "disclosure"
    VERSION = "version"
    DRAFT = "draft"
    COUNTERPART = "counterpart"


class JobStatus(str, Enum):
    """Status of an async processing job."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DLQ = "dlq"


class BundleSourceType(str, Enum):
    """Source from which documents were imported."""

    ZIP = "zip"
    VDR_API = "vdr_api"
    LOCAL = "local"


class PIIMode(str, Enum):
    """PII processing mode (152-FZ compliance)."""

    LOCAL_ONLY = "local_only"
    CLOUD_FALLBACK_ALLOWED = "cloud_fallback_allowed"


class ExportType(str, Enum):
    """Type of export artifact."""

    GRID_XLSX = "grid_xlsx"
    DEAL_SUMMARY_XLSX = "deal_summary_xlsx"
    REPORT_DOCX = "report_docx"
    REPORT_PDF = "report_pdf"
    REQUESTS_DOCX = "requests_docx"


class DealStatus(str, Enum):
    """Overall status of a deal."""

    CREATED = "created"
    IMPORTING = "importing"
    EXTRACTING = "extracting"
    ANALYZING = "analyzing"
    READY_FOR_QC = "ready_for_qc"
    COMPLETED = "completed"


class QCStatus(str, Enum):
    """Quality control status for a check result."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    OVERRIDDEN = "overridden"


class DetectorType(str, Enum):
    """Type of detector used in a check."""

    RULES = "rules"
    LLM = "llm"
    HYBRID = "hybrid"


class ClassificationLevel(str, Enum):
    """Уровень каскада классификации документов."""

    L1_RULES = "L1"  # Filename + folder rules
    L2_HEADER = "L2"  # Header regex
    L3_SEMANTIC = "L3"  # Embeddings similarity
    L4_LLM = "L4"  # LLM fallback
    HYBRID = "HYBRID"  # Weighted voting из нескольких уровней


class TriggerType(str, Enum):
    """Типы триггеров для conditional checks из YAML."""

    RESIDENTIAL_PROPERTY = "residential_property"
    LAND_PLOT_SALE = "land_plot_sale"
    BUILDING_SALE = "building_sale"
    SHARE_IN_RIGHT_SALE = "share_in_right_sale"
    LEGAL_ENTITY_PARTY = "legal_entity_party"
    INDIVIDUAL_PARTY = "individual_party"
    MORTGAGE_RELATED = "mortgage_related"
    LEASE_RELATED = "lease_related"
    FOREIGN_BUYER = "foreign_buyer_keywords"
    AGRICULTURAL_LAND = "agricultural_land_keywords"
    BORDER_ZONE = "border_zone_keywords"
    MCD_COMMON_PROPERTY = "mcd_common_property_sale"


# Пороги классификации (будут использоваться в HybridClassifier)
CLASSIFICATION_THRESHOLDS = {
    "L1_accept": 0.90,  # L1 уверен → стоп
    "L2_accept": 0.85,  # L2 уверен → стоп
    "L3_accept": 0.80,  # L3 уверен → стоп
    "voting_threshold": 0.75,  # Порог для weighted voting
    "uncertain_threshold": 0.50,  # Ниже — UNKNOWN
}
