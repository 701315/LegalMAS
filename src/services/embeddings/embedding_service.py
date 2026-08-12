# src/services/embeddings/embedding_service.py

"""
Singleton service for text embeddings used by retrieval, classification, recovery.

Phase 14.3.B — Embedding Vector Cache:
- in-memory per-text vector cache;
- batch-aware: encode() разделяет cached/uncached, кодирует только uncached;
- cache key = sha256(text + model_name) — raw text не хранится;
- включается через EMBEDDING_CACHE_ENABLED=true;
- thread-safe через RLock в cache;
- async encode_async() тоже через cache.
"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

_ENCODE_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="embed")
_INIT_LOCK = threading.Lock()


class EmbeddingService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            with _INIT_LOCK:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    cls._instance = instance
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        if not settings.RUNNER_EMBEDDINGS_ENABLED:
            logger.warning("EmbeddingService: embeddings disabled via config")
            self.model = None
            self._model_name: str = ""
            self._initialized = True
            return

        self._model_name = settings.RUNNER_EMBEDDINGS_MODEL

        model_path = Path(settings.RUNNER_EMBEDDINGS_CACHE_DIR)
        model_path.mkdir(parents=True, exist_ok=True)

        logger.info(
            "EmbeddingService: loading model",
            model=self._model_name,
            cache_dir=str(model_path),
        )
        self.model = SentenceTransformer(
            self._model_name,
            cache_folder=str(model_path),
        )
        logger.info(
            "EmbeddingService: model ready",
            model=self._model_name,
            dim=self.embedding_dim,
        )
        self._initialized = True

    def _is_cache_enabled(self) -> bool:
        return bool(getattr(settings, "EMBEDDING_CACHE_ENABLED", False))

    def _get_cache(self):
        """Lazy import чтобы не создавать cache если не нужен."""
        from services.embeddings._cache import EmbeddingVectorCache

        if not hasattr(self, "_vector_cache"):
            self._vector_cache = EmbeddingVectorCache()
        return self._vector_cache

    def _get_cache_settings(self) -> tuple[int, int]:
        ttl = int(max(1, int(getattr(settings, "EMBEDDING_CACHE_TTL_SECONDS", 86400))))
        max_items = int(max(1, int(getattr(settings, "EMBEDDING_CACHE_MAX_ITEMS", 50000))))
        return ttl, max_items

    def encode(self, texts: list[str], role: str = "passage") -> np.ndarray:
        """
        Синхронная кодировка с E5-prefix и optional cache.

        role: "passage" для корпуса/прототипов, "query" для поисковых запросов.
        E5-модели семейства (multilingual-e5-small, multilingual-e5-large)
        требуют префиксов "passage: " и "query: " по спецификации модели.
        Без префиксов модель работает ниже своего потенциального качества.

        Если cache включён:
        1. Построить keys для всех texts (с учётом role).
        2. Batch lookup cached vectors.
        3. Добавить префикс и кодировать только uncached.
        4. Сохранить новые vectors в cache.
        5. Собрать результат в правильном порядке.

        Если cache выключён — прямой вызов model.encode() с префиксами.
        """
        if not self.model:
            raise RuntimeError(
                "EmbeddingService: embeddings disabled. "
                "Set RUNNER_EMBEDDINGS_ENABLED=true in config."
            )

        if not texts:
            return np.array([], dtype=np.float32).reshape(0, self.embedding_dim)

        # E5-prefix: добавляем роль-специфический префикс перед кодированием.
        # Это обязательное требование семейства E5 (intfloat/multilingual-e5-*).
        # "query: " — для поисковых запросов
        # "passage: " — для документов, корпуса, прототипов классификатора
        prefix = "query: " if role == "query" else "passage: "
        prefixed_texts = [prefix + t for t in texts]

        if not self._is_cache_enabled():
            return self.model.encode(prefixed_texts, show_progress_bar=False)

        from services.embeddings._cache import build_embedding_cache_key

        cache = self._get_cache()
        ttl, max_items = self._get_cache_settings()

        # Cache key включает role чтобы query и passage векторы не перезаписывали друг друга.
        keys = [build_embedding_cache_key(t, self._model_name, role) for t in texts]
        cached = cache.get_many(keys)

        uncached_indices: list[int] = []
        uncached_prefixed: list[str] = []

        for i, key in enumerate(keys):
            if cached.get(key) is None:
                uncached_indices.append(i)
                uncached_prefixed.append(prefixed_texts[i])

        if uncached_prefixed:
            fresh_vectors = self.model.encode(uncached_prefixed, show_progress_bar=False)
            fresh_vectors = np.asarray(fresh_vectors, dtype=np.float32)

            to_store: dict[str, np.ndarray] = {}
            for j, idx in enumerate(uncached_indices):
                to_store[keys[idx]] = fresh_vectors[j]

            cache.set_many(to_store, ttl_seconds=ttl, max_items=max_items)
        else:
            fresh_vectors = None

        dim = self.embedding_dim
        result = np.empty((len(texts), dim), dtype=np.float32)

        fresh_cursor = 0
        for i, key in enumerate(keys):
            vec = cached.get(key)
            if vec is not None:
                result[i] = vec
            else:
                if fresh_vectors is not None:
                    result[i] = fresh_vectors[fresh_cursor]
                    fresh_cursor += 1

        return result

    async def encode_async(self, texts: list[str], role: str = "passage") -> np.ndarray:
        """
        Async-safe кодировка. Запускает encode() в executor.
        Cache и E5-prefix работают через тот же encode().

        role: "passage" для корпуса/документов, "query" для поисковых запросов.
        """
        if not self.model:
            raise RuntimeError(
                "EmbeddingService: embeddings disabled. "
                "Set RUNNER_EMBEDDINGS_ENABLED=true in config."
            )
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _ENCODE_EXECUTOR,
            lambda: self.encode(texts, role=role),
        )

    @property
    def embedding_dim(self) -> int:
        return self.model.get_sentence_embedding_dimension() if self.model else 0

    @property
    def is_enabled(self) -> bool:
        return self.model is not None


# Global singleton
embedding_service = EmbeddingService()


