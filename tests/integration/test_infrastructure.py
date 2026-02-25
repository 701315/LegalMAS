"""
Integration tests for infrastructure services.
These tests require Docker services to be running (make up).
"""

import pytest
import redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.config import settings
from src.storage.artifact_store import ArtifactPath, ArtifactStore

# ============================================================
# PostgreSQL
# ============================================================


@pytest.mark.asyncio
async def test_postgres_connection():
    """PostgreSQL should accept connections and respond to queries."""
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1 AS check_value"))
            row = result.fetchone()
            assert row is not None
            assert row[0] == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_version():
    """PostgreSQL version should be 16+."""
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SHOW server_version"))
            row = result.fetchone()
            version_str = row[0]
            major_version = int(version_str.split(".")[0])
            assert major_version >= 16, f"Expected PostgreSQL 16+, got {version_str}"
    finally:
        await engine.dispose()


# ============================================================
# Redis
# ============================================================


def test_redis_connection():
    """Redis should respond to PING."""
    r = redis.from_url(settings.REDIS_URL)
    assert r.ping() is True


def test_redis_set_get():
    """Redis should store and retrieve values."""
    r = redis.from_url(settings.REDIS_URL)
    r.set("mas_dd_test_key", "test_value", ex=10)  # expires in 10 sec
    value = r.get("mas_dd_test_key")
    assert value == b"test_value"
    r.delete("mas_dd_test_key")  # cleanup


# ============================================================
# MinIO (ArtifactStore)
# ============================================================


def test_artifact_store_creates_bucket():
    """ArtifactStore should create the bucket on initialization."""
    store = ArtifactStore()
    assert store.client.bucket_exists(store.bucket)


def test_artifact_store_put_and_get_json():
    """ArtifactStore should store and retrieve JSON data."""
    store = ArtifactStore()
    test_path = "tests/test_put_get.json"
    test_data = {
        "document_id": "doc-001",
        "elements": [
            {"id": "e1", "text": "Hello world", "page": 1},
            {"id": "e2", "text": "Привет мир", "page": 2},
        ],
        "metadata": {"pages": 2, "language": "mixed"},
    }

    # Put
    uri = store.put_json(test_path, test_data)
    assert uri == f"s3://{store.bucket}/{test_path}"

    # Get
    retrieved = store.get_json(test_path)
    assert retrieved == test_data
    assert retrieved["elements"][1]["text"] == "Привет мир"  # Unicode works

    # Cleanup
    store.delete(test_path)


def test_artifact_store_put_and_get_file():
    """ArtifactStore should store and retrieve binary files."""
    store = ArtifactStore()
    test_path = "tests/test_binary.bin"
    test_content = b"This is a test binary file content \x00\x01\x02"

    # Put
    uri = store.put_file(test_path, test_content)
    assert uri == f"s3://{store.bucket}/{test_path}"

    # Get
    retrieved = store.get_file(test_path)
    assert retrieved == test_content

    # Cleanup
    store.delete(test_path)


def test_artifact_store_exists():
    """ArtifactStore.exists should correctly detect existing and missing objects."""
    store = ArtifactStore()
    test_path = "tests/test_exists.json"

    # Should not exist yet
    assert store.exists(test_path) is False

    # Create it
    store.put_json(test_path, {"test": True})
    assert store.exists(test_path) is True

    # Delete it
    store.delete(test_path)
    assert store.exists(test_path) is False


def test_artifact_store_presigned_url():
    """ArtifactStore should generate presigned download URLs."""
    store = ArtifactStore()
    test_path = "tests/test_presigned.json"
    store.put_json(test_path, {"presigned": "test"})

    url = store.get_presigned_url(test_path, expires_hours=1)
    assert url.startswith("http")
    assert test_path in url

    # Cleanup
    store.delete(test_path)


def test_artifact_store_get_nonexistent_raises():
    """Getting a non-existent artifact should raise PermanentError."""
    from src.core.exceptions import PermanentError

    store = ArtifactStore()
    with pytest.raises(PermanentError, match="Artifact not found"):
        store.get_json("nonexistent/path/file.json")


# ============================================================
# ArtifactPath
# ============================================================


def test_artifact_path_original():
    """ArtifactPath should build correct paths for originals."""
    path = ArtifactPath.original("tenant-1", "deal-1", "doc-1")
    assert path == "tenants/tenant-1/deals/deal-1/originals/doc-1"


def test_artifact_path_layout_raw():
    """ArtifactPath should build correct paths for raw layouts."""
    path = ArtifactPath.layout_raw("t1", "d1", "doc1")
    assert path == "tenants/t1/deals/d1/layouts/doc1/raw.json"


def test_artifact_path_layout_sanitized():
    """ArtifactPath should build correct paths for sanitized layouts."""
    path = ArtifactPath.layout_sanitized("t1", "d1", "doc1")
    assert path == "tenants/t1/deals/d1/layouts/doc1/sanitized.json"


def test_artifact_path_check_results():
    """ArtifactPath should build correct paths for check results."""
    path = ArtifactPath.check_results("t1", "d1", "run-1")
    assert path == "tenants/t1/deals/d1/results/run-1/check_results.jsonl"


def test_artifact_path_pii_mapping():
    """ArtifactPath should build correct paths for PII mapping."""
    path = ArtifactPath.pii_mapping("t1", "d1", "doc1")
    assert path == "tenants/t1/deals/d1/pii/doc1/mapping.enc"
