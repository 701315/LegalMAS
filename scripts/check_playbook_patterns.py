#!/usr/bin/env python3
"""
check_playbook_patterns.py
==========================
Скрипт проверки YAML-инструкций в /srv/steloom-dev/playbooks/document_types
на предмет соответствия эталонным паттернам, выделенным из образцовых файлов
(contract_1.1_general_sale, contract_2.1_lease, contract_1.6_real_estate).

Использование:
    python check_playbook_patterns.py [--path PATH] [--strict] [--json-report]

Примеры:
    python check_playbook_patterns.py
    python check_playbook_patterns.py --path /srv/steloom-dev/playbooks/document_types
    python check_playbook_patterns.py --strict --json-report
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
except ImportError:
    print("Ошибка: требуется библиотека PyYAML. Установите: pip install pyyaml")
    sys.exit(1)


# ════════════════════════════════════════════════════════════════════════════
# КОНСТАНТЫ
# ════════════════════════════════════════════════════════════════════════════

DEFAULT_PATH = "/srv/steloom-dev/playbooks/document_types"

# ── Обязательные поля верхнего уровня ────────────────────────────────────────
REQUIRED_TOP_LEVEL = [
    "type", "name", "version", "parent", "description",
    "metadata", "classification_runtime_v1", "trigger_definitions",
    "shared_patterns", "compliance_rules", "checks_v8", "dd_request_templates",
]

# ── Запрещённые блоки верхнего уровня ────────────────────────────────────────
FORBIDDEN_TOP_LEVEL = [
    "engine_expectations",
    "doc_type_checks",
]

# ── Обязательные поля metadata ───────────────────────────────────────────────
REQUIRED_METADATA = [
    "category", "subcategory", "complexity", "risk_level",
    "jurisdiction", "language", "legal_base", "doc_types_supported",
]

# ── Обязательные поля classification_runtime_v1 ──────────────────────────────
REQUIRED_CLASSIFICATION = [
    "scoring", "rules",
]
REQUIRED_SCORING = [
    "accept_threshold", "strong_signal_threshold", "ambiguity_margin",
    "input_quality_weight",
]
REQUIRED_CLASSIFICATION_RULES = [
    "filename_patterns", "folder_patterns", "keywords", "exclusions",
]
REQUIRED_KEYWORD_GROUPS = ["high", "medium", "low"]

# ── Обязательные поля каждого check в checks_v8 ──────────────────────────────
REQUIRED_CHECK_FIELDS = [
    "id", "name", "description", "triggers", "ui_mode",
    "severity", "severity_if_pass", "severity_if_fail", "severity_if_unclear",
    "origin", "detector_type", "rules",
]

# ── Обязательные поля llm ────────────────────────────────────────────────────
REQUIRED_LLM_FIELDS = [
    "prompt_template", "context_k", "temperature", "max_tokens",
]

# ── Обязательные секции промпта ──────────────────────────────────────────────
REQUIRED_PROMPT_SECTIONS = [
    "[КОНТЕКСТ]",
    "[ЗАДАЧА]",
    "[ПРАВИЛА]",
    "[ПРИМЕРЫ (FEW-SHOT)]",
    "[ПРОВЕРКА ПЕРЕД ОТВЕТОМ — CoVe]",
    "[ФОРМАТ ОТВЕТА]",
]

# ── Обязательные поля retrieval ──────────────────────────────────────────────
REQUIRED_RETRIEVAL_FIELDS = [
    "corpus_scope", "levels", "required_kind", "retrieval_query",
    "preferred_unit_types", "excluded_unit_types", "preferred_clause_functions",
    "negative_keywords", "position_bias", "context_k", "max_chunks", "rerank",
]
REQUIRED_POSITION_BIAS = ["preferred_range", "boost", "scope"]

# ── Обязательные поля evidence ───────────────────────────────────────────────
REQUIRED_EVIDENCE_FIELDS = [
    "required", "min_snippet_length", "max_snippet_length",
]

# ── Обязательные поля extraction ─────────────────────────────────────────────
REQUIRED_EXTRACTION_FIELDS = [
    "enabled", "mode", "compact_output", "fields",
]

# ── Обязательные теги в llm_prompt_extraction ────────────────────────────────
REQUIRED_EXTRACTION_TAGS = [
    "<role>", "<context>", "<task>", "<rules>",
]

# ── Обязательные поля поля (field) ───────────────────────────────────────────
REQUIRED_FIELD_ATTRS = ["name", "type", "presentation", "description", "required"]
REQUIRED_GRID_ATTRS = ["display_in_grid", "display_priority", "label"]
REQUIRED_ENUM_ATTRS = ["allowed_values"]

# ── Допустимые значения presentation ─────────────────────────────────────────
VALID_PRESENTATIONS = ["signal", "fact"]

# ── Допустимые значения severity ─────────────────────────────────────────────
VALID_SEVERITIES = ["low", "medium", "high", "critical"]

# ── Допустимые значения ui_mode ──────────────────────────────────────────────
VALID_UI_MODES = ["field_extraction", "clause_presence", "risk_check"]

# ── Допустимые значения detector_type ────────────────────────────────────────
VALID_DETECTOR_TYPES = ["rules", "hybrid", "llm"]

# ── Допустимые значения origin ───────────────────────────────────────────────
VALID_ORIGINS = ["DOCUMENT_TYPE", "GLOBAL", "REGULATORY"]

# ── Обязательные поля dd_request_templates ───────────────────────────────────
REQUIRED_DD_TEMPLATE_FIELDS = ["text", "addressee"]

# ── Запрещённые термины ─────────────────────────────────────────────────────
FORBIDDEN_FIELD_VALUES = ["not_found", "None", "null", "not_specified"]
FORBIDDEN_PROMPT_PHRASES = [
    'пиши "not_found"',
    'пиши "None"',
    'пиши "null"',
    'пиши "not_specified"',
]
CORRECT_MISSING_VALUE = "Данные не определены"
CORRECT_ENUM_MISSING = "not_defined"


# ════════════════════════════════════════════════════════════════════════════
# СТРУКТУРЫ ДАННЫХ
# ════════════════════════════════════════════════════════════════════════════

class Severity(Enum):
    PASS = "PASS"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    def __str__(self):
        return self.value

    @property
    def icon(self):
        icons = {
            "PASS": "✅",
            "INFO": "ℹ️ ",
            "WARNING": "⚠️ ",
            "ERROR": "❌",
            "CRITICAL": "🚨",
        }
        return icons[self.value]


@dataclass
class Issue:
    severity: Severity
    section: str
    message: str
    check_id: Optional[str] = None
    line_hint: Optional[str] = None

    def __str__(self):
        loc = f"[{self.section}]"
        if self.check_id:
            loc += f" → {self.check_id}"
        return f"{self.severity.icon} {self.severity.value:8s} {loc}: {self.message}"


@dataclass
class FileReport:
    filepath: str
    type_name: str = ""
    version: str = ""
    issues: List[Issue] = field(default_factory=list)
    checks_count: int = 0
    checks_passed: int = 0

    @property
    def errors_count(self):
        return sum(1 for i in self.issues if i.severity in (Severity.ERROR, Severity.CRITICAL))

    @property
    def warnings_count(self):
        return sum(1 for i in self.issues if i.severity == Severity.WARNING)

    @property
    def passed(self):
        return self.errors_count == 0


# ════════════════════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ════════════════════════════════════════════════════════════════════════════

def load_yaml(filepath: str) -> Tuple[Optional[dict], Optional[str]]:
    """Загружает YAML-файл. Возвращает (данные, ошибка)."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return None, f"Файл не является YAML-словарём (получен тип: {type(data).__name__})"
        return data, None
    except yaml.YAMLError as e:
        return None, f"Ошибка парсинга YAML: {e}"
    except Exception as e:
        return None, f"Ошибка чтения файла: {e}"


