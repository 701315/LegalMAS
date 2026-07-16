"""
Тесты safety semantics для ArtifactStore.get_http_url().

Инварианты:
- get_http_url() допустим только в development-like окружениях
- в production должен fail-closed
- безопасная альтернатива get_presigned_get_url() продолжает работать
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.exceptions import PermanentError
from storage.artifact_store import ArtifactStore


def _make_settings(environment: str = "development", secure: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        MINIO_ENDPOINT="localhost:9000",
        MINIO_ACCESS_KEY="minioadmin",
        MINIO_SECRET_KEY="minioadmin123",
        MINIO_BUCKET="mas-artifacts",
        MINIO_SECURE=secure,
        ENVIRONMENT=environment,
    )


@pytest.fixture
def store_factory():
    """
    Создаёт ArtifactStore без реального подключения к MinIO.
    """
    def _factory(environment: str = "development", secure: bool = False):
        fake_client = MagicMock()
        with (
            patch("storage.artifact_store.Minio", return_value=fake_client),
            patch.object(ArtifactStore, "_ensure_bucket", return_value=None),
        ):
            store = ArtifactStore(_make_settings(environment=environment, secure=secure))
        return store, fake_client

    return _factory


class TestGetHttpUrl:
    """Тесты dev-only direct HTTP URL helper."""

    def test_development_relative_path_returns_http_url(self, store_factory):
        store, _ = store_factory(environment="development", secure=False)

        url = store.get_http_url("tenants/t1/deals/d1/file.pdf")

        assert url == "http://localhost:9000/mas-artifacts/tenants/t1/deals/d1/file.pdf"

    def test_development_s3_uri_is_normalized(self, store_factory):
        store, _ = store_factory(environment="development", secure=False)

        url = store.get_http_url("s3://mas-artifacts/tenants/t1/deals/d1/file.pdf")

        assert url == "http://localhost:9000/mas-artifacts/tenants/t1/deals/d1/file.pdf"

    def test_secure_mode_returns_https(self, store_factory):
        store, _ = store_factory(environment="development", secure=True)

        url = store.get_http_url("tenants/t1/deals/d1/file.pdf")

        assert url == "https://localhost:9000/mas-artifacts/tenants/t1/deals/d1/file.pdf"

    def test_production_raises_permanent_error(self, store_factory):
        store, _ = store_factory(environment="production", secure=False)

        with pytest.raises(PermanentError, match="disabled in production"):
            store.get_http_url("tenants/t1/deals/d1/file.pdf")


class TestGetPresignedGetUrl:
    """Проверяем, что безопасная альтернатива остаётся рабочей."""

    def test_presigned_url_still_works_in_production(self, store_factory):
        store, fake_client = store_factory(environment="production", secure=False)
        fake_client.presigned_get_object.return_value = "https://signed.example/url"

        url = store.get_presigned_get_url("s3://mas-artifacts/tenants/t1/deals/d1/file.pdf")

        assert url == "https://signed.example/url"
        fake_client.presigned_get_object.assert_called_once()
        _, kwargs = fake_client.presigned_get_object.call_args
        assert kwargs["bucket_name"] == "mas-artifacts"
        assert kwargs["object_name"] == "tenants/t1/deals/d1/file.pdf"


        