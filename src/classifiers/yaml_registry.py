# src/classifiers/yaml_registry.py

"""
YAML Registry — loads and caches document type configurations.

Reads registry.yaml (list of types + document type groups) and individual
type YAML files. Thread-safe singleton with lazy loading.

REGISTRY.YAML CONTRACT:

  document_types:              → list of document type entries
    - type / name / category / group

  document_type_groups:        → map of group_id → human-readable label + order
                                 (DD Grid V1 top-level class headers)
    group_id:
      label: "..."
      display_order: <int>

YAML CONTRACT (canonical):

  classification_runtime_v1:   → classification only (L1/L2/L3)
  trigger_definitions:         → trigger detection only (root level, required)
  checks_v8:                   → risk checks (DocTypeCheckLoader)
  doc_type_checks:             → legacy risk checks (DocTypeCheckLoader)
  compliance_rules:            → conditional critical checks (DocTypeCheckLoader)
  shared_patterns:             → regex templates for checks
  dd_request_templates:        → export only, not risk execution
  essential_elements:          → PII tokenizer + L3 prototype
  metadata:                    → display/API/L4 context

LEGACY CONTRACTS (still active, marked for removal):
  rules:                       → root-level fallback for classification_runtime_v1.rules
  header_patterns:             → root-level fallback for classification_runtime_v1.header_patterns
  classification.level:        → used by get_master_doc_types() for family/relations
  parent_doc_type:             → used by get_master_doc_types() for family/relations

DEAD CODE REMOVED:
  validation_engine_v3_2:     → legacy block, no longer read
  validation_metadata:        → legacy block, no longer read
  self.triggerdefinitions:    → typo/dead attribute, removed
  classification_runtime_v1.trigger_definitions: → misplaced, never worked
"""

from __future__ import annotations

import glob
import hashlib
import os
import re
import threading
from dataclasses import dataclass

import yaml

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)
_lock = threading.Lock()
_instance: YAMLRegistry | None = None


