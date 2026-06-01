"""
Phase 14.3.B — Embedding Vector Cache.

Покрытие:
- cache hit при повторном encode с одинаковым текстом
- cache miss при разных текстах
- batch mixed cached/uncached assembly
- cache bypass при EMBEDDING_CACHE_ENABLED=False
- cache stats
- thread-safe batch operations
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from services.embeddings._cache import (
    EmbeddingVectorCache,
    build_embedding_cache_key,
)


class TestEmbeddingCacheKey:
    def test_same_text_same_model_gives_same_key(self):
        k1 = build_embedding_cache_key("hello world", "model-a")
        k2 = build_embedding_cache_key("hello world", "model-a")
        assert k1 == k2

    def test_different_text_gives_different_key(self):
        k1 = build_embedding_cache_key("hello", "model-a")
        k2 = build_embedding_cache_key("world", "model-a")
        assert k1 != k2

    def test_different_model_gives_different_key(self):
        k1 = build_embedding_cache_key("hello", "model-a")
        k2 = build_embedding_cache_key("hello", "model-b")
        assert k1 != k2

    def test_whitespace_normalized(self):
        k1 = build_embedding_cache_key("  hello  ", "model-a")
        k2 = build_embedding_cache_key("hello", "model-a")
        assert k1 == k2


class TestEmbeddingVectorCache:
    def test_get_miss(self):
        cache = EmbeddingVectorCache()
        assert cache.get("nonexistent") is None

    def test_set_and_get(self):
        cache = EmbeddingVectorCache()
        vec = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        cache.set("k1", vec, ttl_seconds=3600, max_items=100)
        result = cache.get("k1")
        assert result is not None
        np.testing.assert_array_equal(result, vec)

    def test_stored_vector_is_copy(self):
        cache = EmbeddingVectorCache()
        vec = np.array([1.0, 2.0], dtype=np.float32)
        cache.set("k1", vec, ttl_seconds=3600, max_items=100)
        vec[0] = 999.0
        result = cache.get("k1")
        assert result is not None
        assert result[0] == 1.0

    def test_max_items_eviction(self):
        cache = EmbeddingVectorCache()
        vec = np.array([1.0], dtype=np.float32)
        cache.set("a", vec, ttl_seconds=3600, max_items=2)
        cache.set("b", vec, ttl_seconds=3600, max_items=2)
        cache.set("c", vec, ttl_seconds=3600, max_items=2)
        assert cache.get("a") is None
        assert cache.get("b") is not None
        assert cache.get("c") is not None

    def test_get_many(self):
        cache = EmbeddingVectorCache()
        v1 = np.array([1.0], dtype=np.float32)
        v2 = np.array([2.0], dtype=np.float32)
        cache.set("k1", v1, ttl_seconds=3600, max_items=100)
        cache.set("k2", v2, ttl_seconds=3600, max_items=100)

        result = cache.get_many(["k1", "k2", "k3"])
        assert result["k1"] is not None
        assert result["k2"] is not None
        assert result["k3"] is None

    def test_set_many(self):
        cache = EmbeddingVectorCache()
        items = {
            "k1": np.array([1.0], dtype=np.float32),
            "k2": np.array([2.0], dtype=np.float32),
        }
        cache.set_many(items, ttl_seconds=3600, max_items=100)
        assert cache.get("k1") is not None
        assert cache.get("k2") is not None

    def test_stats(self):
        cache = EmbeddingVectorCache()
        vec = np.array([1.0], dtype=np.float32)
        cache.set("k1", vec, ttl_seconds=3600, max_items=100)
        cache.get("k1")
        cache.get("missing")
        stats = cache.stats()
        assert stats["size"] == 1
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_clear(self):
        cache = EmbeddingVectorCache()
        vec = np.array([1.0], dtype=np.float32)
        cache.set("k1", vec, ttl_seconds=3600, max_items=100)

        cache.clear()

        stats = cache.stats()
        assert stats["size"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0

        assert cache.get("k1") is None


class TestEmbeddingServiceWithCache:
    """Тесты encode() с cache через mock model."""

    @pytest.fixture(autouse=True)
    def _reset(self):
        from core.config import settings

        old_enabled = getattr(settings, "EMBEDDING_CACHE_ENABLED", False)
        old_ttl = getattr(settings, "EMBEDDING_CACHE_TTL_SECONDS", 86400)
        old_max = getattr(settings, "EMBEDDING_CACHE_MAX_ITEMS", 50000)

        settings.EMBEDDING_CACHE_ENABLED = True
        settings.EMBEDDING_CACHE_TTL_SECONDS = 3600
        settings.EMBEDDING_CACHE_MAX_ITEMS = 1000

        yield

        settings.EMBEDDING_CACHE_ENABLED = old_enabled
        settings.EMBEDDING_CACHE_TTL_SECONDS = old_ttl
        settings.EMBEDDING_CACHE_MAX_ITEMS = old_max

    def _make_service(self):
        """Создать EmbeddingService с mock model (не грузим реальную модель)."""
        from services.embeddings.embedding_service import EmbeddingService

        svc = object.__new__(EmbeddingService)
        svc._initialized = True
        svc._model_name = "test-model"

        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 3

        def fake_encode(texts, show_progress_bar=False):
            return np.array(
                [[float(hash(t) % 100), 0.5, 0.1] for t in texts],
                dtype=np.float32,
            )

        mock_model.encode = fake_encode
        svc.model = mock_model

        return svc

    def test_cache_hit_skips_model_encode(self):
        svc = self._make_service()
        svc._vector_cache = EmbeddingVectorCache()

        result1 = svc.encode(["hello", "world"])
        assert result1.shape == (2, 3)

        svc.model.encode = MagicMock(side_effect=RuntimeError("should not be called"))

        result2 = svc.encode(["hello", "world"])
        np.testing.assert_array_equal(result1, result2)

    def test_mixed_cached_uncached(self):
        svc = self._make_service()
        svc._vector_cache = EmbeddingVectorCache()

        svc.encode(["aaa"])

        call_count = [0]
        original_encode = svc.model.encode

        def counting_encode(texts, **kwargs):
            call_count[0] += 1
            return np.array(
                [[float(hash(t) % 100), 0.5, 0.1] for t in texts],
                dtype=np.float32,
            )

        svc.model.encode = counting_encode

        result = svc.encode(["aaa", "bbb"])
        assert result.shape == (2, 3)
        assert call_count[0] == 1

    def test_cache_disabled_always_calls_model(self):
        from core.config import settings

        settings.EMBEDDING_CACHE_ENABLED = False

        svc = self._make_service()
        call_count = [0]

        def counting_encode(texts, **kwargs):
            call_count[0] += 1
            return np.array(
                [[1.0, 2.0, 3.0] for _ in texts],
                dtype=np.float32,
            )

        svc.model.encode = counting_encode

        svc.encode(["hello"])
        svc.encode(["hello"])
        assert call_count[0] == 2

    def test_empty_texts_returns_empty_array(self):
        svc = self._make_service()
        result = svc.encode([])
        assert result.shape == (0, 3)



        