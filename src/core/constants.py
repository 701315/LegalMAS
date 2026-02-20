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
