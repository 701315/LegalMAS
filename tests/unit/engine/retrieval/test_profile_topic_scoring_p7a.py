"""Tests for P7a: retrieval profile topic scoring with supporting topics."""

import pytest

from core.config import settings
from engine.retrieval.engine import (
    RetrievalEngine,
    _resolve_profile_topics,
    _resolve_profile_supporting_topics,
)


def test_resolve_required_topics_returns_expected_values():
    topics = _resolve_profile_topics("governing_law_check")
    assert isinstance(topics, frozenset)
    assert "governing_law" in topics
    assert "choice_of_law" in topics


def test_resolve_supporting_topics_returns_expected_values():
    topics = _resolve_profile_supporting_topics("governing_law_check")
    assert isinstance(topics, frozenset)
    assert "jurisdiction" in topics
    assert "dispute_resolution" in topics


def test_resolve_profile_topics_none_returns_empty():
    assert _resolve_profile_topics(None) == frozenset()
    assert _resolve_profile_supporting_topics(None) == frozenset()


def test_resolve_unknown_profile_returns_empty():
    assert _resolve_profile_topics("unknown_profile_xyz") == frozenset()
    assert _resolve_profile_supporting_topics("unknown_profile_xyz") == frozenset()


def test_required_topic_scores_higher_than_supporting_topic(monkeypatch):
    monkeypatch.setattr(settings, "RUNNER_EMBEDDINGS_ENABLED", False)
    monkeypatch.setattr(settings, "RUNNER_METADATA_TOPIC_MATCH_BOOST", 0.6)
    monkeypatch.setattr(settings, "RUNNER_METADATA_TOPIC_SUPPORTING_BOOST", 0.3)

    chunks = [
        {
            "id": "required",
            "text": "chunk with required topic",
            "metadata": {"topic_tags": ["governing_law"]},
        },
        {
            "id": "supporting",
            "text": "chunk with supporting topic",
            "metadata": {"topic_tags": ["jurisdiction"]},
        },
        {
            "id": "neutral",
            "text": "chunk without profile topics",
            "metadata": {"topic_tags": ["payment_terms"]},
        },
    ]

    engine = RetrievalEngine(
        chunks,
        retrieval_profile_id="governing_law_check",
    )

    scores = engine._compute_metadata_scores()

    assert scores[0] > scores[1] > scores[2]
    assert float(scores[0]) == pytest.approx(0.6, abs=1e-5)
    assert float(scores[1]) == pytest.approx(0.3, abs=1e-5)
    assert float(scores[2]) == pytest.approx(0.0, abs=1e-5)


def test_required_match_is_not_double_counted_with_supporting(monkeypatch):
    monkeypatch.setattr(settings, "RUNNER_EMBEDDINGS_ENABLED", False)
    monkeypatch.setattr(settings, "RUNNER_METADATA_TOPIC_MATCH_BOOST", 0.6)
    monkeypatch.setattr(settings, "RUNNER_METADATA_TOPIC_SUPPORTING_BOOST", 0.3)

    chunks = [
        {
            "id": "both",
            "text": "chunk with both required and supporting topics",
            "metadata": {"topic_tags": ["governing_law", "jurisdiction"]},
        },
    ]

    engine = RetrievalEngine(
        chunks,
        retrieval_profile_id="governing_law_check",
    )

    scores = engine._compute_metadata_scores()

    assert float(scores[0]) == pytest.approx(0.6, abs=1e-5)


def test_supporting_topics_exist_for_p6_profiles():
    for profile_id in [
        "rent_check",
        "interest_rate_check",
        "license_scope_check",
        "security_check",
        "acceptance_check",
        "change_of_control_check",
    ]:
        topics = _resolve_profile_supporting_topics(profile_id)
        assert topics, f"{profile_id} should have supporting topics"