def find_yaml_files(root_path: str) -> List[str]:
    """Рекурсивно находит все YAML-файлы в подпапках."""
    yaml_files = []
    root = Path(root_path)
    if not root.exists():
        return []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix in (".yaml", ".yml"):
            yaml_files.append(str(path))
    return yaml_files


def get_nested(data: dict, dotpath: str) -> Any:
    """Доступ к вложенному ключу по точечной нотации."""
    keys = dotpath.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current


def is_nonempty(value) -> bool:
    """Проверяет, что значение непустое."""
    if value is None:
        return False
    if isinstance(value, str):
        return len(value.strip()) > 0
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


# ════════════════════════════════════════════════════════════════════════════
# МОДУЛИ ПРОВЕРКИ
# ════════════════════════════════════════════════════════════════════════════

def check_top_level_structure(data: dict, report: FileReport):
    """Проверяет структуру верхнего уровня."""
    # Запрещённые блоки
    for key in FORBIDDEN_TOP_LEVEL:
        if key in data:
            report.issues.append(Issue(
                Severity.CRITICAL, "top_level",
                f"Присутствует запрещённый блок '{key}' — должен быть удалён"
            ))

    # Обязательные поля
    for key in REQUIRED_TOP_LEVEL:
        if key not in data:
            report.issues.append(Issue(
                Severity.ERROR, "top_level",
                f"Отсутствует обязательное поле '{key}'"
            ))

    # compliance_rules должен быть пустым списком или отсутствовать
    compliance = data.get("compliance_rules")
    if compliance is not None and compliance != []:
        if isinstance(compliance, list) and len(compliance) > 0:
            report.issues.append(Issue(
                Severity.ERROR, "compliance_rules",
                f"compliance_rules должен быть пустым ([]), но содержит {len(compliance)} правил(а)"
            ))
        elif not isinstance(compliance, list):
            report.issues.append(Issue(
                Severity.ERROR, "compliance_rules",
                f"compliance_rules должен быть списком, получен тип: {type(compliance).__name__}"
            ))

    # version должен быть строкой
    version = data.get("version")
    if version is not None:
        report.version = str(version)
    type_name = data.get("type", "")
    if type_name:
        report.type_name = type_name


