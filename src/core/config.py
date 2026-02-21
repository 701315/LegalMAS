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


# Singleton: one settings instance for the whole application
settings = Settings()
