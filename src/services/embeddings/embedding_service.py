from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from src.core.config import settings
from src.core.logging import get_logger

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
