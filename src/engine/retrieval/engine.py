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

import re
from collections.abc import Iterable
from typing import Any

import numpy as np
from rank_bm25 import BM25Okapi

from core.config import settings
from engine.retrieval.models import RetrievalChunk
from services.embeddings.embedding_service import embedding_service


# =============================================================================
# Module-level tokenization
# =============================================================================

# Паттерн для удаления пунктуации из текста перед BM25-токенизацией.
#
# Оставляем: буквы (любые Unicode), цифры, underscore (\w), пробелы (\s).
# Удаляем: всё остальное — точки, запятые, скобки, кавычки и т.д.
#
# Почему \w а не [a-zа-яё]:
#   \w в Python с Unicode покрывает все буквы и цифры без явного перечисления
#   алфавитов. Работает корректно для русского, английского и смешанных текстов.
#
# Почему НЕ разбиваем дополнительно по точке:
#   "3.1.2"   → после sub → "3 1 2"   → токены ["3", "1", "2"]
#   "п.3.1.2" → после sub → "п 3 1 2" → токены ["п", "3", "1", "2"]
#   Запрос "п.3.1.2" даёт те же токены → BM25 матчинг корректен.
#   Разбивать отдельно не нужно — re.sub справляется автоматически.
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    """
    Нормализованная токенизация для BM25-индекса и BM25-запросов.

    Алгоритм:
      1. lower()         — привести к нижнему регистру
      2. re.sub(punct)   — заменить пунктуацию на пробел
      3. split()         — разбить по пробелам
      4. filter(None)    — убрать пустые токены

    Симметричность:
      ОБЯЗАТЕЛЬНО использовать одну и ту же функцию для индексирования
      корпуса (__init__) и для токенизации запроса (search).
      Нарушение симметрии → BM25 scores деградируют к нулю.

    Примеры:
      "ПОКУПАТЕЛЬ обязан," → ["покупатель", "обязан"]
      "force-majeure"      → ["force", "majeure"]
      "Статья 3.1.2:"      → ["статья", "3", "1", "2"]
      "party's obligation" → ["party", "s", "obligation"]
      "обязан."            → ["обязан"]

    Args:
        text: исходный текст чанка или поисковый запрос.

    Returns:
        Список нормализованных токенов, готовых для BM25Okapi.
    """
    if not text:
        return []
    lowered = text.lower()
    cleaned = _PUNCT_RE.sub(" ", lowered)
    return [tok for tok in cleaned.split() if tok]


# =============================================================================
# Module-level profile helpers
# =============================================================================

def _resolve_profile_topics(retrieval_profile_id: str | None) -> frozenset[str]:
    """
    Загрузить required_topics из retrieval profile — один раз до цикла по чанкам.

    Вызывается в _compute_metadata_scores() перед итерацией по чанкам,
    чтобы не делать N вызовов get_profile() — по одному на каждый чанк.

    Изоляция отказов:
      Любое исключение (profile не найден, реестр недоступен, импорт упал)
      → возвращаем пустой frozenset, scoring продолжается без topic boost.
      Это намеренно: profile topics — дополнительный сигнал, не критичный путь.

    Args:
        retrieval_profile_id: идентификатор профиля или None.

    Returns:
        frozenset нормализованных (lower().strip()) topic-меток,
        или frozenset() если профиль не задан / не найден / ошибка.
    """
    if not retrieval_profile_id:
        return frozenset()

    try:
        from engine.playbook.retrieval_profiles import get_profile as _get_profile

        profile = _get_profile(retrieval_profile_id)
        if profile is None:
            return frozenset()

        required = profile.required_topics
        if not required:
            return frozenset()

        return frozenset(
            t.lower().strip()
            for t in required
            if isinstance(t, str) and t.strip()
        )
    except Exception:
        # Намеренно проглатываем: profile topics — опциональный сигнал.
        # Если реестр недоступен — retrieval продолжается без topic boost.
        return frozenset()