def check_metadata(data: dict, report: FileReport):
    """Проверяет блок metadata."""
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        return

    for key in REQUIRED_METADATA:
        if key not in metadata:
            report.issues.append(Issue(
                Severity.WARNING, "metadata",
                f"Отсутствует поле metadata.{key}"
            ))


def check_classification(data: dict, report: FileReport):
    """Проверяет блок classification_runtime_v1."""
    classification = data.get("classification_runtime_v1")
    if not isinstance(classification, dict):
        return

    # scoring
    scoring = classification.get("scoring")
    if isinstance(scoring, dict):
        for key in REQUIRED_SCORING:
            if key not in scoring:
                report.issues.append(Issue(
                    Severity.WARNING, "classification.scoring",
                    f"Отсутствует scoring.{key}"
                ))

    # rules
    rules = classification.get("rules")
    if isinstance(rules, dict):
        for key in REQUIRED_CLASSIFICATION_RULES:
            if key not in rules:
                report.issues.append(Issue(
                    Severity.WARNING, "classification.rules",
                    f"Отсутствует rules.{key}"
                ))

        # keywords группы
        keywords = rules.get("keywords", {})
        if isinstance(keywords, dict):
            for group in REQUIRED_KEYWORD_GROUPS:
                if group not in keywords:
                    report.issues.append(Issue(
                        Severity.WARNING, "classification.rules.keywords",
                        f"Отсутствует группа ключевых слов '{group}'"
                    ))
            # Проверка структуры каждого паттерна в группах
            for group_name, patterns in keywords.items():
                if not isinstance(patterns, list):
                    continue
                for i, pat in enumerate(patterns):
                    if not isinstance(pat, dict):
                        report.issues.append(Issue(
                            Severity.WARNING, f"classification.rules.keywords.{group_name}[{i}]",
                            "Паттерн не является словарем"
                        ))
                        continue
                    for req_key in ["pattern", "weight", "distinctiveness", "context", "description"]:
                        if req_key not in pat:
                            report.issues.append(Issue(
                                Severity.INFO, f"classification.rules.keywords.{group_name}[{i}]",
                                f"Отсутствует поле '{req_key}' в паттерне"
                            ))

        # filename_patterns структура
        for pat_group in ["filename_patterns", "folder_patterns"]:
            patterns = rules.get(pat_group, [])
            if isinstance(patterns, list):
                for i, pat in enumerate(patterns):
                    if not isinstance(pat, dict):
                        continue
                    for req_key in ["pattern", "kind", "weight"]:
                        if req_key not in pat:
                            report.issues.append(Issue(
                                Severity.INFO, f"classification.rules.{pat_group}[{i}]",
                                f"Отсутствует поле '{req_key}'"
                            ))

        # exclusions структура
        exclusions = rules.get("exclusions", [])
        if isinstance(exclusions, list):
            for i, pat in enumerate(exclusions):
                if not isinstance(pat, dict):
                    continue
                for req_key in ["pattern", "severity", "weight", "description"]:
                    if req_key not in pat:
                        report.issues.append(Issue(
                            Severity.INFO, f"classification.rules.exclusions[{i}]",
                            f"Отсутствует поле '{req_key}'"
                        ))


