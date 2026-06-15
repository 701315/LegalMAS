# tests/classifiers/test_priority_rules_l2_ambiguity.py

"""
Regression tests for L2_STRONG_WINS guardrail added in fix:
  _priority_rules.py :: _rule_strong_l2()

Root cause: When two L2 candidates both reached confidence=1.0 (saturated),
L2_STRONG_WINS triggered based on winner confidence alone,
without checking if the top-2 margin was within ambiguity range.

Fix: L2_STRONG_WINS is now suppressed when top2_margin < ambiguity_margin.
"""

import pytest

from classifiers.stage8._priority_rules import PriorityRulesEvaluator


# ── Stubs ─────────────────────────────────────────────────────────────────────


class DummyBuilder:
    def build(self, **kwargs):
        return {**kwargs}

    def build_triggers(self, doc_id, final_type):
        return []


class _Observer:
    def observe(self, v):
        pass


class _Metric:
    def labels(self, **kw):
        return _Observer()


class DummyMetrics:
    classification_duration = _Metric()


class DummyConfig:
    def __init__(self, strong_threshold=0.85, ambiguity_margin=0.15):
        self.scoring = {
            "strong_signal_threshold": strong_threshold,
            "ambiguity_margin": ambiguity_margin,
        }


class DummyRegistry:
    def __init__(self, cfg_map=None):
        self._map = cfg_map or {}

    def get_config(self, type_code):
        return self._map.get(type_code)


class DummyTopL2:
    def __init__(self, doctype, confidence, extra=None):
        self.doctype = doctype
        self.confidence = confidence
        self.extra = extra or {}
        self.method = "header_pattern"
        self.evidence = "test"


class DummyTopL3:
    def __init__(self, doctype, confidence, raw_sim=0.5):
        self.doctype = doctype
        self.confidence = confidence
        self.extra = {"raw_similarity": raw_sim}


@pytest.fixture
def make_evaluator():
    def _make(cfg_map=None):
        return PriorityRulesEvaluator(
            registry=DummyRegistry(cfg_map or {}),
            builder=DummyBuilder(),
            metrics=DummyMetrics(),
        )
    return _make


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_l2_strong_suppressed_when_top2_margin_below_ambiguity(monkeypatch, make_evaluator):
    """
    REGRESSION: L2_STRONG_WINS must NOT trigger when
    top2_margin < ambiguity_margin, even if L2 confidence >= strong_threshold.

    This is the root cause of lease → real_estate misclassification:
    - L2 lease: confidence = 1.0 (raw=1.7)
    - L2 real_estate: confidence = 1.0 (raw=1.267)
    - top2_margin = 0.0 < ambiguity_margin = 0.15
    - Before fix: L2_STRONG_WINS triggered → wrong type
    - After fix: suppressed → cascade continues to voting
    """
    monkeypatch.setattr(
        "classifiers.stage8._priority_rules.settings.CLASSIFICATION_L2_STRONG",
        0.85,
        raising=False,
    )
    monkeypatch.setattr(
        "classifiers.stage8._priority_rules.settings.CLASSIFICATION_L2_AMBIGUITY_MARGIN",
        0.15,
        raising=False,
    )
    monkeypatch.setattr(
        "classifiers.stage8._priority_rules.settings.CLASSIFICATION_L1_CONSENSUS_MIN",
        0.7,
        raising=False,
    )
    monkeypatch.setattr(
        "classifiers.stage8._priority_rules.settings.CLASSIFICATION_L3_CONSENSUS_RAW_MIN",
        0.5,
        raising=False,
    )
    monkeypatch.setattr(
        "classifiers.stage8._priority_rules.settings.CLASSIFICATION_L3_STRONG_CONFLICT_RAW",
        0.75,
        raising=False,
    )

    evaluator = make_evaluator(
        {"contract_2.1_lease": DummyConfig(strong_threshold=0.85, ambiguity_margin=0.15)}
    )

    top_l2 = DummyTopL2(
        doctype="contract_2.1_lease",
        confidence=0.85,
        extra={
            "top2_margin": 0.0,
            "runner_up_type": "contract_1.6_real_estate",
            "runner_up_confidence": 1.0,
            "high_hits": 2,
            "distinctive_high_hits": 2,
            "generic_high_hits": 0,
        },
    )

    details = {"levels_tried": ["L1", "L2", "L3"], "contradiction_detected": False}

    result = evaluator.evaluate(
        doc_id="test-doc",
        top_l1=None,
        top_l2=top_l2,
        top_l3=DummyTopL3("contract_2.1_lease", 0.012),
        candidates=[],
        details=details,
        language="ru",
        jurisdiction="RU",
        started_at=0.0,
    )

    assert result is None, (
        "L2_STRONG_WINS must be suppressed when top2_margin < ambiguity_margin. "
        "Got early result instead of continuing to voting."
    )
    assert "l2_strong_suppressed" in details, (
        "details must contain l2_strong_suppressed when suppression occurs"
    )
    assert details["l2_strong_suppressed"]["reason"] == "L2_TOP2_AMBIGUITY", (
        f"Expected reason L2_TOP2_AMBIGUITY, got {details['l2_strong_suppressed'].get('reason')}"
    )


