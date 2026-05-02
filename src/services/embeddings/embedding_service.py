# src/services/embeddings/embedding_service.py

"""
Singleton service for text embeddings used by retrieval in the Runner.

Сервис инкапсулирует загрузку SentenceTransformer-модели и предоставляет
единый глобальный объект для кодирования текстов в dense embeddings.

Изменения vs предыдущей версии:
- threading.Lock в __new__ предотвращает двойную инициализацию при параллельном
  старте нескольких Celery-воркеров (issue #15).
- encode_async() запускает синхронный encode() в ThreadPoolExecutor через
  asyncio.get_event_loop().run_in_executor(), не блокируя event loop (issue #5).
- encode() оставлен для синхронных контекстов (Celery tasks без asyncio).
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

# Один executor на процесс — переиспользуется всеми encode_async() вызовами.
# max_workers=1: модель не thread-safe для параллельных encode одновременно,
# но последовательная очередь через executor безопасна.
_ENCODE_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="embed")

_INIT_LOCK = threading.Lock()


class EmbeddingService:
    _instance = None

    def __new__(cls):
        # Double-checked locking: быстрый путь без lock если уже создан,
        # медленный путь с lock только при первом создании.
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
            self._initialized = True
            return

        model_path = Path(settings.RUNNER_EMBEDDINGS_CACHE_DIR)
        model_path.mkdir(parents=True, exist_ok=True)

        logger.info(
            "EmbeddingService: loading model",
            model=settings.RUNNER_EMBEDDINGS_MODEL,
            cache_dir=str(model_path),
        )
        self.model = SentenceTransformer(
            settings.RUNNER_EMBEDDINGS_MODEL,
            cache_folder=str(model_path),
        )
        logger.info(
            "EmbeddingService: model ready",
            model=settings.RUNNER_EMBEDDINGS_MODEL,
            dim=self.embedding_dim,
        )
        self._initialized = True

    def encode(self, texts: list[str]) -> np.ndarray:
        """
        Синхронная кодировка. Использовать в Celery-тасках без asyncio event loop.
        Не вызывать из async-функций напрямую — используй encode_async().
        """
        if not self.model:
            raise RuntimeError(
                "EmbeddingService: embeddings disabled. "
                "Set RUNNER_EMBEDDINGS_ENABLED=true in config."
            )
        return self.model.encode(texts, show_progress_bar=False)

    async def encode_async(self, texts: list[str]) -> np.ndarray:
        """
        Async-safe кодировка для использования в async-контекстах (FastAPI, async workers).
        Запускает синхронный encode() в ThreadPoolExecutor, не блокируя event loop.
        """
        if not self.model:
            raise RuntimeError(
                "EmbeddingService: embeddings disabled. "
                "Set RUNNER_EMBEDDINGS_ENABLED=true in config."
            )
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _ENCODE_EXECUTOR,
            lambda: self.model.encode(texts, show_progress_bar=False),
        )

    @property
    def embedding_dim(self) -> int:
        return self.model.get_sentence_embedding_dimension() if self.model else 0

    @property
    def is_enabled(self) -> bool:
        return self.model is not None


# Global singleton
embedding_service = EmbeddingService()
