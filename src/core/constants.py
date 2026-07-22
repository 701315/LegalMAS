# src/core/constants.py

"""
All enumerations and constants used across the system.
String-based enums use Enum/StrEnum and are compatible with JSON/DB serialization.
"""

from enum import Enum, StrEnum


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
    DELETED = "deleted"  # excluded from active work, retained for audit/history
    FAILED = "failed"
    ENRICHED = "enriched"


class SemanticEnrichmentStageOutcome(str, Enum):
    """
    Terminal outcome of the semantic enrichment formal pipeline stage.

    Semantics:
    - COMPLETED   — all candidate segments enriched successfully
    - DEGRADED    — partial success: some enriched, some failed/timed_out
    - SKIPPED     — no candidate segments or feature disabled
    - TIMED_OUT   — document budget exhausted before any enrichment succeeded
    - UNAVAILABLE — LLM not available at stage start
    """
    COMPLETED = "completed"
    DEGRADED = "degraded"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"
    UNAVAILABLE = "unavailable"


class SemanticEnrichmentDegradationSeverity(str, Enum):
    """
    Степень деградации при terminal outcome DEGRADED
    для стадии semantic enrichment.

    Semantics:
    - MINOR    — обогащено ≥ 80% кандидат-сегментов;
                 retrieval и checks остаются полезными.
    - PARTIAL  — обогащено 20–79% кандидат-сегментов;
                 частичный рабочий результат.
    - CRITICAL — обогащено < 20% кандидат-сегментов;
                 почти полная деградация, retrieval существенно ограничен.

    Используется только когда terminal_outcome == DEGRADED.
    При COMPLETED / SKIPPED / TIMED_OUT / UNAVAILABLE — None.
    """
    MINOR = "minor"
    PARTIAL = "partial"
    CRITICAL = "critical"


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

    Important:
    - this is NOT the business result of the check;
    - the business result is stored separately in CheckResult.result;
    - this enum describes only the technical execution outcome.

    Semantics:
    - PENDING         — check has not started yet;
    - RUNNING         — check is in progress;
    - SUCCESS         — compute and persist completed successfully;
    - COMPUTE_FAILED  — check could not be computed correctly;
    - PERSIST_FAILED  — check was computed, but DB persist failed;
    - TIMEOUT         — check did not finish due to timeout;
    - FAILED          — legacy terminal status kept for backward compatibility.
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    COMPUTE_FAILED = "COMPUTE_FAILED"
    PERSIST_FAILED = "PERSIST_FAILED"
    FAILED = "FAILED"  # legacy compatibility
    TIMEOUT = "TIMEOUT"


class PlaybookStatus(str, Enum):
    """
    Lifecycle status of a playbook version.

    Lifecycle: draft → published → archived
    Selection: is_default flag (separate from lifecycle)

    Legacy mapping:
    - 'stable' treated as 'published' at runtime
    - 'default' treated as 'published' + is_default=True at runtime
    """

    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"

    # Legacy values — kept for backward compatibility with existing DB rows.
    # New code should use PUBLISHED instead of STABLE/DEFAULT.
    STABLE = "stable"
    DEFAULT = "default"

    @property
    def is_runtime_ready(self) -> bool:
        """True if this version can be used for execution."""
        return self in (self.PUBLISHED, self.STABLE, self.DEFAULT)

    @property
    def is_immutable(self) -> bool:
        """True if content of this version must not be changed."""
        return self in (self.PUBLISHED, self.STABLE, self.DEFAULT, self.ARCHIVED)


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


class RunCheckPlanItemStatus(str, Enum):
    """
    Lifecycle статус элемента execution ledger (RunCheckPlanItem).

    Canonical source-of-truth для допустимых значений колонки
    run_check_plan_items.status. Используется как:
    - typed query-параметр в GET /runs/{run_id}/check-plan;
    - строго типизированный параметр RunCheckPlanItemRepository.list_by_run_id;
    - источник TERMINAL_STATUSES / ERROR_STATUSES в repository layer.
    """

    PLANNED = "planned"
    DISPATCHED = "dispatched"
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"
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


