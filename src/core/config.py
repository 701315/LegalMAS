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


def _split_csv_config(raw_value: str | None) -> list[str]:
    """
    Разобрать comma-separated env setting в список непустых строк.

    Примеры:
      "http://a,http://b" -> ["http://a", "http://b"]
      "*"                 -> ["*"]
      "" / None           -> []
    """
    if raw_value is None:
        return []

    return [
        item.strip()
        for item in str(raw_value).split(",")
        if item and item.strip()
    ]

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
    MINIO_ENDPOINT: str = "127.0.0.1:9000"
    MINIO_PUBLIC_ENDPOINT: str | None = None  # <-- ДОБАВЛЕНО
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "Kesko-701315" # (Значение по умолчанию, перекроется из .env)
    MINIO_BUCKET: str = "mas-artifacts"
    MINIO_SECURE: bool = False

    # --- Application ---
    BASE_DIR: str = str(Path(__file__).resolve().parent.parent.parent)
    ENVIRONMENT: str = "development"

    # --- CORS ---
    #
    # Храним как comma-separated env strings, а не как Python list / JSON,
    # чтобы .env оставался простым и операционно удобным.
    #
    # Примеры:
    #   CORS_ALLOW_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
    #   CORS_ALLOW_METHODS=GET,POST,PUT,DELETE,OPTIONS
    #   CORS_ALLOW_HEADERS=Authorization,Content-Type
    #
    # ВАЖНО:
    # - при CORS_ALLOW_CREDENTIALS=true нельзя использовать origin "*";
    #   validator ниже блокирует такую конфигурацию fail-fast на старте.
    CORS_ALLOW_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: str = "*"
    CORS_ALLOW_HEADERS: str = "Accept,Accept-Language,Authorization,Content-Language,Content-Type,If-Match,If-None-Match,X-Request-ID"

    # --- Auth (JWT) ---
    # Секретный ключ для подписи JWT-токенов.
    # В production ОБЯЗАТЕЛЬНО заменить на случайную строку длиной >= 32 символов.
    # Генерация: python3 -c "import secrets; print(secrets.token_hex(32))"
    JWT_SECRET_KEY: str = "dev-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    # Время жизни access token в минутах.
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8  # 8 часов для dev

    LOG_LEVEL: str = "DEBUG"
    LOG_FORMAT: str = "console"
    LOG_TO_STDOUT: bool = True
    LOG_TO_FILE: bool = False
    LOG_FILE_DIR: str | None = None
    LOG_FILE_NAME: str = "app.log"
    LOG_FILE_MAX_BYTES: int = 20 * 1024 * 1024   # 20 MB
    LOG_FILE_BACKUP_COUNT: int = 10
    LLM_EXTRACTION_JSON_GRAMMAR_PATH: str | None = None

    # Дефолтный output budget для extraction LLM вызовов.
    # Может быть переопределён per-check через ExtractionConfig.llm_max_tokens.
    #
    # История изменений:
    # - 512 (устаревший): недостаточно для extraction V1.3 contract,
    #   который требует value+confidence+location для каждого поля.
    #   Даже простой check с 5-7 полями получал truncated JSON.
    # - 900 (текущий): безопасный baseline для большинства checks.
    #   Checks с 8+ полями обязаны задавать llm_max_tokens явно в YAML.
    LLM_EXTRACTION_MAX_TOKENS: int = 900

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
    IMPORT_ALLOWED_EXTENSIONS: str = ".pdf,.docx,.doc,.xlsx,.xls,.png,.jpg,.jpeg,.tiff,.tif"
    IMPORT_MAX_FILES_PER_BUNDLE: int = 10000

    # --- Extractor ---
    EXTRACTION_MIN_TEXT_LENGTH_PER_PAGE: int = 50
    EXTRACTION_OCR_QUARANTINE_THRESHOLD: float = 0.6
    EXTRACTION_HYBRID_MIN_OCR_RATE_FOR_QUARANTINE: float = 0.5
    EXTRACTION_OCR_DPI: int = 300
    EXTRACTION_MAX_PAGES: int = 500
    EXTRACTION_OCR_ENABLED: bool = True
    EXTRACTION_OCR_PROVIDER: str = "tesseract"
    # Поддерживаемые значения: "tesseract", "paddle"
    # paddle — stub, требует реализации PaddleOCRAdapter
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
    # Role mapping (PERSON_NAME → SELLER/BUYER/...) is an optional hint, disabled by default.
    # PII sanitization primary goal is privacy (PERSON → PERSONAMEn), not legal role assignment.
    # Legal role resolution belongs to downstream semantic analysis (classification/enrichment).
    # Enable explicitly only when applicable_triggers are present AND role hints are needed.
    PII_PRESERVE_PARTY_ROLES: bool = False
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

    # Default LLM provider. Поддерживаемые значения: ollama | openai | llamacpp.
    # llamacpp — legacy embedded provider, оставлен для backward compatibility.
    LLM_PROVIDER: str = "ollama"

    LLM_TIMEOUT_SECONDS: int = 3600
    LLM_TEMPERATURE: float = 0.0
    LLM_MAX_TOKENS: int = 256

    LLM_OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    LLM_OPENAI_API_KEY: str = ""
    LLM_OPENAI_MODEL: str = "gpt-4o-mini"

    LLM_OLLAMA_BASE_URL: str = "http://localhost:11434"
    LLM_OLLAMA_MODEL: str = "llama3.1"

    # Path к gguf файлу — используется ТОЛЬКО когда LLM_PROVIDER=llamacpp.
    # Пустой default чтобы случайная попытка загрузить gguf при ollama path
    # давала явную ошибку конфигурации, а не падала по несуществующему пути.
    LLM_LOCAL_MODEL_PATH: str = ""

    # Контекстное окно — источник истины для llamacpp.
    # LLM_CONTEXT_LIMIT синхронизируется с этим значением через @model_validator.
    LLM_LOCAL_N_CTX: int = 8192
    LLM_LOCAL_N_GPU_LAYERS: int = 0

    # Default context window для LLMClient._compute_token_budget().
    # Для llamacpp авто-синхронизируется с LLM_LOCAL_N_CTX (см. _sync_llm_context_limit).
    # Для ollama path можно поднимать до n_ctx модели (qwen2.5 — до 32768).
    LLM_CONTEXT_LIMIT: int = 32768

    LLM_SAFETY_MARGIN_TOKENS: int = 512
    LLM_MIN_OUTPUT_TOKENS: int = 64

    LLM_CLOUD_MODEL: str = "gpt-4o-mini"
    LLM_CLOUD_API_KEY: str = ""
    LLM_DEFAULT_CONFIDENCE: float = 0.70

    # ---------------------------------------------------------------------------
    # --- LLM Retry & Backoff ---
    #
    # LLM_MAX_RETRIES — максимальное число повторных попыток при TransientError.
    #   0 = без повторов (один вызов).
    #   2 = до 3 вызовов итого: первый + 2 retry.
    #
    #   ВАЖНО: ранее это значение читалось через getattr(settings, "LLM_MAX_RETRIES", 2),
    #   что делало его "phantom setting" — Pydantic не знал о поле, значение из .env
    #   молча игнорировалось. Теперь это полноценный typed field.
    #
    # LLM_RETRY_BASE_DELAY_SECONDS — базовая задержка перед первым retry.
    #   Формула задержки: min(base * 2^(attempt-1), cap) + jitter
    #   attempt=1 → base * 1 = base
    #   attempt=2 → base * 2
    #   attempt=3 → base * 4  (но не более cap)
    #
    # LLM_RETRY_MAX_DELAY_SECONDS — потолок задержки.
    #   Защищает от бесконечного ожидания при большом числе retry.
    #   Рекомендации по провайдерам:
    #     openai:   30s — rate limit window обычно 60s, 30s даёт второй шанс
    #     ollama:   15s — локальный сервис восстанавливается быстро
    #     llamacpp: 60s — CPU inference занимает долго, пауза оправдана
    #
    # LLM_RETRY_JITTER_SECONDS — максимальный случайный сдвиг задержки.
    #   Защита от thundering herd: когда N Celery-воркеров одновременно
    #   получают TransientError (например, Ollama перезапускается), они
    #   не должны синхронно retry-ть через одинаковые интервалы.
    #   Jitter разбрасывает retry во времени.
    #   Значение 1.0 означает uniform(0, 1.0) секунды добавляется к задержке.
    # ---------------------------------------------------------------------------
    LLM_MAX_RETRIES: int = 2
    LLM_RETRY_BASE_DELAY_SECONDS: float = 1.0
    LLM_RETRY_MAX_DELAY_SECONDS: float = 30.0
    LLM_RETRY_JITTER_SECONDS: float = 1.0


    # --- Structure LLM Refiner ---
    STRUCTURE_ENABLE_LLM_REFINER: bool = True

    # Structure refiner LLM provider. Поддерживаемые значения:
    # ollama | local | local_endpoint (все три = Ollama-compatible HTTP API).
    STRUCTURE_LLM_PROVIDER: str = "ollama"

    # Имя модели в Ollama для structure refiner. Должно быть валидным именем
    # из `ollama list`. Пустой default чтобы заставить explicit configuration.
    STRUCTURE_LLM_MODEL: str = ""
    
    STRUCTURE_LLM_TIMEOUT_SECONDS: int = 20
    STRUCTURE_LLM_MAX_AMBIGUOUS_PER_DOC: int = 8
    STRUCTURE_LLM_MIN_CONFIDENCE: float = 0.80
    STRUCTURE_LLM_MAX_CONTEXT_CHARS: int = 1200
    STRUCTURE_LLM_SHADOW_MODE: bool = False

    # --- Semantic Enrichment (Phase 12) ---
    SEMANTIC_ENRICHMENT_ENABLED: bool = True   # чтобы отключить для тестов надо сменить на False.
    # Отдельный порог для unit_type — строже чем для clause_function.
    # unit_type является semantic identity юнита и влияет на routing
    # в retrieval и checks pipeline. Ошибка системная, поэтому 0.80.
    SEMANTIC_ENRICHMENT_MIN_CONFIDENCE_FILL_UNIT_TYPE: float = 0.80
    SEMANTIC_ENRICHMENT_MIN_CONFIDENCE_FILL: float = 0.72
    SEMANTIC_ENRICHMENT_MIN_CONFIDENCE_TOPICS: float = 0.72
    SEMANTIC_ENRICHMENT_MIN_CONFIDENCE_OVERRIDE: float = 0.92
    SEMANTIC_ENRICHMENT_ALLOW_OVERRIDE_TYPE: bool = False
    SEMANTIC_ENRICHMENT_ALLOW_OVERRIDE_FUNCTION: bool = False
    SEMANTIC_ENRICHMENT_ALLOW_ADD_TOPICS: bool = True
    SEMANTIC_ENRICHMENT_MAX_TOPICS_FROM_LLM: int = 8
    SEMANTIC_ENRICHMENT_MIN_TEXT_CHARS: int = 40