def check_prompt_template(prompt: str, check_id: str, report: FileReport):
    """Проверяет промпт на наличие обязательных секций."""
    if not isinstance(prompt, str):
        return

    for section in REQUIRED_PROMPT_SECTIONS:
        if section not in prompt:
            report.issues.append(Issue(
                Severity.ERROR, "llm.prompt_template",
                f"Отсутствует секция '{section}' в промпте",
                check_id=check_id
            ))

    # Проверка запрещённых фраз
    for phrase in FORBIDDEN_PROMPT_PHRASES:
        if phrase in prompt:
            report.issues.append(Issue(
                Severity.ERROR, "llm.prompt_template",
                f"Запрещённая фраза '{phrase}' — заменить на «Данные не определены» / 'not_defined'",
                check_id=check_id
            ))

    # Проверка наличия [ФОРМАТ ОТВЕТА] с JSON
    if "[ФОРМАТ ОТВЕТА]" in prompt:
        format_section = prompt.split("[ФОРМАТ ОТВЕТА]")[-1]
        if "JSON" not in format_section and "json" not in format_section:
            report.issues.append(Issue(
                Severity.WARNING, "llm.prompt_template",
                "В секции [ФОРМАТ ОТВЕТА] не упомянут JSON",
                check_id=check_id
            ))


def check_extraction_fields(check: dict, check_id: str, report: FileReport):
    """Проверяет extraction-блок."""
    extraction = check.get("extraction")
    if not isinstance(extraction, dict):
        return

    # Обязательные поля extraction
    for key in REQUIRED_EXTRACTION_FIELDS:
        if key not in extraction:
            report.issues.append(Issue(
                Severity.WARNING, "extraction",
                f"Отсутствует поле extraction.{key}",
                check_id=check_id
            ))

    # llm_prompt_extraction
    llm_prompt = extraction.get("llm_prompt_extraction", "")
    if isinstance(llm_prompt, str) and llm_prompt.strip():
        for tag in REQUIRED_EXTRACTION_TAGS:
            if tag not in llm_prompt:
                report.issues.append(Issue(
                    Severity.ERROR, "extraction.llm_prompt_extraction",
                    f"Отсутствует тег '{tag}' в llm_prompt_extraction",
                    check_id=check_id
                ))

    # compact_output должен быть false
    compact = extraction.get("compact_output")
    if compact is True:
        report.issues.append(Issue(
            Severity.WARNING, "extraction",
            "compact_output должно быть false",
            check_id=check_id
        ))

    # llm_max_tokens должен быть > 0
    llm_tokens = extraction.get("llm_max_tokens")
    if llm_tokens is not None and isinstance(llm_tokens, (int, float)):
        if llm_tokens <= 0:
            report.issues.append(Issue(
                Severity.WARNING, "extraction",
                f"llm_max_tokens должно быть > 0, получено: {llm_tokens}",
                check_id=check_id
            ))

    # Поля (fields)
    fields = extraction.get("fields", [])
    if not isinstance(fields, list):
        return

    for i, fld in enumerate(fields):
        if not isinstance(fld, dict):
            continue
        fld_name = fld.get("name", f"field_{i}")
        field_label = f"extraction.fields[{i}] ({fld_name})"

        # Обязательные атрибуты поля
        for req_attr in REQUIRED_FIELD_ATTRS:
            if req_attr not in fld:
                report.issues.append(Issue(
                    Severity.WARNING, field_label,
                    f"Отсутствует обязательный атрибут '{req_attr}' поля '{fld_name}'",
                    check_id=check_id
                ))

        # presentation должен быть допустимым
        presentation = fld.get("presentation")
        if presentation is not None and presentation not in VALID_PRESENTATIONS:
            report.issues.append(Issue(
                Severity.WARNING, field_label,
                f"Недопустимое значение presentation: '{presentation}'. Допустимо: {VALID_PRESENTATIONS}",
                check_id=check_id
            ))

        # Для grid-полей проверяем grid-атрибуты
        display_in_grid = fld.get("display_in_grid")
        if display_in_grid is True:
            for grid_attr in REQUIRED_GRID_ATTRS:
                if grid_attr not in fld:
                    report.issues.append(Issue(
                        Severity.WARNING, field_label,
                        f"Для grid-поля отсутствует атрибут '{grid_attr}'",
                        check_id=check_id
                    ))

        # Для enum-полей проверяем allowed_values
        if "allowed_values" in fld:
            allowed = fld["allowed_values"]
            if not isinstance(allowed, list) or len(allowed) == 0:
                report.issues.append(Issue(
                    Severity.WARNING, field_label,
                    "allowed_values должен быть непустым списком",
                    check_id=check_id
                ))
            else:
                # Проверка запрещённых значений
                for val in allowed:
                    if isinstance(val, str) and val in FORBIDDEN_FIELD_VALUES:
                        report.issues.append(Issue(
                            Severity.ERROR, field_label,
                            f"Запрещённое значение '{val}' в allowed_values поля '{fld_name}' — заменить на 'not_defined'",
                            check_id=check_id
                        ))

        # Если есть allowed_values, но нет presentation — предупреждение
        if "allowed_values" in fld and "presentation" not in fld:
            report.issues.append(Issue(
                Severity.INFO, field_label,
                f"Рекомендуется добавить presentation для enum-поля '{fld_name}'",
                check_id=check_id
            ))


