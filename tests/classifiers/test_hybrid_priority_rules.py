import types

import pytest

from classifiers.stage8.hybrid_classifier import HybridClassifier


class DummyBuilder:
    def build(self, **kwargs):
        return kwargs

    def build_triggers(self, doc_id: str, final_type: str):
        return []


class DummyMetricsObserver:
    def observe(self, value: float) -> None:
        return None


class DummyMetric:
    def labels(self, **kwargs):
        return DummyMetricsObserver()


class DummyMetrics:
    classification_duration = DummyMetric()


class DummyTopL2:
    def __init__(self, doctype: str, confidence: float, extra: dict | None = None):
        self.doctype = doctype
        self.confidence = confidence
        self.extra = extra or {}
        self.method = "header_pattern"
        self.evidence = ["dummy"]


class DummyConfig:
    def __init__(self, strong_signal_threshold: float | None = None):
        self.scoring = {}
        if strong_signal_threshold is not None:
            self.scoring["strong_signal_threshold"] = strong_signal_threshold


class DummyRegistry:
    def __init__(self, mapping: dict[str, DummyConfig]):
        self.mapping = mapping

    def get_config(self, type_code: str):
        return self.mapping.get(type_code)


@pytest.fixture
def hybrid_stub(monkeypatch):
    """
    Создаём минимальный экземпляр HybridClassifier без вызова тяжёлого __init__.
    """
    hybrid = object.__new__(HybridClassifier)
    hybrid._builder = DummyBuilder()
    hybrid.metrics = DummyMetrics()
    hybrid.registry = DummyRegistry({})
    return hybrid


def test_check_priority_rules_uses_type_specific_strong_threshold(monkeypatch, hybrid_stub):
    """
    Если per-type strong_signal_threshold ниже глобального,
    то L2_STRONG_WINS должен сработать по type-specific threshold.
    """
    monkeypatch.setattr(
        "classifiers.stage8.hybrid_classifier.settings.CLASSIFICATION_L2_STRONG",
        0.85,
        raising=False,
    )

    hybrid_stub.registry = DummyRegistry(
        {
            "doc_type_a": DummyConfig(strong_signal_threshold=0.70),
        }
    )

    top_l2 = DummyTopL2(
        doctype="doc_type_a",
        confidence=0.74,
        extra={
            "high_hits": 2,
            "medium_hits": 1,
            "distinctive_high_hits": 2,
            "distinctive_medium_hits": 1,
            "generic_high_hits": 0,
        },
    )

    details = {"levels_tried": ["L1", "L2"]}

    result = hybrid_stub._check_priority_rules(
        doc_id="doc-1",
        top_l1=None,
        top_l2=top_l2,
        top_l3=None,
        candidates=[],
        details=details,
        language="ru",
        jurisdiction="RU",
        started_at=0.0,
    )

    assert result is not None
    assert result["final_type"] == "doc_type_a"
    assert result["final_confidence"] == pytest.approx(0.74)
    assert result["level"] == "L2"
    assert details["voting"]["strategy"] == "L2_STRONG_WINS"
    assert details["voting"]["l2_strong_threshold"] == pytest.approx(0.70)


def test_check_priority_rules_falls_back_to_voting_when_type_threshold_not_met(
    monkeypatch,
    hybrid_stub,
):
    """
    Если per-type strong_signal_threshold выше confidence кандидата,
    shortcut L2_STRONG_WINS не должен срабатывать.
    """
    monkeypatch.setattr(
        "classifiers.stage8.hybrid_classifier.settings.CLASSIFICATION_L2_STRONG",
        0.85,
        raising=False,
    )

    hybrid_stub.registry = DummyRegistry(
        {
            "doc_type_b": DummyConfig(strong_signal_threshold=0.90),
        }
    )

    top_l2 = DummyTopL2(
        doctype="doc_type_b",
        confidence=0.84,
        extra={
            "high_hits": 3,
            "medium_hits": 1,
            "distinctive_high_hits": 3,
            "distinctive_medium_hits": 1,
            "generic_high_hits": 0,
        },
    )

    details = {"levels_tried": ["L1", "L2"]}

    result = hybrid_stub._check_priority_rules(
        doc_id="doc-2",
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
    assert "voting" not in details


    