def _pattern_to_text(raw_pattern: str) -> str:
    """Извлекает читаемый текст из regex-паттерна для L3-прототипа.

    Убирает regex-специфичный синтаксис, чтобы embedding-модель
    получала семантически осмысленный текст, а не шум из \b, (?i) и т.п.
    """
    s = raw_pattern.strip()
    s = re.sub(r"^\(\?[imsux]+\)", "", s)
    s = re.sub(r"\\[bBsSwWdD]", " ", s)
    s = re.sub(r"[+*?]|\{\d+,?\d*\}", "", s)
    s = re.sub(r"[\[\]()^$|\\]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


@dataclass(slots=True)
class FilenamePatternRule:
    """
    Rule object for L1 filename/folder matching.

    kind:
    - generic_form:    общий маркер формы документа (SPA, agreement)
    - specific_subject: предметно-специфичный маркер (real estate, factoring)
    - context:         вспомогательный контекстный маркер
    """

    pattern: re.Pattern
    raw_pattern: str
    kind: str = "generic_form"
    weight: float = 1.0


# ─── Document type group metadata (DD Grid V1) ────────────────────────────────


_GROUP_LABEL_FALLBACK_ORDER = 9999


@dataclass(frozen=True, slots=True)
class DocumentTypeGroupConfig:
    """
    Human-readable metadata for a document type group.

    Referenced from registry.yaml section `document_type_groups`.
    Consumed by DD Grid V1 builder (V1.7) as top-level class header data.

    Fields:
        group_id:      Internal machine-readable id (matches document_types[].group).
        label:         Human-readable label shown to a lawyer in DD Grid.
        display_order: Sort key for hierarchy display. Lower = earlier.
                       Fallback = 9999 when not declared.

    Source of truth:
        registry.yaml → document_type_groups[group_id]

    Fallback semantics:
        If group_id is used in document_types[].group but not declared in
        document_type_groups, YAMLRegistry produces a fallback entry with
        label = group_id and display_order = 9999. This prevents silent data
        loss and makes missing entries visible in UI.
    """

    group_id: str
    label: str
    display_order: int = _GROUP_LABEL_FALLBACK_ORDER


class DocumentTypeConfig:
    """
    Parsed configuration for one document type.

    Строит runtime-представление одного YAML-файла типа документа
    для всех уровней классификации (L1–L3), trigger detector,
    risk checks, PII tokenizer и persistence.

    Provenance fields (для persistence в DocumentTypeInstructionVersion):
    - source_yaml:         полный raw YAML text snapshot
    - source_path:         путь к YAML-файлу
    - source_sha256:       SHA256 от source_yaml
    - source_kind:         'file' | 'registry_fallback'
    - registry_entry_raw:  исходная запись из registry.yaml
    - load_warnings:       предупреждения загрузки
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

        # ── Provenance ────────────────────────────────────────────────
        self.source_yaml = source_yaml
        self.source_path = source_path
        self.source_kind = source_kind
        self.registry_entry_raw = registry_entry_raw or {}
        self.load_warnings = list(load_warnings or [])
        self.source_sha256 = source_sha256 or self._compute_sha256(
            source_yaml
            if isinstance(source_yaml, str) and source_yaml.strip()
            else self._dump_canonical_yaml(self.raw)
        )

        # ── Identity ──────────────────────────────────────────────────
        self.type_code = str(self.raw.get("type", ""))
        self.name = str(self.raw.get("name", ""))

        # Registry-level grouping (из registry.yaml, поле group)
        self.group: str = str(self.raw.get("group", "") or "").strip()

        # Type-level family class (из type YAML, поле parent)
        self.parent: str = str(self.raw.get("parent", "") or "").strip()

        # ── Classification runtime ────────────────────────────────────
        runtime = self.raw.get("classification_runtime_v1") or {}

        # LEGACY FALLBACK: поддерживает YAML без classification_runtime_v1.
        # Убрать после миграции всех type YAML на расширенный формат.
        # Критерий готовности к удалению:
        #   - все YAML имеют classification_runtime_v1.rules
        #   - L2._classify_with_legacy_format() не вызывается ни для одного типа
        rules = runtime.get("rules") or self.raw.get("rules", {}) or {}

        self.scoring = runtime.get("scoring") or {}

        # ── L1: filename/folder patterns ──────────────────────────────
        self.filename_patterns: list[FilenamePatternRule] = (
            self._parse_filename_pattern_rules(rules.get("filename_patterns", []))
        )
        self.folder_patterns: list[FilenamePatternRule] = (
            self._parse_filename_pattern_rules(rules.get("folder_patterns", []))
        )

        # ── L2: header patterns ───────────────────────────────────────
        # LEGACY FALLBACK: три источника для header_patterns.
        # Убрать после того как убран L2._classify_with_legacy_format().
        # Canonical источник: classification_runtime_v1.header_patterns
        explicit_header = (
            runtime.get("header_patterns")
            or self.raw.get("header_patterns")
            or rules.get("header_patterns")
            or []
        )

        # LEGACY FALLBACK: если header_patterns не заданы,
        # используем keywords.high как proxy для L2 legacy path.
        # Будет удалено вместе с L2._classify_with_legacy_format().
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
                compiled = re.compile(
                    p.lstrip("r").strip('"').strip("'"),
                    re.IGNORECASE,
                )
                self.header_patterns.append(compiled)
            except re.error:
                logger.warning(
                    "Invalid header pattern in YAML",
                    extra={"type_code": self.type_code, "pattern": p},
                )

        # ── L2/L3: lexical signals (extended format) ──────────────────
        kw = rules.get("keywords", {}) or {}

        self.lexical_signals = {
            "high": self._parse_signal_list(kw.get("high", []), "high"),
            "medium": self._parse_signal_list(kw.get("medium", []), "medium"),
            "low": self._parse_signal_list(kw.get("low", []), "low"),
        }

        # ── L2: legacy compiled keyword lists ────────────────────────
        # Используются только в L2._classify_with_legacy_format().
        # Убрать вместе с legacy L2 path.
        self.keywords_high = self._compile_regex_list(kw.get("high", []))
        self.keywords_medium = self._compile_regex_list(kw.get("medium", []))
        self.keywords_low = self._compile_regex_list(kw.get("low", []))

        self.negative_signals = self._parse_negative_signals(rules.get("exclusions", []))
        self.exclusions = self._compile_regex_list(rules.get("exclusions", []))

        # ── L3: text representations for embedding prototypes ─────────
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

        # ── Triggers ──────────────────────────────────────────────────
        # CANONICAL: trigger_definitions только на root-уровне YAML.
        # Нигде else не должно быть trigger_definitions.
        # Валидация в validate_all_patterns() запрещает
        # classification_runtime_v1.trigger_definitions.
        tdef = self.raw.get("trigger_definitions", {}) or {}
        self.trigger_ids: list[str] = list(tdef.keys())
        self.trigger_definitions: dict = tdef

        # ── Metadata ──────────────────────────────────────────────────
        metadata = self.raw.get("metadata", {}) or {}
        self.category: str = str(metadata.get("category", "contract"))
        self.subcategory: str = str(metadata.get("subcategory", "") or "").strip()
        self.complexity: str = str(metadata.get("complexity", "medium"))
        self.risk_level: str = str(metadata.get("risk_level", "medium"))
        self.language: str = str(metadata.get("language", "ru"))
        self.jurisdiction: str = str(metadata.get("jurisdiction", "RU"))
        self.aliases: list[str] = list(metadata.get("aliases", []) or [])
        self.section_markers: list[str] = list(metadata.get("section_markers", []) or [])

        # ── PII / party roles ─────────────────────────────────────────
        self.essential_elements: list[dict] = list(self.raw.get("essential_elements") or [])
        self.party_role_keywords: dict[str, str] = self._build_party_role_keywords(self.raw)

    # ── Static helpers ────────────────────────────────────────────────

    @staticmethod
    def _compute_sha256(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _dump_canonical_yaml(raw: dict) -> str:
        """
        Fallback canonical representation для hash computation
        когда source_yaml недоступен (registry_fallback configs).
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
        Компилирует список regex-паттернов в list[re.Pattern].
        Поддерживает str и dict (расширенный формат, извлекает поле pattern).
        Не падает при ошибке компиляции.
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
        Парсит filename_patterns/folder_patterns в list[FilenamePatternRule].

        Форматы:
        - str  → kind='generic_form', weight=1.0
        - dict → используем pattern/kind/weight
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
                    "Negative filename/folder rule weight, using 1.0",
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
        Парсит keywords.high/medium/low в структурированные lexical signals.

        Форматы:
        - str  → {pattern, weight (default), distinctiveness='medium', context='any'}
        - dict → {pattern, weight, distinctiveness, context, description}
        """
        default_weights = {"high": 0.5, "medium": 0.3, "low": 0.15}

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
                    weight = float(
                        item.get("weight", default_weights.get(group_level, 0.3))
                    )
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
        Парсит exclusions в структурированные negative signals.

        Форматы:
        - str  → {pattern, severity='soft', weight=-0.3}
        - dict → {pattern, severity, weight, description}
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
        Строит {keyword_lower: ROLE_ID} из essential_elements.parties.party_roles.
        Используется PII tokenizer.
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
        cfg      = registry.get_config("contract_1.1_general_sale")
    """

    def __init__(self, registry_path: str):
        self.registry_path = registry_path
        self._configs: dict[str, DocumentTypeConfig] = {}
        self._groups: dict[str, DocumentTypeGroupConfig] = {}
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
    def _normalize_pattern_source(
        pattern: re.Pattern | FilenamePatternRule | str | None,
    ) -> str:
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
            logger.warning("YAML registry not found", path=registry_file)
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
                    warning_message=(
                        "Type YAML not found — using minimal config from registry"
                    ),
                )
                continue

            try:
                source_yaml = self._read_text_file(yaml_path)
                type_raw = self._safe_yaml_load(source_yaml) or {}
            except Exception as e:
                self._configs[type_code] = self._build_fallback_config(
                    type_code=type_code,
                    registry_entry=entry,
                    warning_message=(
                        "Type YAML cannot be read — using minimal config from registry"
                    ),
                    yaml_path=yaml_path,
                    error=e,
                )
                continue

            if not type_raw:
                self._configs[type_code] = self._build_fallback_config(
                    type_code=type_code,
                    registry_entry=entry,
                    warning_message=(
                        "Type YAML is empty or not a mapping "
                        "— using minimal config from registry"
                    ),
                    yaml_path=yaml_path,
                )
                continue

            merged_raw = dict(type_raw)

            # Preserve registry-level metadata when missing in type YAML.
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

        self._parse_document_type_groups(registry)

        logger.info(
            "YAML registry loaded",
            total_types=len(self._configs),
            total_groups=len(self._groups),
        )
        logger.debug(
            "YAML registry types preview",
            sample_types=list(self._configs.keys())[:10],
        )
        logger.debug(
            "YAML registry groups preview",
            sample_groups=sorted(self._groups.keys())[:10],
        )

    def _parse_document_type_groups(self, registry: dict) -> None:
        """
        Parse `document_type_groups` section from registry.yaml.

        Contract:
            document_type_groups:
              <group_id>:
                label: <str>            # required, non-empty
                display_order: <int>    # optional, defaults to 9999

        Behaviour:
        - Malformed entries are skipped with a warning (never fail the load).
        - After parsing declared entries, ensure every group_id actually
          used in document_types[] has an entry. Missing group_ids get a
          fallback DocumentTypeGroupConfig with label = group_id and
          display_order = 9999. This prevents silent data loss.
        """
        raw_groups = registry.get("document_type_groups") or {}
        if not isinstance(raw_groups, dict):
            logger.warning(
                "YAML registry: document_type_groups is not a mapping, ignoring",
                type_got=type(raw_groups).__name__,
            )
            raw_groups = {}

        # Step 1: parse explicitly declared entries.
        for group_id, entry in raw_groups.items():
            group_id_norm = str(group_id or "").strip()
            if not group_id_norm:
                logger.warning(
                    "YAML registry: document_type_groups entry with empty id, skipping",
                    entry_preview=str(entry)[:100],
                )
                continue

            if not isinstance(entry, dict):
                logger.warning(
                    "YAML registry: document_type_groups entry is not a mapping, "
                    "using fallback",
                    group_id=group_id_norm,
                    type_got=type(entry).__name__,
                )
                self._groups[group_id_norm] = DocumentTypeGroupConfig(
                    group_id=group_id_norm,
                    label=group_id_norm,
                    display_order=_GROUP_LABEL_FALLBACK_ORDER,
                )
                continue

            label_raw = entry.get("label")
            label = str(label_raw).strip() if isinstance(label_raw, str) else ""
            if not label:
                logger.warning(
                    "YAML registry: document_type_groups entry has empty label, "
                    "using group_id as label",
                    group_id=group_id_norm,
                )
                label = group_id_norm

            display_order_raw = entry.get("display_order", _GROUP_LABEL_FALLBACK_ORDER)
            if isinstance(display_order_raw, int) and not isinstance(display_order_raw, bool):
                display_order = display_order_raw
            else:
                logger.warning(
                    "YAML registry: document_type_groups entry has non-int "
                    "display_order, using fallback",
                    group_id=group_id_norm,
                    display_order_raw=str(display_order_raw),
                )
                display_order = _GROUP_LABEL_FALLBACK_ORDER

            self._groups[group_id_norm] = DocumentTypeGroupConfig(
                group_id=group_id_norm,
                label=label,
                display_order=display_order,
            )

        # Step 2: fallback for groups actually used but not declared.
        used_group_ids: set[str] = set()
        for cfg in self._configs.values():
            group_id = getattr(cfg, "group", "") or ""
            group_id = group_id.strip()
            if group_id:
                used_group_ids.add(group_id)

        missing = used_group_ids - set(self._groups.keys())
        for group_id in sorted(missing):
            logger.warning(
                "YAML registry: group_id used in document_types but not declared "
                "in document_type_groups, generating fallback entry",
                group_id=group_id,
            )
            self._groups[group_id] = DocumentTypeGroupConfig(
                group_id=group_id,
                label=group_id,
                display_order=_GROUP_LABEL_FALLBACK_ORDER,
            )

    def validate_all_patterns(self) -> tuple[bool, list[dict]]:
        """
        Валидация всех паттернов и схемы YAML-конфигов.

        Проверяет:
        1. regex компилируемость (filename, folder, header, keywords, exclusions)
        2. kind/weight у filename/folder patterns
        3. distinctiveness, context у lexical signals
        4. severity, weight у exclusions
        5. scoring параметры
        6. архитектурные ошибки схемы:
           - trigger_definitions не на root-уровне
           - запрещённые legacy блоки
           - неверный тип trigger_definitions
        """
        errors = []
        allowed_filename_kinds = {"generic_form", "specific_subject", "context"}

        for type_code, cfg in self._configs.items():
            raw = cfg.raw or {}
            runtime = raw.get("classification_runtime_v1") or {}
            rules = runtime.get("rules") or raw.get("rules", {}) or {}

            # ── Schema validation ─────────────────────────────────────

            # Запрет misplaced trigger_definitions
            if runtime.get("trigger_definitions"):
                errors.append({
                    "type_code": type_code,
                    "field": "classification_runtime_v1.trigger_definitions",
                    "pattern": "",
                    "error": (
                        "trigger_definitions must be at root level, "
                        "not inside classification_runtime_v1. "
                        "This silently produces empty applicable_triggers."
                    ),
                })

            # Запрет legacy validation blocks
            for legacy_block in ("validation_engine_v3_2", "validation_metadata"):
                if legacy_block in raw:
                    errors.append({
                        "type_code": type_code,
                        "field": legacy_block,
                        "pattern": "",
                        "error": (
                            f"Legacy block '{legacy_block}' is no longer supported. "
                            "Remove it from the YAML file."
                        ),
                    })

            # Проверка типа trigger_definitions
            trigger_defs = raw.get("trigger_definitions")
            if trigger_defs is not None and not isinstance(trigger_defs, dict):
                errors.append({
                    "type_code": type_code,
                    "field": "trigger_definitions",
                    "pattern": "",
                    "error": (
                        f"trigger_definitions must be a dict, "
                        f"got {type(trigger_defs).__name__}. "
                        "This will produce empty applicable_triggers."
                    ),
                })

            # ── Pattern validation ────────────────────────────────────

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
                        errors.append({
                            "type_code": type_code,
                            "field": f"{field_name}[{idx}]",
                            "pattern": pattern_str,
                            "error": str(e),
                        })

                    if (
                        field_name in ("filename_patterns", "folder_patterns")
                        and isinstance(item, dict)
                    ):
                        kind = item.get("kind")
                        if kind is not None and kind not in allowed_filename_kinds:
                            errors.append({
                                "type_code": type_code,
                                "field": f"{field_name}[{idx}].kind",
                                "pattern": pattern_str,
                                "error": (
                                    f"Invalid value: {kind}, "
                                    f"expected one of {sorted(allowed_filename_kinds)}"
                                ),
                            })

                        if "weight" in item:
                            weight = item.get("weight")
                            if not isinstance(weight, int | float):
                                errors.append({
                                    "type_code": type_code,
                                    "field": f"{field_name}[{idx}].weight",
                                    "pattern": pattern_str,
                                    "error": (
                                        f"Expected numeric weight, got {weight!r}"
                                    ),
                                })
                            elif weight < 0:
                                errors.append({
                                    "type_code": type_code,
                                    "field": f"{field_name}[{idx}].weight",
                                    "pattern": pattern_str,
                                    "error": (
                                        f"Expected weight >= 0, got {weight}"
                                    ),
                                })

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

                        if "distinctiveness" in item and item["distinctiveness"] not in (
                            "high", "medium", "low",
                        ):
                            errors.append({
                                "type_code": type_code,
                                "field": f"keywords.{level}[{idx}].distinctiveness",
                                "pattern": pattern_str,
                                "error": (
                                    f"Invalid value: {item['distinctiveness']}, "
                                    "expected 'high'|'medium'|'low'"
                                ),
                            })

                        if "context" in item and item["context"] not in (
                            "header", "body", "any",
                        ):
                            errors.append({
                                "type_code": type_code,
                                "field": f"keywords.{level}[{idx}].context",
                                "pattern": pattern_str,
                                "error": (
                                    f"Invalid value: {item['context']}, "
                                    "expected 'header'|'body'|'any'"
                                ),
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
                            "error": (
                                f"Invalid value: {item['severity']}, "
                                "expected 'hard'|'soft'"
                            ),
                        })

            scoring = runtime.get("scoring", {})
            if scoring:
                for param, value in scoring.items():
                    if param in (
                        "accept_threshold",
                        "strong_signal_threshold",
                        "max_confidence",
                    ):
                        if not isinstance(value, int | float) or not (0 < value <= 1):
                            errors.append({
                                "type_code": type_code,
                                "field": f"scoring.{param}",
                                "pattern": str(value),
                                "error": (
                                    f"Expected float in range (0, 1], got {value}"
                                ),
                            })
                    elif param == "ambiguity_margin":
                        if not isinstance(value, int | float) or not (0 <= value <= 1):
                            errors.append({
                                "type_code": type_code,
                                "field": f"scoring.{param}",
                                "pattern": str(value),
                                "error": (
                                    f"Expected float in range [0, 1], got {value}"
                                ),
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
        Коллизии означают, что один паттерн не различает типы.
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

                    normalized_pattern = self._normalize_pattern_source(
                        signal.get("pattern")
                    )
                    if not normalized_pattern:
                        continue

                    index.setdefault(normalized_pattern, []).append({
                        "type_code": type_code,
                        "level": level,
                        "context": signal.get("context", "any"),
                        "weight": signal.get("weight"),
                        "description": signal.get("description"),
                        "source_path": getattr(cfg, "source_path", None),
                    })

        warnings: list[dict] = []
        for pattern, occurrences in index.items():
            unique_types = sorted({item["type_code"] for item in occurrences})
            if len(unique_types) <= 1:
                continue
            warnings.append({
                "pattern": pattern,
                "types": unique_types,
                "occurrences": occurrences,
            })

        if warnings:
            logger.warning(
                "YAML Registry cross-type distinctive pattern collisions detected",
                extra={"total_collisions": len(warnings), "sample": warnings[:10]},
            )
        else:
            logger.info(
                "YAML Registry cross-type distinctive pattern validation passed",
                total_types=len(self._configs),
            )

        return warnings

    # ── Public API ────────────────────────────────────────────────────

    def get_all_configs(self) -> list[DocumentTypeConfig]:
        return list(self._configs.values())

    def get_config(self, type_code: str) -> DocumentTypeConfig | None:
        return self._configs.get(type_code)

    def get_parent(self, type_code: str) -> str | None:
        cfg = self._configs.get(type_code)
        if not cfg:
            return None
        parent = getattr(cfg, "parent", "") or ""
        return parent or None

    def get_group(self, type_code: str) -> str | None:
        cfg = self._configs.get(type_code)
        if not cfg:
            return None
        group = getattr(cfg, "group", "") or ""
        return group or None

    def get_types_by_parent(self, parent: str) -> list[str]:
        parent = (parent or "").strip()
        if not parent:
            return []
        return [
            type_code
            for type_code, cfg in self._configs.items()
            if (getattr(cfg, "parent", "") or "") == parent
        ]

    def get_types_by_group(self, group: str) -> list[str]:
        group = (group or "").strip()
        if not group:
            return []
        return [
            type_code
            for type_code, cfg in self._configs.items()
            if (getattr(cfg, "group", "") or "") == group
        ]

    # ── Document type group metadata (DD Grid V1) ─────────────────────

    def get_document_type_groups(self) -> dict[str, DocumentTypeGroupConfig]:
        """
        Return all document type groups keyed by group_id.

        Contract for consumers:
        - includes all explicitly declared groups from registry.yaml
        - includes fallback entries for group_ids used in document_types[]
          but not declared in document_type_groups section
        - returns a shallow copy to prevent accidental mutation of the
          singleton state
        """
        return dict(self._groups)

    def get_document_type_group(
        self, group_id: str
    ) -> DocumentTypeGroupConfig | None:
        """
        Return metadata for a single document type group, or None if not found.

        Empty / whitespace-only group_id returns None.
        """
        if not isinstance(group_id, str):
            return None
        normalized = group_id.strip()
        if not normalized:
            return None
        return self._groups.get(normalized)

    # ─────────────────────────────────────────────────────────────────

    def get_classification_rules(self, type_code: str) -> dict:
        """
        Правила классификации для HybridClassifier / L1 / L2 / L3.
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
        return list(self._configs.keys())

    def get_master_doc_types(self) -> list[str]:
        """
        Возвращает типы, подходящие как master-документы для family/relations.

        LEGACY CONTRACT: читает raw["classification"]["level"] и "parent_doc_type".
        Убрать/заменить после рефакторинга family_builder.py и runner_repo.py.
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

    @classmethod
    def get_instance(cls, validate: bool = True) -> YAMLRegistry:
        """Получить singleton-экземпляр YAMLRegistry."""
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
                                f"  • {e['type_code']}.{e['field']}: "
                                f"{e['pattern']!r} → {e['error']}"
                                for e in errors[:5]
                            )
                            total_errors = len(errors)
                            more_msg = (
                                f"\n  ... and {total_errors - 5} more errors"
                                if total_errors > 5
                                else ""
                            )
                            raise RuntimeError(
                                f"YAML Registry has {total_errors} "
                                f"invalid pattern(s) or schema error(s):\n"
                                f"{error_summary}{more_msg}\n"
                                f"Fix YAML files before starting the service."
                            )

                        collision_warnings = (
                            _instance.validate_cross_type_distinctive_patterns()
                        )
                        if collision_warnings:
                            logger.warning(
                                "YAML Registry loaded with distinctive "
                                "pattern collisions",
                                extra={
                                    "total_collisions": len(collision_warnings),
                                    "sample": collision_warnings[:10],
                                },
                            )

        return _instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton — used in tests."""
        global _instance
        with _lock:
            _instance = None