def check_retrieval(check: dict, check_id: str, report: FileReport):
    """Проверяет retrieval-блок."""
    retrieval = check.get("retrieval")
    if not isinstance(retrieval, dict):
        report.issues.append(Issue(
            Severity.ERROR, "retrieval",
            "Отсутствует блок retrieval",
            check_id=check_id
        ))
        return

    for key in REQUIRED_RETRIEVAL_FIELDS:
        if key not in retrieval:
            report.issues.append(Issue(
                Severity.WARNING, "retrieval",
                f"Отсутствует поле retrieval.{key}",
                check_id=check_id
            ))

    # position_bias
    position_bias = retrieval.get("position_bias")
    if isinstance(position_bias, dict):
        for pb_key in REQUIRED_POSITION_BIAS:
            if pb_key not in position_bias:
                report.issues.append(Issue(
                    Severity.WARNING, "retrieval.position_bias",
                    f"Отсутствует поле position_bias.{pb_key}",
                    check_id=check_id
                ))
    elif position_bias is not None:
        report.issues.append(Issue(
            Severity.WARNING, "retrieval.position_bias",
            f"position_bias должен быть словарем, получен: {type(position_bias).__name__}",
            check_id=check_id
        ))


def check_evidence(check: dict, check_id: str, report: FileReport):
    """Проверяет evidence-блок."""
    evidence = check.get("evidence")
    if not isinstance(evidence, dict):
        report.issues.append(Issue(
            Severity.WARNING, "evidence",
            "Отсутствует блок evidence",
            check_id=check_id
        ))
        return

    for key in REQUIRED_EVIDENCE_FIELDS:
        if key not in evidence:
            report.issues.append(Issue(
                Severity.WARNING, "evidence",
                f"Отсутствует поле evidence.{key}",
                check_id=check_id
            ))


def check_single_check(check: dict, check_id: str, report: FileReport):
    """Проверяет один check из checks_v8."""
    # Обязательные поля check
    for key in REQUIRED_CHECK_FIELDS:
        if key not in check:
            report.issues.append(Issue(
                Severity.ERROR, f"checks_v8.{check_id}",
                f"Отсутствует обязательное поле '{key}'",
                check_id=check_id
            ))

    # Валидация severity
    severity = check.get("severity")
    if severity is not None and severity not in VALID_SEVERITIES:
        report.issues.append(Issue(
            Severity.WARNING, f"checks_v8.{check_id}",
            f"Недопустимое значение severity: '{severity}'. Допустимо: {VALID_SEVERITIES}",
            check_id=check_id
        ))

    for sev_key in ["severity_if_pass", "severity_if_fail", "severity_if_unclear"]:
        sev_val = check.get(sev_key)
        if sev_val is not None and sev_val not in VALID_SEVERITIES:
            report.issues.append(Issue(
                Severity.WARNING, f"checks_v8.{check_id}",
                f"Недопустимое значение {sev_key}: '{sev_val}'",
                check_id=check_id
            ))

    # Валидация ui_mode
    ui_mode = check.get("ui_mode")
    if ui_mode is not None and ui_mode not in VALID_UI_MODES:
        report.issues.append(Issue(
            Severity.WARNING, f"checks_v8.{check_id}",
            f"Недопустимое значение ui_mode: '{ui_mode}'. Допустимо: {VALID_UI_MODES}",
            check_id=check_id
        ))

    # Валидация detector_type
    detector_type = check.get("detector_type")
    if detector_type is not None and detector_type not in VALID_DETECTOR_TYPES:
        report.issues.append(Issue(
            Severity.WARNING, f"checks_v8.{check_id}",
            f"Недопустимое значение detector_type: '{detector_type}'. Допустимо: {VALID_DETECTOR_TYPES}",
            check_id=check_id
        ))

    # Валидация origin
    origin = check.get("origin")
    if origin is not None and origin not in VALID_ORIGINS:
        report.issues.append(Issue(
            Severity.WARNING, f"checks_v8.{check_id}",
            f"Недопустимое значение origin: '{origin}'. Допустимо: {VALID_ORIGINS}",
            check_id=check_id
        ))

    # llm блок
    llm = check.get("llm")
    if isinstance(llm, dict):
        for key in REQUIRED_LLM_FIELDS:
            if key not in llm:
                report.issues.append(Issue(
                    Severity.WARNING, "llm",
                    f"Отсутствует поле llm.{key}",
                    check_id=check_id
                ))

        prompt_template = llm.get("prompt_template", "")
        check_prompt_template(prompt_template, check_id, report)

        # temperature должен быть 0.0
        temp = llm.get("temperature")
        if temp is not None and temp != 0.0:
            report.issues.append(Issue(
                Severity.WARNING, "llm",
                f"Рекомендуется temperature=0.0 для детерминированности, получено: {temp}",
                check_id=check_id
            ))

    # retrieval
    check_retrieval(check, check_id, report)

    # evidence
    check_evidence(check, check_id, report)

    # extraction
    extraction = check.get("extraction")
    if isinstance(extraction, dict):
        check_extraction_fields(check, check_id, report)
    else:
        report.issues.append(Issue(
            Severity.WARNING, "extraction",
            "Отсутствует блок extraction",
            check_id=check_id
        ))

    # enrichment_hints
    enrichment = check.get("enrichment_hints")
    if not isinstance(enrichment, dict):
        report.issues.append(Issue(
            Severity.INFO, "enrichment_hints",
            "Отсутствует блок enrichment_hints (рекомендуется)",
            check_id=check_id
        ))


