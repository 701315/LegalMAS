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

    # --- PII ---
    PII_ENCRYPTION_KEY: str = "dev-encryption-key-change-in-production"

    # --- Classification & Embeddings ---
    EMBEDDINGS_MODEL: str = "intfloat/multilingual-e5-large"
    CLASSIFICATION_REGISTRY_PATH: str = "playbooks/document_types/registry.yaml"

    # --- LLM Providers ---
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    LOCAL_LLM_ENDPOINT: str = "http://localhost:11434"

    # --- Circuit Breaker ---
    CIRCUIT_BREAKER_THRESHOLD: int = 5
    CIRCUIT_BREAKER_TIMEOUT: int = 60

    # Import Worker ---
    IMPORT_MAX_FILE_SIZE_MB: int = 200
    # Максимальный размер одного файла в мегабайтах
    # Import Worker использует folder_path из структуры ZIP (например, 02. Contracts/SPA/)
    # как сигнал предварительной классификации — эта информация сохраняется в
    # Document.folder_path и впоследствии используется L1-классификатором для folder_patterns
    # из YAML-реестра

    IMPORT_ALLOWED_EXTENSIONS: str = ".pdf,.docx,.doc,.xlsx,.xls,.png,.jpg,.jpeg,.tiff,.tif"
    # Разрешённые расширения файлов через запятую

    IMPORT_MAX_FILES_PER_BUNDLE: int = 10000
    # Максимальное количество файлов в одном ZIP-пакете

    #  Registry path (используется Classifier) ---
    CLASSIFIER_REGISTRY_PATH: str = "playbooks/document_types"
    # Путь к YAML-реестру типов документов.
    # Устанавливается уже здесь, т.к. Import Worker на шаге folder_path-разбора
    # может использовать folder_patterns из реестра для предварительной маршрутизации.
    # Читается Classifier'ом (Stage 6), но путь объявляется глобально.

    # --- Stage 4: Extractor ---
    EXTRACTION_MIN_TEXT_LENGTH_PER_PAGE: int = 50
    # Символов на странице ниже этого → стратегия OCR

    EXTRACTION_OCR_QUARANTINE_THRESHOLD: float = 0.6
    # Средняя OCR-уверенность ниже → документ в карантин

    EXTRACTION_OCR_DPI: int = 300
    # DPI при конвертации страниц в изображения для OCR

    EXTRACTION_MAX_PAGES: int = 500
    # Максимум страниц в одном документе

    EXTRACTION_OCR_ENABLED: bool = True
    # False → отключить OCR полностью, только pdfplumber

    # --- Stage 4: Element enrichment для Classifier/Structure Builder ---
    EXTRACTION_ENRICH_ELEMENT_TYPES: bool = True
    # True → классифицировать каждый элемент как heading/text/listitem
    # Используется на Этапах 6 (Structure Builder) и 7 (Dedup)
    # Добавлен флаг EXTRACTION_ENRICH_ELEMENT_TYPES. Structure Builder (Этап 6)
    # использует element.type для разбиения на clause_uid, классификатор L2 (Этап 6)
    # — первые 1500 символов elements. Обогащение типов критично для качества обоих.

    # --- Testing / Integration ---
    DISABLE_DOWNSTREAM_TASKS: bool = False
    # True → отключить запуск downstream-тасок (PII Sanitizer, Structure Builder и т.д.)
    # из воркеров для изолированного тестирования отдельных стадий pipeline.
    # Используется в интеграционных тестах.

    # PII Sanitization settings (Stage 5)

    # --- PII Sanitization (Stage 5) ---
    PII_ENCRYPTION_KEY: str = ""
    # Fernet key (base64). Пустой = dev mode (plaintext mapping).
    # Генерация: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

    PII_NER_ENABLED: bool = True
    # Использовать natasha NER для обнаружения имён

    PII_PRESERVE_INN: bool = True
    # Не токенизировать ИНН (10/12 цифр) — используется в playbook positive_keywords

    PII_PRESERVE_OGRN: bool = True
    # Не токенизировать ОГРН (13/15 цифр)

    PII_PRESERVE_CADASTRAL: bool = True
    # Не токенизировать кадастровые номера

    PII_PRESERVE_PARTY_ROLES: bool = True
    # Заменять person_name → роль договора (SELLER/BUYER), если обнаружена в контексте

    PII_AUDIT_ENABLED: bool = True
    # Писать AuditLog при каждой санитации

    PII_SKIP_IF_ALREADY_SANITIZED: bool = True
    # Идемпотентность: пропустить если doc.status == sanitized

    # --- Stage 6: Structure Builder ---
    STRUCTURE_MIN_CLAUSE_COVERAGE: float = 0.60
    STRUCTURE_DEGRADED_CHUNK_TOKENS: int = 500
    STRUCTURE_MAX_CLAUSE_TITLE_LEN: int = 100

    # --- Stage 6: Classifier ---
    CLASSIFIER_L1_WEIGHT: float = 0.20  # L1 — слабый hint, не финальный вердикт
    CLASSIFIER_L2_ACCEPT_THRESHOLD: float = 0.85
    CLASSIFIER_L3_ACCEPT_THRESHOLD: float = 0.80
    CLASSIFIER_VOTING_THRESHOLD: float = 0.75
    CLASSIFIER_UNCERTAIN_THRESHOLD: float = 0.50
    CLASSIFIER_EMBEDDINGS_MODEL: str = "intfloat/multilingual-e5-small"  # L3
    CLASSIFIER_REGISTRY_PATH: str = "playbooks/document_types"

    # --- Stage 6: LLM Provider (L4) ---
    LLM_PROVIDER: str = "none"  # "none" | "local" | "openai" | "anthropic"
    LLM_LOCAL_MODEL_PATH: str = "C:/LegalMAS/LLMmodel/model.gguf"
    LLM_LOCAL_N_CTX: int = 4096  # context window for GGUF model
    LLM_LOCAL_N_GPU_LAYERS: int = 0  # 0 = CPU only, >0 = GPU offload
    LLM_CLOUD_MODEL: str = "gpt-4o-mini"
    LLM_CLOUD_API_KEY: str = ""


# Singleton: one settings instance for the whole application
settings = Settings()
