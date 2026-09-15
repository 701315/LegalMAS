#!/usr/bin/env python3
"""
audit_checks_structure.py — аудитор структуры checks_v8 в doc-type YAML.

Проверяет:
1. Валидность YAML (парсинг).
2. Корректность вложенности блоков (retrieval/extraction/evidence не под llm).
3. Правильность отступов (2/4/6/8/10 пробелов).
4. Расположение store_payload (внутри extraction, не на top-level).
5. Полную валидацию через Pydantic-модели (CheckDefinition).
6. Валидность конфигов (UT ∈ 29, CF canonical, retrieval_profile).
7. Контрактные требования: label у fact-полей, {context} в llm_prompt_extraction.
8. Naming contract: уникальность fields[].name, отсутствие paired/singleton коллизий.

Использование:
    python scripts/audit_checks_structure.py <path_to_folder>
    python scripts/audit_checks_structure.py /srv/steloom-dev/playbooks/document_types/group_1_ownership

Опции:
    --verbose     Показать все проверки, включая пройденные.
    --json        Вывод в JSON-формате.
    --strict      Считать WARNING как ERROR при определении exit-кода.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ─── Подключаемся к внутренним моделям проекта ─────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC_PATH = _PROJECT_ROOT / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

try:
    from engine.playbook.models import CheckDefinition  # noqa: E402
    from services.structure.legal_unit_models import (  # noqa: E402
        LegalUnitType,
        normalize_clause_function_label,
    )
    _PYDANTIC_AVAILABLE = True
except Exception as e:
    print(f"⚠️  Не удалось импортировать Pydantic-модели: {e}", file=sys.stderr)
    print(f"    sys.path[0] = {sys.path[0]}", file=sys.stderr)
    _PYDANTIC_AVAILABLE = False

# Пытаемся импортировать retrieval-профили (опционально)
try:
    from engine.playbook.retrieval_profiles import ALL_PROFILES  # noqa: E402
    _KNOWN_PROFILES = set(ALL_PROFILES.keys())
except Exception:
    _KNOWN_PROFILES = set()

# ─── Валидные UT / CF ──────────────────────────────────────────────────────
_VALID_UNIT_TYPES: set[str] = (
    {m.value for m in LegalUnitType} if _PYDANTIC_AVAILABLE else set()
)

_CANONICAL_CLAUSE_FUNCTIONS = {
    "rights", "obligations", "limitations", "procedures",
    "definitions", "representations", "remedies", "boilerplate",
}

# ─── Контракт отступов ─────────────────────────────────────────────────────
# Индексация: количество пробелов слева от ключа
_EXPECTED_INDENTS = {
    "check_list_item": 2,          # "- id:" в списке checks_v8
    "check_property": 4,           # name, description, retrieval, ...
    "nested_block_property": 6,    # keywords, prompt_template, fields, ...
    "field_list_item": 8,          # "- name:" в extraction.fields
    "field_property": 10,          # type, label, required, ...
}

_TOP_LEVEL_ALLOWED_KEYS = {
    "id", "name", "description", "doc_types", "origin", "ui_mode",
    "display_order", "group", "scope", "severity",
    "severity_if_pass", "severity_if_fail", "severity_if_unclear",
    "detector_type", "triggers", "rules", "llm", "retrieval",
    "evidence", "extraction", "enrichment_hints", "conditional",
}

_NESTED_BLOCKS_MUST_BE_TOP_LEVEL = {
    "retrieval", "extraction", "evidence",
}

# ─── Модель отчёта ────────────────────────────────────────────────────────
@dataclass
class Issue:
    severity: str            # "ERROR" | "WARNING" | "INFO"
    category: str
    file: str
    check_id: str | None
    line: int | None
    message: str
    hint: str | None = None

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "category": self.category,
            "file": self.file,
            "check_id": self.check_id,
            "line": self.line,
            "message": self.message,
            "hint": self.hint,
        }

@dataclass
class FileReport:
    file: str
    parsed: bool = False
    checks_count: int = 0
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> int:
        return sum(1 for i in self.issues if i.severity == "ERROR")

    @property
    def warnings(self) -> int:
        return sum(1 for i in self.issues if i.severity == "WARNING")

    @property
    def infos(self) -> int:
        return sum(1 for i in self.issues if i.severity == "INFO")

# ─── Утилиты ──────────────────────────────────────────────────────────────
def _detect_leading_spaces(line: str) -> int:
    return len(line) - len(line.lstrip(" "))

def _find_line_of_key(raw: str, key: str, after_line: int = 0) -> int | None:
    """Возвращает 1-based номер строки, где встречается '<key>:' после after_line."""
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*:", re.MULTILINE)
    lines = raw.splitlines()
    for i, line in enumerate(lines, 1):
        if i <= after_line:
            continue
        if pattern.match(line):
            return i
    return None

# ─── Проверки уровня RAW-текста ───────────────────────────────────────────
def check_raw_indentation(raw: str, file: str) -> list[Issue]:
    """
    Проверяет отступы внутри checks_v8 по сырому тексту (без парсинга).
    Ловит случаи, когда name/description выровнены с '- id:' вместо +2 пробелов.
    """
    issues: list[Issue] = []
    lines = raw.splitlines()

    # Ищем блок checks_v8
    in_checks_v8 = False
    checks_v8_indent: int | None = None
    current_check_id: str | None = None
    current_check_indent: int | None = None
    current_check_line: int = 0

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = _detect_leading_spaces(line)

        # Вход в блок checks_v8
        if not in_checks_v8:
            if re.match(r"^checks_v8\s*:", line):
                in_checks_v8 = True
                checks_v8_indent = indent
            continue

        # Выход из блока checks_v8 (новый top-level ключ на том же уровне)
        if indent <= checks_v8_indent and not stripped.startswith("-"):
            in_checks_v8 = False
            continue

        # Строка "- id: xxx" — начало нового чека
        m = re.match(r"^(\s*)-\s*id\s*:\s*(\S+)", line)
        if m:
            list_indent = len(m.group(1))
            current_check_id = m.group(2).strip('"\'')
            current_check_indent = list_indent
            current_check_line = i

            expected = _EXPECTED_INDENTS["check_list_item"]
            if list_indent != expected:
                issues.append(Issue(
                    severity="ERROR",
                    category="INDENTATION",
                    file=file,
                    check_id=current_check_id,
                    line=i,
                    message=(
                        f"Отступ '- id:' = {list_indent} пробелов, "
                        f"ожидается {expected}."
                    ),
                    hint="Правило: '- id:' в списке checks_v8 должен иметь 2 пробела.",
                ))
            continue

        # Проверка отступов свойств чека
        if current_check_indent is not None:
            expected_prop_indent = current_check_indent + 2  # 4 пробела
            # Свойство первого уровня внутри чека
            if indent == current_check_indent and not stripped.startswith("-"):
                # Явно неверный отступ: свойство выровнено с '- id:'
                issues.append(Issue(
                    severity="ERROR",
                    category="INDENTATION",
                    file=file,
                    check_id=current_check_id,
                    line=i,
                    message=(
                        f"Ключ '{stripped.split(':')[0]}' выровнен с '- id:' "
                        f"({indent} пробелов), но должен быть глубже на 2 пробела "
                        f"(ожидается {expected_prop_indent})."
                    ),
                    hint=(
                        "Все свойства чека (name, description, retrieval и т.д.) "
                        "должны быть смещены на +2 пробела от '- id:'."
                    ),
                ))

    return issues

# ─── Проверки уровня СТРУКТУРЫ (после парсинга) ───────────────────────────
def check_top_level_blocks_not_under_llm(
    check: dict,
    file: str,
    check_id: str,
    raw: str,
) -> list[Issue]:
    """STRUCTURE-SANITY v1: retrieval/extraction/evidence/store_payload не под llm."""
    issues: list[Issue] = []
    llm = check.get("llm") or {}
    if not isinstance(llm, dict):
        return issues

    for key in ("retrieval", "extraction", "evidence", "store_payload"):
        if key in llm:
            line = _find_line_of_key(raw, key)
            issues.append(Issue(
                severity="ERROR",
                category="TOP_LEVEL",
                file=file,
                check_id=check_id,
                line=line,
                message=(
                    f"Ключ '{key}' находится под 'llm:', но должен быть "
                    f"на top-level чека."
                ),
                hint=(
                    "STRUCTURE-SANITY v1: retrieval/extraction/evidence/"
                    "store_payload читаются только с top-level."
                ),
            ))
    return issues

def check_extraction_nested_children(
    check: dict,
    file: str,
    check_id: str,
    raw: str,
) -> list[Issue]:
    """STRUCTURE-SANITY v2: extraction: пустой, но дети на top-level чека."""
    issues: list[Issue] = []
    extraction = check.get("extraction")
    orphan_children = ("enabled", "mode", "fields", "llm_prompt_extraction",
                       "llm_max_tokens", "compact_output")

    if extraction is None:
        found = [k for k in orphan_children if k in check]
        if found:
            line = _find_line_of_key(raw, found[0])
            issues.append(Issue(
                severity="ERROR",
                category="EXTRACTION_NESTED",
                file=file,
                check_id=check_id,
                line=line,
                message=(
                    f"Блок 'extraction:' пустой/отсутствует, но его дети "
                    f"({', '.join(found)}) на top-level чека."
                ),
                hint=(
                    "STRUCTURE-SANITY v2: сдвинуть дети extraction на +2 пробела, "
                    "чтобы они стали child'ами extraction, а не сиблингами."
                ),
            ))
    return issues

def check_store_payload_location(
    check: dict,
    file: str,
    check_id: str,
    raw: str,
) -> list[Issue]:
    """store_payload должен быть внутри extraction, а не на top-level чека."""
    issues: list[Issue] = []
    if "store_payload" in check:
        # store_payload на top-level чека — код это НЕ читает
        line = _find_line_of_key(raw, "store_payload")
        issues.append(Issue(
            severity="ERROR",
            category="STORE_PAYLOAD_LOCATION",
            file=file,
            check_id=check_id,
            line=line,
            message=(
                "Ключ 'store_payload' находится на top-level чека, "
                "но loader.py читает его ТОЛЬКО из блока 'extraction:'."
            ),
            hint=(
                "Переместить 'store_payload: true' внутрь блока extraction: "
                "(6 пробелов индентации, сиблинг к 'fields:')."
            ),
        ))
    return issues

def check_llm_prompt_extraction_has_context(
    check: dict,
    file: str,
    check_id: str,
    raw: str,
) -> list[Issue]:
    """extraction.llm_prompt_extraction обязан содержать {context}."""
    issues: list[Issue] = []
    ext = check.get("extraction") or {}
    prompt = ext.get("llm_prompt_extraction")
    if isinstance(prompt, str) and prompt.strip():
        if "{context}" not in prompt:
            line = _find_line_of_key(raw, "llm_prompt_extraction")
            issues.append(Issue(
                severity="ERROR",
                category="CONTRACT_VIOLATIONS",
                file=file,
                check_id=check_id,
                line=line,
                message=(
                    "extraction.llm_prompt_extraction не содержит "
                    "обязательного плейсхолдера '{context}'."
                ),
                hint=(
                    "Pydantic-валидатор _validate_llm_prompt_extraction "
                    "выбросит ValueError при загрузке."
                ),
            ))
    return issues

def check_extraction_fields_labels(
    check: dict,
    file: str,
    check_id: str,
    raw: str,
) -> list[Issue]:
    """
    Для ui_mode=field_extraction (или пустой) у всех fact-полей
    ОБЯЗАН быть непустой label.
    """
    issues: list[Issue] = []
    ext = check.get("extraction") or {}
    if not ext.get("enabled"):
        return issues

    ui_mode = str(check.get("ui_mode") or "").strip().lower()
    is_field_extraction = (ui_mode == "field_extraction") or (not ui_mode)
    if not is_field_extraction:
        return issues

    fields = ext.get("fields") or []
    has_summary = any(
        (f.get("presentation") or "fact") == "summary" for f in fields if isinstance(f, dict)
    )
    if has_summary:
        return issues

    reserved = {"reason", "evidence", "explanation", "notes"}
    missing: list[str] = []

    for f in fields:
        if not isinstance(f, dict):
            continue
        presentation = f.get("presentation", "fact")
        if presentation in ("signal", "diagnostic"):
            continue
        name = f.get("name")
        if name in reserved:
            continue
        label = f.get("label")
        if not (label and str(label).strip()):
            missing.append(name or "<unnamed>")

    if missing:
        line = _find_line_of_key(raw, "fields")
        issues.append(Issue(
            severity="ERROR",
            category="CONTRACT_VIOLATIONS",
            file=file,
            check_id=check_id,
            line=line,
            message=(
                f"У fact-полей отсутствует обязательный 'label': {missing}."
            ),
            hint=(
                "Добавить label или изменить presentation на "
                "'signal' / 'diagnostic'."
            ),
        ))
    return issues

def check_naming_contract(
    check: dict,
    file: str,
    check_id: str,
    raw: str,
) -> list[Issue]:
    """
    1. Дубликаты fields[].name.
    2. Коллизия paired/singleton (buyer + buyer_status и т.д.).
    """
    issues: list[Issue] = []
    ext = check.get("extraction") or {}
    fields = ext.get("fields") or []

    names: dict[str, int] = {}
    for f in fields:
        if not isinstance(f, dict):
            continue
        name = f.get("name")
        if name:
            names[name] = names.get(name, 0) + 1

    dups = sorted(n for n, c in names.items() if c > 1)
    if dups:
        line = _find_line_of_key(raw, "fields")
        issues.append(Issue(
            severity="ERROR",
            category="NAMING_CONTRACT",
            file=file,
            check_id=check_id,
            line=line,
            message=f"Дубликаты имён полей: {dups}",
        ))

    # Paired vs singleton
    paired_suffixes = ("_status", "_details", "_value")
    all_names = set(names.keys())
    paired_prefixes: set[str] = set()
    for n in all_names:
        for suf in paired_suffixes:
            if n.endswith(suf):
                prefix = n[: -len(suf)]
                if prefix:
                    paired_prefixes.add(prefix)
                break

    conflicts: list[tuple[str, list[str]]] = []
    for prefix in sorted(paired_prefixes):
        if prefix in all_names:
            related = sorted(
                n for n in all_names
                if any(n == f"{prefix}{s}" for s in paired_suffixes)
            )
            conflicts.append((prefix, related))

    if conflicts:
        details = "; ".join(
            f"singleton '{s}' конфликтует с paired {p}" for s, p in conflicts
        )
        line = _find_line_of_key(raw, "fields")
        issues.append(Issue(
            severity="ERROR",
            category="NAMING_CONTRACT",
            file=file,
            check_id=check_id,
            line=line,
            message=f"DD Grid naming contract нарушен: {details}",
        ))

    return issues

def check_config_validity(
    check: dict,
    file: str,
    check_id: str,
    raw: str,
) -> list[Issue]:
    """Валидность UT / CF / retrieval_profile."""
    issues: list[Issue] = []
    r = check.get("retrieval") or {}

    # UT
    for ut in r.get("preferred_unit_types") or []:
        if isinstance(ut, str) and _VALID_UNIT_TYPES:
            normalized = ut.strip().lower().replace("-", "_").replace(" ", "_")
            if normalized not in _VALID_UNIT_TYPES:
                line = _find_line_of_key(raw, "preferred_unit_types")
                issues.append(Issue(
                    severity="WARNING",
                    category="CONFIG_VALIDITY",
                    file=file,
                    check_id=check_id,
                    line=line,
                    message=f"preferred_unit_types содержит невалидное значение: '{ut}'",
                    hint=f"Валидные UT ({len(_VALID_UNIT_TYPES)}): см. LegalUnitType.",
                ))

    for ut in r.get("excluded_unit_types") or []:
        if isinstance(ut, str) and _VALID_UNIT_TYPES:
            normalized = ut.strip().lower().replace("-", "_").replace(" ", "_")
            if normalized not in _VALID_UNIT_TYPES:
                line = _find_line_of_key(raw, "excluded_unit_types")
                issues.append(Issue(
                    severity="WARNING",
                    category="CONFIG_VALIDITY",
                    file=file,
                    check_id=check_id,
                    line=line,
                    message=f"excluded_unit_types содержит невалидное значение: '{ut}'",
                ))

    # CF
    for cf in r.get("preferred_clause_functions") or []:
        if isinstance(cf, str) and _PYDANTIC_AVAILABLE:
            if normalize_clause_function_label(cf) is None:
                line = _find_line_of_key(raw, "preferred_clause_functions")
                issues.append(Issue(
                    severity="WARNING",
                    category="CONFIG_VALIDITY",
                    file=file,
                    check_id=check_id,
                    line=line,
                    message=f"preferred_clause_functions содержит невалидное значение: '{cf}'",
                    hint=f"Canonical: {sorted(_CANONICAL_CLAUSE_FUNCTIONS)}",
                ))

    # retrieval_profile
    profile = r.get("retrieval_profile")
    if profile and _KNOWN_PROFILES:
        if profile not in _KNOWN_PROFILES:
            line = _find_line_of_key(raw, "retrieval_profile")
            issues.append(Issue(
                severity="WARNING",
                category="CONFIG_VALIDITY",
                file=file,
                check_id=check_id,
                line=line,
                message=f"retrieval_profile '{profile}' не найден в реестре.",
                hint=f"Доступно {len(_KNOWN_PROFILES)} профилей.",
            ))

    return issues

def check_pydantic_validation(
    check: dict,
    file: str,
    check_id: str,
) -> list[Issue]:
    """
    Полная валидация через CheckDefinition.
    Ловит все контрактные нарушения одним махом.
    """
    if not _PYDANTIC_AVAILABLE:
        return []

    issues: list[Issue] = []
    try:
        # Строим CheckDefinition как это делает loader.py
        cd = CheckDefinition(
            id=check.get("id") or "unknown",
            name=check.get("name", check_id),
            description=check.get("description", ""),
            doc_types=[],
            origin=check.get("origin"),
            ui_mode=check.get("ui_mode"),
            severity=check.get("severity", "medium"),
            severity_if_pass=check.get("severity_if_pass"),
            severity_if_fail=check.get("severity_if_fail"),
            severity_if_unclear=check.get("severity_if_unclear"),
            # Rules и остальные блоки — минимально нужное для валидации
        )
        # Полная валидация extraction через отдельную сборку
        from engine.playbook.models import (
            ExtractionConfig, ExtractionFieldConfig, ExtractionMode,
            ExtractionFieldType, RetrievalConfig, EvidenceConfig, LLMConfig,
        )

        ext_raw = check.get("extraction")
        if ext_raw and ext_raw.get("enabled"):
            fields = []
            for f in ext_raw.get("fields") or []:
                if not isinstance(f, dict):
                    continue
                try:
                    ftype = ExtractionFieldType(f.get("type", "string"))
                except ValueError:
                    ftype = ExtractionFieldType.STRING
                fields.append(ExtractionFieldConfig(
                    name=f.get("name", ""),
                    type=ftype,
                    label=f.get("label"),
                    presentation=f.get("presentation", "fact"),
                    display_in_grid=bool(f.get("display_in_grid", False)),
                    display_priority=f.get("display_priority"),
                    description=f.get("description", ""),
                    allowed_values=f.get("allowed_values") or [],
                    required=f.get("required", False),
                    role=f.get("role"),
                ))

            try:
                ec = ExtractionConfig(
                    enabled=True,
                    mode=ExtractionMode(ext_raw.get("mode", "hybrid")),
                    fields=fields,
                    store_payload=ext_raw.get("store_payload", True),
                    llm_prompt_extraction=ext_raw.get("llm_prompt_extraction"),
                    llm_max_tokens=ext_raw.get("llm_max_tokens"),
                    compact_output=ext_raw.get("compact_output"),
                )
                # Сшиваем в CheckDefinition для запуска
                # _validate_field_extraction_display_contract
                cd_full = CheckDefinition(
                    id=cd.id, name=cd.name, description=cd.description,
                    doc_types=cd.doc_types, origin=cd.origin,
                    ui_mode=cd.ui_mode, severity=cd.severity,
                    severity_if_pass=cd.severity_if_pass,
                    severity_if_fail=cd.severity_if_fail,
                    severity_if_unclear=cd.severity_if_unclear,
                    extraction=ec,
                )
            except Exception as ve:
                issues.append(Issue(
                    severity="ERROR",
                    category="PYDANTIC",
                    file=file,
                    check_id=check_id,
                    line=None,
                    message=f"Pydantic-валидация extraction/check провалилась: {ve}",
                ))

        # Retrieval
        r_raw = check.get("retrieval")
        if r_raw:
            try:
                RetrievalConfig(**{k: v for k, v in r_raw.items()
                                   if k in RetrievalConfig.model_fields})
            except Exception as ve:
                issues.append(Issue(
                    severity="ERROR",
                    category="PYDANTIC",
                    file=file,
                    check_id=check_id,
                    line=None,
                    message=f"Pydantic-валидация retrieval провалилась: {ve}",
                ))

    except Exception as e:
        issues.append(Issue(
            severity="ERROR",
            category="PYDANTIC",
            file=file,
            check_id=check_id,
            line=None,
            message=f"Не удалось построить CheckDefinition: {e}",
        ))

    return issues

# ─── Основной цикл ────────────────────────────────────────────────────────
def audit_file(path: Path) -> FileReport:
    rep = FileReport(file=str(path))
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception as e:
        rep.issues.append(Issue(
            severity="ERROR", category="STRUCTURE",
            file=str(path), check_id=None, line=None,
            message=f"Не удалось прочитать файл: {e}",
        ))
        return rep

    # RAW-проверки отступов (до парсинга)
    rep.issues.extend(check_raw_indentation(raw, str(path)))

    # Парсинг YAML
    try:
        data = yaml.safe_load(raw)
        rep.parsed = True
    except yaml.YAMLError as e:
        rep.issues.append(Issue(
            severity="ERROR", category="STRUCTURE",
            file=str(path), check_id=None,
            line=getattr(e, "problem_mark", None).line + 1
                if getattr(e, "problem_mark", None) else None,
            message=f"YAML не парсится: {e}",
        ))
        return rep

    if not isinstance(data, dict):
        rep.issues.append(Issue(
            severity="ERROR", category="STRUCTURE",
            file=str(path), check_id=None, line=None,
            message="Корень YAML не является объектом.",
        ))
        return rep

    checks = data.get("checks_v8") or []
    if not isinstance(checks, list):
        rep.issues.append(Issue(
            severity="ERROR", category="STRUCTURE",
            file=str(path), check_id=None, line=None,
            message="'checks_v8' не является списком.",
        ))
        return rep

    rep.checks_count = len(checks)

    for check in checks:
        if not isinstance(check, dict):
            rep.issues.append(Issue(
                severity="ERROR", category="STRUCTURE",
                file=str(path), check_id=None, line=None,
                message=f"Элемент checks_v8 не является объектом: {type(check)}",
            ))
            continue

        check_id = check.get("id") or "<no_id>"

        # Обязательные ключи
        if not check.get("id"):
            rep.issues.append(Issue(
                severity="ERROR", category="REQUIRED_KEYS",
                file=str(path), check_id=None, line=None,
                message="Отсутствует обязательный ключ 'id'.",
            ))

        # Неизвестные top-level ключи
        for k in check.keys():
            if k not in _TOP_LEVEL_ALLOWED_KEYS and k != "store_payload":
                rep.issues.append(Issue(
                    severity="WARNING", category="TOP_LEVEL",
                    file=str(path), check_id=check_id, line=None,
                    message=f"Неизвестный top-level ключ: '{k}' (будет проигнорирован loader.py).",
                ))

        # Все структурные проверки
        rep.issues.extend(check_top_level_blocks_not_under_llm(check, str(path), check_id, raw))
        rep.issues.extend(check_extraction_nested_children(check, str(path), check_id, raw))
        rep.issues.extend(check_store_payload_location(check, str(path), check_id, raw))
        rep.issues.extend(check_llm_prompt_extraction_has_context(check, str(path), check_id, raw))
        rep.issues.extend(check_extraction_fields_labels(check, str(path), check_id, raw))
        rep.issues.extend(check_naming_contract(check, str(path), check_id, raw))
        rep.issues.extend(check_config_validity(check, str(path), check_id, raw))
        rep.issues.extend(check_pydantic_validation(check, str(path), check_id))

    return rep

# ─── CLI ──────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Аудит структуры checks_v8 в doc-type YAML."
    )
    ap.add_argument("folder", type=Path, help="Папка с YAML.")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="WARNING считать как ERROR для exit-кода.")
    args = ap.parse_args()

    if not args.folder.exists():
        print(f"❌ Папка не найдена: {args.folder}", file=sys.stderr)
        return 2

    yaml_files = sorted(args.folder.rglob("*.yaml")) + sorted(args.folder.rglob("*.yml"))
    if not yaml_files:
        print(f"⚠️  YAML-файлы не найдены в {args.folder}", file=sys.stderr)
        return 1

    reports = [audit_file(p) for p in yaml_files]

    if args.json:
        out = {
            "folder": str(args.folder),
            "files": [
                {
                    "file": r.file,
                    "parsed": r.parsed,
                    "checks_count": r.checks_count,
                    "errors": r.errors,
                    "warnings": r.warnings,
                    "infos": r.infos,
                    "issues": [i.to_dict() for i in r.issues],
                }
                for r in reports
            ],
            "summary": {
                "files_total": len(reports),
                "files_with_errors": sum(1 for r in reports if r.errors > 0),
                "errors_total": sum(r.errors for r in reports),
                "warnings_total": sum(r.warnings for r in reports),
                "checks_total": sum(r.checks_count for r in reports),
            },
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        # Человекочитаемый отчёт
        print(f"\n{'=' * 78}")
        print(f"АУДИТ ПАПКИ: {args.folder}")
        print(f"{'=' * 78}\n")

        total_e = total_w = total_i = total_c = 0
        for r in reports:
            fname = Path(r.file).name
            status = "✅" if r.errors == 0 else "❌"
            summary = (
                f"{status} {fname}  "
                f"[checks: {r.checks_count}, "
                f"errors: {r.errors}, warnings: {r.warnings}]"
            )
            print(summary)

            if r.errors or r.warnings or args.verbose:
                for iss in r.issues:
                    if iss.severity == "INFO" and not args.verbose:
                        continue
                    icon = {"ERROR": "🔴", "WARNING": "🟡", "INFO": "🔵"}[iss.severity]
                    line_str = f"L{iss.line}" if iss.line else "  -"
                    check_str = f"[{iss.check_id}]" if iss.check_id else ""
                    print(f"    {icon} {line_str:>5} {check_str} "
                          f"[{iss.category}] {iss.message}")
                    if iss.hint:
                        print(f"          💡 {iss.hint}")
                print()

            total_e += r.errors
            total_w += r.warnings
            total_i += r.infos
            total_c += r.checks_count

        print(f"\n{'=' * 78}")
        print(f"ИТОГО:  файлов: {len(reports)},  чеков: {total_c},  "
              f"errors: {total_e},  warnings: {total_w}")
        print(f"{'=' * 78}\n")

    total_errors = sum(r.errors for r in reports)
    total_warnings = sum(r.warnings for r in reports)
    if total_errors > 0:
        return 1
    if args.strict and total_warnings > 0:
        return 1
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception:
        traceback.print_exc()
        sys.exit(2)

        