def check_checks_v8(data: dict, report: FileReport):
    """Проверяет блок checks_v8."""
    checks = data.get("checks_v8")
    if not isinstance(checks, list):
        if checks is None:
            report.issues.append(Issue(
                Severity.CRITICAL, "checks_v8",
                "Отсутствует блок checks_v8"
            ))
        else:
            report.issues.append(Issue(
                Severity.CRITICAL, "checks_v8",
                f"checks_v8 должен быть списком, получен: {type(checks).__name__}"
            ))
        return

    if len(checks) == 0:
        report.issues.append(Issue(
            Severity.WARNING, "checks_v8",
            "checks_v8 пуст — нет проверок"
        ))
        return

    report.checks_count = len(checks)
    check_ids = set()

    for i, check in enumerate(checks):
        if not isinstance(check, dict):
            report.issues.append(Issue(
                Severity.ERROR, f"checks_v8[{i}]",
                f"Check #{i} не является словарем"
            ))
            continue

        check_id = check.get("id", f"check_{i}")

        # Проверка дубликатов id
        if check_id in check_ids:
            report.issues.append(Issue(
                Severity.ERROR, "checks_v8",
                f"Дубликат check id: '{check_id}'",
                check_id=check_id
            ))
        check_ids.add(check_id)

        check_single_check(check, check_id, report)

    return check_ids


def check_dd_templates(data: dict, report: FileReport, check_ids: Optional[set]):
    """Проверяет блок dd_request_templates."""
    templates = data.get("dd_request_templates")
    if not isinstance(templates, dict):
        if templates is None:
            report.issues.append(Issue(
                Severity.WARNING, "dd_request_templates",
                "Отсутствует блок dd_request_templates"
            ))
        else:
            report.issues.append(Issue(
                Severity.WARNING, "dd_request_templates",
                f"dd_request_templates должен быть словарем, получен: {type(templates).__name__}"
            ))
        return

    # Проверка _default
    if "_default" not in templates:
        report.issues.append(Issue(
            Severity.WARNING, "dd_request_templates",
            "Отсутствует шаблон '_default'"
        ))

    # Проверка структуры каждого шаблона
    for tmpl_id, tmpl in templates.items():
        if not isinstance(tmpl, dict):
            report.issues.append(Issue(
                Severity.WARNING, f"dd_request_templates.{tmpl_id}",
                "Шаблон не является словарем"
            ))
            continue

        for req_key in REQUIRED_DD_TEMPLATE_FIELDS:
            if req_key not in tmpl:
                report.issues.append(Issue(
                    Severity.WARNING, f"dd_request_templates.{tmpl_id}",
                    f"Отсутствует поле '{req_key}'"
                ))

        # Проверка {doc_names} в text
        text = tmpl.get("text", "")
        if isinstance(text, str) and "{doc_names}" not in text and tmpl_id != "_default":
            report.issues.append(Issue(
                Severity.INFO, f"dd_request_templates.{tmpl_id}",
                "В тексте шаблона отсутствует плейсхолдер {doc_names}"
            ))

    # Проверка соответствия ключей шаблонов check_ids
    if check_ids is not None:
        template_keys = set(templates.keys()) - {"_default"}
        # Шаблоны без соответствующего check
        orphan_templates = template_keys - check_ids
        for orphan in sorted(orphan_templates):
            report.issues.append(Issue(
                Severity.WARNING, f"dd_request_templates.{orphan}",
                f"Шаблон '{orphan}' не имеет соответствующего check в checks_v8"
            ))

        # Checks без шаблонов
        missing_templates = check_ids - template_keys
        for missing in sorted(missing_templates):
            report.issues.append(Issue(
                Severity.INFO, "dd_request_templates",
                f"Для check '{missing}' отсутствует DD-шаблон",
                check_id=missing
            ))


