# src/engine/retrieval/engine.py

"""Stage 8 Retrieval: BM25 + embeddings + metadata weighting.

Гибридный поиск:
- BM25 по токенизированным чанкам
- Dense-скоринг через EmbeddingService (SentenceTransformer)
- Линейная смесь после пер-запросной min-max нормализации
- Базовый metadata-boost по section_title / позиции (если есть)
"""


import numpy as np
from rank_bm25 import BM25Okapi

from core.config import settings
from services.embeddings.embedding_service import embedding_service


class RetrievalEngine:
    def __init__(self, chunks: list[dict]):
        """
        chunks: список чанков вида:
            [{"id": ..., "text": "...", "metadata": {...}}, ...]

        metadata может содержать doc_type, clause_number, section_title,
        page, position_ratio и другие поля из layout/clause_tree.
        """
        # Безопасно приводим текст к строке и гарантируем наличие metadata
        texts: list[str] = [str(c.get("text", "") or "") for c in chunks]
        self.chunks: list[dict] = [
            {
                "id": c.get("id"),
                "text": t,
                "metadata": c.get("metadata", {}) or {},
            }
            for c, t in zip(chunks, texts)
        ]

        # Если чанков нет — деградирующий режим
        if not self.chunks:
            self.tokenized: list[list[str]] = []
            self.bm25: BM25Okapi | None = None
            self.emb_vectors: np.ndarray | None = None
            return

        # BM25 ожидает список списков токенов
        self.tokenized = [t.split() for t in texts]

        # Если после токенизации нет ни одного токена — тоже деградируем,
        # чтобы BM25Okapi не падал на пустом корпусе.
        if all(len(toks) == 0 for toks in self.tokenized):
            self.bm25 = None
            self.emb_vectors = None
            return

        self.bm25 = BM25Okapi(self.tokenized)

        # Dense-вектора для эмбеддингов
        if settings.RUNNER_EMBEDDINGS_ENABLED:
            # embedding_service.encode возвращает np.ndarray (N, D)
            self.emb_vectors = embedding_service.encode(texts)
        else:
            self.emb_vectors = None

    def search(self, query: str, top_k: int | None = None) -> list[dict]:
        """
        Выполняет гибридный поиск по BM25 + dense + metadata.

        Возвращает top_k чанков в формате:
            {"id", "text", "metadata", "score"}
        """
        if not self.chunks or self.bm25 is None:
            return []

        top_k = top_k or settings.RUNNER_RETRIEVAL_TOP_K

        # 1. BM25 scores (sparse)
        tokenized_query = query.split()
        bm25_scores = np.array(self.bm25.get_scores(tokenized_query), dtype=np.float32)

        # 2. Dense scores (cosine similarity), если включены
        if self.emb_vectors is not None:
            q_vec = embedding_service.encode([query])[0].astype(np.float32)
            q_norm = np.linalg.norm(q_vec) + 1e-9
            q_vec = q_vec / q_norm

            emb = self.emb_vectors.astype(np.float32)
            emb_norms = np.linalg.norm(emb, axis=1, keepdims=True) + 1e-9
            emb = emb / emb_norms

            dense_scores = np.dot(emb, q_vec)
        else:
            dense_scores = np.zeros_like(bm25_scores, dtype=np.float32)

        # 3. Metadata boost: лёгкие эвристики по section_title / позиции
        metadata_scores = self._compute_metadata_scores()

        # --- Нормализация перед взвешиванием ---

        def _min_max_normalize(arr: np.ndarray) -> np.ndarray:
            """Пер-запросная min-max нормализация в [0, 1]."""
            if arr.size == 0:
                return arr
            a_min = float(arr.min())
            a_max = float(arr.max())
            if a_max <= a_min + 1e-9:
                # Все значения одинаковы — возвращаем нули
                return np.zeros_like(arr, dtype=np.float32)
            return (arr - a_min) / (a_max - a_min + 1e-9)

        bm25_norm = _min_max_normalize(bm25_scores)
        dense_norm = _min_max_normalize(dense_scores)
        meta_norm = _min_max_normalize(metadata_scores)

        # 4. Weighted sum (после нормализации каждая модальность в [0,1])
        scores = (
            settings.RUNNER_SPARSE_WEIGHT * bm25_norm
            + settings.RUNNER_DENSE_WEIGHT * dense_norm
            + settings.RUNNER_METADATA_WEIGHT * meta_norm
        )

        # Top-K по комбинированному score
        idx = np.argsort(-scores)[:top_k]

        result: list[dict] = []
        for i in idx:
            i_int = int(i)
            chunk = self.chunks[i_int].copy()
            chunk["score"] = float(scores[i_int])
            result.append(chunk)

        return result

    def _compute_metadata_scores(self) -> np.ndarray:
        """
        Простая, но полезная реализация metadata-boost:

        - section_title: если содержит ключевые слова для важных секций,
          повышаем score.
        - position_ratio: если есть и находится в разумном диапазоне
          (например, середина документа), даём небольшой бонус.

        Всё это — чистые эвристики, не требующие изменений в других слоях.
        """
        n = len(self.chunks)
        scores = np.zeros(n, dtype=np.float32)

        if n == 0:
            return scores

        # Набор "важных" секций — можно расширять/подтягивать из конфига
        important_sections = [
            "change of control",
            "изменение контроля",
            "termination",
            "расторжение",
            "governing law",
            "применимое право",
            "representations and warranties",
            "представления и гарантии",
        ]

        for idx, ch in enumerate(self.chunks):
            meta = ch.get("metadata", {}) or {}

            # 1) Boost по section_title
            title = str(meta.get("section_title", "") or "").lower()
            if title and any(key in title for key in important_sections):
                scores[idx] += 1.0  # фиксированный бонус за важную секцию

            # 2) Boost по позиции (если есть position_ratio в [0,1])
            pos = meta.get("position_ratio")
            try:
                if pos is not None:
                    pos_f = float(pos)
                    # Например, clauses в "центре" документа для некоторых checks
                    # считаем чуть более значимыми (но очень мягко).
                    if 0.2 <= pos_f <= 0.8:
                        scores[idx] += 0.3
            except (TypeError, ValueError):
                # Некорректное значение позиции — игнорируем
                pass

        return scores
