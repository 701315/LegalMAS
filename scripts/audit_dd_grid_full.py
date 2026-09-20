#!/usr/bin/env python3
"""
Comprehensive audit of YAML playbooks for DD Grid compatibility.

Generates THREE separate report files by severity:
1. dd_grid_audit_ERRORS.txt    — blocking issues (checks won't load)
2. dd_grid_audit_WARNINGS.txt  — degraded issues (checks load but invisible/broken)
3. dd_grid_audit_INFO.txt      — sync mismatches (non-blocking, review recommended)

Each report contains:
- Russian-language explanation of the category
- Impact on code and YAML quality
- How to fix
- Per-check finding list with field names, locations, and fix examples

Usage:
    python scripts/audit_dd_grid_full.py
    python scripts/audit_dd_grid_full.py --output-json scripts/dd_grid_audit_report.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except ImportError as exc:
    raise SystemExit(
        "PyYAML is required. Install it in the project venv: pip install pyyaml"
    ) from exc


SCRIPT_DIR = Path(__file__).resolve().parent

DEFAULT_ROOTS: tuple[Path, ...] = (
    Path("/home/vladi/projects/LegalMAS/playbooks/document_types"),
    Path("/home/vladi/projects/LegalMAS/playbooks/global_checks"),
)

YAML_EXTENSIONS: frozenset[str] = frozenset({".yml", ".yaml"})
RESERVED_SUFFIXES: tuple[str, ...] = ("_status", "_details", "_value")

KNOWN_METADATA_FIELD_NAMES: frozenset[str] = frozenset({
    "evidence", "evidence_items", "reason", "explanation", "notes",
})


# ───────────────────────────────────────────────────────────────────────
# Data models
# ───────────────────────────────────────────────────────────────────────

@dataclass(slots=True)
class FieldMeta:
    name: str
    field_type: str | None
    presentation: str | None
    allowed_values: list[Any] | None
    required: bool | None
    display_in_grid: bool | None
    label: str | None
    raw_index: int


@dataclass(slots=True)
class LocationHit:
    line_no: int
    section: str
    text: str


@dataclass(slots=True)
class Finding:
    file_path: str
    check_id: str
    check_name: str | None
    category: str
    severity: str
    field_name: str | None
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    occurrences: list[LocationHit] = field(default_factory=list)
    suggested_fix: str | None = None
    example_replacements: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParseIssue:
    file_path: str
    error: str


# ───────────────────────────────────────────────────────────────────────
# CLI
# ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Comprehensive audit of YAML playbooks for DD Grid compatibility."
    )
    parser.add_argument(
        "--roots", nargs="*", type=Path, default=list(DEFAULT_ROOTS),
        help="Root folders to scan recursively.",
    )
    parser.add_argument(
        "--output-json", type=Path, default=None,
        help="Optional path to save machine-readable JSON report.",
    )
    parser.add_argument(
        "--max-occurrences", type=int, default=20,
        help="Limit reported line hits per conflict field.",
    )
    return parser.parse_args()


# ───────────────────────────────────────────────────────────────────────
# File collection & YAML loading
# ───────────────────────────────────────────────────────────────────────

def iter_yaml_files(roots: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            print(f"[WARN] Root does not exist: {root}", file=sys.stderr)
            continue
        if root.is_file() and root.suffix.lower() in YAML_EXTENSIONS:
            files.append(root)
            continue
        if root.is_dir():
            files.extend(sorted(
                p for p in root.rglob("*")
                if p.is_file() and p.suffix.lower() in YAML_EXTENSIONS
            ))
    return sorted(set(files))


def safe_load_yaml(path: Path) -> tuple[list[Any], str | None]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [], f"read error: {exc}"
    try:
        docs = list(yaml.safe_load_all(raw))
    except yaml.YAMLError as exc:
        return [], f"yaml parse error: {exc}"
    return docs, None


def collect_check_nodes(node: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            if "id" in value and any(
                k in value for k in ("extraction", "llm", "rules", "origin", "detector_type")
            ):
                found.append(value)
            for child in value.values():
                _walk(child)
        elif isinstance(value, list):
            for child in value:
                _walk(child)

    _walk(node)
    return found


# ───────────────────────────────────────────────────────────────────────
# Field normalization
# ───────────────────────────────────────────────────────────────────────

def normalize_fields(fields_raw: Any) -> list[FieldMeta]:
    if not isinstance(fields_raw, list):
        return []
    result: list[FieldMeta] = []
    for idx, item in enumerate(fields_raw):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        allowed = item.get("allowed_values")
        if not isinstance(allowed, list):
            allowed = None
        result.append(FieldMeta(
            name=name.strip(),
            field_type=item.get("type") if isinstance(item.get("type"), str) else None,
            presentation=item.get("presentation") if isinstance(item.get("presentation"), str) else None,
            allowed_values=allowed,
            required=item.get("required") if isinstance(item.get("required"), bool) else None,
            display_in_grid=item.get("display_in_grid") if isinstance(item.get("display_in_grid"), bool) else None,
            label=item.get("label") if isinstance(item.get("label"), str) else None,
            raw_index=idx,
        ))
    return result


# ───────────────────────────────────────────────────────────────────────
# Location helpers
# ───────────────────────────────────────────────────────────────────────

def locate_check_block(lines: list[str], check_id: str) -> tuple[int, int] | None:
    start_pat = re.compile(rf'^\s*-\s+id:\s*["\']?{re.escape(check_id)}["\']?\s*$')
    next_pat = re.compile(r'^\s*-\s+id:\s*["\']?.+["\']?\s*$')
    start: int | None = None
    for idx, line in enumerate(lines):
        if start_pat.match(line):
            start = idx
            break
    if start is None:
        return None
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        if next_pat.match(lines[idx]):
            end = idx
            break
    return start, end


def find_token_occurrences(
    raw_text: str, check_id: str, token: str, max_hits: int,
) -> list[LocationHit]:
    lines = raw_text.splitlines()
    block = locate_check_block(lines, check_id)
    if block is None:
        return []
    start_idx, end_idx = block
    hits: list[LocationHit] = []
    token_re = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])")
    multiline_section: str | None = None
    multiline_indent: int | None = None

    for idx in range(start_idx, end_idx):
        line = lines[idx]
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))
        if multiline_section is not None and multiline_indent is not None:
            if stripped and indent <= multiline_indent:
                multiline_section = None
                multiline_indent = None
        section = "check_block"
        if re.match(r'^\s*-\s+name:\s*["\']?.+["\']?\s*$', line):
            section = "extraction.fields"
        elif multiline_section is not None:
            section = multiline_section
        if token_re.search(line):
            hits.append(LocationHit(line_no=idx + 1, section=section, text=line.rstrip()))
            if len(hits) >= max_hits:
                break
        if stripped.startswith("prompt_template: |"):
            multiline_section = "llm.prompt_template"
            multiline_indent = indent
        elif stripped.startswith("llm_prompt_extraction: |"):
            multiline_section = "extraction.llm_prompt_extraction"
            multiline_indent = indent
    return hits


# ───────────────────────────────────────────────────────────────────────
# Naming contract helpers
# ───────────────────────────────────────────────────────────────────────

def build_paired_prefix_map(field_names: set[str]) -> dict[str, list[str]]:
    prefix_map: dict[str, list[str]] = {}
    for name in field_names:
        for suffix in RESERVED_SUFFIXES:
            if name.endswith(suffix) and len(name) > len(suffix):
                prefix = name[:-len(suffix)]
                prefix_map.setdefault(prefix, []).append(name)
    for fields in prefix_map.values():
        fields.sort()
    return prefix_map


def choose_suggested_name(fm: FieldMeta, existing: set[str]) -> tuple[str, str]:
    is_code = fm.presentation == "signal" or bool(fm.allowed_values)
    preferred = "_code" if is_code else "_value"
    reason = "signal/enum → *_code" if is_code else "fact/scalar → *_value"
    candidates = [
        f"{fm.name}{preferred}", f"{fm.name}_value", f"{fm.name}_code",
        f"{fm.name}_text", f"{fm.name}_label", f"{fm.name}_raw",
    ]
    for c in candidates:
        if c not in existing:
            return c, reason
    idx = 2
    while True:
        c = f"{fm.name}{preferred}_{idx}"
        if c not in existing:
            return c, f"{reason}; fallback"
        idx += 1


# ───────────────────────────────────────────────────────────────────────
# Prompt-fields sync
# ───────────────────────────────────────────────────────────────────────

# PATCHED: field extraction v2
_ENUM_NOISE = frozenset({
    "yes", "no", "not_defined", "unclear", "mixed", "present", "missing",
    "not_specified", "not_applicable", "not_mentioned", "not_required",
    "required", "optional", "true", "false", "defined", "partial",
    "general", "prohibited", "specified", "excluded", "preserved",
    "restricted", "other", "shared", "none", "unknown", "absent",
    "applicable", "included", "cash", "gost", "tu", "na", "n_a",
})


def _looks_like_field(name: str) -> bool:
    """Отсеиваем короткие токены и enum-значения."""
    if name in _ENUM_NOISE:
        return False
    if "_" not in name and len(name) < 6:
        return False
    return True


# PATCHED: field extraction v6
_ENUM_NOISE = frozenset({
    "yes", "no", "not_defined", "unclear", "mixed", "present", "missing",
    "not_specified", "not_applicable", "not_mentioned", "not_required",
    "required", "optional", "true", "false", "defined", "partial",
    "general", "prohibited", "specified", "excluded", "preserved",
    "restricted", "other", "shared", "none", "unknown", "absent",
    "applicable", "included", "cash", "gost", "tu", "na", "n_a",
    "allowed", "allowed_with_consent", "explicitly_none", "consent_present",
    "consent_required", "not_married_confirmed", "contract_specified",
    "percent_per_day", "fixed_amount", "third_party", "specific",
    "limited", "movable", "real_estate", "listed", "perpetual", "notarized",
    "detailed", "custom", "market", "receiver", "guarantee", "fallback",
    "restriction_scope", "full_ban",
})

_METADATA = frozenset({
    "evidence", "clause_ref", "quote", "page", "reason", "explanation", "notes",
})


def _looks_like_field(name: str) -> bool:
    if name in _ENUM_NOISE or name in _METADATA:
        return False
    if name.endswith("_display"):
        return False
    if "_" not in name:
        return False
    if name and name[0].isupper():
        return False
    return True


def extract_field_names_from_prompt(prompt_text: str | None) -> set[str]:
    if not prompt_text:
        return set()
    names: set[str] = set()
    CHARS = r"[a-zA-Z][a-zA-Z0-9_]*"  # PATCHED: field extraction v7
    # 1. `N. field_name` или `N.field_name` (пробел после точки — опционален)
    for m in re.finditer(rf"^\s*\d+\.\s*({CHARS})\b", prompt_text, re.MULTILINE):
        names.add(m.group(1))
    # 2. `N. field_a / field_b` — второй через /
    for m in re.finditer(rf"^\s*\d+\.\s*{CHARS}\s*/\s*({CHARS})\b",
                         prompt_text, re.MULTILINE):
        names.add(m.group(1))
    # 3. `- field_name:` / `- field_name —` / `- field_name =`
    for m in re.finditer(rf"^\s*-\s*({CHARS})\s*[:=—]", prompt_text, re.MULTILINE):
        names.add(m.group(1))
    # 4. `"field_name":` (JSON-пример) — с любым регистром внутри
    for m in re.finditer(rf'"([a-zA-Z][a-zA-Z0-9_]*)"\s*:', prompt_text):
        names.add(m.group(1))
    # 5. `field_name — описание` (без номера)
    for m in re.finditer(rf"^\s*({CHARS})\s+—", prompt_text, re.MULTILINE):
        names.add(m.group(1))

    names = {n for n in names if _looks_like_field(n)}
    names -= KNOWN_METADATA_FIELD_NAMES
    return names


# ───────────────────────────────────────────────────────────────────────
# Auditors
# ───────────────────────────────────────────────────────────────────────

def _check_meta(node: dict[str, Any]) -> tuple[str, str | None]:
    cid = str(node.get("id", "")).strip()
    cn = node.get("name")
    cn = cn.strip() if isinstance(cn, str) else None
    return cid, cn


def audit_naming_contract(
    *, file_path: Path, check_node: dict[str, Any], raw_text: str, max_occ: int,
) -> list[Finding]:
    extraction = check_node.get("extraction")
    if not isinstance(extraction, dict):
        return []
    fields = normalize_fields(extraction.get("fields"))
    if not fields:
        return []
    field_names = {f.name for f in fields}
    prefix_map = build_paired_prefix_map(field_names)
    cid, cn = _check_meta(check_node)
    findings: list[Finding] = []
    for fm in fields:
        paired = prefix_map.get(fm.name)
        if not paired:
            continue
        suggested, reason = choose_suggested_name(fm, field_names)
        occurrences = find_token_occurrences(raw_text, cid, fm.name, max_occ)
        findings.append(Finding(
            file_path=str(file_path), check_id=cid, check_name=cn,
            category="NAMING_CONTRACT", severity="ERROR", field_name=fm.name,
            message=f'Singleton "{fm.name}" конфликтует с paired {paired}.',
            details={
                "paired_fields": paired, "suggested_name": suggested,
                "suggestion_reason": reason, "field_type": fm.field_type,
                "presentation": fm.presentation,
            },
            occurrences=occurrences,
            suggested_fix=f'"{fm.name}" → "{suggested}"',
            example_replacements=[
                f'extraction.fields:       - name: "{fm.name}"  →  - name: "{suggested}"',
                f'JSON-ключи в промптах:   "{fm.name}": ...     →  "{suggested}": ...',
                f'Нумерованные списки:     {fm.name} — ...      →  {suggested} — ...',
            ],
        ))
    return findings


def audit_no_extraction(*, file_path: Path, check_node: dict[str, Any]) -> list[Finding]:
    cid, cn = _check_meta(check_node)
    extraction = check_node.get("extraction")
    ui_mode = check_node.get("ui_mode", "")
    if extraction is None:
        return [Finding(
            file_path=str(file_path), check_id=cid, check_name=cn,
            category="NO_EXTRACTION", severity="WARNING", field_name=None,
            message="Блок 'extraction' отсутствует. Чек будет невидим в DD Grid.",
            suggested_fix="Добавить extraction с хотя бы одним полем presence_status.",
        )]
    if not isinstance(extraction, dict):
        return [Finding(
            file_path=str(file_path), check_id=cid, check_name=cn,
            category="NO_EXTRACTION", severity="WARNING", field_name=None,
            message=f"Блок 'extraction' не является dict (type={type(extraction).__name__}).",
        )]
    if extraction.get("enabled") is False:
        return [Finding(
            file_path=str(file_path), check_id=cid, check_name=cn,
            category="NO_EXTRACTION", severity="WARNING", field_name=None,
            message=f"extraction.enabled=false (ui_mode={ui_mode!r}). Чек невидим в DD Grid.",
            suggested_fix=(
                "Установить extraction.enabled=true и добавить хотя бы одно поле "
                "с display_in_grid=true."
            ),
        )]
    return []


def audit_empty_fields(*, file_path: Path, check_node: dict[str, Any]) -> list[Finding]:
    extraction = check_node.get("extraction")
    if not isinstance(extraction, dict) or extraction.get("enabled") is False:
        return []
    cid, cn = _check_meta(check_node)
    fields_raw = extraction.get("fields")
    if fields_raw is None:
        return [Finding(
            file_path=str(file_path), check_id=cid, check_name=cn,
            category="EMPTY_FIELDS", severity="WARNING", field_name=None,
            message="extraction.enabled=true, но 'fields' отсутствует. Нет runtime-колонок.",
            suggested_fix="Добавить список 'fields' с определением полей.",
        )]
    if isinstance(fields_raw, list) and len(fields_raw) == 0:
        return [Finding(
            file_path=str(file_path), check_id=cid, check_name=cn,
            category="EMPTY_FIELDS", severity="WARNING", field_name=None,
            message="extraction.enabled=true, но fields=[] (пустой список). Нет runtime-колонок.",
            suggested_fix="Добавить хотя бы одно поле в 'fields'.",
        )]
    return []


def audit_duplicate_fields(*, file_path: Path, check_node: dict[str, Any]) -> list[Finding]:
    extraction = check_node.get("extraction")
    if not isinstance(extraction, dict):
        return []
    fields = normalize_fields(extraction.get("fields"))
    if not fields:
        return []
    cid, cn = _check_meta(check_node)
    counts = Counter(f.name for f in fields)
    return [
        Finding(
            file_path=str(file_path), check_id=cid, check_name=cn,
            category="DUPLICATE_FIELD", severity="ERROR", field_name=name,
            message=f'Поле "{name}" встречается {count} раз в extraction.fields.',
            suggested_fix=f"Удалить или переименовать дубликаты поля '{name}'.",
        )
        for name, count in counts.items() if count > 1
    ]


def audit_missing_attributes(*, file_path: Path, check_node: dict[str, Any]) -> list[Finding]:
    extraction = check_node.get("extraction")
    if not isinstance(extraction, dict):
        return []
    fields_raw = extraction.get("fields")
    if not isinstance(fields_raw, list):
        return []
    cid, cn = _check_meta(check_node)
    findings: list[Finding] = []
    for idx, item in enumerate(fields_raw):
        if not isinstance(item, dict):
            findings.append(Finding(
                file_path=str(file_path), check_id=cid, check_name=cn,
                category="MISSING_ATTR", severity="ERROR", field_name=None,
                message=f"fields[{idx}] не является dict (type={type(item).__name__}).",
            ))
            continue
        name = item.get("name")
        if not name or not isinstance(name, str) or not name.strip():
            findings.append(Finding(
                file_path=str(file_path), check_id=cid, check_name=cn,
                category="MISSING_ATTR", severity="ERROR", field_name=None,
                message=f"fields[{idx}]: отсутствует или пуст атрибут 'name'.",
            ))
        ftype = item.get("type")
        if not ftype or not isinstance(ftype, str) or not ftype.strip():
            display = name if isinstance(name, str) else f"fields[{idx}]"
            findings.append(Finding(
                file_path=str(file_path), check_id=cid, check_name=cn,
                category="MISSING_ATTR", severity="WARNING", field_name=display,
                message=f'Поле "{display}": отсутствует атрибут \'type\'.',
            ))
    return findings


# PATCHED: sync v4
# Поля, которые backend формирует сам (из *_code), не должны быть в промпте.
_BACKEND_ONLY_SUFFIXES = ("_display",)
# Явный мусор, который регулярка может поймать в тексте, но это не поля.
_PROMPT_NOISE = frozenset({
    "clause_ref", "quote", "page", "evidence", "evidence_items",
    "reason", "explanation", "notes", "fallback", "status", "term",
    "agent", "regime", "charter", "personal",
})


def _is_backend_only(name: str) -> bool:
    return any(name.endswith(s) for s in _BACKEND_ONLY_SUFFIXES)


def audit_prompt_field_sync(*, file_path: Path, check_node: dict[str, Any]) -> list[Finding]:
    extraction = check_node.get("extraction")
    if not isinstance(extraction, dict) or extraction.get("enabled") is False:
        return []
    fields = normalize_fields(extraction.get("fields"))
    if not fields:
        return []
    prompt_text = extraction.get("llm_prompt_extraction")
    if not isinstance(prompt_text, str) or not prompt_text.strip():
        return []
    cid, cn = _check_meta(check_node)
    # declared: убираем metadata + backend-only (*_display)
    declared = {
        f.name for f in fields
        if not _is_backend_only(f.name)
    } - KNOWN_METADATA_FIELD_NAMES
    # in_prompt: убираем backend-only и явный мусор
    in_prompt = extract_field_names_from_prompt(prompt_text)
    in_prompt = {
        n for n in in_prompt
        if not _is_backend_only(n) and n not in _PROMPT_NOISE
    }
    if not in_prompt:
        return []
    findings: list[Finding] = []
    for name in sorted(declared - in_prompt):
        findings.append(Finding(
            file_path=str(file_path), check_id=cid, check_name=cn,
            category="PROMPT_FIELD_MISMATCH", severity="INFO", field_name=name,
            message=(
                f'Поле "{name}" объявлено в extraction.fields, но НЕ найдено '
                f'в llm_prompt_extraction. LLM может его не извлечь.'
            ),
        ))
    for name in sorted(in_prompt - declared):
        findings.append(Finding(
            file_path=str(file_path), check_id=cid, check_name=cn,
            category="PROMPT_FIELD_MISMATCH", severity="INFO", field_name=name,
            message=(
                f'Поле "{name}" упомянуто в llm_prompt_extraction, но НЕ объявлено '
                f'в extraction.fields. Оно не будет сохранено и отображено.'
            ),
        ))
    return findings


def audit_check(
    *, file_path: Path, check_node: dict[str, Any], raw_text: str, max_occ: int,
) -> list[Finding]:
    results: list[Finding] = []
    results.extend(audit_naming_contract(
        file_path=file_path, check_node=check_node, raw_text=raw_text, max_occ=max_occ))
    results.extend(audit_no_extraction(file_path=file_path, check_node=check_node))
    results.extend(audit_empty_fields(file_path=file_path, check_node=check_node))
    results.extend(audit_duplicate_fields(file_path=file_path, check_node=check_node))
    results.extend(audit_missing_attributes(file_path=file_path, check_node=check_node))
    results.extend(audit_prompt_field_sync(file_path=file_path, check_node=check_node))
    return results


# ───────────────────────────────────────────────────────────────────────
# Report: Russian-language category headers
# ───────────────────────────────────────────────────────────────────────

ERRORS_HEADER = """\
══════════════════════════════════════════════════════════════════════════════════
  🔴 ОТЧЁТ: КРИТИЧЕСКИЕ ОШИБКИ (ERRORS)
  Дата: {now}
