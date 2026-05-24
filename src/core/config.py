# src/core/config.py

"""
Application configuration.
Loads settings from environment variables / .env file.
"""

import logging
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_config_logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """
    All application settings.
    Values are loaded from environment variables or .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- Database ---
    DATABASE_URL: str = "postgresql+asyncpg://mas:mas_dev_password@localhost:5432/mas_dd"

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- MinIO / S3 ---
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin123"
    MINIO_BUCKET: str = "mas-artifacts"
    MINIO_SECURE: bool = False

    # --- Application ---
    BASE_DIR: str = str(Path(__file__).resolve().parent.parent.parent)
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "DEBUG"
    LOG_FORMAT: str = "console"
    LLM_EXTRACTION_JSON_GRAMMAR_PATH: str | None = None
    LOG_FILE_DIR: str | None = None

    # --- Classification explainability / observability ---
    CLASSIFICATION_DECISION_TRACE_SCHEMA_VERSION: int = 1
    CLASSIFICATION_LOG_DECISIONS: bool = True
    CLASSIFICATION_LOG_L4_SKIPS: bool = True
    CLASSIFICATION_TRACE_INCLUDE_RANKING: bool = True
    CLASSIFICATION_TRACE_INCLUDE_CANDIDATES: bool = True

    # --- Classification & Embeddings (общие) ---
    EMBEDDINGS_MODEL: str = "intfloat/multilingual-e5-large"
    CLASSIFICATION_REGISTRY_PATH: str = "playbooks/document_types/registry.yaml"

    # --- LLM Providers (общий верхнеуровневый) ---
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    LOCAL_LLM_ENDPOINT: str = "http://localhost:11434"

    # --- Circuit Breaker ---
    CIRCUIT_BREAKER_THRESHOLD: int = 5
    CIRCUIT_BREAKER_TIMEOUT: int = 60

    # --- Import Worker ---
    IMPORT_MAX_FILE_SIZE_MB: int = 200
    IMPORT_ALLOWED_EXTENSIONS: str = (
        ".pdf,.docx,.doc,.xlsx,.xls,.png,.jpg,.jpeg,.tiff,.tif"
    )
    IMPORT_MAX_FILES_PER_BUNDLE: int = 10000

    # --- Extractor ---
    EXTRACTION_MIN_TEXT_LENGTH_PER_PAGE: int = 50
    EXTRACTION_OCR_QUARANTINE_THRESHOLD: float = 0.6
    EXTRACTION_HYBRID_MIN_OCR_RATE_FOR_QUARANTINE: float = 0.5
    EXTRACTION_OCR_DPI: int = 300
    EXTRACTION_MAX_PAGES: int = 500
    EXTRACTION_OCR_ENABLED: bool = True
    EXTRACTION_HARD_TIMEOUT_SECONDS: int = 300
    EXTRACTION_DEBUG_LOG: bool = False
    EXTRACTION_DEBUG_DOC_ID: str | None = None

    # --- Office → PDF Converter (DOC/DOCX) ---
    DOCX_CONVERTER_URL: str | None = None
    DOCX_CONVERTER_TIMEOUT_SECONDS: int = 60

    # --- Element enrichment ---
    EXTRACTION_ENRICH_ELEMENT_TYPES: bool = True

    # --- Testing / Integration ---
    DISABLE_DOWNSTREAM_TASKS: bool = False

    # --- PII Sanitization ---
    PII_ENCRYPTION_KEY: str = ""
    PII_NER_ENABLED: bool = True
    PII_PRESERVE_INN: bool = True
    PII_PRESERVE_OGRN: bool = True
    PII_PRESERVE_CADASTRAL: bool = True
    PII_PRESERVE_PARTY_ROLES: bool = True
    PII_AUDIT_ENABLED: bool = True
    PII_SKIP_IF_ALREADY_SANITIZED: bool = True

    # --- Structure Builder ---
    STRUCTURE_MIN_CLAUSE_COVERAGE: float = 0.60
    STRUCTURE_DEGRADED_CHUNK_TOKENS: int = 500
    STRUCTURE_MAX_CLAUSE_TITLE_LEN: int = 100
    STRUCTURE_ENABLE_SEGMENTATION: bool = False
    STRUCTURE_STORE_FILE_GRAPH: bool = True
    ALLOW_LEGACY_LAYOUT_FALLBACK: bool = False
    STRUCTURE_STORE_SEGMENT_TREES: bool = True

    # --- Chunks / CHUNKS v2 ---
    CHUNKS_V2_ENABLED: bool = True

    # ---------------------------------------------------------------------------
    # --- Classifier (L1 → L2 → L3 → L4 → voting) ---
    # ---------------------------------------------------------------------------

    CLASSIFIER_EMBEDDINGS_MODEL: str = "intfloat/multilingual-e5-small"
    CLASSIFIER_REGISTRY_PATH: str = "playbooks/document_types"

    CLASSIFIER_L1_WEIGHT: float = 0.20
    CLASSIFIER_L2_WEIGHT: float = 0.40
    CLASSIFIER_L3_WEIGHT: float = 0.40

    CLASSIFICATION_L4_PROMPT_PATH: str = str(
        Path(__file__).resolve().parent.parent.parent
        / "prompts"
        / "classification"
        / "classify_document.txt"
    )
    CLASSIFICATION_L4_MAX_INPUT_CHARS: int = 6000
    CLASSIFIER_L4_ENABLED: bool = True

    # --- L1 ---
    CLASSIFICATION_L1_ACCEPT: float = 0.90
    CLASSIFICATION_L1_STRONG: float = 0.90
    CLASSIFICATION_L1_CONSENSUS_MIN: float = 0.90
    L1_FILENAME_SPECIFIC_WEIGHT_FACTOR: float = 0.20
    L1_FILENAME_GENERIC_WEIGHT_FACTOR: float = 0.05
    L1_FILENAME_CONTEXT_WEIGHT_FACTOR: float = 0.03
    L1_FILENAME_CONTEXT_WEIGHT_SECONDARY_FACTOR: float = 0.02
    L1_FILENAME_BASE_CONF_DELTA: float = 0.10
    L1_FILENAME_MAX_SPECIFIC_DELTA: float = 0.10
    L1_FILENAME_RULE_WEIGHT_DECAY: float = 0.75
    L1_FILENAME_GENERIC_MIN_CONF: float = 0.50
    L1_FILENAME_GENERIC_MIN_EXTRA: float = 0.10
    L1_FILENAME_GENERIC_MAX_CONF: float = 0.65
    L1_FILENAME_GENERIC_WEIGHT_CAP: float = 0.50
    L1_FILENAME_CONTEXT_WEIGHT_CAP: float = 0.50

    CLASSIFICATION_L1_FOLDER_RULE_WEIGHT_FACTOR: float = 0.75
    CLASSIFICATION_L1_SPECIFIC_CONF_BOOST: float = 0.10
    CLASSIFICATION_L1_SPECIFIC_WEIGHT_FACTOR: float = 0.20
    CLASSIFICATION_L1_GENERIC_WEIGHT_CAP: float = 0.50
    CLASSIFICATION_L1_GENERIC_WEIGHT_FACTOR: float = 0.05
    CLASSIFICATION_L1_CONTEXT_WEIGHT_CAP: float = 0.50
    CLASSIFICATION_L1_CONTEXT_WEIGHT_FACTOR_SPECIFIC: float = 0.03
    CLASSIFICATION_L1_CONTEXT_WEIGHT_FACTOR_GENERIC: float = 0.02
    CLASSIFICATION_L1_CONTEXT_WEIGHT_FACTOR_CONTEXT_ONLY: float = 0.03
    CLASSIFICATION_L1_GENERIC_MIN_CONF: float = 0.50
    CLASSIFICATION_L1_GENERIC_MIN_EXTRA_FACTOR: float = 0.10
    CLASSIFICATION_L1_GENERIC_MAX_CONF: float = 0.65
    CLASSIFICATION_L1_CONTEXT_ONLY_MAX_CONF: float = 0.65
    CLASSIFICATION_L1_GENERIC_UNDER_SPECIFIC_MARGIN: float = 0.10

    # --- L2 ---
    CLASSIFICATION_L2_ACCEPT: float = 0.85
    CLASSIFICATION_L2_STRONG: float = 0.90
    CLASSIFICATION_L2_AMBIGUITY_MARGIN: float = 0.15
    CLASSIFICATION_L2_L3_TIEBREAK_DELTA: float = 0.05
    CLASSIFICATION_L2_INPUT_QUALITY_WEIGHT: float = 1.0
    CLASSIFICATION_L2_EXCL_HARD: int = 1
    CLASSIFICATION_L2_DEFAULT_POSITIVE_WEIGHT: float = 0.3
    CLASSIFICATION_L2_DEFAULT_NEGATIVE_WEIGHT: float = -0.3
    CLASSIFICATION_L2_INPUT_QUALITY_FULL_CHARS: float = 120.0

    # --- L3 ---
    CLASSIFICATION_L3_INPUT_QUALITY_MIN_CHARS: int = 300
    CLASSIFICATION_L3_INPUT_QUALITY_FULL_CHARS: int = 1500
    CLASSIFICATION_L3_SINGLE_WINDOW_MAX_CHARS: int = 1000
    CLASSIFICATION_L3_MULTI_WINDOW_MIN_TEXT_CHARS: int = 1500
    CLASSIFICATION_L3_WINDOW_HEAD_CHARS: int = 800
    CLASSIFICATION_L3_WINDOW_MIDDLE_CHARS: int = 600
    CLASSIFICATION_L3_WINDOW_TAIL_CHARS: int = 400
    CLASSIFICATION_L3_WINDOW_WEIGHT_HEAD: float = 0.50
    CLASSIFICATION_L3_WINDOW_WEIGHT_MIDDLE: float = 0.30
    CLASSIFICATION_L3_WINDOW_WEIGHT_TAIL: float = 0.20
    CLASSIFICATION_L3_NEGATIVE_PROTOTYPE_FACTOR: float = 0.35
    CLASSIFICATION_L3_AMBIGUITY_MARGIN: float = 0.20
    CLASSIFICATION_L3_MAX_AMBIGUITY_PENALTY: float = 0.15
    CLASSIFICATION_L3_CONFIDENCE_SIMILARITY_WEIGHT: float = 0.70
    CLASSIFICATION_L3_CONFIDENCE_MARGIN_WEIGHT: float = 0.30
    CLASSIFICATION_L3_MARGIN_SATURATION: float = 0.20
    CLASSIFICATION_L3_TOP_ALTERNATIVES: int = 3
    CLASSIFICATION_L3_POSITIVE_PROTOTYPE_MAX_CHARS: int = 4000
    CLASSIFICATION_L3_NEGATIVE_PROTOTYPE_MAX_CHARS: int = 2000
    CLASSIFICATION_L3_ACCEPT: float = 0.80
    CLASSIFICATION_L3_STRONG: float = 0.85
    CLASSIFICATION_L3_CONSENSUS_RAW_MIN: float = 0.60
    CLASSIFICATION_L3_STRONG_CONFLICT_RAW: float = 0.75
    CLASSIFICATION_L3_SIGNAL_QUALITY_UPLIFT: float = 0.15

    # --- L4 ---
    CLASSIFICATION_L4_ACCEPT: float = 0.70
    CLASSIFICATION_L4_MARGIN_MIN: float = 0.25
    CLASSIFICATION_L4_INPUT_QUALITY_MIN: float = 0.60
    CLASSIFICATION_L4_REVIEW_QUALITY_FLOOR: float = 0.30
    CLASSIFICATION_L4_UNKNOWN_MIN_CONFIDENCE: float = 0.05
    CLASSIFICATION_L4_REASONING_MAX_CHARS: int = 1000

    # --- Voting / ensemble ---
    CLASSIFICATION_HYBRID_ACCEPT: float = 0.45
    CLASSIFICATION_UNKNOWN_MAX: float = 0.40
    CLASSIFICATION_SINGLE_SOURCE_CAP: float = 0.80
    CLASSIFICATION_SINGLE_SOURCE_HIGH_QUALITY_CAP: float = 0.88
    CLASSIFICATION_SINGLE_SOURCE_MARGIN_MIN: float = 0.15
    CLASSIFICATION_DOMINANT_FLOOR_FACTOR: float = 0.85
    CLASSIFICATION_MAX_AGREEMENT_BONUS: float = 0.08
    CLASSIFICATION_AGREEMENT_BONUS_STEP: float = 0.04
    CLASSIFICATION_MULTI_LEVEL_FLOOR_UPLIFT: float = 0.03
    CLASSIFICATION_SINGLE_SOURCE_HIGH_CONF_MIN: float = 0.90
    CLASSIFICATION_MARGIN_BONUS_STRONG_SCORE_MIN: float = 0.70
    CLASSIFICATION_MARGIN_BONUS_MEDIUM_SCORE_MIN: float = 0.60
    CLASSIFICATION_MARGIN_BONUS_STRONG_CAP: float = 0.08
    CLASSIFICATION_MARGIN_BONUS_STRONG_FACTOR: float = 0.40
    CLASSIFICATION_MARGIN_BONUS_MEDIUM_CAP: float = 0.04
    CLASSIFICATION_MARGIN_BONUS_MEDIUM_FACTOR: float = 0.20
    CLASSIFICATION_AGREEMENT_BONUS_MIN_SCORE: float = 0.45
    CLASSIFICATION_AGREEMENT_BONUS_FULL_SCORE: float = 0.60
    CLASSIFICATION_AGREEMENT_BONUS_WEAK_FACTOR: float = 0.50
    CLASSIFICATION_AMBIGUITY_PENALTY_MAX: float = 0.50
    CLASSIFICATION_AMBIGUITY_FACTOR_MIN: float = 0.50
    CLASSIFICATION_SOFT_NEGATIVE_MAX_PENALTY: float = 0.60
    CLASSIFICATION_SOFT_NEGATIVE_STEP: float = 0.20
    CLASSIFICATION_DEFAULT_LEVEL_WEIGHT: float = 0.20

    # --- Priority rules ---
    CLASSIFICATION_L1_L2_AGREE_MIN: float = 0.70

    # ---------------------------------------------------------------------------
    # --- LLM Provider ---
    # ---------------------------------------------------------------------------

    LLM_PROVIDER: str = "llamacpp"
    LLM_TIMEOUT_SECONDS: int = 3600
    LLM_TEMPERATURE: float = 0.0
    LLM_MAX_TOKENS: int = 256

    LLM_OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    LLM_OPENAI_API_KEY: str = ""
    LLM_OPENAI_MODEL: str = "gpt-4o-mini"

    LLM_OLLAMA_BASE_URL: str = "http://localhost:11434"
    LLM_OLLAMA_MODEL: str = "llama3.1"

    LLM_LOCAL_MODEL_PATH: str = r"C:\LegalMAS\LLMmodel\model.gguf"

    # Контекстное окно — источник истины для llamacpp.
    # LLM_CONTEXT_LIMIT синхронизируется с этим значением через @model_validator.
    LLM_LOCAL_N_CTX: int = 8192
    LLM_LOCAL_N_GPU_LAYERS: int = 0

    # Лимит токенов для LLMClient._compute_token_budget().
    # Для llamacpp авто-синхронизируется с LLM_LOCAL_N_CTX (см. _sync_llm_context_limit).
    # Для openai/ollama — задаётся явно или остаётся дефолтом.
    LLM_CONTEXT_LIMIT: int = 8192

    LLM_SAFETY_MARGIN_TOKENS: int = 512
    LLM_MIN_OUTPUT_TOKENS: int = 64

    LLM_CLOUD_MODEL: str = "gpt-4o-mini"
    LLM_CLOUD_API_KEY: str = ""
    LLM_DEFAULT_CONFIDENCE: float = 0.70

    # --- Structure LLM Refiner ---
    STRUCTURE_ENABLE_LLM_REFINER: bool = True
    STRUCTURE_LLM_PROVIDER: str = "llamacpp"
    STRUCTURE_LLM_MODEL: str = "..."
    STRUCTURE_LLM_TIMEOUT_SECONDS: int = 20
    STRUCTURE_LLM_MAX_AMBIGUOUS_PER_DOC: int = 8
    STRUCTURE_LLM_MIN_CONFIDENCE: float = 0.80
    STRUCTURE_LLM_MAX_CONTEXT_CHARS: int = 1200
    STRUCTURE_LLM_SHADOW_MODE: bool = False

    # --- Dedup & Relations ---
    DEDUP_EXACT_ENABLED: bool = True
    RELATIONS_FILENAME_ENABLED: bool = True
    RELATIONS_TEXT_ENABLED: bool = True
    RELATIONS_FILENAME_SIMILARITY_THRESHOLD: int = 75
    RELATIONS_MAX_HOPS: int = 2
    RELATIONS_MAX_FAMILY_SIZE: int = 20

    FAMILY_MASTER_DOC_TYPES: list[str] = [
        "SPA", "SHA", "Loan", "RealEstate", "ServiceAgreement",
    ]
    FAMILY_MASTER_MIN_CLASSIFICATION_LEVEL: str = "L1"
    FAMILY_CLASSIFICATION_LEVEL_PRIORITY: list[str] = ["L0", "L1", "L2", "L3"]

    # --- Runner / Core Engine ---
    RELATIONS_DEDUP_ENABLED: bool = True
    RELATIONS_ENABLED: bool = True
    RUNNER_RETRIEVAL_TOP_K: int = 5
    RUNNER_DENSE_WEIGHT: float = 0.6
    RUNNER_SPARSE_WEIGHT: float = 0.3
    RUNNER_METADATA_WEIGHT: float = 0.1
    RUNNER_METADATA_KIND_BONUS_SUBCLAUSE: float = 0.3
    RUNNER_METADATA_KIND_PENALTY_SECTION: float = 0.1
    RUNNER_METADATA_SECTION_TITLE_BOOST: float = 1.0
    RUNNER_METADATA_POSITION_MID_BOOST: float = 0.3
    RUNNER_METADATA_PATH_TITLES_BOOST: float = 0.5
    RUNNER_METADATA_SUMMARY_BOOST: float = 0.2
    CHECK_RUNNER_MODE: str = "global_and_doc_type"
    RUNNER_EMBEDDINGS_ENABLED: bool = True
    RUNNER_EMBEDDINGS_MODEL: str = "intfloat/multilingual-e5-small"
    RUNNER_EMBEDDINGS_CACHE_DIR: str = ".cache/embeddings"

    PLAYBOOK_DOCUMENT_TYPES_DIR: str = "playbooks/document_types"
    PLAYBOOK_DEFAULT_PATH: str = "playbooks/test/v1.0/playbook.yaml"
    PROMPTS_DIR: str = "prompts"

    RULES_CONFIDENCE_THRESHOLD: float = 0.7
    CHECK_PASS_THRESHOLD: float = 0.6
    CHECK_UNCLEAR_THRESHOLD: float = 0.3

    # --- Aggregator & Exporter ---
    EXPORT_TOP_RISKS_COUNT: int = 20
    EXPORT_EVIDENCE_MAX_LENGTH: int = 300
    EXPORT_DD_REQUEST_DEDUP: bool = True
    EXPORT_DEFAULT_REQUESTER_ROLE: str = "deal_owner"
    EXPORT_DD_REQUEST_SOURCE: str = "yaml"
    EXPORT_STRUCTURED_DATA_ENABLED: bool = True
    EXPORT_CONDITIONAL_CHECKS_SHEET: bool = True
    EXPORT_CLASSIFICATION_METADATA: bool = True

    # --- Classification API ---
    API_EXPOSE_YAML_METADATA: bool = True
    API_ALLOW_FORCE_RECLASSIFY: bool = True
    API_RECLASSIFY_BATCH_LIMIT: int = 50

    # --- Ops: Metrics & Regression ---
    METRICS_ENABLED: bool = True
    METRICS_PREFIX: str = "mas_dd"
    GATE_EVIDENCE_VALIDITY_MIN: float = 0.95
    GATE_PRECISION_CRITICAL_MIN: float = 0.90
    GATE_RECALL_CRITICAL_MIN: float = 0.85
    GATE_UNCLEAR_RATE_MAX: float = 0.10
    GATE_RETRIEVAL_HIT_RATE_MIN: float = 0.80
    GATE_F1_DELTA_MIN: float = -0.05
    GATE_CLASSIFICATION_ACCURACY_MIN: float = 0.90
    GATE_YAML_COVERAGE_MIN: float = 0.70
    GATE_LOW_CONFIDENCE_RATE_MAX: float = 0.15

    GOLDEN_DATASET_PATH: str = "golden_dataset"

    # --- Celery ---
    CELERY_DEFAULT_WORKER_CONCURRENCY: int = 4
    CELERY_HEAVY_WORKER_CONCURRENCY: int = 1

    # ---------------------------------------------------------------------------
    # --- Validators ---
    # ---------------------------------------------------------------------------

    @model_validator(mode="after")
    def _sync_llm_context_limit(self) -> "Settings":
        """
        Для llamacpp: LLM_CONTEXT_LIMIT ОБЯЗАН совпадать с LLM_LOCAL_N_CTX,
        т.к. модель загружается с n_ctx=LLM_LOCAL_N_CTX, а LLMClient проверяет
        бюджет по LLM_CONTEXT_LIMIT. Рассинхрон → ложные LLMContextLimitError
        → fallback в UNKNOWN.

        Источник истины: LLM_LOCAL_N_CTX.
        Для openai/ollama validator не вмешивается.
        """
        if self.LLM_PROVIDER == "llamacpp":
            if self.LLM_CONTEXT_LIMIT != self.LLM_LOCAL_N_CTX:
                _config_logger.warning(
                    "LLM_CONTEXT_LIMIT (%d) != LLM_LOCAL_N_CTX (%d) "
                    "for llamacpp provider — auto-syncing to LLM_LOCAL_N_CTX. "
                    "Set LLM_CONTEXT_LIMIT=%d in .env to suppress this warning.",
                    self.LLM_CONTEXT_LIMIT,
                    self.LLM_LOCAL_N_CTX,
                    self.LLM_LOCAL_N_CTX,
                )
                self.LLM_CONTEXT_LIMIT = self.LLM_LOCAL_N_CTX
        return self


# Singleton
settings = Settings()
