"""
YAML Registry — loads and caches document type configurations.

Reads registry.yaml (list of types) and individual type YAML files.
Thread-safe singleton with lazy loading.

Full version with hot-reload in Stage 6.
"""

import os
import re
import threading
from typing import Optional

import yaml

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)
_lock = threading.Lock()
_instance: Optional["YAMLRegistry"] = None


class DocumentTypeConfig:
    """Parsed configuration for one document type."""

    def __init__(self, raw: dict):
        self.raw = raw
        self.type_code = str(raw.get("type", ""))
        self.name = str(raw.get("name", ""))
        runtime = raw.get("classification_runtime_v1") or {}
        rules = runtime.get("rules") or raw.get("rules", {})
        validation = raw.get("validation_engine_v3_2") or raw.get("validation_metadata") or {}
        self.triggerdefinitions = dict(
            runtime.get("trigger_definitions") or validation.get("trigger_definitions") or {}
        )

        self.filename_patterns: list = [
            re.compile(p.lstrip("r").strip('"').strip("'"))
            for p in rules.get("filename_patterns", [])
        ]
        self.folder_patterns: list = [
            re.compile(p.lstrip("r").strip('"').strip("'"))
            for p in rules.get("folder_patterns", [])
        ]
        self.keywords_high: list = rules.get("keywords", {}).get("high", [])
        self.keywords_medium: list = rules.get("keywords", {}).get("medium", [])
        self.keywords_low: list = rules.get("keywords", {}).get("low", [])
        self.exclusions: list = rules.get("exclusions", [])

        # trigger_definitions → applicable_triggers list
        # Keys of trigger_definitions become trigger IDs
        tdef = raw.get("trigger_definitions", {}) or {}
        self.trigger_ids: list = list(tdef.keys())

        # trigger_definitions with their keyword matchers (used by TriggerDetector)
        self.trigger_definitions: dict = tdef

        metadata = raw.get("metadata", {}) or {}
        self.category: str = metadata.get("category", "contract")
        self.complexity: str = metadata.get("complexity", "medium")
        self.risk_level: str = metadata.get("risk_level", "medium")
        self.language: str = metadata.get("language", "ru")
        self.jurisdiction: str = metadata.get("jurisdiction", "RU")


class YAMLRegistry:
    """
    Singleton registry of all document type configurations.

    Usage:
        registry = YAMLRegistry.get_instance()
        configs  = registry.get_all_configs()
        cfg      = registry.get_config("contract1.1spa")
    """

    def __init__(self, registry_path: str):
        self.registry_path = registry_path
        self._configs: dict = {}
        self._load()

    def _load(self):
        registry_file = os.path.join(self.registry_path, "registry.yaml")
        if not os.path.exists(registry_file):
            logger.warning(
                "YAML registry not found",
                path=registry_file,
            )
            return

        with open(registry_file, encoding="utf-8") as f:
            registry = yaml.safe_load(f)

        for entry in registry.get("document_types", []):
            type_code = entry.get("type", "")
            yaml_file = os.path.join(self.registry_path, f"{type_code}.yaml")
            if not os.path.exists(yaml_file):
                logger.warning(
                    "Type YAML not found — using minimal config from registry",
                    type_code=type_code,
                )
                self._configs[type_code] = DocumentTypeConfig(entry)
                continue
            with open(yaml_file, encoding="utf-8") as f:
                type_raw = yaml.safe_load(f)
            self._configs[type_code] = DocumentTypeConfig(type_raw)

        logger.info(
            "YAML registry loaded",
            types=list(self._configs.keys()),
        )

    def get_all_configs(self) -> list:
        return list(self._configs.values())

    def get_config(self, type_code: str) -> DocumentTypeConfig | None:
        return self._configs.get(type_code)

    @classmethod
    def get_instance(cls) -> "YAMLRegistry":
        global _instance
        if _instance is None:
            with _lock:
                if _instance is None:
                    path = getattr(settings, "CLASSIFIER_REGISTRY_PATH", "playbooks/document_types")
                    _instance = cls(path)
        return _instance

    @classmethod
    def reset(cls):
        """Reset singleton — used in tests to reload registry between runs."""
        global _instance
        with _lock:
            _instance = None
