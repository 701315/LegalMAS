# src/services/embeddings/_cache.py

"""
In-memory vector cache для EmbeddingService.

Назначение:
- хранить per-text embedding vectors;
- ускорять повторные encode() вызовы для уже встречавшихся текстов;
- не пересчитывать embeddings при reprocessing / retries / benchmark.

Архитектурные решения:
- cache process-local (in-memory), НЕ shared между worker processes;
- cache key = sha256(normalized_text + model_name) — raw text не хранится;
- cache stores np.ndarray vectors (одна строка = один текст);
- TTL + LRU eviction;
- thread-safe через RLock;
- batch-aware: encode() разделяет cached/uncached, кодирует только uncached.
"""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from threading import RLock

import numpy as np


def build_embedding_cache_key(text: str, model_name: str, role: str = "passage") -> str:
    """
    Построить cache key для одного текста.

    Безопасность:
    - raw text не используется как открытый key;
    - key = sha256(model_name + role + normalized_text).

    role включён в key потому что E5-модели добавляют разные префиксы
    ("query: " или "passage: ") перед кодированием. Векторы для одного текста
    в роли query и passage отличаются — они не должны делить один cache key.
    """
    normalized = text.strip()
    payload = f"{model_name}::{role}::{normalized}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class EmbeddingVectorCache:
    """
    Process-local LRU+TTL cache для embedding vectors.

    Хранит:
        key -> (vector: np.ndarray shape (D,), expires_at_monotonic)
    """

    def __init__(self) -> None:
        self._store: OrderedDict[str, tuple[np.ndarray, float]] = OrderedDict()
        self._lock = RLock()
        self._hits = 0
        self._misses = 0

    def _evict_expired_locked(self, now: float) -> None:
        expired_keys: list[str] = []
        for key, (_, expires_at) in self._store.items():
            if expires_at <= now:
                expired_keys.append(key)
        for key in expired_keys:
            self._store.pop(key, None)

    def get(self, key: str) -> np.ndarray | None:
        """Получить вектор из cache. None если miss."""
        if not key:
            return None

        now = time.monotonic()

        with self._lock:
            self._evict_expired_locked(now)

            entry = self._store.pop(key, None)
            if entry is None:
                self._misses += 1
                return None

            vec, expires_at = entry
            if expires_at <= now:
                self._misses += 1
                return None

            # LRU touch
            self._store[key] = (vec, expires_at)
            self._hits += 1
            return vec

    def set(
        self,
        key: str,
        vector: np.ndarray,
        *,
        ttl_seconds: int,
        max_items: int,
    ) -> None:
        """Сохранить вектор в cache."""
        if not key or vector is None:
            return
        if ttl_seconds <= 0 or max_items <= 0:
            return

        now = time.monotonic()
        expires_at = now + float(ttl_seconds)

        with self._lock:
            if key in self._store:
                self._store.pop(key, None)

            self._store[key] = (vector.copy(), expires_at)
            self._evict_expired_locked(now)

            while len(self._store) > max_items:
                self._store.popitem(last=False)

    def get_many(self, keys: list[str]) -> dict[str, np.ndarray | None]:
        """
        Batch lookup. Возвращает dict key -> vector|None.

        Эффективнее чем N отдельных get() вызовов: один lock acquire.
        """
        now = time.monotonic()
        result: dict[str, np.ndarray | None] = {}

        with self._lock:
            self._evict_expired_locked(now)

            for key in keys:
                if not key:
                    result[key] = None
                    self._misses += 1
                    continue

                entry = self._store.pop(key, None)
                if entry is None:
                    result[key] = None
                    self._misses += 1
                    continue

                vec, expires_at = entry
                if expires_at <= now:
                    result[key] = None
                    self._misses += 1
                    continue

                self._store[key] = (vec, expires_at)
                result[key] = vec
                self._hits += 1

        return result

    def set_many(
        self,
        items: dict[str, np.ndarray],
        *,
        ttl_seconds: int,
        max_items: int,
    ) -> None:
        """Batch store. Один lock acquire для всех items."""
        if ttl_seconds <= 0 or max_items <= 0:
            return

        now = time.monotonic()
        expires_at = now + float(ttl_seconds)

        with self._lock:
            for key, vec in items.items():
                if not key or vec is None:
                    continue
                if key in self._store:
                    self._store.pop(key, None)
                self._store[key] = (vec.copy(), expires_at)

            self._evict_expired_locked(now)

            while len(self._store) > max_items:
                self._store.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "size": len(self._store),
                "hits": self._hits,
                "misses": self._misses,
            }
        

