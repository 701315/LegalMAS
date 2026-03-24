# src/classifiers/yaml_registry.py

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
import glob

import yaml

from core.config import settings
from core.logging import get_logger

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
        # Правила классификации: в приоритете блок classification_runtime_v1.rules
        rules = runtime.get("rules") or raw.get("rules", {})
        validation = raw.get("validation_engine_v3_2") or raw.get("validation_metadata") or {}
        self.triggerdefinitions = dict(
            runtime.get("trigger_definitions") or validation.get("trigger_definitions") or {}
        )

        # --- filename_patterns / folder_patterns: для L1 ---
        self.filename_patterns: list = [
            re.compile(p.lstrip("r").strip('"').strip("'"))
            for p in rules.get("filename_patterns", [])
            if isinstance(p, str)
        ]
        self.folder_patterns: list = [
            re.compile(p.lstrip("r").strip('"').strip("'"))
            for p in rules.get("folder_patterns", [])
            if isinstance(p, str)
        ]

        # --- header_patterns: для L2 ---
        # 1) пытаемся взять явные header_patterns из YAML (runtime или корень)
        explicit_header = (
            runtime.get("header_patterns")
            or raw.get("header_patterns")
            or rules.get("header_patterns")
            or []
        )
        if explicit_header:
            header_source = explicit_header
        else:
            # 2) если явных нет — используем keywords.high как паттерны заголовка
            header_source = rules.get("keywords", {}).get("high", []) or []

        self.header_patterns: list = []
        for p in header_source:
            if not isinstance(p, str):
                continue
            try:
                compiled = re.compile(p.lstrip("r").strip('"').strip("'"), re.IGNORECASE)
                self.header_patterns.append(compiled)
            except re.error:
                logger.warning(
                    "Invalid header pattern in YAML",
                    extra={"type_code": self.type_code, "pattern": p},
                )

        # --- keywords.* и exclusions: для L2/L3 и TriggerDetector ---
        kw = rules.get("keywords", {}) or {}
        self.keywords_high = self._compile_regex_list(kw.get("high", []))
        self.keywords_medium = self._compile_regex_list(kw.get("medium", []))
        self.keywords_low = self._compile_regex_list(kw.get("low", []))
        self.exclusions = self._compile_regex_list(rules.get("exclusions", []))

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

        # NEW: party role keywords from essential_elements.parties
        self.party_role_keywords: dict[str, str] = self._build_party_role_keywords(raw)

    @staticmethod
    def _compile_regex_list(items: list) -> list[re.Pattern]:
        """
        Компилирует список строковых regex-паттернов в объекты re.Pattern.

        Для продакшн-уровня:
        - игнорируем нестроковые элементы;
        - обрезаем обрамляющие кавычки и префикс r;
        - логируем, но НЕ падаем при ошибке компиляции, чтобы
          один кривой паттерн не клал весь сервис.
        """
        compiled: list[re.Pattern] = []
        for raw in items or []:
            if not isinstance(raw, str):
                continue
            # убираем возможный префикс r и внешние кавычки из YAML
            pattern_str = raw.lstrip("r").strip('"').strip("'")
            if not pattern_str:
                continue
            try:
                # Внутренний (?i) и другие флаги останутся рабочими.
                compiled.append(re.compile(pattern_str))
            except re.error as e:
                logger.warning(
                    "Invalid regex in YAML keywords/exclusions",
                    extra={"pattern": raw, "error": str(e)},
                )
        return compiled

    @staticmethod
    def _build_party_role_keywords(raw: dict) -> dict[str, str]:
        """
        Build {keyword_lower: ROLE_ID} from essential_elements.parties.party_roles.
        """
        mapping: dict[str, str] = {}
        for elem in raw.get("essential_elements") or []:
            if elem.get("element") != "parties":
                continue
            for role in elem.get("party_roles", []) or []:
                role_id = role.get("id")
                if not role_id:
                    continue
                for kw in role.get("keywords", []) or []:
                    mapping[kw.lower()] = role_id
        return mapping


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
            if not type_code:
                continue

            # 1) Прямой путь в корне (на случай, если часть файлов лежит без подпапок)
            direct = os.path.join(self.registry_path, f"{type_code}.yaml")

            yaml_path: str | None = None
            if os.path.exists(direct):
                yaml_path = direct
            else:
                # 2) Рекурсивный поиск по подпапкам, как в DocTypeCheckLoader
                pattern = os.path.join(self.registry_path, "**", f"{type_code}.yaml")
                candidates = sorted(glob.glob(pattern, recursive=True))
                if candidates:
                    yaml_path = candidates[0]

            if yaml_path is None:
                logger.warning(
                    "Type YAML not found — using minimal config from registry",
                    type_code=type_code,
                )
                self._configs[type_code] = DocumentTypeConfig(entry)
                continue

            try:
                with open(yaml_path, encoding="utf-8") as f:
                    type_raw = yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning(
                    "Type YAML cannot be read — using minimal config from registry",
                    extra={"type_code": type_code, "path": yaml_path, "error": str(e)},
                )
                self._configs[type_code] = DocumentTypeConfig(entry)
                continue

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

    def get_master_doc_types(self) -> list[str]:
        """
        Stage 7: Return doc_types suitable as family master documents.

        A doc_type is a master candidate if:
        - Its YAML config exists (already loaded in _configs)
        - classification.level is "L2" or "L3"
        - No "parent_doc_type" key is set (meaning it's not subordinate)
        """
        master_types: list[str] = []

        for type_code, cfg in self._configs.items():
            raw = cfg.raw or {}
            classification = raw.get("classification", {}) or {}
            level = classification.get("level", "L0")

            if level not in ("L2", "L3"):
                continue

            # subordinate if has parent_doc_type
            if raw.get("parent_doc_type"):
                continue

            master_types.append(type_code)

        logger.debug(
            "YAMLRegistry.get_master_doc_types",
            yaml_master_types=master_types,
        )
        return master_types

    def get_classification_rules(self, type_code: str) -> dict:
        """Получить правила классификации для HybridClassifier/L1/L2/L3."""
        config = self.get_config(type_code)
        if not config:
            return {
                "filename_patterns": [],
                "folder_patterns": [],
                "keywords_high": [],
                "keywords_medium": [],
                "keywords_low": [],
                "exclusions": [],
            }

        return {
            "filename_patterns": config.filename_patterns,
            "folder_patterns": config.folder_patterns,
            "keywords_high": config.keywords_high,
            "keywords_medium": config.keywords_medium,
            "keywords_low": config.keywords_low,
            "exclusions": config.exclusions,
        }

    def list_types(self) -> list[str]:
        """
        Вернуть список всех type_code, известных реестру.

        Используется L1/L2/L3/HybridClassifier для обхода всех типов.
        """
        return list(self._configs.keys())

    @classmethod
    def reset(cls):
        """Reset singleton — used in tests to reload registry between runs."""
        global _instance
        with _lock:
            _instance = None
