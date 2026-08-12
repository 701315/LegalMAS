# src/services/embeddings/embedding_service.py

"""
Singleton service for text embeddings used by retrieval, classification, recovery.

Phase 14.3.B — Embedding Vector Cache:
- in-memory per-text vector cache;
- batch-aware: encode() разделяет cached/uncached, кодирует только uncached;
- cache key = sha256(text + model_name + role + token_limit) — raw text не хранится;
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
from ops.metrics import METRICS
from services.embeddings._preprocess import (
    apply_embedding_role_prefix,
    truncate_text_to_token_limit,
)

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

    def _get_embedding_max_input_tokens(self) -> int:
        """
        Safe token limit before model.encode().

        Явно ограничиваем размер входа, чтобы убрать silent truncation
        внутри SentenceTransformer и сделать его наблюдаемым через metrics/logs.
        """
        return int(max(1, int(getattr(settings, "EMBEDDING_MAX_INPUT_TOKENS", 500))))

    def _prepare_texts_for_encoding(
        self,
        texts: list[str],
        role: str,
    ) -> list[str]:
        """
        Apply E5 role prefix and explicit token truncation.

        Steps:
        1. Add role prefix ("query: " / "passage: ")
        2. Truncate explicitly to EMBEDDING_MAX_INPUT_TOKENS using tokenizer
        3. Increment metric and log if truncation happened
        """
        prefixed_texts = [apply_embedding_role_prefix(t, role=role) for t in texts]

        tokenizer = getattr(self.model, "tokenizer", None) if self.model is not None else None
        if tokenizer is None:
            logger.warning(
                "EmbeddingService: tokenizer unavailable, explicit truncation skipped",
                role=role,
            )
            return prefixed_texts

        max_input_tokens = self._get_embedding_max_input_tokens()
        prepared: list[str] = []
        truncated_count = 0
        max_original_tokens_seen = 0

        for text in prefixed_texts:
            truncated_text, was_truncated, original_token_count = truncate_text_to_token_limit(
                tokenizer=tokenizer,
                text=text,
                max_tokens=max_input_tokens,
            )
            prepared.append(truncated_text)
            if was_truncated:
                truncated_count += 1
            if original_token_count > max_original_tokens_seen:
                max_original_tokens_seen = original_token_count

        if truncated_count > 0:
            try:
                METRICS.embedding_text_truncated_total.labels(role=role).inc(truncated_count)
            except Exception:
                logger.debug(
                    "EmbeddingService: failed to increment embedding truncation metric",
                    exc_info=True,
                )

            logger.warning(
                "EmbeddingService: input texts explicitly truncated before encode",
                role=role,
                truncated_count=truncated_count,
                total_texts=len(texts),
                max_input_tokens=max_input_tokens,
                max_original_tokens_seen=max_original_tokens_seen,
            )

        return prepared

    def encode(self, texts: list[str], role: str = "passage") -> np.ndarray:
        """
        Синхронная кодировка с E5-prefix, explicit truncation и optional cache.

        role:
        - "passage" для корпуса/прототипов/документных фрагментов
        - "query"   для поисковых запросов и document-as-query сценариев

        ВАЖНО:
        - E5 требует role prefix ("query:" / "passage:")
        - длинные тексты теперь ЯВНО обрезаются по token limit до model.encode(),
          чтобы не полагаться на silent truncation внутри SentenceTransformer
        - truncation является observability-first fix: мы не меняем общую идею
          "вектор по префиксу текста", но делаем это явно и измеримо

        Cache key включает:
        - model_name
        - role
        - token_limit
        - original text
        """
        if not self.model:
            raise RuntimeError(
                "EmbeddingService: embeddings disabled. "
                "Set RUNNER_EMBEDDINGS_ENABLED=true in config."
            )

        if not texts:
            return np.array([], dtype=np.float32).reshape(0, self.embedding_dim)

        prepared_texts = self._prepare_texts_for_encoding(texts, role)

        if not self._is_cache_enabled():
            return self.model.encode(prepared_texts, show_progress_bar=False)

        from services.embeddings._cache import build_embedding_cache_key

        cache = self._get_cache()
        ttl, max_items = self._get_cache_settings()
        max_input_tokens = self._get_embedding_max_input_tokens()

        keys = [
            build_embedding_cache_key(
                t,
                self._model_name,
                role=role,
                max_input_tokens=max_input_tokens,
            )
            for t in texts
        ]
        cached = cache.get_many(keys)

        uncached_indices: list[int] = []
        uncached_prepared_texts: list[str] = []

        for i, key in enumerate(keys):
            if cached.get(key) is None:
                uncached_indices.append(i)
                uncached_prepared_texts.append(prepared_texts[i])

        if uncached_prepared_texts:
            fresh_vectors = self.model.encode(uncached_prepared_texts, show_progress_bar=False)
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


