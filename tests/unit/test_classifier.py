"""
Unit tests for HybridClassifier cascade and Analyzers.
"""

import asyncio

from src.classifiers.hybrid_classifier import HybridClassifier
from src.classifiers.keyword_analyzer import KeywordAnalyzer
from src.classifiers.rule_based import RuleBasedClassifier
from src.classifiers.semantic_matcher import SemanticMatcher
from src.classifiers.trigger_detector import detect_triggers

REGISTRY = "playbooks/document_types"


def _run(coro):
    return asyncio.run(coro)


def _make_hybrid():
    return HybridClassifier(
        rule_based=RuleBasedClassifier(registry_path=REGISTRY),
        keyword_analyzer=KeywordAnalyzer(registry_path=REGISTRY),
        semantic_matcher=SemanticMatcher(registry_path=REGISTRY),
        llm_classifier=None,
        registry_path=REGISTRY,
    )


class TestRuleBasedL1:
    def test_l1_confidence_is_capped(self):
        clf = RuleBasedClassifier(registry_path=REGISTRY)
        # Даже при идеальном совпадении имени файла, confidence <= 0.60
        result = _run(clf.classify("", "contract_1.6_real_estate_draft.pdf", "/deals/123"))
        assert result.confidence <= 0.60
        assert result.doctype == "contract_1.6_real_estate"


class TestKeywordAnalyzerL2:
    def test_l2_detects_real_estate_keywords(self):
        clf = KeywordAnalyzer(registry_path=REGISTRY)
        text = (
            "Договор купли-продажи недвижимости. Кадастровый номер 77:01:001. Объект недвижимости."
        )
        result = _run(clf.classify(text, "file.pdf", ""))
        assert result.doctype == "contract_1.6_real_estate"
        assert result.confidence > 0.5
        # Проверка метаданных из YAML
        assert result.language == "ru"
        assert result.jurisdiction == "RU"


class TestTriggerDetector:
    def test_dynamic_trigger_loading(self):
        from src.classifiers.registry_loader import load_registry

        reg = load_registry(REGISTRY)
        text = "Продается квартира в жилом доме, оформлена ипотека."
        triggers = detect_triggers(reg, text, "contract_1.6_real_estate")
        # Должны сработать триггеры из YAML секции trigger_definitions
        assert "residential_property" in triggers
        assert "mortgage_related" in triggers


class TestHybridClassifier:
    def test_cascade_early_stop_at_l2(self):
        clf = _make_hybrid()
        text = "ДОГОВОР КУПЛИ-ПРОДАЖИ НЕДВИЖИМОСТИ. Кадастровый номер 123. ЕГРН."
        result = _run(clf.classify(text, text, "doc.pdf", ""))

        assert result.doctype == "contract_1.6_real_estate"
        assert "L2" in result.details["levels_tried"]
        # Если L2 уверен, L3 может не запускаться (зависит от настроек порога)
        assert result.language == "ru"
        assert result.jurisdiction == "RU"

    def test_hybrid_fallback_to_voting(self):
        clf = _make_hybrid()
        # Слабые сигналы везде
        result = _run(clf.classify("купли-продажи", "купли-продажи", "unknown.pdf", ""))
        assert "levels_tried" in result.details
        assert len(result.details["levels_tried"]) >= 2
