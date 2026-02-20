"""Tests for application configuration."""

import os

from src.core.config import Settings


def test_settings_loads_defaults():
    """Settings should have sensible defaults for development."""
    s = Settings(
        _env_file=None,  # Don't load .env for this test
        DATABASE_URL="postgresql+asyncpg://test:test@localhost/test",
    )
    assert s.ENVIRONMENT == "development"
    assert s.LOG_LEVEL == "DEBUG"
    assert s.MINIO_BUCKET == "mas-artifacts"


def test_settings_loads_from_env(monkeypatch):
    """Settings should load values from environment variables."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://custom:custom@db:5432/custom")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")

    s = Settings(_env_file=None)

    assert s.DATABASE_URL == "postgresql+asyncpg://custom:custom@db:5432/custom"
    assert s.ENVIRONMENT == "production"
    assert s.LOG_LEVEL == "WARNING"


def test_settings_minio_config():
    """MinIO settings should have correct defaults."""
    s = Settings(_env_file=None)
    assert s.MINIO_ENDPOINT == "localhost:9000"
    assert s.MINIO_SECURE is False