══════════════════════════════════════════════════════════════════════════════════

ЧТО ЭТО:
  Критические ошибки в YAML-инструкциях, из-за которых чеки НЕ ЗАГРУЖАЮТСЯ
  в систему. Backend отбрасывает такие чеки при старте — они не выполняются
  и не отображаются в DD Grid.

КАКИЕ КАТЕГОРИИ ВХОДЯТ:

  NAMING_CONTRACT — Конфликт именования полей
    Поле-singleton (напр. "buyer_details") совпадает по имени с префиксом
    парного поля (напр. "buyer_details_status"). DD Grid naming contract
    резервирует суффиксы _status / _details / _value для парных полей.
    Singleton не может иметь то же имя, что и prefix парных полей.

  DUPLICATE_FIELD — Дублирование имени поля
    Одно и то же имя поля встречается несколько раз в extraction.fields.
    Это приводит к конфликту column_id в DD Grid.

  MISSING_ATTR — Отсутствие обязательного атрибута
    У поля в extraction.fields отсутствует 'name' или элемент не является dict.

КАК ИСПРАВЛЯТЬ:
  Для каждого найденного конфликта ниже указаны:
  • Файл инструкции
  • ID и название чека
  • Проблемное поле
  • Рекомендованное новое имя
  • Места в файле, где нужно заменить старое имя на новое
    (extraction.fields, llm.prompt_template, llm_prompt_extraction)

  Замена имени поля должна быть выполнена ОДНОВРЕМЕННО во всех местах:
  1. extraction.fields → name: "old_name" → name: "new_name"
  2. llm.prompt_template → все JSON-примеры и формат ответа
  3. extraction.llm_prompt_extraction → нумерованный список полей в <task>

