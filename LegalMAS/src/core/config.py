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


# Singleton: one settings instance for the whole application
settings = Settings()
