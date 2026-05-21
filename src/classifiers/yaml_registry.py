# src/classifiers/yaml_registry.py

"""
YAML Registry — loads and caches document type configurations.

Reads registry.yaml (list of types) and individual type YAML files.
Thread-safe singleton with lazy loading.

Full version with hot-reload in Stage 6.

UPDATED:
- stores source provenance for each loaded doc_type config;
- exposes raw YAML snapshot and SHA256 for durable persistence into
  DocumentTypeInstructionVersion;
- keeps backward compatibility for all existing classifier consumers.

ADDITIONAL UPDATES:
- exposes registry-level group and type-level parent on DocumentTypeConfig;
- preserves registry.yaml grouping metadata for file-based configs when missing in type YAML;
- exposes helper accessors for parent/group and family lookup.
"""

from __future__ import annotations

import glob
import hashlib
import os
import re
import threading
from dataclasses import dataclass
from typing import Optional

import yaml

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)
_lock = threading.Lock()
_instance: Optional["YAMLRegistry"] = None


def _pattern_to_text(raw_pattern: str) -> str:
    """Извлекает читаемый текст из regex-паттерна для L3-прототипа.

    Убирает regex-специфичный синтаксис, чтобы embedding-модель
    получала семантически осмысленный текст, а не шум из \b, (?i) и т.п.
    """
    s = raw_pattern.strip()
    s = re.sub(r'^\(\?[imsux]+\)', '', s)
    s = re.sub(r'\\[bBsSwWdD]', ' ', s)
    s = re.sub(r'[+*?]|\{\d+,?\d*\}', '', s)
    s = re.sub(r'[\[\]()^$|\\]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


@dataclass(slots=True)
class FilenamePatternRule:
    """
    Rule object for L1 filename/folder matching.

    kind:
    - generic_form: общий маркер формы документа (например, SPA, agreement)
    - specific_subject: предметно-специфичный маркер (real estate, factoring)
    - context: вспомогательный контекстный маркер
    """

    pattern: re.Pattern
    raw_pattern: str
    kind: str = "generic_form"
    weight: float = 1.0


class DocumentTypeConfig:
    """
    Parsed configuration for one document type.

    Для непрофессионального программиста:
    - Этот класс отвечает за то, чтобы один YAML-файл типа документа
      превратить в удобный объект для всех уровней классификации (L1–L3)
      и детектора триггеров.

    Источник данных: YAML типа (например, contract_1.6_real_estate.yaml).

    НОВОЕ в Sprint 3 (расширенный формат classification_runtime_v1):
    - Поддержка структурированных сигналов с явными weight, distinctiveness, context
    - Поддержка scoring параметров per-type
    - Backwards compatibility с legacy форматом строк

    NEW provenance fields:
    - source_yaml: полный raw YAML text snapshot, если тип загружен из файла;
    - source_path: путь к YAML-файлу, если известен;
    - source_sha256: SHA256 от source_yaml либо canonical dumped YAML fallback;
    - source_kind: 'file' | 'registry_fallback';
    - registry_entry_raw: исходная запись из registry.yaml для отладки/audit;
    - load_warnings: список предупреждений загрузки конкретного типа.
    """

    def __init__(
        self,
        raw: dict,
        *,
        source_yaml: str | None = None,
        source_path: str | None = None,
        source_sha256: str | None = None,
        source_kind: str = "file",
        registry_entry_raw: dict | None = None,
        load_warnings: list[str] | None = None,
    ):
        self.raw = raw or {}

        self.source_yaml = source_yaml
        self.source_path = source_path
        self.source_kind = source_kind
        self.registry_entry_raw = registry_entry_raw or {}
        self.load_warnings = list(load_warnings or [])
        self.source_sha256 = source_sha256 or self._compute_sha256(
            source_yaml if isinstance(source_yaml, str) and source_yaml.strip() else self._dump_canonical_yaml(self.raw)
        )

        self.type_code = str(self.raw.get("type", ""))
        self.name = str(self.raw.get("name", ""))

        # Registry-level grouping (registry.yaml)
        self.group: str = str(self.raw.get("group", "") or "").strip()

        # Type-level family/class (individual type YAML)
        self.parent: str = str(self.raw.get("parent", "") or "").strip()

        runtime = self.raw.get("classification_runtime_v1") or {}
        rules = runtime.get("rules") or self.raw.get("rules", {}) or {}
        validation = self.raw.get("validation_engine_v3_2") or self.raw.get("validation_metadata") or {}
        self.triggerdefinitions = dict(
            runtime.get("trigger_definitions") or validation.get("trigger_definitions") or {}
        )

        self.scoring = runtime.get("scoring") or {}

        # L1-specific structured rules with backward compatibility.
        self.filename_patterns: list[FilenamePatternRule] = self._parse_filename_pattern_rules(
            rules.get("filename_patterns", [])
        )
        self.folder_patterns: list[FilenamePatternRule] = self._parse_filename_pattern_rules(
            rules.get("folder_patterns", [])
        )

        explicit_header = (
            runtime.get("header_patterns")
            or self.raw.get("header_patterns")
            or rules.get("header_patterns")
            or []
        )
        if explicit_header:
            header_source = explicit_header
        else:
            header_source = rules.get("keywords", {}).get("high", []) or []

        self.header_patterns: list[re.Pattern] = []
        for p in header_source:
            if isinstance(p, dict):
                p = p.get("pattern", "")
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

        kw = rules.get("keywords", {}) or {}

        self.lexical_signals = {
            "high": self._parse_signal_list(kw.get("high", []), "high"),
            "medium": self._parse_signal_list(kw.get("medium", []), "medium"),
            "low": self._parse_signal_list(kw.get("low", []), "low"),
        }

        self.keywords_high = self._compile_regex_list(kw.get("high", []))
        self.keywords_medium = self._compile_regex_list(kw.get("medium", []))
        self.keywords_low = self._compile_regex_list(kw.get("low", []))

        self.negative_signals = self._parse_negative_signals(
            rules.get("exclusions", [])
        )

        self.exclusions = self._compile_regex_list(rules.get("exclusions", []))

        def _extract_raw_pattern(x) -> str:
            return str(x) if isinstance(x, str) else str(x.get("pattern", ""))

        self.rules_keywords: dict[str, list[str]] = {
            "high": [
                _pattern_to_text(_extract_raw_pattern(x))
                for x in kw.get("high", []) or []
                if _extract_raw_pattern(x).strip()
            ],
            "medium": [
                _pattern_to_text(_extract_raw_pattern(x))
                for x in kw.get("medium", []) or []
                if _extract_raw_pattern(x).strip()
            ],
            "low": [
                _pattern_to_text(_extract_raw_pattern(x))
                for x in kw.get("low", []) or []
                if _extract_raw_pattern(x).strip()
            ],
        }

        phrases = rules.get("phrases", {}) or {}
        self.rules_phrases: dict[str, list[str]] = {
            "high": [str(x) for x in phrases.get("high", []) or []],
            "medium": [str(x) for x in phrases.get("medium", []) or []],
            "low": [str(x) for x in phrases.get("low", []) or []],
        }

        tdef = self.raw.get("trigger_definitions", {}) or {}
        self.trigger_ids: list[str] = list(tdef.keys())
        self.trigger_definitions: dict = tdef

        metadata = self.raw.get("metadata", {}) or {}
        self.category: str = str(metadata.get("category", "contract"))
        self.subcategory: str = str(metadata.get("subcategory", "") or "").strip()
        self.complexity: str = str(metadata.get("complexity", "medium"))
        self.risk_level: str = str(metadata.get("risk_level", "medium"))
        self.language: str = str(metadata.get("language", "ru"))
        self.jurisdiction: str = str(metadata.get("jurisdiction", "RU"))

        self.aliases: list[str] = list(metadata.get("aliases", []) or [])
        self.section_markers: list[str] = list(metadata.get("section_markers", []) or [])

        self.essential_elements: list[dict] = list(self.raw.get("essential_elements") or [])
        self.party_role_keywords: dict[str, str] = self._build_party_role_keywords(self.raw)

    @staticmethod
    def _compute_sha256(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _dump_canonical_yaml(raw: dict) -> str:
        """
        Fallback canonical representation used only when original source text is absent.
        This keeps hash computation deterministic for registry-fallback configs.
        """
        try:
            return yaml.safe_dump(
                raw or {},
                allow_unicode=True,
                sort_keys=True,
            )
        except Exception:
            return str(raw or {})

    @staticmethod
    def _compile_regex_list(items: list) -> list[re.Pattern]:
        """
        Компилирует список строковых regex-паттернов в объекты re.Pattern.

        Для продакшн-уровня:
        - игнорируем нестроковые элементы;
        - обрезаем обрамляющие кавычки и префикс r;
        - логируем, но НЕ падаем при ошибке компиляции, чтобы
          один кривой паттерн не клал весь сервис.

        UPDATED: теперь также поддерживает dict-элементы (расширенный формат),
        извлекая из них поле "pattern".
        """
        compiled: list[re.Pattern] = []
        for raw in items or []:
            if isinstance(raw, dict):
                pattern_str = raw.get("pattern", "")
            elif isinstance(raw, str):
                pattern_str = raw
            else:
                continue

            pattern_str = pattern_str.lstrip("r").strip('"').strip("'")
            if not pattern_str:
                continue
            try:
                compiled.append(re.compile(pattern_str))
            except re.error as e:
                logger.warning(
                    "Invalid regex in YAML keywords/exclusions",
                    extra={"pattern": raw, "error": str(e)},
                )
        return compiled

    @staticmethod
    def _parse_filename_pattern_rules(items: list) -> list[FilenamePatternRule]:
        """
        Парсит filename_patterns/folder_patterns в typed rules.

        Backward compatibility:
        - legacy string -> kind='generic_form', weight=1.0
        - dict -> используем pattern/kind/weight
        """
        allowed_kinds = {"generic_form", "specific_subject", "context"}
        compiled_rules: list[FilenamePatternRule] = []

        for raw in items or []:
            if isinstance(raw, str):
                pattern_str = raw
                kind = "generic_form"
                weight = 1.0
            elif isinstance(raw, dict):
                pattern_str = str(raw.get("pattern", "")).strip()
                kind = str(raw.get("kind", "generic_form") or "generic_form").strip()
                try:
                    weight = float(raw.get("weight", 1.0))
                except (TypeError, ValueError):
                    weight = 1.0
            else:
                continue

            pattern_str = pattern_str.lstrip("r").strip('"').strip("'")
            if not pattern_str:
                continue

            if kind not in allowed_kinds:
                logger.warning(
                    "Invalid filename/folder rule kind, using 'generic_form'",
                    extra={"pattern": pattern_str, "kind": kind},
                )
                kind = "generic_form"

            if weight < 0:
                logger.warning(
                    "Negative filename/folder rule weight is not allowed, using 1.0",
                    extra={"pattern": pattern_str, "weight": weight},
                )
                weight = 1.0

            try:
                compiled = re.compile(pattern_str)
            except re.error as e:
                logger.warning(
                    "Invalid regex in YAML filename/folder patterns",
                    extra={"pattern": raw, "error": str(e)},
                )
                continue

            compiled_rules.append(
                FilenamePatternRule(
                    pattern=compiled,
                    raw_pattern=pattern_str,
                    kind=kind,
                    weight=weight,
                )
            )

        return compiled_rules

    def _parse_signal_list(self, items: list, group_level: str) -> list[dict]:
        """
        Парсит список сигналов из keywords.high/medium/low с поддержкой
        расширенного формата.
        """
        default_weights = {
            "high": 0.5,
            "medium": 0.3,
            "low": 0.15,
        }

        signals = []
        for item in items or []:
            if isinstance(item, str):
                pattern_str = item.lstrip("r").strip('"').strip("'")
                if not pattern_str:
                    continue

                try:
                    compiled = re.compile(pattern_str, re.IGNORECASE)
                except re.error as e:
                    logger.warning(
                        "Invalid regex pattern in lexical signals",
                        extra={"pattern": item, "error": str(e)},
                    )
                    continue

                signals.append({
                    "pattern": compiled,
                    "weight": default_weights.get(group_level, 0.3),
                    "distinctiveness": "medium",
                    "context": "any",
                    "description": None,
                })

            elif isinstance(item, dict):
                pattern_str = item.get("pattern", "")
                if not pattern_str:
                    continue

                pattern_str = pattern_str.lstrip("r").strip('"').strip("'")
                try:
                    compiled = re.compile(pattern_str, re.IGNORECASE)
                except re.error as e:
                    logger.warning(
                        "Invalid regex pattern in lexical signals",
                        extra={"pattern": pattern_str, "error": str(e)},
                    )
                    continue

                try:
                    weight = float(item.get("weight", default_weights.get(group_level, 0.3)))
                except (TypeError, ValueError):
                    logger.warning(
                        "Invalid weight in lexical signals, using default",
                        extra={"pattern": pattern_str, "weight": item.get("weight")},
                    )
                    weight = default_weights.get(group_level, 0.3)

                distinctiveness = item.get("distinctiveness", "medium")
                context = item.get("context", "any")
                description = item.get("description")

                if distinctiveness not in ("high", "medium", "low"):
                    logger.warning(
                        "Invalid distinctiveness value, using 'medium'",
                        extra={"value": distinctiveness, "pattern": pattern_str},
                    )
                    distinctiveness = "medium"

                if context not in ("header", "body", "any"):
                    logger.warning(
                        "Invalid context value, using 'any'",
                        extra={"value": context, "pattern": pattern_str},
                    )
                    context = "any"

                signals.append({
                    "pattern": compiled,
                    "weight": weight,
                    "distinctiveness": distinctiveness,
                    "context": context,
                    "description": description,
                })

        return signals

    def _parse_negative_signals(self, items: list) -> list[dict]:
        """
        Парсит список exclusions с поддержкой расширенного формата.
        """
        signals = []
        for item in items or []:
            if isinstance(item, str):
                pattern_str = item.lstrip("r").strip('"').strip("'")
                if not pattern_str:
                    continue

                try:
                    compiled = re.compile(pattern_str, re.IGNORECASE)
                except re.error as e:
                    logger.warning(
                        "Invalid regex pattern in exclusions",
                        extra={"pattern": item, "error": str(e)},
                    )
                    continue

                signals.append({
                    "pattern": compiled,
                    "severity": "soft",
                    "weight": -0.3,
                    "description": None,
                })

            elif isinstance(item, dict):
                pattern_str = item.get("pattern", "")
                if not pattern_str:
                    continue

                pattern_str = pattern_str.lstrip("r").strip('"').strip("'")
                try:
                    compiled = re.compile(pattern_str, re.IGNORECASE)
                except re.error as e:
                    logger.warning(
                        "Invalid regex pattern in exclusions",
                        extra={"pattern": pattern_str, "error": str(e)},
                    )
                    continue

                severity = item.get("severity", "soft")
                try:
                    weight = float(item.get("weight", -0.3))
                except (TypeError, ValueError):
                    logger.warning(
                        "Invalid weight in exclusions, using default",
                        extra={"pattern": pattern_str, "weight": item.get("weight")},
                    )
                    weight = -0.3
                description = item.get("description")

                if severity not in ("hard", "soft"):
                    logger.warning(
                        "Invalid severity value, using 'soft'",
                        extra={"value": severity, "pattern": pattern_str},
                    )
                    severity = "soft"

                signals.append({
                    "pattern": compiled,
                    "severity": severity,
                    "weight": weight,
                    "description": description,
                })

        return signals

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
        configs   = registry.get_all_configs()
        cfg       = registry.get_config("contract1.1spa")
    """

    def __init__(self, registry_path: str):
        self.registry_path = registry_path
        self._configs: dict[str, DocumentTypeConfig] = {}
        self._load()

    @staticmethod
    def _read_text_file(path: str) -> str:
        with open(path, encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def _safe_yaml_load(text: str) -> dict:
        loaded = yaml.safe_load(text)
        return loaded if isinstance(loaded, dict) else {}

    @staticmethod
    def _normalize_pattern_source(pattern: re.Pattern | FilenamePatternRule | str | None) -> str:
        """
        Нормализует regex-паттерн в строку для кросс-типового сравнения.
        """
        if pattern is None:
            return ""

        if isinstance(pattern, FilenamePatternRule):
            raw = pattern.raw_pattern
        elif isinstance(pattern, re.Pattern):
            raw = pattern.pattern
        else:
            raw = str(pattern)

        return raw.lstrip("r").strip('"').strip("'").strip()

    def _build_fallback_config(
        self,
        *,
        type_code: str,
        registry_entry: dict,
        warning_message: str,
        yaml_path: str | None = None,
        error: Exception | None = None,
    ) -> DocumentTypeConfig:
        warnings = [warning_message]
        if error is not None:
            warnings.append(str(error))

        fallback_raw = dict(registry_entry or {})
        canonical_yaml = DocumentTypeConfig._dump_canonical_yaml(fallback_raw)

        logger.warning(
            warning_message,
            extra={
                "type_code": type_code,
                "path": yaml_path,
                "error": str(error) if error else None,
            },
        )

        return DocumentTypeConfig(
            fallback_raw,
            source_yaml=None,
            source_path=yaml_path,
            source_sha256=DocumentTypeConfig._compute_sha256(canonical_yaml),
            source_kind="registry_fallback",
            registry_entry_raw=dict(registry_entry or {}),
            load_warnings=warnings,
        )

    def _load(self) -> None:
        registry_file = os.path.join(self.registry_path, "registry.yaml")
        if not os.path.exists(registry_file):
            logger.warning(
                "YAML registry not found",
                path=registry_file,
            )
            return

        registry_text = self._read_text_file(registry_file)
        registry = self._safe_yaml_load(registry_text)

        for entry in registry.get("document_types", []):
            if not isinstance(entry, dict):
                continue

            type_code = entry.get("type", "")
            if not type_code:
                continue

            direct = os.path.join(self.registry_path, f"{type_code}.yaml")

            yaml_path: str | None = None
            if os.path.exists(direct):
                yaml_path = direct
            else:
                pattern = os.path.join(self.registry_path, "**", f"{type_code}.yaml")
                candidates = sorted(glob.glob(pattern, recursive=True))
                if candidates:
                    yaml_path = candidates[0]

            if yaml_path is None:
                self._configs[type_code] = self._build_fallback_config(
                    type_code=type_code,
                    registry_entry=entry,
                    warning_message="Type YAML not found — using minimal config from registry",
                    yaml_path=None,
                    error=None,
                )
                continue

            try:
                source_yaml = self._read_text_file(yaml_path)
                type_raw = self._safe_yaml_load(source_yaml) or {}
            except Exception as e:
                self._configs[type_code] = self._build_fallback_config(
                    type_code=type_code,
                    registry_entry=entry,
                    warning_message="Type YAML cannot be read — using minimal config from registry",
                    yaml_path=yaml_path,
                    error=e,
                )
                continue

            if not type_raw:
                self._configs[type_code] = self._build_fallback_config(
                    type_code=type_code,
                    registry_entry=entry,
                    warning_message="Type YAML is empty or not a mapping — using minimal config from registry",
                    yaml_path=yaml_path,
                    error=None,
                )
                continue

            merged_raw = dict(type_raw or {})

            # Preserve registry-level metadata for runtime access when missing in type YAML.
            # Do not overwrite fields explicitly defined in the type YAML.
            for key in ("group", "category", "name", "type"):
                if key not in merged_raw and key in entry:
                    merged_raw[key] = entry[key]

            self._configs[type_code] = DocumentTypeConfig(
                merged_raw,
                source_yaml=source_yaml,
                source_path=yaml_path,
                source_sha256=DocumentTypeConfig._compute_sha256(source_yaml),
                source_kind="file",
                registry_entry_raw=dict(entry),
                load_warnings=[],
            )

        logger.info(
            "YAML registry loaded",
            total_types=len(self._configs),
        )
        logger.debug(
            "YAML registry types preview",
            sample_types=list(self._configs.keys())[:10],
        )

    def validate_all_patterns(self) -> tuple[bool, list[dict]]:
        """
        Валидация всех regex-паттернов в загруженных конфигах.

        UPDATED: теперь также валидирует:
        - kind/weight у filename_patterns и folder_patterns
        - поля weight, distinctiveness, context в lexical signals
        - поля severity, weight в negative signals
        - параметры scoring
        """
        errors = []
        allowed_filename_kinds = {"generic_form", "specific_subject", "context"}

        for type_code, cfg in self._configs.items():
            raw = cfg.raw or {}
            runtime = raw.get("classification_runtime_v1") or {}
            rules = runtime.get("rules") or raw.get("rules", {}) or {}

            pattern_fields = {
                "filename_patterns": rules.get("filename_patterns", []),
                "folder_patterns": rules.get("folder_patterns", []),
                "header_patterns": (
                    runtime.get("header_patterns")
                    or raw.get("header_patterns")
                    or rules.get("header_patterns")
                    or []
                ),
            }

            for field_name, patterns in pattern_fields.items():
                for idx, item in enumerate(patterns or []):
                    if isinstance(item, str):
                        pattern_str = item
                    elif isinstance(item, dict):
                        pattern_str = item.get("pattern", "")
                    else:
                        continue

                    clean = str(pattern_str).lstrip("r").strip('"').strip("'")
                    if not clean:
                        continue

                    try:
                        re.compile(clean)
                    except re.error as e:
                        errors.append(
                            {
                                "type_code": type_code,
                                "field": f"{field_name}[{idx}]",
                                "pattern": pattern_str,
                                "error": str(e),
                            }
                        )

                    if field_name in ("filename_patterns", "folder_patterns") and isinstance(item, dict):
                        kind = item.get("kind")
                        if kind is not None and kind not in allowed_filename_kinds:
                            errors.append(
                                {
                                    "type_code": type_code,
                                    "field": f"{field_name}[{idx}].kind",
                                    "pattern": pattern_str,
                                    "error": f"Invalid value: {kind}, expected one of {sorted(allowed_filename_kinds)}",
                                }
                            )

                        if "weight" in item:
                            weight = item.get("weight")
                            if not isinstance(weight, (int, float)):
                                errors.append(
                                    {
                                        "type_code": type_code,
                                        "field": f"{field_name}[{idx}].weight",
                                        "pattern": pattern_str,
                                        "error": f"Expected numeric weight, got {weight!r}",
                                    }
                                )
                            elif weight < 0:
                                errors.append(
                                    {
                                        "type_code": type_code,
                                        "field": f"{field_name}[{idx}].weight",
                                        "pattern": pattern_str,
                                        "error": f"Expected weight >= 0, got {weight}",
                                    }
                                )

            kw = rules.get("keywords", {}) or {}
            for level in ("high", "medium", "low"):
                for idx, item in enumerate(kw.get(level, []) or []):
                    if isinstance(item, str):
                        clean = item.lstrip("r").strip('"').strip("'")
                        if clean:
                            try:
                                re.compile(clean)
                            except re.error as e:
                                errors.append({
                                    "type_code": type_code,
                                    "field": f"keywords.{level}[{idx}]",
                                    "pattern": item,
                                    "error": str(e),
                                })
                    elif isinstance(item, dict):
                        pattern_str = item.get("pattern", "")
                        if pattern_str:
                            clean = pattern_str.lstrip("r").strip('"').strip("'")
                            try:
                                re.compile(clean)
                            except re.error as e:
                                errors.append({
                                    "type_code": type_code,
                                    "field": f"keywords.{level}[{idx}].pattern",
                                    "pattern": pattern_str,
                                    "error": str(e),
                                })

                        if "distinctiveness" in item and item["distinctiveness"] not in ("high", "medium", "low"):
                            errors.append({
                                "type_code": type_code,
                                "field": f"keywords.{level}[{idx}].distinctiveness",
                                "pattern": pattern_str,
                                "error": f"Invalid value: {item['distinctiveness']}, expected 'high'|'medium'|'low'",
                            })

                        if "context" in item and item["context"] not in ("header", "body", "any"):
                            errors.append({
                                "type_code": type_code,
                                "field": f"keywords.{level}[{idx}].context",
                                "pattern": pattern_str,
                                "error": f"Invalid value: {item['context']}, expected 'header'|'body'|'any'",
                            })

            for idx, item in enumerate(rules.get("exclusions", []) or []):
                if isinstance(item, str):
                    clean = item.lstrip("r").strip('"').strip("'")
                    if clean:
                        try:
                            re.compile(clean)
                        except re.error as e:
                            errors.append({
                                "type_code": type_code,
                                "field": f"exclusions[{idx}]",
                                "pattern": item,
                                "error": str(e),
                            })
                elif isinstance(item, dict):
                    pattern_str = item.get("pattern", "")
                    if pattern_str:
                        clean = pattern_str.lstrip("r").strip('"').strip("'")
                        try:
                            re.compile(clean)
                        except re.error as e:
                            errors.append({
                                "type_code": type_code,
                                "field": f"exclusions[{idx}].pattern",
                                "pattern": pattern_str,
                                "error": str(e),
                            })

                    if "severity" in item and item["severity"] not in ("hard", "soft"):
                        errors.append({
                            "type_code": type_code,
                            "field": f"exclusions[{idx}].severity",
                            "pattern": pattern_str,
                            "error": f"Invalid value: {item['severity']}, expected 'hard'|'soft'",
                        })

            scoring = runtime.get("scoring", {})
            if scoring:
                for param, value in scoring.items():
                    if param in ("accept_threshold", "strong_signal_threshold", "max_confidence"):
                        if not isinstance(value, (int, float)) or not (0 < value <= 1):
                            errors.append({
                                "type_code": type_code,
                                "field": f"scoring.{param}",
                                "pattern": str(value),
                                "error": f"Expected float in range (0, 1], got {value}",
                            })
                    elif param == "ambiguity_margin":
                        if not isinstance(value, (int, float)) or not (0 <= value <= 1):
                            errors.append({
                                "type_code": type_code,
                                "field": f"scoring.{param}",
                                "pattern": str(value),
                                "error": f"Expected float in range [0, 1], got {value}",
                            })

        is_valid = len(errors) == 0

        if not is_valid:
            logger.error(
                "YAML Registry validation FAILED",
                extra={"total_errors": len(errors), "errors_sample": errors[:10]},
            )
        else:
            logger.info(
                "YAML Registry validation PASSED",
                total_types=len(self._configs),
            )

        return is_valid, errors

    def validate_cross_type_distinctive_patterns(self) -> list[dict]:
        """
        Ищет дублирующиеся distinctive lexical patterns между разными type_code.
        """
        index: dict[str, list[dict]] = {}

        for type_code, cfg in self._configs.items():
            lexical_signals = getattr(cfg, "lexical_signals", {}) or {}

            for level in ("high", "medium", "low"):
                for signal in lexical_signals.get(level, []) or []:
                    if not isinstance(signal, dict):
                        continue

                    if signal.get("distinctiveness") != "high":
                        continue

                    normalized_pattern = self._normalize_pattern_source(signal.get("pattern"))
                    if not normalized_pattern:
                        continue

                    index.setdefault(normalized_pattern, []).append(
                        {
                            "type_code": type_code,
                            "level": level,
                            "context": signal.get("context", "any"),
                            "weight": signal.get("weight"),
                            "description": signal.get("description"),
                            "source_path": getattr(cfg, "source_path", None),
                        }
                    )

        warnings: list[dict] = []
        for pattern, occurrences in index.items():
            unique_types = sorted({item["type_code"] for item in occurrences})
            if len(unique_types) <= 1:
                continue

            warning = {
                "pattern": pattern,
                "types": unique_types,
                "occurrences": occurrences,
            }
            warnings.append(warning)

        if warnings:
            logger.warning(
                "YAML Registry cross-type distinctive pattern collisions detected",
                extra={
                    "total_collisions": len(warnings),
                    "sample": warnings[:10],
                },
            )
        else:
            logger.info(
                "YAML Registry cross-type distinctive pattern validation passed",
                total_types=len(self._configs),
            )

        return warnings

    def get_all_configs(self) -> list[DocumentTypeConfig]:
        return list(self._configs.values())

    def get_config(self, type_code: str) -> DocumentTypeConfig | None:
        return self._configs.get(type_code)

    def get_parent(self, type_code: str) -> str | None:
        """
        Return type-level parent class from individual YAML, if available.
        Example: class_1_transfer_of_ownership
        """
        cfg = self._configs.get(type_code)
        if not cfg:
            return None
        parent = getattr(cfg, "parent", "") or ""
        return parent or None

    def get_group(self, type_code: str) -> str | None:
        """
        Return registry-level group from registry.yaml, if available.
        Example: group_1_ownership
        """
        cfg = self._configs.get(type_code)
        if not cfg:
            return None
        group = getattr(cfg, "group", "") or ""
        return group or None

    def get_types_by_parent(self, parent: str) -> list[str]:
        """
        Return all type_code values that belong to the given parent class.
        """
        parent = (parent or "").strip()
        if not parent:
            return []

        return [
            type_code
            for type_code, cfg in self._configs.items()
            if (getattr(cfg, "parent", "") or "") == parent
        ]

    def get_types_by_group(self, group: str) -> list[str]:
        """
        Return all type_code values that belong to the given registry group.
        """
        group = (group or "").strip()
        if not group:
            return []

        return [
            type_code
            for type_code, cfg in self._configs.items()
            if (getattr(cfg, "group", "") or "") == group
        ]

    @classmethod
    def get_instance(cls, validate: bool = True) -> "YAMLRegistry":
        """
        Получить singleton-экземпляр YAMLRegistry.
        """
        global _instance
        if _instance is None:
            with _lock:
                if _instance is None:
                    path = getattr(
                        settings,
                        "CLASSIFIER_REGISTRY_PATH",
                        "playbooks/document_types",
                    )
                    _instance = cls(path)

                    if validate:
                        is_valid, errors = _instance.validate_all_patterns()
                        if not is_valid:
                            error_summary = "\n".join(
                                f"  • {e['type_code']}.{e['field']}: {e['pattern']!r} → {e['error']}"
                                for e in errors[:5]
                            )
                            total_errors = len(errors)
                            more_msg = (
                                f"\n  ... and {total_errors - 5} more errors"
                                if total_errors > 5
                                else ""
                            )
                            raise RuntimeError(
                                f"YAML Registry has {total_errors} invalid regex pattern(s):\n"
                                f"{error_summary}{more_msg}\n"
                                f"Fix YAML files before starting the service."
                            )

                        collision_warnings = _instance.validate_cross_type_distinctive_patterns()
                        if collision_warnings:
                            logger.warning(
                                "YAML Registry loaded with distinctive pattern collisions",
                                extra={
                                    "total_collisions": len(collision_warnings),
                                    "sample": collision_warnings[:10],
                                },
                            )

        return _instance

    def get_master_doc_types(self) -> list[str]:
        """
        Stage 7: Return doc_types suitable as family master documents.
        """
        master_types: list[str] = []

        for type_code, cfg in self._configs.items():
            raw = cfg.raw or {}
            classification = raw.get("classification", {}) or {}
            level = classification.get("level", "L0")

            if level not in ("L2", "L3"):
                continue

            if raw.get("parent_doc_type"):
                continue

            master_types.append(type_code)

        logger.debug(
            "YAMLRegistry.get_master_doc_types",
            yaml_master_types=master_types,
        )
        return master_types

    def get_classification_rules(self, type_code: str) -> dict:
        """
        Получить правила классификации (ClassificationRulesSpec-подобный dict)
        для HybridClassifier / L1 / L2 / L3.
        """
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
        """
        return list(self._configs.keys())

    @classmethod
    def reset(cls):
        """Reset singleton — used in tests to reload registry between runs."""
        global _instance
        with _lock:
            _instance = None
            