══════════════════════════════════════════════════════════════════════════════════

"""

WARNINGS_HEADER = """\
══════════════════════════════════════════════════════════════════════════════════
  🟡 ОТЧЁТ: ПРЕДУПРЕЖДЕНИЯ (WARNINGS)
  Дата: {now}
══════════════════════════════════════════════════════════════════════════════════

ЧТО ЭТО:
  Проблемы, из-за которых чеки загружаются, но НЕ ОТОБРАЖАЮТСЯ в DD Grid
  или отображаются некорректно. Юрист не видит результаты этих проверок
  в таблице.

КАКИЕ КАТЕГОРИИ ВХОДЯТ:

  NO_EXTRACTION — Отсутствие блока extraction или extraction.enabled=false
    Чек не имеет runtime-колонок для отображения в DD Grid.
    Builder пропускает такие чеки: «check skipped because it has no runtime columns».
    Результат: чек выполняется, но юрист его не видит в таблице.

  EMPTY_FIELDS — Пустой список полей
    extraction.enabled=true, но fields=[] или отсутствует.
    Эффект тот же: нет runtime-колонок, чек невидим.

  MISSING_ATTR (type) — Отсутствие атрибута 'type' у поля
    Поле объявлено, но без атрибута 'type'. Может вызвать
    непредсказуемое поведение column builder.