# --- Semantic Enrichment Runtime Budget ---

    # Per-segment hard timeout.
    # CPU-only Ollama (Qwen2.5 7B Q4_K_M): ~47 eligible units × ~300s/unit = ~14100s.
    # 3 hours gives reasonable coverage without blocking pipeline indefinitely.
    SEMANTIC_ENRICHMENT_SEGMENT_TIMEOUT_SECONDS: int = 10800  # было: 900

    SEMANTIC_ENRICHMENT_MAX_INFLIGHT_LLM_CALLS: int = 1  # было: 4
    # CPU-only: параллелизм не даёт выигрыша, только конкуренция за RAM/CPU.
    # GPU: можно поднять до 4.

    # Minimum timeout in seconds for primary segment enrichment.
    SEMANTIC_ENRICHMENT_PRIMARY_SEGMENT_MIN_TIMEOUT_SECONDS: int = 600  # без изменений

    # Total wall-clock budget for enriching all segments of a document.
    # 0 = derive adaptively from worker soft limit minus cleanup margin.
    # Explicit value must be < SEMANTIC_ENRICHMENT_WORKER_SOFT_TIME_LIMIT_SECONDS.
    SEMANTIC_ENRICHMENT_DOCUMENT_BUDGET_SECONDS: int = 14400  # было: 3600

    # Time reserved for post-enrichment commit / audit / retrigger.
    SEMANTIC_ENRICHMENT_CLEANUP_MARGIN_SECONDS: int = 120  # без изменений

    # Per-unit timeout for semantic enrichment LLM calls.
    #
    # 0 = adaptive:
    #   timeout = segment_timeout / max(eligible_unit_count, 1),
    #   floor = SEMANTIC_ENRICHMENT_PER_UNIT_MIN_TIMEOUT_SECONDS.
    #   Recommended for GPU inference where per-unit latency is low and
    #   fair budget distribution matters more than absolute cap.
    #
    # > 0 = explicit fixed cap per unit.
    #   Recommended for CPU-only inference where prompt eval alone takes
    #   200-300s per unit regardless of budget arithmetic.
    #   Example: CPU Qwen2.5 7B Q4_K_M → set 360.
    SEMANTIC_ENRICHMENT_PER_UNIT_TIMEOUT_SECONDS: int = 360  # было: 0

    # Absolute minimum per-unit timeout regardless of budget arithmetic.
    # Used only when PER_UNIT_TIMEOUT_SECONDS=0 (adaptive mode).
    SEMANTIC_ENRICHMENT_PER_UNIT_MIN_TIMEOUT_SECONDS: int = 180  # было: 30

    # --- Dedicated Semantic Enrichment Worker Limits ---
    # hard > soft > doc_budget + margin (validator enforces this)
    SEMANTIC_ENRICHMENT_WORKER_SOFT_TIME_LIMIT_SECONDS: int = 16200  # было: 4200
    SEMANTIC_ENRICHMENT_WORKER_TIME_LIMIT_SECONDS: int = 16500       # было: 4320

    # --- Semantic Enrichment Cache (Phase 14.3.A) ---
    # Exact-match cache для raw LLM responses.
    # Scope: document_version-scoped. Process-local, in-memory.
    # Включён по умолчанию — критично для CPU inference где retry дорог.
    SEMANTIC_ENRICHMENT_CACHE_ENABLED: bool = True   # было: False
    SEMANTIC_ENRICHMENT_CACHE_TTL_SECONDS: int = 86400
    SEMANTIC_ENRICHMENT_CACHE_MAX_ITEMS: int = 10000


    # --- Embedding Recovery (Phase 13.4) ---
    RECOVERY_EMBEDDING_ENABLED: bool = True
    RECOVERY_EMBEDDING_SIMILARITY_THRESHOLD: float = 0.72
    RECOVERY_EMBEDDING_MAX_PAGE_DISTANCE: int = 3
    RECOVERY_EMBEDDING_MAX_LEVEL_DELTA: int = 2

    # --- Embedding Vector Cache (Phase 14.3.B) ---
    # Process-local in-memory cache для embedding vectors.
    # Ускоряет повторные encode() при reprocessing / retries / benchmark.
    # По умолчанию выключен.
    EMBEDDING_CACHE_ENABLED: bool = False
    EMBEDDING_CACHE_TTL_SECONDS: int = 86400
    EMBEDDING_CACHE_MAX_ITEMS: int = 50000


    # --- Drift Detection (Phase 13.2) ---
    DRIFT_ORPHAN_RATIO_WARNING: float = 0.15
    DRIFT_ORPHAN_RATIO_CRITICAL: float = 0.35
    DRIFT_GRAMMAR_VIOLATION_RATIO_WARNING: float = 0.15
    DRIFT_GRAMMAR_VIOLATION_RATIO_CRITICAL: float = 0.30
    DRIFT_RETRIEVAL_SAFETY_SCORE_WARNING: float = 0.60
    DRIFT_RETRIEVAL_SAFETY_SCORE_CRITICAL: float = 0.40
    DRIFT_ENRICHMENT_APPLIED_RATIO_WARNING: float = 0.50
    DRIFT_ENRICHMENT_APPLIED_RATIO_CRITICAL: float = 0.20
    DRIFT_ENRICHMENT_FAILED_WARNING: int = 1
    DRIFT_ENRICHMENT_FAILED_CRITICAL: int = 3
    DRIFT_ALERT_ON_ANY_DEGRADED: bool = True
    DRIFT_ALERT_ON_LLM_UNAVAILABLE: bool = True
    DRIFT_ALERT_ON_OVERALL_RETRIEVAL_UNSAFE: bool = True


    # --- Dedup & Relations ---
    DEDUP_EXACT_ENABLED: bool = True
    RELATIONS_FILENAME_ENABLED: bool = True
    RELATIONS_TEXT_ENABLED: bool = True
    RELATIONS_FILENAME_SIMILARITY_THRESHOLD: int = 75
    RELATIONS_MAX_HOPS: int = 2
    RELATIONS_MAX_FAMILY_SIZE: int = 20

    FAMILY_MASTER_DOC_TYPES: list[str] = [
        "SPA",
        "SHA",
        "Loan",
        "RealEstate",
        "ServiceAgreement",
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

    # Structural early-document retrieval prior.
    # Applied when chunk position_ratio <= RUNNER_METADATA_EARLY_DOC_POSITION_THRESHOLD.
    # Replaces mid-document boost logic that caused Definitional Drift.
    # Universal invariant: legal documents open with identification clauses
    # (parties, subject, recitals) regardless of language or document type.
    RUNNER_METADATA_EARLY_DOC_BOOST: float = 0.2
    RUNNER_METADATA_EARLY_DOC_POSITION_THRESHOLD: float = 0.15

    RUNNER_METADATA_PATH_TITLES_BOOST: float = 0.5
    RUNNER_METADATA_SUMMARY_BOOST: float = 0.2

    RUNNER_METADATA_PREAMBLE_BOOST: float = 1.0
    RUNNER_METADATA_TOPIC_MATCH_BOOST: float = 0.6
    RUNNER_METADATA_TOPIC_SUPPORTING_BOOST: float = 0.3

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

    # ── Monitoring URLs (admin / observability) ──────────────────────────────
    # Internal URLs — backend ходит по ним к локальным сервисам внутри контура.
    # В dev задаются в .env, в demo — свои значения в /srv/steloom-demo/.env.
    PROMETHEUS_INTERNAL_URL: str = "http://127.0.0.1:9090"
    LOKI_INTERNAL_URL: str = "http://127.0.0.1:3100"
    ALERTMANAGER_INTERNAL_URL: str = "http://127.0.0.1:9093"

    # External URLs — открываются в браузере из admin UI.
    # Могут отличаться от internal в reverse-proxy / multi-contour deployment.
    GRAFANA_EXTERNAL_URL: str = "http://localhost:3000"
    PROMETHEUS_EXTERNAL_URL: str = "http://localhost:9090"
    ALERTMANAGER_EXTERNAL_URL: str = "http://localhost:9093"
    LOKI_EXTERNAL_URL: str = "http://localhost:3100"
    TEMPO_EXTERNAL_URL: str = "http://localhost:3200"
    MINIO_CONSOLE_EXTERNAL_URL: str = "http://localhost:9001"
    API_DOCS_EXTERNAL_URL: str = "http://localhost:8000/docs"
    OLLAMA_EXTERNAL_URL: str = "http://localhost:11434"
    
    
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
    # --- OpenTelemetry / Distributed Tracing ---
    #
    # Простым языком:
    # Эти настройки управляют системой трейсинга — записью "путей запросов".
    #
    # OTEL_ENABLED — главный рубильник. False = трейсинг полностью выключен,
    #   система работает точно как раньше, никакой дополнительной нагрузки.
    #
    # OTEL_SERVICE_NAME — имя нашего сервиса в трейсах. По этому имени
    #   в Grafana можно фильтровать трейсы именно от нашего API.
    #   Используем "legalmas-api" чтобы совпадало с именованием в метриках.
    #
    # OTEL_EXPORTER_OTLP_ENDPOINT — адрес куда отправлять трейсы.
    #   Backend работает на host-машине, Tempo в Docker.
    #   127.0.0.1:4318 — это порт Tempo, доступный с host-машины.
    #   /v1/traces — стандартный путь OTLP HTTP endpoint.
    #
    # OTEL_TRACES_SAMPLER — стратегия выборки трейсов:
    #   parentbased_traceidratio — умная стратегия:
    #     * если запрос пришёл с уже существующим trace_id (например от gateway),
    #       то решение о sampling принимается на основе родительского решения;
    #     * если запрос новый — применяется OTEL_TRACES_SAMPLER_ARG как вероятность.
    #
    # OTEL_TRACES_SAMPLER_ARG — вероятность записи трейса (0.0 — 1.0):
    #   1.0 = записывать 100% запросов (dev/local — видим всё).
    #   0.1 = записывать 10% (production — экономим место и CPU).
    #
    # TEMPO_EXTERNAL_URL — адрес Tempo для отображения в admin panel.
    #   Аналогично GRAFANA_EXTERNAL_URL и PROMETHEUS_EXTERNAL_URL.
    # ---------------------------------------------------------------------------

    # Главный рубильник трейсинга.
    # Установите OTEL_ENABLED=true в .env чтобы включить трейсинг.
    OTEL_ENABLED: bool = False

    # Имя сервиса в трейсах — так наш API будет виден в Grafana/Tempo.
    OTEL_SERVICE_NAME: str = "legalmas-api"

    # Адрес OTLP HTTP endpoint Tempo.
    # Backend на host → Tempo в Docker → 127.0.0.1:4318 доступен с host.
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://127.0.0.1:4318/v1/traces"

    # Стратегия выборки трейсов.
    # parentbased_traceidratio — умная выборка с учётом родительского span.
    OTEL_TRACES_SAMPLER: str = "parentbased_traceidratio"

    # Вероятность записи трейса: 1.0 = 100% для dev, снижайте в production.
    OTEL_TRACES_SAMPLER_ARG: float = 1.0

    # ---------------------------------------------------------------------------
    # Список "шумных" Celery задач, для которых НЕ создаётся span в Tempo.
    #
    # Простым языком:
    # Некоторые задачи запускаются очень часто (каждые 5 секунд / 10 минут)
    # и не несут бизнес-ценности в трейсинге. Их traces заполняют Tempo и
    # мешают искать реальные бизнес-traces.
    #
    # Формат: строка с именами задач через запятую.
    # Пример в .env:
    #   OTEL_NOISY_TASKS=workers.outbox_dispatcher,workers.reap_stale_stage_executions
    #
    # Пустая строка = фильтрация выключена, все задачи трейсятся.
    #
    # Важно:
    # - задачи из этого списка НЕ получают span в Tempo
    # - их логи продолжают работать нормально
    # - их метрики продолжают работать нормально
    # - если задача упала — ошибка видна в логах (не в Tempo)
    # ---------------------------------------------------------------------------
    OTEL_NOISY_TASKS: str = (
        "workers.outbox_dispatcher,"
        "workers.reap_stale_stage_executions"
    )
    
    @property
    def cors_allow_origins_list(self) -> list[str]:
        """
        CORS origins из comma-separated env в список строк.

        Пример:
          "http://a,http://b" -> ["http://a", "http://b"]
        """
        return _split_csv_config(self.CORS_ALLOW_ORIGINS)

    @property
    def cors_allow_methods_list(self) -> list[str]:
        """
        CORS methods из comma-separated env в список строк.

        Нормализуем HTTP methods к upper-case, кроме wildcard "*".
        """
        values = _split_csv_config(self.CORS_ALLOW_METHODS)
        return [value if value == "*" else value.upper() for value in values]

    @property
    def cors_allow_headers_list(self) -> list[str]:
        """
        CORS headers из comma-separated env в список строк.

        Сохраняем исходный регистр заголовков — это безопаснее для
        операторов и читабельнее в конфигурации.
        """
        return _split_csv_config(self.CORS_ALLOW_HEADERS)
    
    # ---------------------------------------------------------------------------
    # --- Validators ---
    # ---------------------------------------------------------------------------

    @model_validator(mode="after")
    def _validate_cors_settings(self) -> "Settings":
        """
        Validate CORS configuration at startup.

        Инварианты:
        - origins/methods/headers не должны быть пустыми;
        - при allow_credentials=true origin "*" запрещён:
          это небезопасная и фактически невалидная browser-конфигурация.
        """
        origins = self.cors_allow_origins_list
        methods = self.cors_allow_methods_list
        headers = self.cors_allow_headers_list

        if not origins:
            raise ValueError(
                "CORS_ALLOW_ORIGINS must contain at least one origin"
            )

        if not methods:
            raise ValueError(
                "CORS_ALLOW_METHODS must contain at least one method or '*'"
            )

        if not headers:
            raise ValueError(
                "CORS_ALLOW_HEADERS must contain at least one header or '*'"
            )

        if self.CORS_ALLOW_CREDENTIALS and "*" in origins:
            raise ValueError(
                "CORS_ALLOW_ORIGINS cannot contain '*' when "
                "CORS_ALLOW_CREDENTIALS=true"
            )

        return self
    
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


    @model_validator(mode="after")
    def _validate_semantic_enrichment_limits(self) -> "Settings":
        """
        Validate semantic enrichment runtime configuration at startup.

        Invariants enforced:
        - worker hard limit > worker soft limit (gap for cleanup)
        - cleanup margin < worker soft limit
        - if document budget is explicit, it must be < worker soft limit
        - segment timeout must be positive
        """
        soft = self.SEMANTIC_ENRICHMENT_WORKER_SOFT_TIME_LIMIT_SECONDS
        hard = self.SEMANTIC_ENRICHMENT_WORKER_TIME_LIMIT_SECONDS
        margin = self.SEMANTIC_ENRICHMENT_CLEANUP_MARGIN_SECONDS
        doc_budget = self.SEMANTIC_ENRICHMENT_DOCUMENT_BUDGET_SECONDS
        seg_timeout = self.SEMANTIC_ENRICHMENT_SEGMENT_TIMEOUT_SECONDS

        if hard <= soft:
            raise ValueError(
                f"SEMANTIC_ENRICHMENT_WORKER_TIME_LIMIT_SECONDS ({hard}) "
                f"must be greater than SEMANTIC_ENRICHMENT_WORKER_SOFT_TIME_LIMIT_SECONDS ({soft})"
            )
        if margin >= soft:
            raise ValueError(
                f"SEMANTIC_ENRICHMENT_CLEANUP_MARGIN_SECONDS ({margin}) "
                f"must be less than SEMANTIC_ENRICHMENT_WORKER_SOFT_TIME_LIMIT_SECONDS ({soft})"
            )
        if doc_budget > 0 and doc_budget >= soft:
            raise ValueError(
                f"SEMANTIC_ENRICHMENT_DOCUMENT_BUDGET_SECONDS ({doc_budget}) "
                f"must be less than SEMANTIC_ENRICHMENT_WORKER_SOFT_TIME_LIMIT_SECONDS ({soft})"
            )
        if seg_timeout <= 0:
            raise ValueError(
                f"SEMANTIC_ENRICHMENT_SEGMENT_TIMEOUT_SECONDS ({seg_timeout}) must be positive"
            )
        return self

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> "Settings":
        """
        Блокирует запуск с небезопасными дефолтами в production.
        """
        if self.ENVIRONMENT != "production":
            return self

        insecure: list[str] = []

        # 1. PII Key (Находка №1)
        if not self.PII_ENCRYPTION_KEY or len(self.PII_ENCRYPTION_KEY) < 16:
            insecure.append("PII_ENCRYPTION_KEY is missing or too short (min 16 chars)")

        # 2. JWT Secret (Находка №4)
        if self.JWT_SECRET_KEY == "dev-secret-key-change-in-production":
            insecure.append("JWT_SECRET_KEY is set to insecure default value")

        # 3. MinIO Secret (Находка №4)
        if self.MINIO_SECRET_KEY == "minioadmin123":
            insecure.append("MINIO_SECRET_KEY is set to insecure default value")

        # 4. Database Password (NEW)
        if "mas_dev_password" in self.DATABASE_URL:
            insecure.append("DATABASE_URL contains default development password")

        # 5. Localhost check for Prod (NEW)
        if "localhost" in self.DATABASE_URL or "127.0.0.1" in self.DATABASE_URL:
            _config_logger.warning("DATABASE_URL points to localhost in production mode!")

        if insecure:
            raise ValueError(
                "CRITICAL: Insecure configuration detected for ENVIRONMENT=production:\n"
                + "\n".join(f"  - {msg}" for msg in insecure)
            )

        return self

    @property
    def CELERY_BROKER_VISIBILITY_TIMEOUT(self) -> int:
        """
        СИСТЕМНЫЙ ФИКС (Находка №6): 
        Таймаут видимости брокера должен быть больше самой длинной задачи LLM,
        иначе Celery решит, что воркер упал, и запустит задачу повторно.
        """
        # Берем лимит самой долгой стадии (Semantic Enrichment) + 5 минут запаса
        return self.SEMANTIC_ENRICHMENT_WORKER_TIME_LIMIT_SECONDS + 300



# Singleton
settings = Settings()
