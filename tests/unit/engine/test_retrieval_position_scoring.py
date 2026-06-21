"""
Tests for retrieval metadata scoring — position priors and preamble fallback.

Covers:
- preamble chunk (pos=0.0) gets early_doc_boost
- mid-document chunk (pos=0.4) does NOT get early_doc_boost
- preamble without position_ratio in metadata gets pos=0.0 via structural fallback
- preamble_boost applied by effective_uid identity
- position_bias guard uses pos fallback for preamble
"""

import pytest
from unittest.mock import patch, MagicMock

import numpy as np


def _make_engine(chunks: list[dict], **kwargs):
    """Create RetrievalEngine with embeddings disabled to isolate metadata scoring."""
    with patch("core.config.settings") as mock_settings:
        mock_settings.RUNNER_EMBEDDINGS_ENABLED = False
        mock_settings.RUNNER_RETRIEVAL_TOP_K = 10
        mock_settings.RUNNER_SPARSE_WEIGHT = 0.3
        mock_settings.RUNNER_DENSE_WEIGHT = 0.6
        mock_settings.RUNNER_METADATA_WEIGHT = 0.1

        mock_settings.RUNNER_METADATA_KIND_BONUS_SUBCLAUSE = 0.3
        mock_settings.RUNNER_METADATA_KIND_PENALTY_SECTION = 0.1
        mock_settings.RUNNER_METADATA_SECTION_TITLE_BOOST = 1.0
        mock_settings.RUNNER_METADATA_EARLY_DOC_BOOST = 0.2
        mock_settings.RUNNER_METADATA_EARLY_DOC_POSITION_THRESHOLD = 0.15
        mock_settings.RUNNER_METADATA_PATH_TITLES_BOOST = 0.5
        mock_settings.RUNNER_METADATA_SUMMARY_BOOST = 0.2
        mock_settings.RUNNER_METADATA_PREAMBLE_BOOST = 1.0
        mock_settings.RUNNER_METADATA_TOPIC_MATCH_BOOST = 0.6

        mock_settings.RUNNER_METADATA_UNIT_TYPE_BOOST = 0.9
        mock_settings.RUNNER_METADATA_UNIT_TYPE_PENALTY = 0.7
        mock_settings.RUNNER_METADATA_CLAUSE_FUNCTION_BOOST = 0.8
        mock_settings.RUNNER_METADATA_NEGATIVE_KEYWORD_PENALTY = 0.8
        mock_settings.RUNNER_METADATA_CITABILITY_HIGH_BOOST = 0.25
        mock_settings.RUNNER_METADATA_CITABILITY_MEDIUM_BOOST = 0.12
        mock_settings.RUNNER_METADATA_CITABILITY_LOW_PENALTY = 0.08
        mock_settings.RUNNER_METADATA_CITABILITY_SCORE_WEIGHT = 0.25

        from engine.retrieval.engine import RetrievalEngine

        return RetrievalEngine(chunks, **kwargs)


def _chunk(
    chunk_id: str,
    text: str,
    effective_uid: str = "",
    position_ratio: float | None = None,
    chunk_kind: str = "legal_unit",
) -> dict:
    meta: dict = {
        "chunk_kind": chunk_kind,
        "effective_uid": effective_uid,
    }
    if position_ratio is not None:
        meta["position_ratio_within_segment"] = position_ratio
    return {"id": chunk_id, "text": text, "metadata": meta}


class TestEarlyDocBoost:
    def test_preamble_gets_early_doc_boost(self) -> None:
        chunks = [
            _chunk("c1", "Parties text", effective_uid="main:__preamble__", position_ratio=0.0),
            _chunk("c2", "Definitions text", effective_uid="main:1.1", position_ratio=0.35),
        ]
        engine = _make_engine(chunks)
        scores = engine._compute_metadata_scores()
        assert scores[0] > scores[1]

    def test_mid_document_does_not_get_early_boost(self) -> None:
        chunks = [
            _chunk("c1", "Mid text", effective_uid="main:5.1", position_ratio=0.5),
        ]
        engine = _make_engine(chunks)
        scores = engine._compute_metadata_scores()
        assert float(scores[0]) == pytest.approx(0.3, abs=0.01)

    def test_early_document_chunk_gets_boost(self) -> None:
        chunks = [
            _chunk("c1", "Early clause", effective_uid="main:1.0", position_ratio=0.05),
        ]
        engine = _make_engine(chunks)
        scores = engine._compute_metadata_scores()
        assert float(scores[0]) == pytest.approx(0.5, abs=0.01)


class TestPreambleFallback:
    def test_preamble_without_position_gets_zero_position(self) -> None:
        chunks = [
            _chunk("c1", "Preamble text", effective_uid="main:__preamble__"),
            _chunk("c2", "Some clause", effective_uid="main:2.1", position_ratio=0.4),
        ]
        engine = _make_engine(chunks)
        scores = engine._compute_metadata_scores()
        assert scores[0] > scores[1]
        assert float(scores[0]) == pytest.approx(1.5, abs=0.01)

    def test_non_preamble_without_position_gets_no_early_boost(self) -> None:
        chunks = [
            _chunk("c1", "Some clause", effective_uid="main:3.2"),
        ]
        engine = _make_engine(chunks)
        scores = engine._compute_metadata_scores()
        assert float(scores[0]) == pytest.approx(0.3, abs=0.01)


class TestPositionBiasGuardFallback:
    def test_preamble_gets_position_bias_boost_via_fallback(self) -> None:
        chunks = [
            _chunk("c1", "Preamble text", effective_uid="main:__preamble__"),
        ]
        position_bias = {
            "scope": "auto",
            "boost": 0.5,
            "preferred_range": [0.0, 0.1],
        }
        engine = _make_engine(chunks, position_bias=position_bias)
        scores = engine._compute_metadata_scores()
        assert float(scores[0]) == pytest.approx(2.0, abs=0.01)

    def test_non_preamble_without_position_does_not_get_position_bias(self) -> None:
        chunks = [
            _chunk("c1", "Some clause", effective_uid="main:4.1"),
        ]
        position_bias = {
            "scope": "auto",
            "boost": 0.5,
            "preferred_range": [0.0, 0.1],
        }
        engine = _make_engine(chunks, position_bias=position_bias)
        scores = engine._compute_metadata_scores()
        assert float(scores[0]) == pytest.approx(0.3, abs=0.01)