def test_l2_strong_wins_when_clear_margin(monkeypatch, make_evaluator):
    """
    L2_STRONG_WINS must still trigger when top2_margin >= ambiguity_margin.
    This is the non-regression case: genuine real_estate sale document
    must still get fast L2 exit.

    Real example: ec013b2c document
    - L2 real_estate: confidence = 1.0, raw = 2.025
    - top2_margin = 0.7 >> ambiguity_margin = 0.15
    - L2_STRONG_WINS must trigger
    """
    monkeypatch.setattr(
        "classifiers.stage8._priority_rules.settings.CLASSIFICATION_L2_STRONG",
        0.85,
        raising=False,
    )
    monkeypatch.setattr(
        "classifiers.stage8._priority_rules.settings.CLASSIFICATION_L2_AMBIGUITY_MARGIN",
        0.15,
        raising=False,
    )
    monkeypatch.setattr(
        "classifiers.stage8._priority_rules.settings.CLASSIFICATION_L1_CONSENSUS_MIN",
        0.7,
        raising=False,
    )
    monkeypatch.setattr(
        "classifiers.stage8._priority_rules.settings.CLASSIFICATION_L3_CONSENSUS_RAW_MIN",
        0.5,
        raising=False,
    )
    monkeypatch.setattr(
        "classifiers.stage8._priority_rules.settings.CLASSIFICATION_L3_STRONG_CONFLICT_RAW",
        0.75,
        raising=False,
    )

    evaluator = make_evaluator(
        {"contract_1.6_real_estate": DummyConfig(strong_threshold=0.85, ambiguity_margin=0.15)}
    )

    top_l2 = DummyTopL2(
        doctype="contract_1.6_real_estate",
        confidence=1.0,
        extra={
            "top2_margin": 0.7,
            "runner_up_type": "contract_4.6_trust_management",
            "runner_up_confidence": 0.3,
            "high_hits": 3,
            "distinctive_high_hits": 3,
            "generic_high_hits": 0,
        },
    )

    details = {"levels_tried": ["L1", "L2", "L3"], "contradiction_detected": False}

    result = evaluator.evaluate(
        doc_id="test-doc",
        top_l1=None,
        top_l2=top_l2,
        top_l3=DummyTopL3("contract_1.6_real_estate", 0.014),
        candidates=[],
        details=details,
        language="ru",
        jurisdiction="RU",
        started_at=0.0,
    )

    assert result is not None, (
        "L2_STRONG_WINS must trigger for clear winner with large top2_margin"
    )
    assert result.get("final_type") == "contract_1.6_real_estate"
    assert details.get("voting", {}).get("strategy") == "L2_STRONG_WINS"


def test_l2_strong_suppressed_stores_runner_up_info(monkeypatch, make_evaluator):
    """
    When suppression occurs, details must include runner_up_type
    for explainability / diagnostics.
    """
    monkeypatch.setattr(
        "classifiers.stage8._priority_rules.settings.CLASSIFICATION_L2_STRONG",
        0.85, raising=False,
    )
    monkeypatch.setattr(
        "classifiers.stage8._priority_rules.settings.CLASSIFICATION_L2_AMBIGUITY_MARGIN",
        0.15, raising=False,
    )
    monkeypatch.setattr(
        "classifiers.stage8._priority_rules.settings.CLASSIFICATION_L1_CONSENSUS_MIN",
        0.7, raising=False,
    )
    monkeypatch.setattr(
        "classifiers.stage8._priority_rules.settings.CLASSIFICATION_L3_CONSENSUS_RAW_MIN",
        0.5, raising=False,
    )
    monkeypatch.setattr(
        "classifiers.stage8._priority_rules.settings.CLASSIFICATION_L3_STRONG_CONFLICT_RAW",
        0.75, raising=False,
    )

    evaluator = make_evaluator(
        {"type_a": DummyConfig(strong_threshold=0.85, ambiguity_margin=0.15)}
    )

    top_l2 = DummyTopL2(
        doctype="type_a",
        confidence=0.85,
        extra={
            "top2_margin": 0.0,
            "runner_up_type": "type_b",
            "runner_up_confidence": 0.85,
        },
    )

    details = {"levels_tried": ["L1", "L2"], "contradiction_detected": False}

    result = evaluator.evaluate(
        doc_id="test-doc",
        top_l1=None,
        top_l2=top_l2,
        top_l3=None,
        candidates=[],
        details=details,
        language="ru",
        jurisdiction="RU",
        started_at=0.0,
    )

    assert result is None
    suppressed = details.get("l2_strong_suppressed", {})
    assert suppressed.get("runner_up_type") == "type_b"
    assert suppressed.get("l2_top2_margin") == pytest.approx(0.0)



    