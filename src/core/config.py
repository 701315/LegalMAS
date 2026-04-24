# src/core/config.py


"""
Application configuration.
Loads settings from environment variables / .env file.
"""

from pathlib import Path
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
    BASE_DIR: str = str(Path(__file__).resolve().parent.parent.parent)
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "DEBUG"
    LOG_FORMAT: str = "console"  # "console" for dev, "json" for production
    LLM_EXTRACTION_JSON_GRAMMAR_PATH: str | None = None

    # --- Classification & Embeddings (общие) ---
    EMBEDDINGS_MODEL: str = "intfloat/multilingual-e5-large"
    CLASSIFICATION_REGISTRY_PATH: str = "playbooks/document_types/registry.yaml"

    # --- LLM Providers (общий верхнеуровневый) ---
    # Эти ключи можно использовать в других частях системы, если понадобится.
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
    # CLASSIFIER_REGISTRY_PATH уже задан выше и используется Import Worker'ом.

    # --- Extractor (Stage 4) ---
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

    # --- PII Sanitization (Stage 5) ---
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
    STRUCTURE_ENABLE_SEGMENTATION: bool = False  # feature-flag для multi-doc pipeline
    STRUCTURE_STORE_FILE_GRAPH: bool = True   # v2 pipeline: file_graph + segment trees
    ALLOW_LEGACY_LAYOUT_FALLBACK: bool = False  # не нужен в v2-only режиме
    STRUCTURE_STORE_SEGMENT_TREES: bool = True    # сохранять segment_* trees (если STORE_FILE_GRAPH=True)

    # --- Chunks / CHUNKS v2 (Stage 6.5) ---
    # Управляет тем, какой режим chunking используется:
    # - False: legacy CHUNKS v1 (один chunks.json на файл, schema_version=1);
    # - True: CHUNKS v2 (per-segment snapshots + file-level manifest).
    CHUNKS_V2_ENABLED: bool = True   # v2-only pipeline: per-segment snapshots + manifest

    # --- Classifier (Stage 6) ---
    CLASSIFIER_L1_WEIGHT: float = 0.20  # L1 — слабый hint, не финальный вердикт
    CLASSIFIER_L2_ACCEPT_THRESHOLD: float = 0.85
    CLASSIFIER_L3_ACCEPT_THRESHOLD: float = 0.80
    CLASSIFIER_VOTING_THRESHOLD: float = 0.75
    CLASSIFIER_UNCERTAIN_THRESHOLD: float = 0.50
    CLASSIFIER_EMBEDDINGS_MODEL: str = "intfloat/multilingual-e5-small"  # L3
    CLASSIFIER_REGISTRY_PATH: str = "playbooks/document_types"

    # --- LLM Provider (Stage 6/8 L4) ---
    # Базовый провайдер LLM для Stage 6/8:
    #   "none"    — LLM полностью выключен.
    #   "openai"  — OpenAI-совместимый HTTP API (опция).
    #   "ollama"  — локальный сервер Ollama (опция).
    #   "llamacpp" — локальная GGUF-модель (наша базовая конфигурация).
    LLM_PROVIDER: str = "llamacpp"

    # Общие настройки для всех провайдеров.
    # Время ожидания ответа от LLM в секундах.
    LLM_TIMEOUT_SECONDS: int = 3600
    # Температура выборки (0.0 — максимально детерминированный ответ).
    LLM_TEMPERATURE: float = 0.0
    # Максимальное количество токенов, которое модель может сгенерировать в ответе.
    LLM_MAX_TOKENS: int = 512

    # --- OpenAI‑совместимый провайдер ("openai") — опционально ---
    LLM_OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    LLM_OPENAI_API_KEY: str = ""
    LLM_OPENAI_MODEL: str = "gpt-4o-mini"

    # --- Локальный провайдер Ollama ("ollama") — опционально ---
    LLM_OLLAMA_BASE_URL: str = "http://localhost:11434"
    LLM_OLLAMA_MODEL: str = "llama3.1"

    # --- Локальный провайдер llama-cpp ("llamacpp") — базовый ---
    # Путь к локальному GGUF-файлу модели.
    # Важно: используем Windows-путь по умолчанию, но в коде он нормализуется
    # (обратные слэши меняются на прямые), чтобы работало и под WSL/Linux.
    LLM_LOCAL_MODEL_PATH: str = r"C:\LegalMAS\LLMmodel\model.gguf"

    # Контекстное окно и слои для CPU/GPU при использовании llama-cpp.
    LLM_LOCAL_N_CTX: int = 4096
    LLM_LOCAL_N_GPU_LAYERS: int = 0  # 0 = CPU only, >0 = GPU offload

    # --- LLM: контроль контекстного окна ---
    # Максимальный размер контекстного окна модели в токенах.
    # Для llamacpp должен совпадать с LLM_LOCAL_N_CTX.
    # Если None или 0 — бюджетная проверка отключена (небезопасно для llamacpp).
    LLM_CONTEXT_LIMIT: int = 4096

    # Запас токенов между концом промпта и концом окна.
    # Компенсирует неточность подсчёта токенов и системные overhead'ы модели.
    LLM_SAFETY_MARGIN_TOKENS: int = 256

    # Минимальный бюджет под ответ. Если после промпта остаётся меньше —
    # вызов блокируется с LLMContextLimitError.
    LLM_MIN_OUTPUT_TOKENS: int = 64

    # Старые "облачные" поля оставляем для совместимости (если где-то ещё используются).
    LLM_CLOUD_MODEL: str = "gpt-4o-mini"
    LLM_CLOUD_API_KEY: str = ""

    # Structure LLM Refiner
    STRUCTURE_ENABLE_LLM_REFINER: bool = True
    STRUCTURE_LLM_PROVIDER: str = "llamacpp"
    STRUCTURE_LLM_MODEL: str = "..."
    STRUCTURE_LLM_TIMEOUT_SECONDS: int = 20
    STRUCTURE_LLM_MAX_AMBIGUOUS_PER_DOC: int = 8
    STRUCTURE_LLM_MIN_CONFIDENCE: float = 0.80
    STRUCTURE_LLM_MAX_CONTEXT_CHARS: int = 1200
    STRUCTURE_LLM_SHADOW_MODE: bool = False

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

    # Runner: metadata-boost для RetrievalEngine
    # Для непрофессионального программиста:
    # - Эти коэффициенты задают, насколько сильно влияют разные метаданные
    #   (тип чанка, заголовки, позиция в документе, summary) на итоговый score.
    # - Их можно тюнить через переменные окружения без изменения кода.
    RUNNER_METADATA_KIND_BONUS_SUBCLAUSE: float = 0.3
    RUNNER_METADATA_KIND_PENALTY_SECTION: float = 0.1
    RUNNER_METADATA_SECTION_TITLE_BOOST: float = 1.0
    RUNNER_METADATA_POSITION_MID_BOOST: float = 0.3
    RUNNER_METADATA_PATH_TITLES_BOOST: float = 0.5
    RUNNER_METADATA_SUMMARY_BOOST: float = 0.2

    # Runner: режим выбора проверок
    #   "global_and_doc_type" — глобальный плейбук + doc-type YAML
    #   "global_only"         — только глобальный плейбук
    #   "doc_type_only"       — только doc-type YAML
    CHECK_RUNNER_MODE: str = "global_and_doc_type"

    # Runner: классификационные пороги (для HybridClassifier Stage 8)
    CLASSIFICATION_L1_ACCEPT: float = 0.90
    CLASSIFICATION_L2_ACCEPT: float = 0.85
    CLASSIFICATION_L3_ACCEPT: float = 0.80
    CLASSIFICATION_L4_ACCEPT: float = 0.70
    CLASSIFICATION_VOTING_THRESHOLD: float = 0.75

    # Дополнительные пороги для HybridClassifier (Stage 8)
    CLASSIFICATION_HYBRID_ACCEPT: float = 0.65
    CLASSIFICATION_UNKNOWN_MAX: float = 0.40
    CLASSIFICATION_L2_EXCL_HARD: int = 2
    CLASSIFICATION_L2_STRONG: float = 0.85
    CLASSIFICATION_L1_STRONG: float = 0.90

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
    EXPORT_DD_REQUEST_SOURCE: str = "yaml"

    # --- Structured data export ---
    EXPORT_STRUCTURED_DATA_ENABLED: bool = True
    EXPORT_CONDITIONAL_CHECKS_SHEET: bool = True
    EXPORT_CLASSIFICATION_METADATA: bool = True

    # --- Classification API settings ---
    API_EXPOSE_YAML_METADATA: bool = True
    API_ALLOW_FORCE_RECLASSIFY: bool = True
    API_RECLASSIFY_BATCH_LIMIT: int = 50

    # --- Ops: Metrics & Regression ---
    METRICS_ENABLED: bool = True
    METRICS_PREFIX: str = "mas_dd"

    # Promotion Gate — пороги качества
    GATE_EVIDENCE_VALIDITY_MIN: float = 0.95
    GATE_PRECISION_CRITICAL_MIN: float = 0.90
    GATE_RECALL_CRITICAL_MIN: float = 0.85
    GATE_UNCLEAR_RATE_MAX: float = 0.10
    GATE_RETRIEVAL_HIT_RATE_MIN: float = 0.80
    GATE_F1_DELTA_MIN: float = -0.05

    # Пороги классификации для Promotion Gate
    GATE_CLASSIFICATION_ACCURACY_MIN: float = 0.90
    GATE_YAML_COVERAGE_MIN: float = 0.70
    GATE_LOW_CONFIDENCE_RATE_MAX: float = 0.15

    # Golden Dataset
    GOLDEN_DATASET_PATH: str = "golden_dataset"

    # --- Celery worker runtime topology ---
    CELERY_DEFAULT_WORKER_CONCURRENCY: int = 4
    CELERY_HEAVY_WORKER_CONCURRENCY: int = 1




# Singleton: one settings instance for the whole application
settings = Settings()

