"""
Tests for retrieval tokenization and profile resolution.

Покрывает:
- _tokenize(): нормализация, пунктуация, регистр, симметрия corpus/query
- _resolve_profile_topics(): изоляция ошибок, нормализация, пустые значения
- RetrievalEngine: BM25 находит совпадение после нормализации
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from engine.retrieval.engine import RetrievalEngine, _resolve_profile_topics, _tokenize


# =============================================================================
# _tokenize()
# =============================================================================

class TestTokenize:
    """Unit-тесты функции _tokenize()."""

    def test_empty_string_returns_empty_list(self) -> None:
        assert _tokenize("") == []

    def test_lowercase_conversion(self) -> None:
        assert _tokenize("ПОКУПАТЕЛЬ") == ["покупатель"]

    def test_trailing_punctuation_removed(self) -> None:
        assert _tokenize("обязан.") == ["обязан"]
        assert _tokenize("обязан,") == ["обязан"]
        assert _tokenize("обязан!") == ["обязан"]

    def test_hyphenated_term_split(self) -> None:
        """force-majeure должен разбиться на два токена."""
        result = _tokenize("force-majeure")
        assert result == ["force", "majeure"]

    def test_legal_article_number(self) -> None:
        """Номер статьи разбивается по точкам."""
        result = _tokenize("Статья 3.1.2:")
        assert result == ["статья", "3", "1", "2"]

    def test_possessive_apostrophe(self) -> None:
        """Апостроф удаляется."""
        result = _tokenize("party's obligation")
        assert result == ["party", "s", "obligation"]

    def test_mixed_russian_english(self) -> None:
        """Смешанный текст токенизируется корректно."""
        result = _tokenize("ПОКУПАТЕЛЬ (Buyer) обязан.")
        assert result == ["покупатель", "buyer", "обязан"]

    def test_multiple_spaces_collapsed(self) -> None:
        """Множественные пробелы не дают пустых токенов."""
        result = _tokenize("слово   другое")
        assert result == ["слово", "другое"]
        assert "" not in result

    def test_only_punctuation_returns_empty(self) -> None:
        """Строка только из пунктуации → пустой список."""
        result = _tokenize(".,;:!?")
        assert result == []

    def test_cyrillic_preserved(self) -> None:
        """Кириллица остаётся."""
        result = _tokenize("договор купли-продажи")
        assert "договор" in result
        assert "купли" in result
        assert "продажи" in result

    def test_numbers_preserved(self) -> None:
        """Цифры остаются как токены."""
        result = _tokenize("пункт 42")
        assert result == ["пункт", "42"]

    def test_symmetry_corpus_and_query(self) -> None:
        """
        Критически важно: токенизация корпуса и запроса должна быть симметричной.
        Один и тот же текст должен давать одинаковые токены независимо от
        того, индексируем мы его или ищем по нему.
        """
        corpus_text = "ПОКУПАТЕЛЬ обязан уплатить сумму 100,000 руб."
        query_text = "покупатель обязан уплатить сумму 100 000 руб"

        corpus_tokens = set(_tokenize(corpus_text))
        query_tokens = set(_tokenize(query_text))

        # Ключевые слова должны совпадать после нормализации
        assert "покупатель" in corpus_tokens
        assert "покупатель" in query_tokens
        assert "обязан" in corpus_tokens
        assert "обязан" in query_tokens
        assert "уплатить" in corpus_tokens
        assert "уплатить" in query_tokens


# =============================================================================
# _resolve_profile_topics()
# =============================================================================

class TestResolveProfileTopics:
    """Unit-тесты функции _resolve_profile_topics()."""

    def test_none_returns_empty_frozenset(self) -> None:
        result = _resolve_profile_topics(None)
        assert result == frozenset()
        assert isinstance(result, frozenset)

    def test_empty_string_returns_empty_frozenset(self) -> None:
        result = _resolve_profile_topics("")
        assert result == frozenset()

    def test_profile_not_found_returns_empty(self) -> None:
        with patch(
            "engine.retrieval.engine._resolve_profile_topics",
            wraps=_resolve_profile_topics,
        ):
            with patch(
                "engine.playbook.retrieval_profiles.get_profile",
                return_value=None,
            ):
                result = _resolve_profile_topics("nonexistent_profile")
        assert result == frozenset()

    def test_import_error_returns_empty(self) -> None:
        """Если модуль retrieval_profiles недоступен — возвращаем пустой frozenset."""
        import builtins
        real_import = builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if "retrieval_profiles" in name:
                raise ImportError("module not found")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_mock_import):
            result = _resolve_profile_topics("some_profile")

        assert result == frozenset()

    def test_topics_normalized_to_lowercase(self) -> None:
        mock_profile = MagicMock()
        mock_profile.required_topics = ["Liability", "FORCE MAJEURE", "indemnity"]

        with patch(
            "engine.playbook.retrieval_profiles.get_profile",
            return_value=mock_profile,
        ):
            result = _resolve_profile_topics("test_profile")

        assert "liability" in result
        assert "force majeure" in result
        assert "indemnity" in result
        # Оригинальные значения не должны присутствовать
        assert "Liability" not in result
        assert "FORCE MAJEURE" not in result

    def test_empty_topics_list_returns_empty(self) -> None:
        mock_profile = MagicMock()
        mock_profile.required_topics = []

        with patch(
            "engine.playbook.retrieval_profiles.get_profile",
            return_value=mock_profile,
        ):
            result = _resolve_profile_topics("test_profile")

        assert result == frozenset()

    def test_none_topics_returns_empty(self) -> None:
        mock_profile = MagicMock()
        mock_profile.required_topics = None

        with patch(
            "engine.playbook.retrieval_profiles.get_profile",
            return_value=mock_profile,
        ):
            result = _resolve_profile_topics("test_profile")

        assert result == frozenset()

    def test_non_string_topics_filtered(self) -> None:
        """Нестроковые элементы в required_topics игнорируются."""
        mock_profile = MagicMock()
        mock_profile.required_topics = ["liability", None, 42, "indemnity", ""]

        with patch(
            "engine.playbook.retrieval_profiles.get_profile",
            return_value=mock_profile,
        ):
            result = _resolve_profile_topics("test_profile")

        assert result == frozenset({"liability", "indemnity"})

    def test_returns_frozenset_type(self) -> None:
        """Результат всегда frozenset — иммутабельный, hashable."""
        mock_profile = MagicMock()
        mock_profile.required_topics = ["liability"]

        with patch(
            "engine.playbook.retrieval_profiles.get_profile",
            return_value=mock_profile,
        ):
            result = _resolve_profile_topics("test_profile")

        assert isinstance(result, frozenset)


# =============================================================================
# RetrievalEngine — интеграционные тесты токенизации
# =============================================================================

class TestRetrievalEngineTokenization:
    """
    Интеграционные тесты: BM25 находит совпадения после нормализации.
    embeddings отключены через patch settings.
    """

    def _make_engine(self, chunks: list[dict]) -> RetrievalEngine:
        with patch("engine.retrieval.engine.settings") as mock_settings:
            mock_settings.RUNNER_EMBEDDINGS_ENABLED = False
            mock_settings.RUNNER_RETRIEVAL_TOP_K = 5
            mock_settings.RUNNER_SPARSE_WEIGHT = 1.0
            mock_settings.RUNNER_DENSE_WEIGHT = 0.0
            mock_settings.RUNNER_METADATA_WEIGHT = 0.0
            engine = RetrievalEngine(chunks=chunks)
        return engine

    def test_uppercase_chunk_found_by_lowercase_query(self) -> None:
        """
        BM25 должен найти чанк с ПОКУПАТЕЛЬ при запросе 'покупатель'.
        До патча: .split() давал ['ПОКУПАТЕЛЬ'] vs ['покупатель'] — промах.
        После патча: оба токенизируются в ['покупатель'] — совпадение.
        """
        chunks = [
            {"id": "1", "text": "ПОКУПАТЕЛЬ обязан уплатить сумму", "metadata": {}},
            {"id": "2", "text": "совершенно другой текст про аренду", "metadata": {}},
        ]

        with patch("engine.retrieval.engine.settings") as mock_settings:
            mock_settings.RUNNER_EMBEDDINGS_ENABLED = False
            mock_settings.RUNNER_RETRIEVAL_TOP_K = 5
            mock_settings.RUNNER_SPARSE_WEIGHT = 1.0
            mock_settings.RUNNER_DENSE_WEIGHT = 0.0
            mock_settings.RUNNER_METADATA_WEIGHT = 0.0
            # metadata boost constants
            mock_settings.RUNNER_METADATA_KIND_BONUS_SUBCLAUSE = 0.0
            mock_settings.RUNNER_METADATA_KIND_PENALTY_SECTION = 0.0
            mock_settings.RUNNER_METADATA_SECTION_TITLE_BOOST = 0.0
            mock_settings.RUNNER_METADATA_EARLY_DOC_BOOST = 0.0
            mock_settings.RUNNER_METADATA_EARLY_DOC_POSITION_THRESHOLD = 0.15
            mock_settings.RUNNER_METADATA_PATH_TITLES_BOOST = 0.0
            mock_settings.RUNNER_METADATA_SUMMARY_BOOST = 0.0
            mock_settings.RUNNER_METADATA_PREAMBLE_BOOST = 0.0
            mock_settings.RUNNER_METADATA_TOPIC_MATCH_BOOST = 0.0
            mock_settings.RUNNER_METADATA_UNIT_TYPE_BOOST = 0.0
            mock_settings.RUNNER_METADATA_UNIT_TYPE_PENALTY = 0.0
            mock_settings.RUNNER_METADATA_CLAUSE_FUNCTION_BOOST = 0.0
            mock_settings.RUNNER_METADATA_NEGATIVE_KEYWORD_PENALTY = 0.0
            mock_settings.RUNNER_METADATA_CITABILITY_HIGH_BOOST = 0.0
            mock_settings.RUNNER_METADATA_CITABILITY_MEDIUM_BOOST = 0.0
            mock_settings.RUNNER_METADATA_CITABILITY_LOW_PENALTY = 0.0
            mock_settings.RUNNER_METADATA_CITABILITY_SCORE_WEIGHT = 0.0

            engine = RetrievalEngine(chunks=chunks)
            results = engine.search("покупатель обязан", top_k=2)

        assert len(results) > 0
        top_result = results[0]
        assert top_result["id"] == "1", (
            f"Ожидался чанк '1' (ПОКУПАТЕЛЬ), получен '{top_result['id']}'. "
            f"Вероятно, токенизация несимметрична."
        )

    def test_punctuation_in_query_does_not_break_match(self) -> None:
        """
        Запрос с пунктуацией должен находить чанк без пунктуации.
        """
        chunks = [
            {"id": "1", "text": "обязательство покупателя", "metadata": {}},
            {"id": "2", "text": "права продавца на расторжение", "metadata": {}},
        ]

        with patch("engine.retrieval.engine.settings") as mock_settings:
            mock_settings.RUNNER_EMBEDDINGS_ENABLED = False
            mock_settings.RUNNER_RETRIEVAL_TOP_K = 5
            mock_settings.RUNNER_SPARSE_WEIGHT = 1.0
            mock_settings.RUNNER_DENSE_WEIGHT = 0.0
            mock_settings.RUNNER_METADATA_WEIGHT = 0.0
            mock_settings.RUNNER_METADATA_KIND_BONUS_SUBCLAUSE = 0.0
            mock_settings.RUNNER_METADATA_KIND_PENALTY_SECTION = 0.0
            mock_settings.RUNNER_METADATA_SECTION_TITLE_BOOST = 0.0
            mock_settings.RUNNER_METADATA_EARLY_DOC_BOOST = 0.0
            mock_settings.RUNNER_METADATA_EARLY_DOC_POSITION_THRESHOLD = 0.15
            mock_settings.RUNNER_METADATA_PATH_TITLES_BOOST = 0.0
            mock_settings.RUNNER_METADATA_SUMMARY_BOOST = 0.0
            mock_settings.RUNNER_METADATA_PREAMBLE_BOOST = 0.0
            mock_settings.RUNNER_METADATA_TOPIC_MATCH_BOOST = 0.0
            mock_settings.RUNNER_METADATA_UNIT_TYPE_BOOST = 0.0
            mock_settings.RUNNER_METADATA_UNIT_TYPE_PENALTY = 0.0
            mock_settings.RUNNER_METADATA_CLAUSE_FUNCTION_BOOST = 0.0
            mock_settings.RUNNER_METADATA_NEGATIVE_KEYWORD_PENALTY = 0.0
            mock_settings.RUNNER_METADATA_CITABILITY_HIGH_BOOST = 0.0
            mock_settings.RUNNER_METADATA_CITABILITY_MEDIUM_BOOST = 0.0
            mock_settings.RUNNER_METADATA_CITABILITY_LOW_PENALTY = 0.0
            mock_settings.RUNNER_METADATA_CITABILITY_SCORE_WEIGHT = 0.0

            engine = RetrievalEngine(chunks=chunks)
            results = engine.search("обязательство, покупателя!", top_k=2)

        assert len(results) > 0
        assert results[0]["id"] == "1"

    def test_get_profile_called_once_not_per_chunk(self) -> None:
        """
        _resolve_profile_topics() должна вызываться один раз,
        а не N раз (по числу чанков).
        """
        chunks = [
            {"id": str(i), "text": f"текст чанка номер {i}", "metadata": {}}
            for i in range(10)
        ]

        mock_profile = MagicMock()
        mock_profile.required_topics = ["liability"]

        call_count = 0

        def _counting_get_profile(profile_id: str):
            nonlocal call_count
            call_count += 1
            return mock_profile

        with (
            patch("engine.retrieval.engine.settings") as mock_settings,
            patch(
                "engine.playbook.retrieval_profiles.get_profile",
                side_effect=_counting_get_profile,
            ),
        ):
            mock_settings.RUNNER_EMBEDDINGS_ENABLED = False
            mock_settings.RUNNER_RETRIEVAL_TOP_K = 5
            mock_settings.RUNNER_SPARSE_WEIGHT = 0.5
            mock_settings.RUNNER_DENSE_WEIGHT = 0.0
            mock_settings.RUNNER_METADATA_WEIGHT = 0.5
            mock_settings.RUNNER_METADATA_KIND_BONUS_SUBCLAUSE = 0.0
            mock_settings.RUNNER_METADATA_KIND_PENALTY_SECTION = 0.0
            mock_settings.RUNNER_METADATA_SECTION_TITLE_BOOST = 0.0
            mock_settings.RUNNER_METADATA_EARLY_DOC_BOOST = 0.0
            mock_settings.RUNNER_METADATA_EARLY_DOC_POSITION_THRESHOLD = 0.15
            mock_settings.RUNNER_METADATA_PATH_TITLES_BOOST = 0.0
            mock_settings.RUNNER_METADATA_SUMMARY_BOOST = 0.0
            mock_settings.RUNNER_METADATA_PREAMBLE_BOOST = 0.0
            mock_settings.RUNNER_METADATA_TOPIC_MATCH_BOOST = 0.6
            mock_settings.RUNNER_METADATA_UNIT_TYPE_BOOST = 0.0
            mock_settings.RUNNER_METADATA_UNIT_TYPE_PENALTY = 0.0
            mock_settings.RUNNER_METADATA_CLAUSE_FUNCTION_BOOST = 0.0
            mock_settings.RUNNER_METADATA_NEGATIVE_KEYWORD_PENALTY = 0.0
            mock_settings.RUNNER_METADATA_CITABILITY_HIGH_BOOST = 0.0
            mock_settings.RUNNER_METADATA_CITABILITY_MEDIUM_BOOST = 0.0
            mock_settings.RUNNER_METADATA_CITABILITY_LOW_PENALTY = 0.0
            mock_settings.RUNNER_METADATA_CITABILITY_SCORE_WEIGHT = 0.0

            engine = RetrievalEngine(
                chunks=chunks,
                retrieval_profile_id="test_profile",
            )
            engine.search("текст", top_k=5)

        assert call_count == 1, (
            f"get_profile() вызван {call_count} раз вместо 1. "
            f"Вероятно, вызов остался внутри цикла по чанкам."
        )


        