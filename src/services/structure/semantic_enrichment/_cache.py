# src/services/structure/semantic_enrichment/_cache.py

"""
In-memory response cache for semantic enrichment LLM calls.

Назначение:
- хранить exact-match raw LLM responses для semantic enrichment;
- ускорять retries / reprocessing одного и того же document_version;
- не вызывать LLM повторно для идентичного prompt в рамках одного документа.

Архитектурные решения:
- cache process-local (in-memory), НЕ shared между worker processes;
- cache document-version scoped на уровне cache key (ключ строится выше);
- cache stores only raw response text;
- TTL + LRU eviction;
- thread-safe через RLock;
- async-safe, потому что операции очень короткие и синхронные in-memory.

Важно:
- Этот cache НЕ хранит raw prompt как key.
- Во внешний API/логи не выводится содержимое legal текста.
- Ключ cache должен строиться как hash/fingerprint выше по стеку.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from threading import RLock


class SemanticEnrichmentResponseCache:
    """
    Простой process-local LRU+TTL cache для raw LLM responses.

    Хранит:
        key -> (value, expires_at_monotonic)

    Где:
    - key: уже готовый безопасный fingerprint (не raw text)
    - value: raw response text от LLM
    """

    def __init__(self) -> None:
        self._store: OrderedDict[str, tuple[str, float]] = OrderedDict()
        self._lock = RLock()
        self._hits = 0
        self._misses = 0

    def _evict_expired_locked(self, now: float) -> None:
        """
        Удалить протухшие entries.

        Идём по OrderedDict слева направо и удаляем только expired entries.
        """
        expired_keys: list[str] = []
        for key, (_, expires_at) in self._store.items():
            if expires_at <= now:
                expired_keys.append(key)

        for key in expired_keys:
            self._store.pop(key, None)

    def get(self, key: str) -> str | None:
        """
        Получить значение из cache.

        Возвращает:
        - raw response text, если entry существует и не протухла
        - None иначе
        """
        if not key:
            return None

        now = time.monotonic()

        with self._lock:
            self._evict_expired_locked(now)

            entry = self._store.pop(key, None)
            if entry is None:
                self._misses += 1
                return None

            value, expires_at = entry
            if expires_at <= now:
                self._misses += 1
                return None

            # LRU touch: переносим в конец
            self._store[key] = (value, expires_at)
            self._hits += 1
            return value

    def set(
        self,
        key: str,
        value: str,
        *,
        ttl_seconds: int,
        max_items: int,
    ) -> None:
        """
        Сохранить значение в cache.

        Ограничения:
        - ttl_seconds <= 0  -> не сохраняем
        - max_items <= 0    -> не сохраняем
        - пустой key/value  -> не сохраняем
        """
        if not key or not value:
            return
        if ttl_seconds <= 0 or max_items <= 0:
            return

        now = time.monotonic()
        expires_at = now + float(ttl_seconds)

        with self._lock:
            if key in self._store:
                self._store.pop(key, None)

            self._store[key] = (value, expires_at)
            self._evict_expired_locked(now)

            while len(self._store) > max_items:
                self._store.popitem(last=False)

    def clear(self) -> None:
        """Полностью очистить cache."""
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict[str, int]:
        """Вернуть диагностические stats cache."""
        with self._lock:
            return {
                "size": len(self._store),
                "hits": self._hits,
                "misses": self._misses,
            }


_RESPONSE_CACHE: SemanticEnrichmentResponseCache | None = None


def get_semantic_enrichment_response_cache() -> SemanticEnrichmentResponseCache:
    """
    Вернуть singleton cache для semantic enrichment.
    """
    global _RESPONSE_CACHE
    if _RESPONSE_CACHE is None:
        _RESPONSE_CACHE = SemanticEnrichmentResponseCache()
    return _RESPONSE_CACHE


