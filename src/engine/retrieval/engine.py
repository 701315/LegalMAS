# src/engine/retrieval/engine.py

"""
Retrieval: BM25 + embeddings + metadata weighting.

Гибридный поиск:
- BM25 по токенизированным чанкам,
- Dense-скоринг через EmbeddingService (SentenceTransformer),
- Линейная смесь после пер-запросной min-max нормализации,
- Базовый metadata-boost по section_title / позиции (если есть).

После ввода RetrievalChunk этот движок умеет работать и со "старыми"
dict-чанками, и с новыми объектами RetrievalChunk.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
from rank_bm25 import BM25Okapi

from core.config import settings
from engine.retrieval.models import RetrievalChunk
from services.embeddings.embedding_service import embedding_service


class RetrievalEngine:
    """
    Движок гибридного поиска по чанкам.

    Для непрофессионального программиста:

    - На вход мы даём список чанков (кусочков текста договора).
      Сейчас поддерживаются два формата:
        1) "старый" формат:
           {"id": "...", "text": "...", "metadata": {...}}
        2) новый формат: объекты RetrievalChunk (универсальный "паспорт" чанка).

    - Дополнительно можно передать список "важных слов" (important_terms):
      это фразы, которые описывают КОНКРЕТНУЮ проверку (risk/check)
      и используются для небольшого бонуса к скору по заголовкам/summary.

    - Внутри движок:
        * строит BM25-индекс по тексту,
        * считает эмбеддинги (векторное представление текста),
        * при запросе комбинирует BM25 + dense + небольшие бонусы по метаданным.

    - На выходе возвращается список dict:
        {"id", "text", "metadata", "score}
      чтобы не ломать старый код.
    """

    def __init__(self, chunks: Iterable[Any], important_terms: Iterable[str] | None = None):
        """
        chunks: список чанков одного из форматов:
          - dict: {"id": "...", "text": "...", "metadata": {...}}
          - RetrievalChunk: объект из engine.retrieval.models.

        important_terms: список важных слов/фраз для текущей проверки (check),
        которые мы будем использовать для лёгкого буста по метаданным
        (заголовки, "хлебные крошки", summary). Если не задано — тема
        конкретной проверки при metadata-boost не учитывается.

        metadata/паспорт чанка может содержать:
          - doc_type, language, jurisdiction,
          - clause_uid, level, path_titles,
          - section_title, page, position_ratio,
          - и другие поля из layout/clause_tree.

        ВАЖНО:
        - self.chunks хранит ОРИГИНАЛЬНЫЙ текст чанка (без summary).
        - Для BM25 мы индексируем summary + text (если summary есть),
          чтобы заголовки и короткое summary тоже участвовали в поиске.
        """
        # Нормализуем вход, чтобы внутри всегда был один формат self.chunks:
        # список dict с ключами "id", "text", "metadata".
        self.chunks: list[dict] = []
        texts_for_index: list[str] = []

        for c in chunks:
            if isinstance(c, RetrievalChunk):
                # Новый формат: берём текст и паспорт через to_legacy_dict().
                legacy = c.to_legacy_dict()
                text = str(legacy.get("text", "") or "")
                meta = legacy.get("metadata", {}) or {}

                # Для BM25 мы будем использовать не только text, но и summary,
                # если оно есть в metadata. Это помогает лучше находить чанк
                # по заголовку/краткому описанию, а не только по "теле" текста.
                summary = str(meta.get("summary", "") or "")
                if summary:
                    indexed_text = f"{summary}\n\n{text}"
                else:
                    indexed_text = text

                self.chunks.append(
                    {
                        "id": legacy.get("id"),
                        "text": text,  # исходный текст чанка
                        "metadata": meta,
                    }
                )
                texts_for_index.append(indexed_text)
            else:
                # Старый формат: ch — это dict вида {"id","text","metadata"}.
                text = str(c.get("text", "") or "")
                meta = c.get("metadata", {}) or {}

                summary = str(meta.get("summary", "") or "")
                if summary:
                    indexed_text = f"{summary}\n\n{text}"
                else:
                    indexed_text = text

                self.chunks.append(
                    {
                        "id": c.get("id"),
                        "text": text,  # исходный текст чанка
                        "metadata": meta,
                    }
                )
                texts_for_index.append(indexed_text)

        # Нормализуем список важных терминов для metadata-boost.
        # Это слова/фразы, релевантные КОНКРЕТНОЙ проверке (check),
        # которые приходят сверху (из плейбука через CheckDefinition).
        if important_terms is None:
            self.important_terms_lower: list[str] = []
        else:
            norm_terms: list[str] = []
            for t in important_terms:
                if not isinstance(t, str):
                    continue
                s = t.strip().lower()
                if s:
                    norm_terms.append(s)
            self.important_terms_lower = norm_terms

        # Если чанков нет — деградирующий режим (поиск ничего не вернёт).
        if not self.chunks:
            self.tokenized: list[list[str]] = []
            self.bm25: BM25Okapi | None = None
            self.emb_vectors: np.ndarray | None = None
            return

        # BM25 ожидает список списков токенов (слов).
        # Для простоты сейчас токенизация — это обычный split по пробелам.
        self.tokenized = [t.split() for t in texts_for_index]

        # Если после токенизации нет ни одного токена — тоже деградируем,
        # чтобы BM25Okapi не падал на пустом корпусе.
        if all(len(toks) == 0 for toks in self.tokenized):
            self.bm25 = None
            self.emb_vectors = None
            return

        # Инициализируем BM25 по корпусу текстов
        self.bm25 = BM25Okapi(self.tokenized)

        # Dense-вектора для эмбеддингов.
        #
        # ВАЖНО:
        # Для эмбеддингов мы по-прежнему используем ИСХОДНЫЙ текст чанка
        # (без склейки с summary), т.к. summary уже "зашито" в metadata-boost,
        # и мы не хотим сильно менять длину/структуру текста для модели.
        if settings.RUNNER_EMBEDDINGS_ENABLED:
            original_texts = [ch["text"] for ch in self.chunks]
            # embedding_service.encode возвращает np.ndarray (N, D)
            self.emb_vectors = embedding_service.encode(original_texts)
        else:
            self.emb_vectors = None

    def search(self, query: str, top_k: int | None = None) -> list[dict]:
        """
        Выполняет гибридный поиск по BM25 + dense + metadata.

        На вход:
          - query: строка запроса (то, что мы ищем в договоре),
          - top_k: сколько лучших чанков вернуть (если не задано —
            берём значение из настроек RUNNER_RETRIEVAL_TOP_K).

        На выход:
          - список dict, один dict на чанк:
              {
                "id": ...,
                "text": "...",
                "metadata": {...},
                "score": float,  # итоговый комбинированный score
              }
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

        # 3. Metadata boost: лёгкие эвристики по заголовкам / позиции / summary
        metadata_scores = self._compute_metadata_scores()

        # --- Нормализация перед взвешиванием ---
        def _min_max_normalize(arr: np.ndarray) -> np.ndarray:
            """
            Пер-запросная min-max нормализация в [0, 1].

            Для непрофессионального программиста:
            - Мы приводим оценки BM25/dense/metadata к одному диапазону [0,1],
              чтобы их можно было честно сложить с весами.
            """
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
        Простая, но полезная реализация metadata-boost.

        Сейчас используем несколько эвристик:

        0) kind: лёгкий bias в пользу subclause и против section.
        1) section_title: если содержит важные слова для текущей проверки
           (check), повышаем score.
        2) position_ratio: если есть и находится в разумном диапазоне
           (например, середина документа), даём небольшой бонус.
        3) path_titles: если в пути заголовков встречаются важные слова,
           даём дополнительный бонус.
        4) summary: если краткое summary содержит важные слова, даём небольшой
           бонус (summary обычно более компактно отражает суть чанка).

        Важные слова задаются извне (через important_terms в конструкторе)
        и зависят от конкретной проверки (check). Если important_terms
        не задан, работает только позиционная эвристика и bias по kind.
        """
        n = len(self.chunks)
        scores = np.zeros(n, dtype=np.float32)

        if n == 0:
            return scores

        # Важные слова/фразы для текущей проверки (check),
        # приведённые к нижнему регистру в __init__.
        important_terms = getattr(self, "important_terms_lower", []) or []

        # Читаем конфигurable веса из settings (с дефолтами, как было хардкожено).
        kind_bonus_subclause = float(getattr(settings, "RUNNER_METADATA_KIND_BONUS_SUBCLAUSE", 0.3))
        kind_penalty_section = float(getattr(settings, "RUNNER_METADATA_KIND_PENALTY_SECTION", 0.1))
        section_title_boost = float(getattr(settings, "RUNNER_METADATA_SECTION_TITLE_BOOST", 1.0))
        position_mid_boost = float(getattr(settings, "RUNNER_METADATA_POSITION_MID_BOOST", 0.3))
        path_titles_boost = float(getattr(settings, "RUNNER_METADATA_PATH_TITLES_BOOST", 0.5))
        summary_boost = float(getattr(settings, "RUNNER_METADATA_SUMMARY_BOOST", 0.2))

        for idx, ch in enumerate(self.chunks):
            meta = ch.get("metadata", {}) or {}

            # 0) Лёгкий bias по типу чанка (kind / chunk_kind).
            #
            # P8.8d: legal_unit — новый primary retrieval substrate,
            # получает тот же бонус, что раньше subclause.
            # chunk_kind используется в snapshot chunks, kind — в legacy path.
            kind = str(meta.get("chunk_kind") or meta.get("kind") or "").lower()
            if kind in ("legal_unit", "subclause"):
                scores[idx] += kind_bonus_subclause
            elif kind == "section":
                scores[idx] -= kind_penalty_section
            # "clause" и всё остальное — без смещения

            # 1) Boost по section_title: если заголовок содержит важные слова
            title = str(meta.get("section_title", "") or "").lower()
            if title and important_terms and any(key in title for key in important_terms):
                scores[idx] += section_title_boost

            # 2) Boost по позиции (если есть position_ratio в [0,1])
            pos = meta.get("position_ratio")
            try:
                if pos is not None:
                    pos_f = float(pos)
                    # Например, clauses в "центре" документа для некоторых checks
                    # считаем чуть более значимыми (но очень мягко).
                    if 0.2 <= pos_f <= 0.8:
                        scores[idx] += position_mid_boost
            except (TypeError, ValueError):
                # Некорректное значение позиции — игнорируем
                pass

            # 3) Boost по path_titles: ищем важные слова в "хлебных крошках"
            if important_terms:
                path_titles = meta.get("path_titles") or []
                try:
                    titles_joined = " ".join(str(t) for t in path_titles).lower()
                except Exception:
                    titles_joined = ""
                if titles_joined and any(key in titles_joined for key in important_terms):
                    scores[idx] += path_titles_boost

            # 4) Boost по summary: если краткое summary содержит важные слова
            if important_terms:
                summary = str(meta.get("summary", "") or "").lower()
                if summary and any(key in summary for key in important_terms):
                    scores[idx] += summary_boost

        return scores
