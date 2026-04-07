# src/services/embeddings/embedding_service.py

"""
Singleton service for text embeddings used by retrieval in the Runner.

Сервис инкапсулирует загрузку SentenceTransformer‑модели и предоставляет
единый глобальный объект для кодирования текстов в dense embeddings.

Как работает:
- при первом создании проверяет `settings.RUNNER_EMBEDDINGS_ENABLED`;
  если эмбеддинги выключены, инициализируется в disabled‑режиме
  (`model=None`) и все попытки encode(...) приводят к RuntimeError;
- если эмбеддинги включены, создаёт cache directory
  `RUNNER_EMBEDDINGS_CACHE_DIR` и загружает модель
  `RUNNER_EMBEDDINGS_MODEL` через `SentenceTransformer`;
- использует singleton‑паттерн (`__new__`) чтобы модель загружалась
  только один раз на процесс и переиспользовалась всеми вызовами.

Публичный API:
- encode(texts: list[str]) -> np.ndarray:
  возвращает эмбеддинги для списка текстов без progress bar;
- embedding_dim -> int:
  размерность эмбеддингов текущей модели, либо 0 если сервис отключён.

Назначение:
- использоваться Runner/retrieval‑слоем для semantic search,
  ранжирования и сопоставления текстовых чанков по смыслу.
- global singleton `embedding_service` служит стандартной точкой доступа
  к модели во всём приложении.
"""

from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)


class EmbeddingService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        if not settings.RUNNER_EMBEDDINGS_ENABLED:
            logger.warning("Embeddings disabled")
            self.model = None
            self._initialized = True
            return

        model_path = Path(settings.RUNNER_EMBEDDINGS_CACHE_DIR)
        # ВАЖНО: создаём все родительские каталоги
        model_path.mkdir(parents=True, exist_ok=True)

        self.model = SentenceTransformer(
            settings.RUNNER_EMBEDDINGS_MODEL, cache_folder=str(model_path)
        )
        logger.info(
            "EmbeddingService initialized",
            model=settings.RUNNER_EMBEDDINGS_MODEL,
        )
        self._initialized = True

    def encode(self, texts: list[str]) -> np.ndarray:
        if not self.model:
            raise RuntimeError("Embeddings disabled")
        return self.model.encode(texts, show_progress_bar=False)

    @property
    def embedding_dim(self) -> int:
        return self.model.get_sentence_embedding_dimension() if self.model else 0


# Global singleton
embedding_service = EmbeddingService()
