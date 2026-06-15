# tests/classifiers/test_l2_header_tie_resolution.py

"""
Regression tests for L2 lexical tie-resolution.

Root cause discovered:
- When two candidates both reach clamped confidence = 1.0 (saturation),
  the winner was determined by registry iteration order, not by actual
  lexical evidence strength.
- Lease document was misclassified as real_estate_sale because
  real_estate appeared earlier in registry.

Fix validated:
- Ranking key now uses (confidence, raw_confidence, distinctive_hits, -exclusion_hits).
- Ambiguity penalty is now applied to final best_conf, not only written to extra.
- Ordering is consistent across winner selection and scored_candidates.sort().
"""

import re

import pytest

from classifiers.stage8.l2_header import L2HeaderClassifier
from classifiers.yaml_registry import YAMLRegistry


# ── Stubs ─────────────────────────────────────────────────────────────────────


class DummyRegistry(YAMLRegistry):
    def __init__(self, configs):
        self._configs = configs

    @classmethod
    def get_instance(cls):
        raise RuntimeError("not used in tests")

    def get_all_configs(self):
        return list(self._configs)

    def get_config(self, type_code: str):
        for cfg in self._configs:
            if cfg.type_code == type_code:
                return cfg
        return None


class _Cfg:
    """Minimal extended-format config."""

    def __init__(
        self,
        type_code: str,
        high_signals: list[dict],
        exclusions: list[dict] | None = None,
        ambiguity_margin: float = 0.15,
    ):
        self.type_code = type_code
        self.scoring = {
            "accept_threshold": 0.5,
            "input_quality_weight": 1.0,
            "ambiguity_margin": ambiguity_margin,
        }
        self.lexical_signals = {
            "high": high_signals,
            "medium": [],
            "low": [],
        }
        self.negative_signals = [
            {
                "pattern": s["pattern"],
                "severity": s.get("severity", "soft"),
                "weight": s.get("weight", -0.3),
                "context": s.get("context", "any"),
            }
            for s in (exclusions or [])
        ]
        self.header_patterns = []
        self.keywords_high = []
        self.keywords_medium = []
        self.keywords_low = []
        self.exclusions = []


def _signal(pattern_str: str, weight: float, distinctiveness: str = "high", context: str = "any") -> dict:
    return {
        "pattern": re.compile(pattern_str, re.IGNORECASE),
        "weight": weight,
        "distinctiveness": distinctiveness,
        "context": context,
    }


def _exclusion(pattern_str: str, severity: str = "hard") -> dict:
    return {
        "pattern": re.compile(pattern_str, re.IGNORECASE),
        "severity": severity,
        "weight": -1.0,
        "context": "any",
    }


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tie_winner_by_raw_confidence_not_registry_order():
    """
    REGRESSION: When two candidates both clamp to confidence=1.0,
    the winner must be determined by raw_confidence (pre-clamp score),
    not by registry iteration order.

    Scenario:
      - type_a (registry first): raw = 0.9 * 1.0 + 0.6 * 0.667 = 1.300 → clamp 1.0
      - type_b (registry second): raw = 0.85 * 1.0 + 0.85 * 1.0 = 1.700 → clamp 1.0

    Expected: winner = type_b (stronger raw signal)
    Before fix: winner = type_a (first in registry)
    """
    cfg_a = _Cfg(
        type_code="type_a",
        high_signals=[
            _signal("НЕДВИЖИМОСТЬ", weight=0.9, distinctiveness="high"),
            _signal("ЗЕМЕЛЬНЫЙ УЧАСТОК", weight=0.6, distinctiveness="medium"),
        ],
    )
    cfg_b = _Cfg(
        type_code="type_b",
        high_signals=[
            _signal("АРЕНДОДАТЕЛЬ", weight=0.85, distinctiveness="high"),
            _signal("АРЕНДАТОР", weight=0.85, distinctiveness="high"),
        ],
    )

    # type_a is first — before fix it would always win
    registry = DummyRegistry([cfg_a, cfg_b])
    classifier = L2HeaderClassifier(registry=registry)

    header_text = "ДОГОВОР КРАТКОСРОЧНОЙ АРЕНДЫ\nАРЕНДОДАТЕЛЬ\nАРЕНДАТОР"
    body_text = "НЕДВИЖИМОСТЬ ОБЪЕКТЫ ЗЕМЕЛЬНЫЙ УЧАСТОК"

    result = await classifier.classify(
        text=header_text,
        filename="test_lease.docx",
        folder_path="",
        metadata={"body_text": body_text},
    )

    assert result.doctype == "type_b", (
        f"Expected type_b (stronger raw signal), got {result.doctype}. "
        "Regression: winner determined by registry order, not raw evidence."
    )


