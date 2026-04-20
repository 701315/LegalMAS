# src/core/constants.py

"""
All enumerations and constants used across the system.
Every Enum inherits from (str, Enum) for JSON/DB serialization.
"""

from enum import Enum


class DocumentStatus(str, Enum):
    """Status of a document in the processing pipeline."""

    PENDING = "pending"
    LANGUAGE_SELECTION_REQUIRED = "language_selection_required"
    PRIMARY_READY = "primary_ready"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    SANITIZED = "sanitized"
    STRUCTURED = "structured"
    CHUNKED = "chunked"
    CLASSIFIED = "classified"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    QUARANTINE = "quarantine"
    DUPLICATE = "duplicate"
    DELETED = "deleted"   # исключён из активной работы, но данные сохраняются для аудита/истории
    FAILED = "failed"


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


class CheckExecutionStatus(str, Enum):
    """
    Technical execution status of a single check.

    Важно:
    - это НЕ бизнес-результат проверки;
    - бизнес-результат хранится отдельно в CheckResult.result;
    - этот enum описывает именно технический факт исполнения check.

    Семантика:
    - PENDING         — check ещё не исполнялся;
    - RUNNING         — check запущен, но ещё не завершён;
    - SUCCESS         — compute и persist завершились успешно;
    - COMPUTE_FAILED  — check не смог корректно вычислиться;
    - PERSIST_FAILED  — check вычислился, но запись результата в БД не удалась;
    - TIMEOUT         — check не завершился из-за таймаута;
    - FAILED          — legacy terminal статус, сохраняем для обратной совместимости.
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    COMPUTE_FAILED = "COMPUTE_FAILED"
    PERSIST_FAILED = "PERSIST_FAILED"
    FAILED = "FAILED"  # legacy compatibility
    TIMEOUT = "TIMEOUT"


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


class RunStatus(str, Enum):
    """Status of an analysis run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class DocumentStageExecutionStatus(str, Enum):
    """Lifecycle of a single document stage execution attempt."""

    PLANNED = "planned"
    DISPATCHED = "dispatched"
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


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


class PIIEntityType(str, Enum):
    """Сущности для детекции PII."""

    PERSON_NAME = "person_name"
    PASSPORT = "passport"
    PHONE = "phone"
    EMAIL = "email"
    ADDRESS = "address"
    INN = "inn"
    OGRN = "ogrn"
    CADASTRAL = "cadastral"


class PIITokenPolicy(str, Enum):
    """Политика токенизации PII."""

    TOKENIZE = "tokenize"  # заменить на TYPE_N
    PRESERVE = "preserve"  # оставить как есть
    ROLE_MAP = "role_map"  # заменить на роль стороны договора


class ClassificationLevel(str, Enum):
    """Уровни каскада классификации."""

    L1_RULES = "L1"  # Filename/path/extension — weak hint only
    L2_KEYWORDS = "L2"  # Keywords/phrases/regex from YAML
    L3_SEMANTIC = "L3"  # Embeddings similarity
    L4_LLM = "L4"  # LLM fallback (local GGUF or cloud API)
    HYBRID = "HYBRID"  # Weighted voting across levels


# Настройки классификации
CLASSIFICATION_WEIGHTS = {
    "L1": 0.20,  # Weak hint — NEVER final verdict
    "L2": 0.40,  # Keywords/regex from YAML — primary signal
    "L3": 0.40,  # Embeddings similarity
}


CLASSIFICATION_THRESHOLDS = {
    "L2_accept": 0.85,
    "L3_accept": 0.80,
    "voting_threshold": 0.75,
    "uncertain_threshold": 0.50,
}

