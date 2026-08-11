# tests/unit/engine/detectors/test_llm_detector_grounding.py

"""
Tests for LLMDetector grounding score calculation and confidence adjustment.

Covers:
- _calculate_grounding_score: exact match, token overlap, empty evidence
- _build_result: confidence adjustment based on grounding
- grounding metadata in details
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from engine.detectors.llm_detector import (
    LLMDetector,
    _GROUNDING_UNCLEAR_THRESHOLD,
    _GROUNDING_WARN_THRESHOLD,
    _GROUNDING_CONFIDENCE_CAP_WEAK,
    _GROUNDING_CONFIDENCE_CAP_VERY_WEAK,
)
from engine.detectors.models import RetrievedChunk


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_chunk(text: str, element_id: str = "elem1") -> RetrievedChunk:
    return RetrievedChunk(
        element_id=element_id,
        text=text,
        page=1,
        clause_uid="main_contract:1.1",
        bbox=[],
        dense_score=0.8,
        sparse_score=0.5,
        metadata_score=0.2,
        combined_score=0.75,
    )


def _make_response(
    found: bool = True,
    evidence: str = "",
    confidence: float = 0.9,
) -> MagicMock:
    resp = MagicMock()
    resp.found = found
    resp.evidence = evidence
    resp.confidence = confidence
    resp.clause = None
    resp.provider = "test"
    resp.model = "test-model"
    resp.tokens_used = 100
    resp.prompt_tokens = 80
    resp.completion_tokens = 20
    resp.parse_success = True
    resp.raw_response = ""
    resp.reasoning = None
    return resp


def _make_detector() -> LLMDetector:
    client = MagicMock()
    client.is_available.return_value = True
    return LLMDetector(client=client)


# ─── _calculate_grounding_score tests ────────────────────────────────────────


class TestCalculateGroundingScore:

    def test_exact_substring_returns_1(self):
        """Exact substring match → grounding score = 1.0."""
        chunk = _make_chunk("Стороны несут ответственность за нарушение договора.")
        score = LLMDetector._calculate_grounding_score(
            "ответственность за нарушение",
            [chunk],
        )
        assert score == 1.0

    def test_exact_match_case_insensitive(self):
        """Case-insensitive exact match → 1.0."""
        chunk = _make_chunk("ОТВЕТСТВЕННОСТЬ ЗА НАРУШЕНИЕ ДОГОВОРА.")
        score = LLMDetector._calculate_grounding_score(
            "ответственность за нарушение",
            [chunk],
        )
        assert score == 1.0

    def test_high_token_overlap_returns_high_score(self):
        """Evidence with most words in chunk → high score."""
        chunk = _make_chunk(
            "Покупатель обязан оплатить стоимость объекта в течение тридцати дней."
        )
        # 4 из 5 слов evidence есть в chunk
        score = LLMDetector._calculate_grounding_score(
            "оплатить стоимость объекта тридцати",
            [chunk],
        )
        assert score >= 0.5

    def test_low_token_overlap_returns_low_score(self):
        """Evidence with few matching words → low score."""
        chunk = _make_chunk("Стороны договорились о следующем.")
        score = LLMDetector._calculate_grounding_score(
            "покупатель обязан уплатить неустойку в размере пяти процентов",
            [chunk],
        )
        assert score < _GROUNDING_WARN_THRESHOLD

    def test_no_overlap_returns_zero(self):
        """No word overlap → score = 0.0."""
        chunk = _make_chunk("абвгд ежзий клмно прстуф хцчшщ")
        score = LLMDetector._calculate_grounding_score(
            "покупатель продавец договор",
            [chunk],
        )
        assert score == 0.0

    def test_empty_evidence_returns_zero(self):
        """Empty evidence → 0.0."""
        chunk = _make_chunk("любой текст")
        score = LLMDetector._calculate_grounding_score("", [chunk])
        assert score == 0.0

    def test_empty_chunks_returns_zero(self):
        """Empty chunks list → 0.0."""
        score = LLMDetector._calculate_grounding_score("evidence text", [])
        assert score == 0.0

    def test_multiple_chunks_uses_best_match(self):
        """Score is max over all chunks."""
        chunk_bad = _make_chunk("абсолютно другой текст", "elem1")
        chunk_good = _make_chunk(
            "Покупатель обязан оплатить стоимость объекта.",
            "elem2",
        )
        score = LLMDetector._calculate_grounding_score(
            "покупатель обязан оплатить",
            [chunk_bad, chunk_good],
        )
        assert score >= 0.5

    def test_score_bounded_between_0_and_1(self):
        """Score must always be in [0.0, 1.0]."""
        chunk = _make_chunk("а б в г д е ж з и к")
        score = LLMDetector._calculate_grounding_score("а б в г д", [chunk])
        assert 0.0 <= score <= 1.0


# ─── _build_result confidence adjustment tests ───────────────────────────────


class TestBuildResultGrounding:

    def test_high_grounding_preserves_confidence(self):
        """
        When evidence is exactly in chunk text,
        confidence must NOT be lowered.
        """
        detector = _make_detector()
        chunk = _make_chunk("Стороны несут ответственность за нарушение условий договора.")
        response = _make_response(
            found=True,
            evidence="ответственность за нарушение",
            confidence=0.9,
        )

        result = detector._build_result(response, [chunk])

        assert result.confidence == pytest.approx(0.9, abs=0.01)
        assert result.details["grounding_score"] == 1.0
        assert result.details["evidence_grounded"] is True

    def test_weak_grounding_caps_confidence(self):
        """
        When evidence has weak token overlap (< WARN threshold),
        confidence must be capped at _GROUNDING_CONFIDENCE_CAP_WEAK.
        """
        detector = _make_detector()
        # Chunk и evidence почти не пересекаются
        chunk = _make_chunk("абвгд ежзий клмно прстуф хцчшщ ыьэюя")
        response = _make_response(
            found=True,
            evidence="покупатель обязан уплатить неустойку пяти процентов",
            confidence=0.9,
        )

        result = detector._build_result(response, [chunk])

        assert result.confidence <= _GROUNDING_CONFIDENCE_CAP_WEAK
        assert result.details["grounding_score"] < _GROUNDING_WARN_THRESHOLD
        assert result.details["evidence_grounded"] is False

    def test_very_weak_grounding_caps_confidence_lower(self):
        """
        When grounding is below UNCLEAR threshold,
        confidence must be capped at _GROUNDING_CONFIDENCE_CAP_VERY_WEAK.
        """
        detector = _make_detector()
        chunk = _make_chunk("совершенно другой текст без общих слов")
        response = _make_response(
            found=True,
            evidence="квантовая физика нейронные сети блокчейн",
            confidence=0.95,
        )

        result = detector._build_result(response, [chunk])

        assert result.confidence <= _GROUNDING_CONFIDENCE_CAP_VERY_WEAK
        assert result.details["grounding_score"] < _GROUNDING_UNCLEAR_THRESHOLD

    def test_grounding_score_in_details(self):
        """
        grounding_score and evidence_grounded must always be present in details.
        """
        detector = _make_detector()
        chunk = _make_chunk("договор купли-продажи")
        response = _make_response(found=True, evidence="договор", confidence=0.8)

        result = detector._build_result(response, [chunk])

        assert "grounding_score" in result.details
        assert "evidence_grounded" in result.details
        assert isinstance(result.details["grounding_score"], float)
        assert isinstance(result.details["evidence_grounded"], bool)

    def test_no_evidence_grounding_score_is_zero(self):
        """
        When found=True but evidence is empty,
        grounding_score must be 0.0.
        """
        detector = _make_detector()
        chunk = _make_chunk("любой текст")
        response = _make_response(found=True, evidence="", confidence=0.8)

        result = detector._build_result(response, [chunk])

        assert result.details["grounding_score"] == 0.0

    def test_found_false_confidence_not_adjusted(self):
        """
        When found=False, confidence must not be adjusted by grounding.
        Grounding is only relevant when LLM claims to have found something.
        """
        detector = _make_detector()
        chunk = _make_chunk("любой текст")
        response = _make_response(found=False, evidence="", confidence=0.1)

        result = detector._build_result(response, [chunk])

        assert result.confidence == pytest.approx(0.1, abs=0.01)
        assert result.found is False

    def test_original_confidence_preserved_when_grounding_good(self):
        """
        When grounding >= WARN_THRESHOLD, original LLM confidence
        must be returned unchanged.
        """
        detector = _make_detector()
        # Evidence точно в тексте → grounding = 1.0
        chunk = _make_chunk("продавец передаёт объект покупателю по акту приёма-передачи")
        response = _make_response(
            found=True,
            evidence="передаёт объект покупателю",
            confidence=0.75,
        )

        result = detector._build_result(response, [chunk])

        # grounding = 1.0, confidence не должен быть cap'нут
        assert result.confidence == pytest.approx(0.75, abs=0.01)


        