@pytest.mark.asyncio
async def test_raw_confidence_stored_in_extra():
    """
    raw_confidence must be present in extra for extended format candidates.
    This field is the basis for tie-breaking.
    """
    cfg = _Cfg(
        type_code="type_x",
        high_signals=[
            _signal("KEYWORD_A", weight=0.8, distinctiveness="high"),
        ],
    )
    registry = DummyRegistry([cfg])
    classifier = L2HeaderClassifier(registry=registry)

    result = await classifier.classify(
        text="KEYWORD_A in header",
        filename="test.docx",
        folder_path="",
        metadata={"body_text": ""},
    )

    assert result.doctype == "type_x"
    assert result.extra is not None
    assert "raw_confidence" in result.extra, (
        "raw_confidence must be stored in extra for ranking/tie-breaking"
    )
    assert result.extra["raw_confidence"] > 0.0

@pytest.mark.asyncio
async def test_ambiguity_penalty_applied_to_final_confidence():
    """
    REGRESSION: When top-2 candidates have the same clamped confidence = 1.0
    (margin < ambiguity_margin), ambiguity penalty must be actually subtracted
    from best_conf, not just stored in extra.
    """
    cfg_a = _Cfg(
        type_code="type_a",
        high_signals=[
            _signal("НЕДВИЖИМОСТЬ", weight=0.9, distinctiveness="high"),
            _signal("КАДАСТРОВЫЙ", weight=0.85, distinctiveness="high"),
        ],
        ambiguity_margin=0.15,
    )
    cfg_b = _Cfg(
        type_code="type_b",
        high_signals=[
            _signal("АРЕНДОДАТЕЛЬ", weight=0.85, distinctiveness="high"),
            _signal("АРЕНДАТОР", weight=0.85, distinctiveness="high"),
        ],
        ambiguity_margin=0.18,
    )

    registry = DummyRegistry([cfg_a, cfg_b])
    classifier = L2HeaderClassifier(registry=registry)

    long_padding = " padding " * 50
    header_text = f"ДОГОВОР АРЕНДЫ АРЕНДОДАТЕЛЬ АРЕНДАТОР{long_padding}"
    body_text = f"НЕДВИЖИМОСТЬ КАДАСТРОВЫЙ ОБЪЕКТЫ{long_padding}"

    result = await classifier.classify(
        text=header_text,
        filename="test.docx",
        folder_path="",
        metadata={"body_text": body_text},
    )

    extra = result.extra or {}

    assert extra.get("ambiguity_penalty", 0.0) > 0.0, (
        f"Expected ambiguity_penalty > 0 for tied candidates. "
        f"Got: {extra.get('ambiguity_penalty')}. "
        f"top2_margin={extra.get('top2_margin')}, "
        f"confidence_before={extra.get('confidence_before_ambiguity')}"
    )
    assert extra.get("confidence_after_ambiguity", 1.0) < extra.get(
        "confidence_before_ambiguity", 1.0
    ), "ambiguity_penalty must reduce confidence"
    assert result.confidence < 1.0, (
        "After ambiguity penalty, best_conf must be < 1.0"
    )