КАК ИСПРАВЛЯТЬ:
  • NO_EXTRACTION: добавить блок extraction с enabled=true и хотя бы одним
    полем, у которого display_in_grid=true.
  • EMPTY_FIELDS: добавить поля в extraction.fields.
  • MISSING_ATTR: добавить атрибут type: "string" к полю.

  Минимальный пример для clause_presence чека без extraction:
    extraction:
      enabled: true
      mode: "rules"
      fields:
        - name: "check_result_status"
          type: "string"
          presentation: "signal"
          allowed_values: ["defined", "not_defined"]
          label: "Результат"
          display_in_grid: true
          display_priority: 1
      store_payload: false

══════════════════════════════════════════════════════════════════════════════════

"""

INFO_HEADER = """\
══════════════════════════════════════════════════════════════════════════════════
  🔵 ОТЧЁТ: ИНФОРМАЦИОННЫЕ ЗАМЕЧАНИЯ (INFO)
  Дата: {now}
══════════════════════════════════════════════════════════════════════════════════

ЧТО ЭТО:
  Несоответствия между списком полей в extraction.fields и полями,
  упомянутыми в llm_prompt_extraction. Не блокируют загрузку чека,
  но могут привести к потере данных или лишним полям в промпте.

КАКИЕ КАТЕГОРИИ ВХОДЯТ:

  PROMPT_FIELD_MISMATCH — Рассинхрон полей между extraction.fields и промптом

  Два варианта:
  a) Поле объявлено в extraction.fields, но НЕ упомянуто в промпте.
     → LLM может не извлечь это поле, колонка в DD Grid будет пустой.
     Решение: добавить поле в нумерованный список <task> промпта.

  b) Поле упомянуто в промпте, но НЕ объявлено в extraction.fields.
     → LLM извлечёт значение, но backend его не сохранит и не отобразит.
     Решение: добавить поле в extraction.fields или убрать из промпта.

