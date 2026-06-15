# tests/classifiers/test_l2_header_extended_context.py

import re

import pytest

from classifiers.stage8.l2_header import L2HeaderClassifier
from classifiers.yaml_registry import YAMLRegistry


class DummyExtendedConfig:
    """
    Упрощённый DocumentTypeConfig для extended-формата.
    """

    def __init__(self, type_code: str):
        self.type_code = type_code
        self.scoring = {
            "accept_threshold": 0.5,
            "input_quality_weight": 1.0,
            "ambiguity_margin": 0.15,
        }
        # lexical_signals: high/medium/low
        self.lexical_signals = {
            "high": [
                {
                    "pattern": re.compile(r"HEADER_MARKER"),
                    "weight": 0.6,
                    "distinctiveness": "high",
                    "context": "header",
                },
                {
                    "pattern": re.compile(r"BODY_MARKER"),
                    "weight": 0.6,
                    "distinctiveness": "high",
                    "context": "body",
                },
                {
                    "pattern": re.compile(r"ANY_MARKER"),
                    "weight": 0.4,
                    "distinctiveness": "medium",
                    "context": "any",
                },
            ],
            "medium": [],
            "low": [],
        }
        # negative_signals: один hard, один soft
        self.negative_signals = [
            {
                "pattern": re.compile(r"HARD_EXCL"),
                "severity": "hard",
                "weight": -0.5,
                "context": "any",
            },
            {
                "pattern": re.compile(r"SOFT_EXCL"),
                "severity": "soft",
                "weight": -0.3,
                "context": "any",
            },
        ]

    # legacy-поля, чтобы L2 не пытался уйти в legacy-режим
    header_patterns = []
    keywords_high = []
    keywords_medium = []
    keywords_low = []
    exclusions = []


class DummyRegistry(YAMLRegistry):
    def __init__(self, configs):
        self._configs = configs

    @classmethod
    def get_instance(cls):
        raise RuntimeError("Not used")

    def get_all_configs(self):
        return list(self._configs)

    def get_config(self, type_code: str):
        for cfg in self._configs:
            if cfg.type_code == type_code:
                return cfg
        return None


@pytest.mark.asyncio
async def test_extended_context_header_and_body(monkeypatch):
    """
    Проверяем, что context: header/body/any влияет на поиск паттернов:
    - HEADER_MARKER ловится только в header;
    - BODY_MARKER ловится только в body/snippet;
    - ANY_MARKER ловится в любом из двух.
    """
    cfg = DummyExtendedConfig(type_code="extended_type")
    registry = DummyRegistry([cfg])

    monkeypatch.setattr(
        "classifiers.stage8.l2_header.YAMLRegistry.get_instance",
        lambda: registry,
    )

    classifier = L2HeaderClassifier(registry=registry)

    header_text = "HEADER_MARKER here; ANY_MARKER here."
    snippet_text = "BODY_MARKER is in the body; ANY_MARKER also here."

    result = await classifier.classify(
        text=header_text,
        filename="test.docx",
        folder_path="/",
        text_sanitized=None,
        metadata={"body_text": snippet_text},
    )

    assert result.doctype == "extended_type"
    extra = result.extra or {}

    # high_distinctive_hits: HEADER_MARKER + BODY_MARKER = 2
    assert extra["high_distinctive_hits"] == 2
    # ANY_MARKER идёт как high_generic (distinctiveness=medium)
    assert extra["high_generic_hits"] == 1
    # общие diagnostics
    assert extra["soft_exclusion_hits"] == 0
    assert extra["hard_exclusion_hits"] == 0


@pytest.mark.asyncio
async def test_extended_hard_exclusion_suppresses_type(monkeypatch):
    """
    Проверяем, что hard-exclusion в extended-формате полностью
    подавляет кандидата (L2 возвращает None для этого типа).
    """
    cfg = DummyExtendedConfig(type_code="extended_type")
    registry = DummyRegistry([cfg])

    monkeypatch.setattr(
        "classifiers.stage8.l2_header.YAMLRegistry.get_instance",
        lambda: registry,
    )

    classifier = L2HeaderClassifier(registry=registry)

    header_text = "HEADER_MARKER here; HARD_EXCL present."
    snippet_text = "BODY_MARKER in body."

    result = await classifier.classify(
        text=header_text,
        filename="test.docx",
        folder_path="/",
        text_sanitized=None,
        metadata={"body_text": snippet_text},
    )

    # hard exclusion должен приводить к UNKNOWN на уровне L2
    assert result.doctype == "UNKNOWN"
    assert result.confidence == pytest.approx(0.0)


    