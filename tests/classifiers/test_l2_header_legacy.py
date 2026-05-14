# tests/classifiers/test_l2_header_legacy.py

import re

import pytest

from classifiers.stage8.l2_header import L2HeaderClassifier
from classifiers.yaml_registry import DocumentTypeConfig, YAMLRegistry


class DummyRegistry(YAMLRegistry):
    """
    Минимальный заглушечный реестр для теста legacy-формата.

    Мы не лезем в реальные YAML-файлы, а создаём один конфиг в памяти.
    """

    def __init__(self, configs):
        # configs: list[DocumentTypeConfig]
        self._configs = configs

    @classmethod
    def get_instance(cls):
        raise RuntimeError("Not used in tests")

    def get_all_configs(self):
        return list(self._configs)

    def get_config(self, type_code: str):
        for cfg in self._configs:
            if cfg.type_code == type_code:
                return cfg
        return None


class DummyLegacyConfig:
    """
    Упрощённый объект вместо DocumentTypeConfig
    с только legacy-полями, которые нужны L2.
    """

    def __init__(self, type_code: str):
        self.type_code = type_code
        self.header_patterns = []
        # HIGH/medium/low паттерны для legacy-ветки
        self.keywords_high = [re.compile(r"HIGH_UNIQUE_TERM")]
        self.keywords_medium = [re.compile(r"MEDIUM_TERM")]
        self.keywords_low = []
        self.exclusions = []  # без exclusions для упрощения
        # нет lexical_signals / negative_signals → используется legacy-фомат
        self.lexical_signals = {}
        self.negative_signals = []
        self.scoring = {}


@pytest.mark.asyncio
async def test_legacy_high_keywords_are_distinctive(monkeypatch):
    """
    Проверяем, что в legacy-формате keywords_high
    считаются distinctive_high_hits, а не generic_high_hits.
    """
    cfg = DummyLegacyConfig(type_code="legacy_type")

    # Реестр с одним типом
    registry = DummyRegistry([cfg])

    # Подменяем singleton YAMLRegistry.get_instance на нашу заглушку
    monkeypatch.setattr(
        "classifiers.stage8.l2_header.YAMLRegistry.get_instance",
        lambda: registry,
    )

    classifier = L2HeaderClassifier(registry=registry)

    header_text = "This document contains HIGH_UNIQUE_TERM in header."

    result = await classifier.classify(
        text=header_text,
        filename="test.docx",
        folder_path="/",
        text_sanitized=None,
        metadata=None,
    )

    assert result.doctype == "legacy_type"
    assert result.extra is not None
    extra = result.extra

    # Ключевая проверка: high keyword попал в distinctive, а не generic
    assert extra["distinctive_high_hits"] == 1
    assert extra["generic_high_hits"] == 0
    # signal_quality должен быть 1.0, так как все хиты distinctive
    assert extra["signal_quality"] == pytest.approx(1.0)


    