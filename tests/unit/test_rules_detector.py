import pytest

from src.engine.detectors.rules_detector import RulesDetector
from src.engine.playbook.models import RulesConfig


@pytest.fixture
def detector():
    return RulesDetector()


def test_rules_detector_empty_text(detector):
    """Если текста нет, всегда found=False и confidence=0."""
    rules = RulesConfig(
        keywords=["test"],
        regex_patterns=[r"test"],
        clause_patterns=[],
    )

    result = detector.detect("", rules)

    assert result["found"] is False
    assert result["confidence"] == 0.0
    assert result["method"] == "rules"


def test_rules_detector_keyword_any_mode_found(detector):
    """ANY: достаточно одного ключевого слова, чтобы found=True."""
    rules = RulesConfig(
        keywords=["alpha", "beta"],
        keyword_mode="any",
        regex_patterns=[],
        clause_patterns=[],
    )

    text = "This is alpha only."
    result = detector.detect(text, rules)

    assert result["found"] is True
    assert result["confidence"] > 0.0
    assert "alpha" in result["evidence"]
    assert result["method"] == "rules"


def test_rules_detector_keyword_all_mode_not_all_found(detector):
    """ALL: если не все keywords найдены, found=False."""
    rules = RulesConfig(
        keywords=["alpha", "beta"],
        keyword_mode="all",
        regex_patterns=[],
        clause_patterns=[],
    )

    text = "Only alpha is here."
    result = detector.detect(text, rules)

    assert result["found"] is False
    assert result["confidence"] == 0.0


def test_rules_detector_regex_match(detector):
    """Если regex_patterns совпали, found=True и есть evidence."""
    rules = RulesConfig(
        keywords=[],
        regex_patterns=[r"\b\d{3}-\d{2}-\d{2}\b"],
        clause_patterns=[],
    )

    text = "Phone: 123-45-67 is present."
    result = detector.detect(text, rules)

    assert result["found"] is True
    assert result["confidence"] > 0.0
    assert "123-45-67" in result["evidence"]
    assert result["method"] == "rules"