def check_shared_patterns(data: dict, report: FileReport):
    """Проверяет блок shared_patterns."""
    patterns = data.get("shared_patterns")
    if not isinstance(patterns, dict):
        if patterns is None:
            report.issues.append(Issue(
                Severity.INFO, "shared_patterns",
                "Отсутствует блок shared_patterns"
            ))
        return

    for key, value in patterns.items():
        if not isinstance(value, str):
            report.issues.append(Issue(
                Severity.WARNING, f"shared_patterns.{key}",
                f"Паттерн должен быть строкой, получен: {type(value).__name__}"
            ))
        elif value:
            # Попытка скомпилировать regex
            try:
                re.compile(value)
            except re.error as e:
                report.issues.append(Issue(
                    Severity.WARNING, f"shared_patterns.{key}",
                    f"Невалидный regex: {e}"
                ))


def check_trigger_definitions(data: dict, report: FileReport):
    """Проверяет блок trigger_definitions."""
    triggers = data.get("trigger_definitions")
    if not isinstance(triggers, dict):
        return

    for trig_name, trig in triggers.items():
        if not isinstance(trig, dict):
            report.issues.append(Issue(
                Severity.WARNING, f"trigger_definitions.{trig_name}",
                "Триггер не является словарем"
            ))
            continue

        if "any_keywords" not in trig:
            report.issues.append(Issue(
                Severity.WARNING, f"trigger_definitions.{trig_name}",
                "Отсутствует any_keywords в триггере"
            ))
        else:
            keywords = trig["any_keywords"]
            if not isinstance(keywords, list):
                report.issues.append(Issue(
                    Severity.WARNING, f"trigger_definitions.{trig_name}",
                    "any_keywords должен быть списком"
                ))
            elif isinstance(keywords, list):
                for i, kw in enumerate(keywords):
                    if isinstance(kw, str):
                        try:
                            re.compile(kw)
                        except re.error as e:
                            report.issues.append(Issue(
                                Severity.WARNING, f"trigger_definitions.{trig_name}",
                                f"Невалидный regex в any_keywords[{i}]: {e}"
                            ))


def check_filename(filename: str, report: FileReport):
    """Проверяет имя файла на соответствие паттерну."""
    basename = os.path.basename(filename)
    # Ожидаемый формат: <type>.yaml или <type>.yml
    # где type совпадает с полем type в файле
    stem = Path(basename).stem
    if report.type_name and stem != report.type_name:
        report.issues.append(Issue(
            Severity.INFO, "filename",
            f"Имя файла '{stem}' не совпадает с полем type '{report.type_name}'"
        ))


# ════════════════════════════════════════════════════════════════════════════
# ГЛАВНАЯ ФУНКЦИЯ ПРОВЕРКИ
# ════════════════════════════════════════════════════════════════════════════

def check_file(filepath: str) -> FileReport:
    """Полная проверка одного файла."""
    report = FileReport(filepath=filepath)

    # Загрузка YAML
    data, error = load_yaml(filepath)
    if error:
        report.issues.append(Issue(Severity.CRITICAL, "file", error))
        return report

    # Проверка имени файла
    check_filename(filepath, report)

    # Структурные проверки
    check_top_level_structure(data, report)
    check_metadata(data, report)
    check_classification(data, report)
    check_shared_patterns(data, report)
    check_trigger_definitions(data, report)

    # Проверка checks_v8
    check_ids = check_checks_v8(data, report)

    # Проверка dd_request_templates
    check_dd_templates(data, report, check_ids)

    return report


def print_report(report: FileReport, verbose: bool = False):
    """Выводит отчёт по одному файлу."""
    status_icon = "✅" if report.passed else "❌"
    rel_path = report.filepath
    print(f"\n{'='*80}")
    print(f"{status_icon} {rel_path}")
    print(f"   type: {report.type_name or '???'}  |  version: {report.version or '???'}  |  "
          f"checks: {report.checks_count}  |  errors: {report.errors_count}  |  "
          f"warnings: {report.warnings_count}")
    print(f"{'='*80}")

    if not report.issues:
        print("   Все проверки пройдены ✅")
        return

    # Группировка по severity
    for sev in [Severity.CRITICAL, Severity.ERROR, Severity.WARNING, Severity.INFO]:
        issues = [i for i in report.issues if i.severity == sev]
        if issues:
            print(f"\n   --- {sev.value} ({len(issues)}) ---")
            for issue in issues:
                if sev == Severity.INFO and not verbose:
                    continue
                print(f"   {issue}")

    if verbose:
        info_issues = [i for i in report.issues if i.severity == Severity.INFO]
        if info_issues:
            print(f"\n   --- INFO ({len(info_issues)}) ---")
            for issue in info_issues:
                print(f"   {issue}")