@pytest.mark.asyncio
async def test_no_ambiguity_penalty_when_clear_winner():
    """
    When there is a clear winner (large top2_margin),
    no ambiguity penalty should be applied.
    Confidence stays at 1.0.
    """
    cfg_a = _Cfg(
        type_code="type_a",
        high_signals=[
            _signal("НЕДВИЖИМОСТЬ", weight=0.9, distinctiveness="high"),
            _signal("КАДАСТРОВЫЙ", weight=0.8, distinctiveness="high"),
            _signal("ЗЕМЕЛЬНЫЙ", weight=0.65, distinctiveness="high"),
            _signal("ОБЪЕКТЫ", weight=0.55, distinctiveness="high"),
        ],
        ambiguity_margin=0.15,
    )
    cfg_b = _Cfg(
        type_code="type_b",
        high_signals=[
            _signal("АРЕНДАТОР", weight=0.3, distinctiveness="medium"),
        ],
        ambiguity_margin=0.18,
    )

    registry = DummyRegistry([cfg_a, cfg_b])
    classifier = L2HeaderClassifier(registry=registry)

    long_padding = " padding " * 50
    header_text = f"ДОГОВОР КУПЛИ-ПРОДАЖИ ОБЪЕКТОВ НЕДВИЖИМОСТИ{long_padding}"
    body_text = f"КАДАСТРОВЫЙ НОМЕР ЗЕМЕЛЬНЫЙ УЧАСТОК ОБЪЕКТЫ НЕДВИЖИМОСТИ{long_padding}"

    result = await classifier.classify(
        text=header_text,
        filename="test.docx",
        folder_path="",
        metadata={"body_text": body_text},
    )

    assert result.doctype == "type_a"

    extra = result.extra or {}
    assert extra.get("ambiguity_penalty", 0.0) == 0.0, (
        "No ambiguity penalty expected when top2_margin is large"
    )
    assert result.confidence == pytest.approx(1.0), (
        f"Clear winner should keep confidence = 1.0, got {result.confidence}"
    )


@pytest.mark.asyncio
async def test_extra_has_confidence_before_and_after_ambiguity():
    """
    Both confidence_before_ambiguity and confidence_after_ambiguity
    must always be present in extra (even when penalty = 0).
    These fields are needed for explainability and diagnostics.
    """
    cfg = _Cfg(
        type_code="type_x",
        high_signals=[
            _signal("KEYWORD", weight=0.8, distinctiveness="high"),
        ],
    )
    registry = DummyRegistry([cfg])
    classifier = L2HeaderClassifier(registry=registry)

    result = await classifier.classify(
        text="KEYWORD present",
        filename="test.docx",
        folder_path="",
        metadata={"body_text": ""},
    )

    extra = result.extra or {}
    assert "confidence_before_ambiguity" in extra, (
        "confidence_before_ambiguity must always be in extra"
    )
    assert "confidence_after_ambiguity" in extra, (
        "confidence_after_ambiguity must always be in extra"
    )


@pytest.mark.asyncio
async def test_sorted_candidates_consistent_with_winner():
    """
    After classify(), scored_candidates must be sorted in the same order
    as the winner selection ranking key.
    This ensures runner_up_type is correctly identified.
    """
    cfg_a = _Cfg(
        type_code="type_a",
        high_signals=[
            _signal("АРЕНДОДАТЕЛЬ", weight=0.85, distinctiveness="high"),
            _signal("АРЕНДАТОР", weight=0.85, distinctiveness="high"),
        ],
    )
    cfg_b = _Cfg(
        type_code="type_b",
        high_signals=[
            _signal("НЕДВИЖИМОСТЬ", weight=0.9, distinctiveness="high"),
            _signal("КАДАСТРОВЫЙ", weight=0.6, distinctiveness="medium"),
        ],
    )

    # type_b first in registry to verify sort is by ranking key, not insertion
    registry = DummyRegistry([cfg_b, cfg_a])
    classifier = L2HeaderClassifier(registry=registry)

    header_text = "АРЕНДОДАТЕЛЬ И АРЕНДАТОР"
    body_text = "НЕДВИЖИМОСТЬ КАДАСТРОВЫЙ"

    result = await classifier.classify(
        text=header_text,
        filename="test.docx",
        folder_path="",
        metadata={"body_text": body_text},
    )

    # Winner must be type_a (raw = 1.7 > type_b raw ≈ 1.27 after signal_quality)
    assert result.doctype == "type_a"

    extra = result.extra or {}
    # runner_up must be type_b
    assert extra.get("runner_up_type") == "type_b", (
        "runner_up must reflect sorted order, not insertion order"
    )



    