def _resolve_profile_supporting_topics(
    retrieval_profile_id: str | None,
) -> frozenset[str]:
    """
    Загрузить supporting_topics из retrieval profile — один раз до цикла по чанкам.

    Supporting topics дают более слабый boost чем required topics,
    но помогают поднимать контекстно-релевантные chunks.
    """
    if not retrieval_profile_id:
        return frozenset()

    try:
        from engine.playbook.retrieval_profiles import get_profile as _get_profile

        profile = _get_profile(retrieval_profile_id)
        if profile is None:
            return frozenset()

        supporting = profile.supporting_topics
        if not supporting:
            return frozenset()

        return frozenset(
            t.lower().strip()
            for t in supporting
            if isinstance(t, str) and t.strip()
        )
    except Exception:
        return frozenset()


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

    def __init__(
        self,
        chunks: Iterable[Any],
        important_terms: Iterable[str] | None = None,
        negative_keywords: Iterable[str] | None = None,
        preferred_unit_types: Iterable[str] | None = None,
        excluded_unit_types: Iterable[str] | None = None,
        preferred_clause_functions: Iterable[str] | None = None,
        position_bias: Any | None = None,
        retrieval_profile_id: str | None = None,
    ):
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

        # Нормализуем retrieval signals для metadata-aware scoring.
        def _normalize_terms(raw: Iterable[str] | None) -> list[str]:
            if raw is None:
                return []

            out: list[str] = []
            for item in raw:
                if not isinstance(item, str):
                    continue
                normalized = " ".join(item.strip().lower().split())
                if normalized:
                    out.append(normalized)
            return out

        def _normalize_labels(raw: Iterable[str] | None) -> list[str]:
            if raw is None:
                return []

            out: list[str] = []
            for item in raw:
                if not isinstance(item, str):
                    continue
                normalized = item.strip().lower()
                if not normalized:
                    continue
                normalized = normalized.replace("-", "_").replace(" ", "_")
                while "__" in normalized:
                    normalized = normalized.replace("__", "_")
                normalized = normalized.strip("_")
                if normalized:
                    out.append(normalized)
            return out

        self.important_terms_lower = _normalize_terms(important_terms)
        self.negative_keywords_lower = _normalize_terms(negative_keywords)
        self.preferred_unit_types_lower = _normalize_labels(preferred_unit_types)
        self.excluded_unit_types_lower = _normalize_labels(excluded_unit_types)
        self.preferred_clause_functions_lower = _normalize_labels(preferred_clause_functions)
        self.position_bias = position_bias
        self.retrieval_profile_id: str | None = (
            str(retrieval_profile_id).strip() if retrieval_profile_id else None
        )

        # Если чанков нет — деградирующий режим (поиск ничего не вернёт).
        if not self.chunks:
            self.tokenized: list[list[str]] = []
            self.bm25: BM25Okapi | None = None
            self.emb_vectors: np.ndarray | None = None
            return

        # BM25 ожидает список списков токенов (слов).
        # Используем _tokenize() — нормализованную токенизацию с удалением
        # пунктуации и приведением к нижнему регистру.
        # ВАЖНО: та же функция используется в search() для токенизации запроса.
        # Симметрия corpus/query токенизации — обязательное условие корректного BM25.
        self.tokenized = [_tokenize(t) for t in texts_for_index]

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
            # Corpus chunks кодируются как "passage" — это требование E5-модели.
            # embedding_service.encode возвращает np.ndarray (N, D)
            self.emb_vectors = embedding_service.encode(original_texts, role="passage")
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
        # _tokenize() симметрична токенизации корпуса в __init__.
        # Нарушение симметрии corpus/query → BM25 scores деградируют к нулю.
        tokenized_query = _tokenize(query)
        bm25_scores = np.array(self.bm25.get_scores(tokenized_query), dtype=np.float32)

        # 2. Dense scores (cosine similarity), если включены
        if self.emb_vectors is not None:
            # Query кодируется как "query" — это требование E5-модели.
            # Поисковый запрос и корпус должны использовать разные префиксы.
            q_vec = embedding_service.encode([query], role="query")[0].astype(np.float32)
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
            chunk["score_breakdown"] = {
                "bm25_raw": float(bm25_scores[i_int]),
                "bm25_norm": float(bm25_norm[i_int]),
                "dense_raw": float(dense_scores[i_int]),
                "dense_norm": float(dense_norm[i_int]),
                "metadata_raw": float(metadata_scores[i_int]),
                "metadata_norm": float(meta_norm[i_int]),
                "weighted_sparse": float(settings.RUNNER_SPARSE_WEIGHT * bm25_norm[i_int]),
                "weighted_dense": float(settings.RUNNER_DENSE_WEIGHT * dense_norm[i_int]),
                "weighted_metadata": float(settings.RUNNER_METADATA_WEIGHT * meta_norm[i_int]),
                "combined_score": float(scores[i_int]),
            }
            result.append(chunk)

        return result

    def _compute_metadata_scores(self) -> np.ndarray:
        """
        Metadata-aware scoring for retrieval.

        Combines:
        0) chunk kind prior
        1) positive lexical hints in section_title / path_titles / summary
        2) semantic unit_type boost / penalty
        3) clause_function boost
        4) anti-boost by negative_keywords
        5) citability-aware scoring
        6) generic position prior + optional check-specific position_bias
        """
        n = len(self.chunks)
        scores = np.zeros(n, dtype=np.float32)

        if n == 0:
            return scores

        important_terms = getattr(self, "important_terms_lower", []) or []
        negative_keywords = getattr(self, "negative_keywords_lower", []) or []
        preferred_unit_types = getattr(self, "preferred_unit_types_lower", []) or []
        excluded_unit_types = getattr(self, "excluded_unit_types_lower", []) or []
        preferred_clause_functions = getattr(self, "preferred_clause_functions_lower", []) or []
        position_bias_cfg = getattr(self, "position_bias", None)

        kind_bonus_subclause = float(
            getattr(settings, "RUNNER_METADATA_KIND_BONUS_SUBCLAUSE", 0.3)
        )
        kind_penalty_section = float(
            getattr(settings, "RUNNER_METADATA_KIND_PENALTY_SECTION", 0.1)
        )
        section_title_boost = float(
            getattr(settings, "RUNNER_METADATA_SECTION_TITLE_BOOST", 1.0)
        )
        early_doc_boost = float(
            getattr(settings, "RUNNER_METADATA_EARLY_DOC_BOOST", 0.2)
        )
        early_doc_threshold = float(
            getattr(settings, "RUNNER_METADATA_EARLY_DOC_POSITION_THRESHOLD", 0.15)
        )
        path_titles_boost = float(
            getattr(settings, "RUNNER_METADATA_PATH_TITLES_BOOST", 0.5)
        )
        summary_boost = float(
            getattr(settings, "RUNNER_METADATA_SUMMARY_BOOST", 0.2)
        )

        unit_type_boost = float(
            getattr(settings, "RUNNER_METADATA_UNIT_TYPE_BOOST", 0.9)
        )
        unit_type_penalty = float(
            getattr(settings, "RUNNER_METADATA_UNIT_TYPE_PENALTY", 0.7)
        )
        clause_function_boost = float(
            getattr(settings, "RUNNER_METADATA_CLAUSE_FUNCTION_BOOST", 0.8)
        )
        negative_keyword_penalty = float(
            getattr(settings, "RUNNER_METADATA_NEGATIVE_KEYWORD_PENALTY", 0.8)
        )
        citability_high_boost = float(
            getattr(settings, "RUNNER_METADATA_CITABILITY_HIGH_BOOST", 0.25)
        )
        citability_medium_boost = float(
            getattr(settings, "RUNNER_METADATA_CITABILITY_MEDIUM_BOOST", 0.12)
        )
        citability_low_penalty = float(
            getattr(settings, "RUNNER_METADATA_CITABILITY_LOW_PENALTY", 0.08)
        )
        citability_score_weight = float(
            getattr(settings, "RUNNER_METADATA_CITABILITY_SCORE_WEIGHT", 0.25)
        )

        def _cfg_get(obj: Any, key: str, default: Any = None) -> Any:
            if obj is None:
                return default
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        position_scope = str(_cfg_get(position_bias_cfg, "scope", "auto") or "auto").strip().lower()
        position_boost = _cfg_get(position_bias_cfg, "boost", 0.0)

        raw_range = _cfg_get(position_bias_cfg, "preferred_range", None)
        if raw_range is None:
            raw_range = _cfg_get(position_bias_cfg, "range", None)

        position_range: tuple[float, float] | None = None
        if isinstance(raw_range, (list, tuple)) and len(raw_range) == 2:
            try:
                lo = float(raw_range[0])
                hi = float(raw_range[1])
                if 0.0 <= lo <= 1.0 and 0.0 <= hi <= 1.0 and hi >= lo:
                    position_range = (lo, hi)
            except (TypeError, ValueError):
                position_range = None

        # Загружаем required_topics и supporting_topics из retrieval profile
        # один раз до цикла. Supporting topics дают более слабый boost.
        profile_required_topics: frozenset[str] = _resolve_profile_topics(
            self.retrieval_profile_id
        )
        profile_supporting_topics: frozenset[str] = _resolve_profile_supporting_topics(
            self.retrieval_profile_id
        )

        for idx, ch in enumerate(self.chunks):
            # ИСПРАВЛЕНО: метаданные и текст теперь извлекаются внутри основного цикла.
            # Ранее из-за лишнего цикла выше переменные meta/text всегда указывали на последний чанк.
            meta = ch.get("metadata", {}) or {}
            text = str(ch.get("text", "") or "").lower()

            kind = str(meta.get("chunk_kind") or meta.get("kind") or "").lower()
            if kind in ("legal_unit", "subclause"):
                scores[idx] += kind_bonus_subclause
            elif kind == "section":
                scores[idx] -= kind_penalty_section

            # Structural preamble prior.
            #
            # Обоснование:
            # - effective_uid ending with __preamble__ — canonical structural identity,
            #   созданная document parser/structure builder.
            # - Преамбула является primary источником для party identification checks.
            # - Это universal structural invariant, не language/document-specific.
            # - Boost применяется только по structural identity, а не по тексту.
            effective_uid = str(meta.get("effective_uid") or "").lower()
            if effective_uid.endswith("__preamble__"):
                preamble_boost = float(
                    getattr(settings, "RUNNER_METADATA_PREAMBLE_BOOST", 1.0)
                )
                scores[idx] += preamble_boost

            title = str(meta.get("section_title", "") or "").lower()
            if title and important_terms and any(term in title for term in important_terms):
                scores[idx] += section_title_boost

            pos = (
                meta.get("position_ratio_within_segment")
                if meta.get("position_ratio_within_segment") is not None
                else meta.get("position_ratio_within_file")
                if meta.get("position_ratio_within_file") is not None
                else meta.get("position_ratio")
            )

            # Structural preamble position fallback.
            # If position is unavailable but unit carries canonical preamble identity,
            # treat it as position 0.0 for ALL position-based scoring.
            # This is a universal structural invariant: preamble is always
            # the document's logical start regardless of physical page layout.
            if pos is None and effective_uid.endswith("__preamble__"):
                pos = 0.0

            try:
                if pos is not None:
                    pos_f = float(pos)
                    # Early-document structural prior.
                    # Legal documents open with identification clauses
                    # (parties, subject matter, recitals) regardless of
                    # language or document type.
                    # Mild boost for early-document position, no penalty
                    # for mid/late document — neutral treatment.
                    # Replaces former position_mid_boost which systematically
                    # advantaged mid-document Definitions over preamble.
                    if pos_f <= early_doc_threshold:
                        scores[idx] += early_doc_boost
            except (TypeError, ValueError):
                pass

            path_titles = meta.get("path_titles") or []
            try:
                titles_joined = " ".join(str(t) for t in path_titles).lower()
            except Exception:
                titles_joined = ""

            if important_terms and titles_joined and any(term in titles_joined for term in important_terms):
                scores[idx] += path_titles_boost

            summary = str(meta.get("summary", "") or "").lower()
            if important_terms and summary and any(term in summary for term in important_terms):
                scores[idx] += summary_boost

            unit_type = str(meta.get("unit_type") or "").strip().lower()
            if unit_type:
                unit_type = unit_type.replace("-", "_").replace(" ", "_")
                if unit_type in preferred_unit_types:
                    scores[idx] += unit_type_boost
                if unit_type in excluded_unit_types:
                    scores[idx] -= unit_type_penalty

            clause_function = str(meta.get("clause_function") or "").strip().lower()
            if clause_function:
                clause_function = clause_function.replace("-", "_").replace(" ", "_")
                if clause_function in preferred_clause_functions:
                    scores[idx] += clause_function_boost

            # Profile-aware topic_tags boost.
            # Если у chunk есть topic_tags (из legal units enrichment)
            # и они совпадают с required_topics или supporting_topics профиля —
            # boost применяется как дополнительный retrieval signal.
            # Required topics дают сильный boost.
            # Supporting topics дают более слабый boost.
            # Работает только при наличии enrichment, поэтому не является
            # fallback или heuristic, а честным semantic signal.
            if profile_required_topics or profile_supporting_topics:
                chunk_topic_tags = meta.get("topic_tags") or []
                chunk_topics_lower = frozenset(
                    str(t).strip().lower() for t in chunk_topic_tags if t
                )
                if chunk_topics_lower:
                    if profile_required_topics & chunk_topics_lower:
                        topic_match_boost = float(
                            getattr(settings, "RUNNER_METADATA_TOPIC_MATCH_BOOST", 0.6)
                        )
                        scores[idx] += topic_match_boost
                    elif profile_supporting_topics & chunk_topics_lower:
                        topic_supporting_boost = float(
                            getattr(
                                settings,
                                "RUNNER_METADATA_TOPIC_SUPPORTING_BOOST",
                                0.3,
                            )
                        )
                        scores[idx] += topic_supporting_boost

            citability_band = str(
                meta.get("citability_band")
                or meta.get("citability")
                or ""
            ).strip().lower()
            if citability_band == "high":
                scores[idx] += citability_high_boost
            elif citability_band == "medium":
                scores[idx] += citability_medium_boost
            elif citability_band == "low":
                scores[idx] -= citability_low_penalty

            citability_score_raw = meta.get("citability_score")
            try:
                if citability_score_raw is not None:
                    citability_score = float(citability_score_raw)
                    citability_score = max(0.0, min(citability_score, 1.0))
                    scores[idx] += citability_score * citability_score_weight
            except (TypeError, ValueError):
                pass

            if negative_keywords:
                negative_hit = False
                if title and any(term in title for term in negative_keywords):
                    negative_hit = True
                elif titles_joined and any(term in titles_joined for term in negative_keywords):
                    negative_hit = True
                elif summary and any(term in summary for term in negative_keywords):
                    negative_hit = True
                elif text and any(term in text for term in negative_keywords):
                    negative_hit = True

                if negative_hit:
                    scores[idx] -= negative_keyword_penalty

            if position_range is not None and position_boost:
                # Определяем pos_candidate в зависимости от scope
                if position_scope == "segment":
                    pos_candidate = meta.get("position_ratio_within_segment")
                    if pos_candidate is None:
                        pos_candidate = meta.get("position_ratio_within_file")
                    if pos_candidate is None:
                        pos_candidate = meta.get("position_ratio")
                elif position_scope == "file":
                    pos_candidate = meta.get("position_ratio_within_file")
                    if pos_candidate is None:
                        pos_candidate = meta.get("position_ratio")
                else:  # auto
                    pos_candidate = meta.get("position_ratio_within_segment")
                    if pos_candidate is None:
                        pos_candidate = meta.get("position_ratio_within_file")
                    if pos_candidate is None:
                        pos_candidate = meta.get("position_ratio")

                # Reuse global preamble position fallback for position_bias range check.
                # pos was already resolved above (0.0 for preamble units without metadata).
                if pos_candidate is None and pos is not None:
                    pos_candidate = pos

                # Применяем position_bias boost если chunk попадает в preferred_range
                try:
                    if pos_candidate is not None:
                        pos_candidate_f = float(pos_candidate)
                        if position_range[0] <= pos_candidate_f <= position_range[1]:
                            scores[idx] += float(position_boost)
                except (TypeError, ValueError):
                    pass

        return scores
    


    