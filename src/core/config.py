# src/core/config.py

"""
Application configuration.
Loads settings from environment variables / .env file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "DEBUG"
    LOG_FORMAT: str = "console"  # "console" for dev, "json" for production

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
    IMPORT_ALLOWED_EXTENSIONS: str = ".pdf,.docx,.doc,.xlsx,.xls,.png,.jpg,.jpeg,.tiff,.tif"
    IMPORT_MAX_FILES_PER_BUNDLE: int = 10000
    # CLASSIFIER_REGISTRY_PATH уже задан выше и используется Import Worker'ом.

    # --- Extractor (Stage 4) ---
    EXTRACTION_MIN_TEXT_LENGTH_PER_PAGE: int = 50
    EXTRACTION_OCR_QUARANTINE_THRESHOLD: float = 0.6
    EXTRACTION_OCR_DPI: int = 300
    EXTRACTION_MAX_PAGES: int = 500
    EXTRACTION_OCR_ENABLED: bool = True

    # --- Office → PDF Converter (DOC/DOCX) ---
    # URL HTTP‑сервиса конвертации офисных файлов в PDF.
    # Пример: "http://office-converter:8080/convert"
    # Если не задан, DOCX/DOC-документы будут падать на стадии convert
    # с понятной ошибкой "conversion service is not configured".
    DOCX_CONVERTER_URL: str | None = None

    # Таймаут запроса к сервису конвертации, в секундах.
    DOCX_CONVERTER_TIMEOUT_SECONDS: int = 60

    # --- Element enrichment ---
    EXTRACTION_ENRICH_ELEMENT_TYPES: bool = True

    # --- Testing / Integration ---
    DISABLE_DOWNSTREAM_TASKS: bool = False

    # --- PII Sanitization (Stage 5) ---
    # Fernet key (base64). Пустой = dev mode (plaintext mapping).
    PII_ENCRYPTION_KEY: str = ""
    PII_NER_ENABLED: bool = True
    PII_PRESERVE_INN: bool = True
    PII_PRESERVE_OGRN: bool = True
    PII_PRESERVE_CADASTRAL: bool = True
    PII_PRESERVE_PARTY_ROLES: bool = True
    PII_AUDIT_ENABLED: bool = True
    PII_SKIP_IF_ALREADY_SANITIZED: bool = True

    # --- Structure Builder (Stage 6) ---
    STRUCTURE_MIN_CLAUSE_COVERAGE: float = 0.60
    STRUCTURE_DEGRADED_CHUNK_TOKENS: int = 500
    STRUCTURE_MAX_CLAUSE_TITLE_LEN: int = 100

    # --- Classifier (Stage 6) ---
    CLASSIFIER_L1_WEIGHT: float = 0.20  # L1 — слабый hint, не финальный вердикт
    CLASSIFIER_L2_ACCEPT_THRESHOLD: float = 0.85
    CLASSIFIER_L3_ACCEPT_THRESHOLD: float = 0.80
    CLASSIFIER_VOTING_THRESHOLD: float = 0.75
    CLASSIFIER_UNCERTAIN_THRESHOLD: float = 0.50
    CLASSIFIER_EMBEDDINGS_MODEL: str = "intfloat/multilingual-e5-small"  # L3
    CLASSIFIER_REGISTRY_PATH: str = "playbooks/document_types"

    # --- LLM Provider (Stage 6 L4) ---
    LLM_PROVIDER: str = "none"  # "none" | "local" | "openai" | "anthropic"
    LLM_LOCAL_MODEL_PATH: str = "C:/LegalMAS/LLMmodel/model.gguf"
    LLM_LOCAL_N_CTX: int = 4096  # context window for GGUF model
    LLM_LOCAL_N_GPU_LAYERS: int = 0  # 0 = CPU only, >0 = GPU offload
    LLM_CLOUD_MODEL: str = "gpt-4o-mini"
    LLM_CLOUD_API_KEY: str = ""
    LLM_TIMEOUT_SECONDS: int = 30

    # --- Dedup & Relations (Stage 7) ---
    DEDUP_EXACT_ENABLED: bool = True
    RELATIONS_FILENAME_ENABLED: bool = True
    RELATIONS_TEXT_ENABLED: bool = True
    RELATIONS_FILENAME_SIMILARITY_THRESHOLD: int = 75
    RELATIONS_MAX_HOPS: int = 2
    RELATIONS_MAX_FAMILY_SIZE: int = 20

    # Fallback list — Primary source: YAMLRegistry.get_master_doc_types()
    FAMILY_MASTER_DOC_TYPES: list[str] = [
        "SPA",
        "SHA",
        "Loan",
        "RealEstate",
        "ServiceAgreement",
    ]
    FAMILY_MASTER_MIN_CLASSIFICATION_LEVEL: str = "L1"
    FAMILY_CLASSIFICATION_LEVEL_PRIORITY: list[str] = [
        "L0",
        "L1",
        "L2",
        "L3",
    ]

    # --- Runner / Core Engine (Stage 8) ---

    # Интеграция со Stage 7
    RELATIONS_DEDUP_ENABLED: bool = True  # использовать dedup слоя Stage 7
    RELATIONS_ENABLED: bool = True  # учитывать relations/families

    # Runner: retrieval и весовые коэффициенты
    RUNNER_RETRIEVAL_TOP_K: int = 5
    RUNNER_DENSE_WEIGHT: float = 0.6  # embeddings (shared)
    RUNNER_SPARSE_WEIGHT: float = 0.3  # BM25
    RUNNER_METADATA_WEIGHT: float = 0.1  # doc_type / meta

    # Runner: классификационные пороги (для HybridClassifier Stage 8)
    CLASSIFICATION_L1_ACCEPT: float = 0.90
    CLASSIFICATION_L2_ACCEPT: float = 0.85
    CLASSIFICATION_L3_ACCEPT: float = 0.80
    CLASSIFICATION_L4_ACCEPT: float = 0.70
    CLASSIFICATION_VOTING_THRESHOLD: float = 0.75

    # Embeddings для Runner/Stage 8 (shared с L3-классификатором)
    RUNNER_EMBEDDINGS_ENABLED: bool = True
    RUNNER_EMBEDDINGS_MODEL: str = "intfloat/multilingual-e5-small"
    RUNNER_EMBEDDINGS_CACHE_DIR: str = ".cache/embeddings"

    # Playbooks / Prompts
    PLAYBOOK_DOCUMENT_TYPES_DIR: str = "playbooks/document_types"
    PLAYBOOK_DEFAULT_PATH: str = "playbooks/test/v1.0/playbook.yaml"
    PROMPTS_DIR: str = "prompts"

    # Порог уверенности rules, при котором LLM не вызывается.
    RULES_CONFIDENCE_THRESHOLD: float = 0.7
    CHECK_PASS_THRESHOLD: float = 0.6
    CHECK_UNCLEAR_THRESHOLD: float = 0.3

    # --- Aggregator & Exporter settings ---
    EXPORT_TOP_RISKS_COUNT: int = 20
    EXPORT_EVIDENCE_MAX_LENGTH: int = 300
    EXPORT_DD_REQUEST_DEDUP: bool = True
    EXPORT_DEFAULT_REQUESTER_ROLE: str = "deal_owner"

    # --- DD Request templates ---
    # "yaml" = load from playbooks/document_types/*.yaml (dd_request_templates section)
    # "builtin" = use hardcoded dict in aggregator.py
    EXPORT_DD_REQUEST_SOURCE: str = "yaml"

    # --- Structured data export ---
    EXPORT_STRUCTURED_DATA_ENABLED: bool = True  # Include structured_data fields in Excel
    EXPORT_CONDITIONAL_CHECKS_SHEET: bool = True  # Separate sheet for conditional check results
    EXPORT_CLASSIFICATION_METADATA: bool = True  # Include classification_level, confidence in grid

    # --- Classification API settings ---
    API_EXPOSE_YAML_METADATA: bool = True  # показывать метаданные YAML в ответах
    API_ALLOW_FORCE_RECLASSIFY: bool = True  # разрешать force_reclassify в /runs
    API_RECLASSIFY_BATCH_LIMIT: int = 50     # максимум документов в batch reclassify


    # --- Ops: Metrics & Regression ---
    METRICS_ENABLED: bool = True               # Включить сбор метрик
    METRICS_PREFIX: str = "mas_dd"             # Префикс всех метрик

    # Promotion Gate — пороги качества
    GATE_EVIDENCE_VALIDITY_MIN: float = 0.95    # Мин. доля FAIL/HIGH/CRITICAL с валидным evidence
    GATE_PRECISION_CRITICAL_MIN: float = 0.90   # Мин. precision для critical‑проверок
    GATE_RECALL_CRITICAL_MIN: float = 0.85      # Мин. recall для critical‑проверок
    GATE_UNCLEAR_RATE_MAX: float = 0.10         # Макс. доля UNCLEAR по critical‑чекам
    GATE_RETRIEVAL_HIT_RATE_MIN: float = 0.80   # Мин. доля попаданий evidence в топ‑5 retrieval
    GATE_F1_DELTA_MIN: float = -0.05            # Макс. допустимое падение F1 vs базовой версии

    # Пороги классификации для Promotion Gate
    GATE_CLASSIFICATION_ACCURACY_MIN: float = 0.90  # Мин. точность doc_type классификации
    GATE_YAML_COVERAGE_MIN: float = 0.70            # Мин. доля doc_type с YAML‑инструкцией
    GATE_LOW_CONFIDENCE_RATE_MAX: float = 0.15      # Макс. доля документов с conf < 0.6

    # Golden Dataset
    GOLDEN_DATASET_PATH: str = "golden_dataset"     # Путь к golden dataset



# Singleton: one settings instance for the whole application
settings = Settings()