КАК ИСПРАВЛЯТЬ:
  Для каждого замечания ниже указаны файл, чек и имя поля.
  Проверьте, нужно ли это поле — и синхронизируйте extraction.fields
  с текстом llm_prompt_extraction.

══════════════════════════════════════════════════════════════════════════════════

"""


# ───────────────────────────────────────────────────────────────────────
# Report rendering (per severity file)
# ───────────────────────────────────────────────────────────────────────

def _short_path(file_path: str, roots: list[Path]) -> str:
    """Make path relative to the closest root for readability."""
    p = Path(file_path)
    for root in roots:
        try:
            return str(p.relative_to(root.parent))
        except ValueError:
            continue
    return str(p)


def render_findings_body(
    findings: list[Finding],
    roots: list[Path],
) -> str:
    """Render compact finding list grouped by file → check."""
    if not findings:
        return "  Нет замечаний в этой категории.\n"

    lines: list[str] = []
    sorted_findings = sorted(findings, key=lambda f: (
        f.file_path, f.check_id, f.field_name or "",
    ))

    current_file: str | None = None
    current_check: str | None = None
    finding_num = 0

    for f in sorted_findings:
        short = _short_path(f.file_path, roots)
        if f.file_path != current_file:
            current_file = f.file_path
            current_check = None
            lines.append(f"{'─' * 90}")
            lines.append(f"ФАЙЛ: {short}")
            lines.append("")

        if f.check_id != current_check:
            current_check = f.check_id
            name_part = f" │ {f.check_name}" if f.check_name else ""
            lines.append(f"  ЧЕК: {f.check_id}{name_part}")
            lines.append("")

        finding_num += 1
        field_part = f'поле "{f.field_name}"' if f.field_name else "—"
        lines.append(f"    [{finding_num}] {f.category} │ {field_part}")
        lines.append(f"        {f.message}")

        if f.suggested_fix:
            lines.append(f"        ИСПРАВЛЕНИЕ: {f.suggested_fix}")

        if f.example_replacements:
            lines.append("        ПРИМЕРЫ:")
            for ex in f.example_replacements:
                lines.append(f"          • {ex}")

        if f.occurrences:
            lines.append("        МЕСТА В ФАЙЛЕ:")
            for hit in f.occurrences:
                lines.append(f"          стр. {hit.line_no:>4} [{hit.section}]  {hit.text}")

        if f.details:
            for key in ("paired_fields", "suggested_name"):
                if key in f.details:
                    lines.append(f"        {key}: {f.details[key]}")

        lines.append("")

    return "\n".join(lines)


def render_summary_block(
    *,
    files_scanned: int,
    checks_scanned: int,
    parse_issues: list[ParseIssue],
    all_findings: list[Finding],
    severity_label: str,
    severity_findings: list[Finding],
) -> str:
    """Render summary stats block for one report file."""
    lines: list[str] = []
    lines.append("ОБЩАЯ СТАТИСТИКА:")
    lines.append(f"  Файлов просканировано   : {files_scanned}")
    lines.append(f"  Чеков просканировано    : {checks_scanned}")
    lines.append(f"  Ошибок парсинга YAML    : {len(parse_issues)}")
    lines.append(f"  Всего замечаний         : {len(all_findings)}")
    lines.append(f"    🔴 ERRORS             : {len([f for f in all_findings if f.severity == 'ERROR'])}")
    lines.append(f"    🟡 WARNINGS           : {len([f for f in all_findings if f.severity == 'WARNING'])}")
    lines.append(f"    🔵 INFO               : {len([f for f in all_findings if f.severity == 'INFO'])}")
    lines.append("")
    lines.append(f"  В этом файле ({severity_label}): {len(severity_findings)} замечаний")

    affected_files = len({f.file_path for f in severity_findings})
    affected_checks = len({(f.file_path, f.check_id) for f in severity_findings})
    lines.append(f"  Затронуто файлов        : {affected_files}")
    lines.append(f"  Затронуто чеков         : {affected_checks}")

    if severity_findings:
        cat_counts = Counter(f.category for f in severity_findings)
        lines.append("  По категориям:")
        for cat, count in sorted(cat_counts.items()):
            lines.append(f"    {cat}: {count}")

    lines.append("")

    if parse_issues:
        lines.append("ОШИБКИ ПАРСИНГА YAML:")
        for issue in parse_issues:
            lines.append(f"  {issue.file_path}")
            lines.append(f"    {issue.error}")
        lines.append("")

    return "\n".join(lines)


# ───────────────────────────────────────────────────────────────────────
# JSON report
# ───────────────────────────────────────────────────────────────────────

def build_json_report(
    *, files_scanned: int, checks_scanned: int,
    parse_issues: list[ParseIssue], findings: list[Finding],
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "files_scanned": files_scanned,
            "checks_scanned": checks_scanned,
            "parse_issues": len(parse_issues),
            "total_findings": len(findings),
            "errors": len([f for f in findings if f.severity == "ERROR"]),
            "warnings": len([f for f in findings if f.severity == "WARNING"]),
            "infos": len([f for f in findings if f.severity == "INFO"]),
            "by_category": dict(Counter(f.category for f in findings)),
        },
        "parse_issues": [asdict(i) for i in parse_issues],
        "findings": [
            {**{k: v for k, v in asdict(f).items() if k != "occurrences"},
             "occurrences": [asdict(h) for h in f.occurrences]}
            for f in findings
        ],
    }


# ───────────────────────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────────────────────

def main() -> int:
    args = parse_args()
    yaml_files = iter_yaml_files(args.roots)
    parse_issues: list[ParseIssue] = []
    findings: list[Finding] = []
    checks_scanned = 0

    for yf in yaml_files:
        docs, error = safe_load_yaml(yf)
        if error is not None:
            parse_issues.append(ParseIssue(file_path=str(yf), error=error))
            continue
        try:
            raw_text = yf.read_text(encoding="utf-8")
        except OSError as exc:
            parse_issues.append(ParseIssue(file_path=str(yf), error=f"read error: {exc}"))
            continue
        for doc in docs:
            for check_node in collect_check_nodes(doc):
                checks_scanned += 1
                try:
                    findings.extend(audit_check(
                        file_path=yf, check_node=check_node,
                        raw_text=raw_text, max_occ=args.max_occurrences,
                    ))
                except Exception as exc:
                    parse_issues.append(ParseIssue(
                        file_path=str(yf),
                        error=f"audit error in check_id={check_node.get('id')!r}: {exc}",
                    ))

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    errors = [f for f in findings if f.severity == "ERROR"]
    warnings = [f for f in findings if f.severity == "WARNING"]
    infos = [f for f in findings if f.severity == "INFO"]

    report_configs = [
        ("dd_grid_audit_ERRORS.txt", ERRORS_HEADER, "ERRORS", errors),
        ("dd_grid_audit_WARNINGS.txt", WARNINGS_HEADER, "WARNINGS", warnings),
        ("dd_grid_audit_INFO.txt", INFO_HEADER, "INFO", infos),
    ]

    for filename, header_template, severity_label, severity_findings in report_configs:
        header = header_template.format(now=now)
        summary = render_summary_block(
            files_scanned=len(yaml_files),
            checks_scanned=checks_scanned,
            parse_issues=parse_issues,
            all_findings=findings,
            severity_label=severity_label,
            severity_findings=severity_findings,
        )
        body = render_findings_body(severity_findings, args.roots)

        full_report = header + summary + "\n" + body
        report_path = SCRIPT_DIR / filename

        try:
            report_path.write_text(full_report, encoding="utf-8")
            print(f"[OK] {filename}: {len(severity_findings)} замечаний → {report_path}")
        except OSError as exc:
            print(f"[ERROR] Не удалось сохранить {filename}: {exc}", file=sys.stderr)

    # Console summary
    print()
    print("═" * 60)
    print("  ИТОГ АУДИТА")
    print("═" * 60)
    print(f"  Файлов просканировано : {len(yaml_files)}")
    print(f"  Чеков просканировано  : {checks_scanned}")
    print(f"  🔴 ERRORS             : {len(errors)}")
    print(f"  🟡 WARNINGS           : {len(warnings)}")
    print(f"  🔵 INFO               : {len(infos)}")
    print()

    if errors:
        print("  🔴 Есть критические ошибки — чеки НЕ загрузятся.")
        print("     См. scripts/dd_grid_audit_ERRORS.txt")
    if warnings:
        print("  🟡 Есть предупреждения — чеки загрузятся, но не видны в DD Grid.")
        print("     См. scripts/dd_grid_audit_WARNINGS.txt")
    if infos:
        print("  🔵 Есть рассинхронизации промпт ↔ поля (рекомендуется проверить).")
        print("     См. scripts/dd_grid_audit_INFO.txt")
    if not errors and not warnings and not infos:
        print("  ✅ Все инструкции проходят проверку DD Grid.")

    print()

    # Optional JSON
    if args.output_json is not None:
        report = build_json_report(
            files_scanned=len(yaml_files), checks_scanned=checks_scanned,
            parse_issues=parse_issues, findings=findings,
        )
        try:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_json.write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
            )
            print(f"[OK] JSON-отчёт: {args.output_json}")
        except OSError as exc:
            print(f"[ERROR] JSON: {exc}", file=sys.stderr)

    if errors:
        return 2
    if warnings or parse_issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


