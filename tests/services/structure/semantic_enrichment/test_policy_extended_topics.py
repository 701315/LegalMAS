"""Test that enrichment policy uses EXTENDED_TOPICS whitelist."""

from services.structure.semantic_enrichment._policy import _normalize_topics
from services.structure.topic_tagger import CORE_TOPICS, EXTENDED_TOPICS


def test_core_topic_accepted():
    accepted, rejected = _normalize_topics(["rent", "pledge"], max_topics=10)
    assert "rent" in accepted
    assert "pledge" in accepted
    assert rejected == []


def test_extended_only_topic_accepted():
    """Topics in EXTENDED but not CORE should be accepted by policy."""
    accepted, rejected = _normalize_topics(
        ["salary", "sla", "sanctions"],
        max_topics=10,
    )
    assert "salary" in accepted
    assert "sla" in accepted
    assert "sanctions" in accepted
    assert rejected == []


def test_unknown_topic_rejected():
    accepted, rejected = _normalize_topics(
        ["rent", "totally_unknown_topic_xyz"],
        max_topics=10,
    )
    assert "rent" in accepted
    assert "totally_unknown_topic_xyz" in rejected


def test_legacy_topics_still_accepted():
    accepted, rejected = _normalize_topics(
        ["governing_law", "confidentiality", "termination"],
        max_topics=10,
    )
    assert "governing_law" in accepted
    assert "confidentiality" in accepted
    assert "termination" in accepted
    assert rejected == []