class LanguageDiscoveryStatus(StrEnum):
    """
    Status of the pre-run language discovery lifecycle.

    Used at two levels:
    - document-level: language discovery status for a specific document
      (stored in documents.language_discovery_status)
    - deal-level: aggregated status across all deal documents
      (stored in deals.language_discovery_status)

    Semantics:
    - PENDING    — language discovery is waiting to start
    - PROCESSING — language discovery is in progress
    - COMPLETED  — languages were determined successfully
    - FAILED     — language discovery finished with an error
    - PARTIAL    — some documents completed, some failed
                   (deal-level only)
    """

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


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
    """Entity types for PII detection."""

    PERSON_NAME = "person_name"
    PASSPORT = "passport"
    PHONE = "phone"
    EMAIL = "email"
    ADDRESS = "address"
    INN = "inn"
    OGRN = "ogrn"
    CADASTRAL = "cadastral"


class PIITokenPolicy(str, Enum):
    """Policy for PII tokenization."""

    TOKENIZE = "tokenize"  # replace with TYPE_N
    PRESERVE = "preserve"  # keep as is
    ROLE_MAP = "role_map"  # replace with contractual party role


class ClassificationLevel(str, Enum):
    """Classification cascade levels."""

    L1_RULES = "L1"  # Filename/path/extension — weak hint only
    L2_KEYWORDS = "L2"  # Keywords/phrases/regex from YAML
    L3_SEMANTIC = "L3"  # Embeddings similarity
    L4_LLM = "L4"  # LLM fallback (local GGUF or cloud API)
    HYBRID = "HYBRID"  # Weighted voting across levels


class SegmentClassificationStatus(str, Enum):
    """
    Pipeline-статус segment-level классификации для одного сегмента.

    Это статус СТАДИИ, а не бизнес-результат.
    Отвечает на вопрос: "завершена ли классификация этого сегмента?"

    Semantics:
    - PENDING    — сегмент создан, классификация ещё не запускалась
    - CLASSIFIED — классификация завершена, тип определён
    - UNKNOWN    — классификация завершена, тип НЕ определён
    - SKIPPED    — сегмент пропущен (пустой текст, не подходит)
    - FAILED     — классификация завершилась ошибкой

    Terminal statuses (стадия считается завершённой):
      CLASSIFIED, UNKNOWN, SKIPPED

    Non-terminal (стадия НЕ завершена, нужна повторная обработка):
      PENDING, FAILED
    """

    PENDING = "pending"
    CLASSIFIED = "classified"
    UNKNOWN = "unknown"
    SKIPPED = "skipped"
    FAILED = "failed"


# Набор terminal-статусов для segment-level классификации.
# Сегменты в этих статусах считаются обработанными для целей orchestration.
# FAILED намеренно НЕ входит в этот набор: failed-сегмент блокирует прогресс.
SEGMENT_CLASSIFICATION_TERMINAL_STATUSES: frozenset[str] = frozenset({
    SegmentClassificationStatus.CLASSIFIED.value,
    SegmentClassificationStatus.UNKNOWN.value,
    SegmentClassificationStatus.SKIPPED.value,
})


class DocumentClassificationOutcome(str, Enum):
    """
    Business outcome of document-level classification.

    Это НЕ pipeline-stage статус (Document.status).
    Отвечает на вопрос: "Каков итог classification для этого документа?"

    Semantics:
    - PENDING  — классификация ещё не выполнялась
    - TYPED    — тип документа определён (doc_type заполнен)
    - UNKNOWN  — классификация завершена, тип НЕ определён
    - FAILED   — классификация завершилась ошибкой

    Важно:
    - UNKNOWN != PENDING: UNKNOWN означает, что классификатор
      отработал до конца, но не смог определить тип.
    - FAILED != UNKNOWN: FAILED означает техническую ошибку,
      а не бизнес-результат "тип не распознан".
    """

    PENDING = "pending"
    TYPED = "typed"
    UNKNOWN = "unknown"
    FAILED = "failed"

    