def print_summary(reports: List[FileReport]):
    """Выводит сводный отчёт."""
    total = len(reports)
    passed = sum(1 for r in reports if r.passed)
    failed = total - passed
    total_errors = sum(r.errors_count for r in reports)
    total_warnings = sum(r.warnings_count for r in reports)
    total_checks = sum(r.checks_count for r in reports)

    print(f"\n{'='*80}")
    print(f"СВОДНЫЙ ОТЧЁТ")
    print(f"{'='*80}")
    print(f"   Файлов проверено:     {total}")
    print(f"   Пройдено:             {passed} ✅")
    print(f"   С ошибками:           {failed} ❌")
    print(f"   Всего ошибок:         {total_errors}")
    print(f"   Всего предупреждений: {total_warnings}")
    print(f"   Всего checks:         {total_checks}")

    if failed > 0:
        print(f"\n   Файлы с ошибками:")
        for r in reports:
            if not r.passed:
                print(f"   ❌ {r.filepath} ({r.errors_count} ошибок)")

    if total_errors == 0 and total_warnings == 0:
        print(f"\n   🎉 Все файлы полностью соответствуют эталонным паттернам!")
    elif total_errors == 0:
        print(f"\n   ✅ Все файлы прошли обязательные проверки (есть предупреждения)")
    else:
        print(f"\n   ❌ Обнаружены критические несоответствия — требуется исправление")


def save_json_report(reports: List[FileReport], output_path: str):
    """Сохраняет отчёт в JSON."""
    data = {
        "summary": {
            "total_files": len(reports),
            "passed": sum(1 for r in reports if r.passed),
            "failed": sum(1 for r in reports if not r.passed),
            "total_errors": sum(r.errors_count for r in reports),
            "total_warnings": sum(r.warnings_count for r in reports),
            "total_checks": sum(r.checks_count for r in reports),
        },
        "files": []
    }

    for r in reports:
        file_data = {
            "filepath": r.filepath,
            "type": r.type_name,
            "version": r.version,
            "passed": r.passed,
            "checks_count": r.checks_count,
            "errors_count": r.errors_count,
            "warnings_count": r.warnings_count,
            "issues": [
                {
                    "severity": i.severity.value,
                    "section": i.section,
                    "message": i.message,
                    "check_id": i.check_id,
                }
                for i in r.issues
            ]
        }
        data["files"].append(file_data)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n   JSON-отчёт сохранён: {output_path}")


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Проверка YAML-инструкций на соответствие эталонным паттернам"
    )
    parser.add_argument(
        "--path", "-p",
        default=DEFAULT_PATH,
        help=f"Путь к директории с инструкциями (по умолчанию: {DEFAULT_PATH})"
    )
    parser.add_argument(
        "--strict", "-s",
        action="store_true",
        help="Строгий режим: показывать INFO-сообщения"
    )
    parser.add_argument(
        "--json-report", "-j",
        metavar="PATH",
        help="Сохранить отчёт в JSON-файл"
    )
    parser.add_argument(
        "--file", "-f",
        help="Проверить только один файл"
    )
    parser.add_argument(
        "--filter", "-t",
        help="Фильтр по подстроке в имени файла (например: contract_7)"
    )

    args = parser.parse_args()

    # Определение файлов для проверки
    if args.file:
        if not os.path.isfile(args.file):
            print(f"Ошибка: файл не найден: {args.file}")
            sys.exit(1)
        files = [args.file]
    else:
        if not os.path.isdir(args.path):
            print(f"Ошибка: директория не найдена: {args.path}")
            sys.exit(1)
        files = find_yaml_files(args.path)
        if args.filter:
            files = [f for f in files if args.filter.lower() in f.lower()]

    if not files:
        print(f"YAML-файлы не найдены в: {args.path}")
        sys.exit(1)

    print(f"🔍 Проверка {len(files)} файлов в: {args.path}")
    print(f"   Режим: {'строгий (strict)' if args.strict else 'обычный'}")

    # Проверка каждого файла
    reports = []
    for filepath in files:
        report = check_file(filepath)
        reports.append(report)
        print_report(report, verbose=args.strict)

    # Сводный отчёт
    print_summary(reports)

    # JSON-отчёт
    if args.json_report:
        save_json_report(reports, args.json_report)

    # Код возврата
    has_errors = any(r.errors_count > 0 for r in reports)
    sys.exit(1 if has_errors else 0)


if __name__ == "__main__":
    main()

    