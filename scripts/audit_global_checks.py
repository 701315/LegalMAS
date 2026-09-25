#!/usr/bin/env python3
"""
audit_global_checks.py — предварительная оценка GLOBAL checks.

Оценивает соответствие playbooks/global_checks/* требованиям:
  * B7.10  — presence_signal (Task A)
  * Wave 3 — risk_weight на signal-полях + Layer 2 custom prompt (Task B)
  * RF     — авто-детектируемые red-flags (RF4, RF7, RF8, RF9, RF10)
  * Struct — структурные особенности GLOBAL checks (Section 0)

Скрипт НЕ правит YAML. Только читает и отчитывается.
Для ревью юристом — вывод отчёта достаточно.

Использование:
    cd /srv/steloom-dev && source .venv/bin/activate
    export PYTHONPATH=src:.

    python scripts/audit_global_checks.py                     # default root
    python scripts/audit_global_checks.py --root <path>
    python scripts/audit_global_checks.py --only coc_         # filter
    python scripts/audit_global_checks.py --json  out.json
    python scripts/audit_global_checks.py --csv   out.csv
    python scripts/audit_global_checks.py --summary-only
    python scripts/audit_global_checks.py --verbose           # full per-file
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field, asdict
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")


# 1. Литеральные placeholder'ы в prompt
PLACEHOLDER_RE = re.compile(r"<[A-Z][A-Z0-9_]{3,}>")   # <STATUS_FIELD>, <PREFIX>, но не <role>

def find_placeholders(prompt: str) -> list[str]:
    known_tags = {
        "role", "context_rules", "context", "task", "instructions",
        "location_instructions", "edge_cases", "output_expectations",
    }
    hits = []
    for m in PLACEHOLDER_RE.finditer(prompt):
        tag = m.group(0)[1:-1].lower()
        if tag not in known_tags:
            hits.append(m.group(0))
    return sorted(set(hits))

# 2. Дубли в служебных списках
def find_list_dups(data: dict) -> dict[str, list[str]]:
    out = {}
    paths = [
        ("retrieval", "preferred_clause_functions"),
        ("retrieval", "preferred_unit_types"),
        ("retrieval", "excluded_unit_types"),
        ("enrichment_hints", "preferred_segment_types"),
        ("enrichment_hints", "excluded_segment_types"),
        ("enrichment_hints", "preferred_clause_functions"),
    ]
    for section, key in paths:
        lst = (data.get(section) or {}).get(key) or []
        seen, dups = set(), []
        for x in lst:
            if x in seen:
                dups.append(x)
            seen.add(x)
        if dups:
            out[f"{section}.{key}"] = sorted(set(dups))
    return out

# 3. Дубли bullets в context_rules (нормализованные)
def find_context_rules_dups(prompt: str) -> list[str]:
    block = _extract_block(prompt, "context_rules") or ""
    norm = []
    for ln in block.splitlines():
        ln = ln.strip().lstrip("-").strip().lower()
        # отбрасываем стоп-слова и оставляем «скелет»
        key = re.sub(r"[^а-яa-z]", "", ln)[:60]
        if key:
            norm.append(key)
    counter = Counter(norm)
    return [k for k, n in counter.items() if n > 1]

# 4. Порядок <context_rules> vs <context>
def check_tag_order(prompt: str) -> bool:
    i_cr = prompt.find("<context_rules>")
    i_c = prompt.find("<context>")
    return not (i_cr != -1 and i_c != -1 and i_cr > i_c)   # True = OK

# 5. Семантические перекрытия nested keywords (high ∩ medium и т.д.)
def find_keyword_overlaps(data: dict) -> dict[str, list[str]]:
    kw = (data.get("rules") or {}).get("keywords") or {}
    if not isinstance(kw, dict):
        return {}
    sets = {t: set(kw.get(t) or []) for t in ("high", "medium", "low")}
    out = {}
    for a, b in (("high", "medium"), ("high", "low"), ("medium", "low")):
        inter = sets[a] & sets[b]
        if inter:
            out[f"{a}∩{b}"] = sorted(inter)
    return out

# 6. Опечатки — по словарю
TYPOS = {
    "налиличие": "наличие",
    "предоставлятся": "предоставляется",
    "необходимостm": "необходимость",
    # ...пополняется по мере находок
}
def find_typos(prompt: str, description: str) -> list[str]:
    hits = []
    haystack = f"{prompt}\n{description}"
    for bad, good in TYPOS.items():
        if bad in haystack:
            hits.append(f"{bad} → {good}")
    return hits
# ─────────────────────────────────────────────────────────────────────────
# Константы
# ─────────────────────────────────────────────────────────────────────────

DEFAULT_ROOT = Path("/srv/steloom-dev/playbooks/global_checks")

# Эталон — не аудируем (он 100% готов, служит образцом).
ETALON_FILES = {"coc_change_of_control_regime.yaml"}

VALID_WEIGHTS = {"high", "medium", "low", "info"}
VALID_MODES = {"hybrid", "llm"}

REQUIRED_TOP = [
    "id", "name", "description", "doc_types",
    "severity", "severity_if_pass", "severity_if_fail", "severity_if_unclear",
    "detector_type", "ui_mode",
    "rules", "llm", "retrieval", "extraction",
]

# Блоки, ожидаемые в extraction.llm_prompt_extraction.
# Отсутствие 1–2 → ⚠️; отсутствие ≥3 → ❌.
REQUIRED_PROMPT_BLOCKS = [
    "<role>", "</role>",
    "<context_rules>", "</context_rules>",
    "<context>", "</context>",
    "<task>", "</task>",
    "<instructions>", "</instructions>",
    "<location_instructions>", "</location_instructions>",
    "<edge_cases>", "</edge_cases>",
    "<output_expectations>", "</output_expectations>",
]

# RF4 — эвристика «оценка риска в edge_cases».
RISK_EVAL_RE = re.compile(
    r"(риск\s+не\s+хеджирован|существенн\w+\s+риск|значительн\w+\s+риск|"
    r"невыгодн\w+\s+(?:для|условие)|представляет\s+риск|это\s+риск|"
    r"materially\s+adverse|significant\s+risk|material\s+risk)",
    re.IGNORECASE,
)

# RF9 — «description обещает оценку риска», а `<role>` запрещает.
RISK_IN_DESC_RE = re.compile(r"\b(оценива|анализ)\w*\b[^\n]{0,60}\bриск", re.IGNORECASE)
RISK_FORBIDDEN_IN_ROLE_RE = re.compile(r"не\s+оценива\w*\s+риск", re.IGNORECASE)

# RF10 — признаки того, что в `<location_instructions>` описано правило для `no`.
RF10_NO_QUOTE_RE = re.compile(
    r"(?:no|исключ\w*|отсутств\w*)[\s\S]{0,300}(?:quote|цитат|дословн)"
    r"|(?:quote|цитат|дословн)[\s\S]{0,300}(?:no\b|исключ\w*|отсутств\w*)",
    re.IGNORECASE,
)


# ─────────────────────────────────────────────────────────────────────────
# Report
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class CheckReport:
    path: str
    check_id: str = ""
    group: str = ""
    parse_error: str = ""

    # Struct
    struct_issues: list = field(default_factory=list)

    # presence_signal
    has_presence_signal: bool = False
    presence_signal_issues: list = field(default_factory=list)

    # risk_weight
    signal_fields: list = field(default_factory=list)
    signal_fields_without_weight: list = field(default_factory=list)
    invalid_weights: list = field(default_factory=list)

    # Layer 2 prompt
    prompt_missing_required: list = field(default_factory=list)
    prompt_issues: list = field(default_factory=list)

    # RF flags
    rf4_risk_words: list = field(default_factory=list)
    rf7_dups: list = field(default_factory=list)
    rf8_mismatch: bool = False
    rf9_contradiction: bool = False
    rf10_applicable: bool = False
    rf10_issue: bool = False

    # DEEP (v3) — placeholder'ы, дубли, порядок, перекрытия, опечатки
    placeholders: list = field(default_factory=list)
    list_dups: dict = field(default_factory=dict)
    context_rules_dups: list = field(default_factory=list)
    tag_order_ok: bool = True
    keyword_overlaps: dict = field(default_factory=dict)
    typos: list = field(default_factory=list)

    # ── Грейдеры ────────────────────────────────────────────────────

    def grade_struct(self) -> str:
        if self.parse_error:
            return "fail"
        n = len(self.struct_issues)
        return "ok" if n == 0 else ("warn" if n <= 2 else "fail")

    def grade_presence(self) -> str:
        if not self.has_presence_signal:
            return "fail"
        return "warn" if self.presence_signal_issues else "ok"

    def grade_weights(self) -> str:
        if not self.signal_fields:
            return "n/a"
        if not self.signal_fields_without_weight and not self.invalid_weights:
            return "ok"
        if len(self.signal_fields_without_weight) == len(self.signal_fields):
            return "fail"
        return "warn"

    def grade_layer2(self) -> str:
        n = len(self.prompt_missing_required)
        if n == 0 and not self.prompt_issues:
            return "ok"
        if n >= 3:
            return "fail"
        return "warn"

    def grade_rf(self) -> str:
        flags = 0
        if self.rf4_risk_words:
            flags += 1
        if self.rf7_dups:
            flags += 1
        if self.rf8_mismatch:
            flags += 1
        if self.rf9_contradiction:
            flags += 1
        if self.rf10_issue:
            flags += 1
        if flags == 0:
            return "ok"
        if flags <= 2:
            return "warn"
        return "fail"

    def grade_deep(self) -> str:
        # keyword_overlaps НЕ считаем: пересечения regex часто by design
        n = (
            len(self.placeholders)
            + len(self.list_dups)
            + len(self.context_rules_dups)
            + (0 if self.tag_order_ok else 1)
            + len(self.typos)
        )
        if n == 0:
            return "ok"
        if n <= 2:
            return "warn"
        return "fail"

    def grade_overall(self) -> str:
        grades = [
            self.grade_struct(), self.grade_presence(),
            self.grade_weights(), self.grade_layer2(),
            self.grade_rf(), self.grade_deep(),
        ]
        grades = [g for g in grades if g != "n/a"]
        if "fail" in grades:
            return "fail"
        if "warn" in grades:
            return "warn"
        return "ok"


# ─────────────────────────────────────────────────────────────────────────
# YAML helpers
# ─────────────────────────────────────────────────────────────────────────

def load_yaml_first_doc(path: Path):
    with path.open("r", encoding="utf-8") as f:
        docs = list(yaml.safe_load_all(f))
    docs = [d for d in docs if d is not None]
    return docs[0] if docs else None


def _extract_block(prompt: str, tag: str) -> str | None:
    open_tag, close_tag = f"<{tag}>", f"</{tag}>"
    i = prompt.find(open_tag)
    if i == -1:
        return None
    j = prompt.find(close_tag, i)
    if j == -1:
        return None
    return prompt[i + len(open_tag): j]


def _is_field_extraction(data: dict) -> bool:
    return data.get("ui_mode") == "field_extraction"


# ─────────────────────────────────────────────────────────────────────────
# Section 0 — структурные проверки
# ─────────────────────────────────────────────────────────────────────────

def check_structure(data: dict) -> list[str]:
    issues: list[str] = []

    for key in REQUIRED_TOP:
        if key not in data:
            issues.append(f"missing top-level: {key}")

    if data.get("doc_types") not in ([], None) and data.get("doc_types") != []:
        issues.append(f"doc_types must be [] (got {data.get('doc_types')!r})")

    if "origin" in data:
        issues.append("origin must be absent (default = GLOBAL_PLAYBOOK)")

    if "triggers" in data:
        issues.append("triggers must be absent")

    # rules
    rules = data.get("rules")
    if not isinstance(rules, dict):
        issues.append("rules is not a mapping")
    else:
        if "keyword_mode" not in rules:
            issues.append("rules.keyword_mode missing")
        kw = rules.get("keywords")
        if not isinstance(kw, dict):
            issues.append("rules.keywords must be nested dict (high/medium/low), not flat list")
        else:
            for tier in ("high", "medium", "low"):
                if tier not in kw:
                    issues.append(f"rules.keywords missing tier: {tier}")

    # llm (Layer 1)
    llm = data.get("llm") or {}
    if not isinstance(llm, dict):
        issues.append("llm is not a mapping")
    else:
        pf = llm.get("prompt_file")
        if pf != "detection/generic_presence.txt":
            issues.append(
                f"llm.prompt_file should be 'detection/generic_presence.txt' "
                f"(got {pf!r})"
            )
        if "prompt_template" in llm:
            issues.append("llm.prompt_template should not be present (use prompt_file)")

    # extraction
    ext = data.get("extraction") or {}
    if not isinstance(ext, dict):
        issues.append("extraction is not a mapping")
    else:
        if ext.get("enabled") is not True:
            issues.append("extraction.enabled should be true")
        mode = ext.get("mode")
        if mode not in VALID_MODES:
            issues.append(f"extraction.mode unexpected: {mode!r}")

    return issues


# ─────────────────────────────────────────────────────────────────────────
# Task A — presence_signal
# ─────────────────────────────────────────────────────────────────────────

def check_presence_signal(data: dict) -> tuple[bool, list[str]]:
    ext = data.get("extraction") or {}
    ps = ext.get("presence_signal")
    if not isinstance(ps, dict):
        return False, ["presence_signal absent"]

    issues: list[str] = []
    field_name = ps.get("field")
    present = ps.get("present_values")
    missing = ps.get("missing_values")
    unclear = ps.get("unclear_values")

    for key, val in (("field", field_name),
                     ("present_values", present),
                     ("missing_values", missing),
                     ("unclear_values", unclear)):
        if val is None:
            issues.append(f"presence_signal.{key} missing")

    if not field_name:
        return True, issues

    # field declared?
    fields = ext.get("fields") or []
    target = next(
        (f for f in fields if isinstance(f, dict) and f.get("name") == field_name),
        None,
    )
    if target is None:
        issues.append(
            f"presence_signal.field '{field_name}' not declared in extraction.fields"
        )
        return True, issues

    allowed = target.get("allowed_values")
    if not isinstance(allowed, list):
        issues.append(
            f"field '{field_name}' has no allowed_values — cannot validate union"
        )
        return True, issues

    if not (isinstance(present, list) and isinstance(missing, list) and isinstance(unclear, list)):
        return True, issues

    p, m, u = set(present), set(missing), set(unclear)

    for name, a, b in (("present", p, m), ("present", p, u), ("missing", m, u)):
        # intersect сообщаем один раз на пару
        pass
    if p & m:
        issues.append(f"presence_signal: present ∩ missing = {sorted(p & m)}")
    if p & u:
        issues.append(f"presence_signal: present ∩ unclear = {sorted(p & u)}")
    if m & u:
        issues.append(f"presence_signal: missing ∩ unclear = {sorted(m & u)}")

    union = p | m | u
    allowed_set = set(allowed)
    if union != allowed_set:
        only_allowed = sorted(allowed_set - union)
        only_union = sorted(union - allowed_set)
        if only_allowed:
            issues.append(f"presence_signal: union missing allowed_values: {only_allowed}")
        if only_union:
            issues.append(
                f"presence_signal: union contains values not in allowed_values: {only_union}"
            )

    return True, issues


# ─────────────────────────────────────────────────────────────────────────
# Task B.1 — risk_weight на signal-полях
# ─────────────────────────────────────────────────────────────────────────

def check_risk_weights(data: dict) -> tuple[list[str], list[str], list[str]]:
    ext = data.get("extraction") or {}
    fields = ext.get("fields") or []
    signal_fields: list[str] = []
    missing_weight: list[str] = []
    invalid: list[str] = []

    for f in fields:
        if not isinstance(f, dict):
            continue
        if f.get("presentation") == "signal":
            name = f.get("name", "?")
            signal_fields.append(name)
            rw = f.get("risk_weight")
            if rw is None:
                missing_weight.append(name)
            elif rw not in VALID_WEIGHTS:
                invalid.append(f"{name}={rw!r}")

    return signal_fields, missing_weight, invalid


def _has_real_markdown_fence(text: str) -> bool:
    """
    True — если строка НАЧИНАЕТСЯ с ``` (реальный markdown fence).
    Строка 'Не оборачивай в markdown-блоки (без ```).' — НЕ fence.
    """
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────
# Task B.2 — Layer 2 prompt
# ─────────────────────────────────────────────────────────────────────────

def check_prompt(data: dict) -> tuple[list[str], list[str]]:
    ext = data.get("extraction") or {}
    prompt = ext.get("llm_prompt_extraction")
    if not isinstance(prompt, str) or not prompt.strip():
        return ["<llm_prompt_extraction absent>"], []

    missing = [b for b in REQUIRED_PROMPT_BLOCKS if b not in prompt]
    issues: list[str] = []

    # Порядок: <context_rules> перед <context>.
    i_cr = prompt.find("<context_rules>")
    i_c = prompt.find("<context>")
    if i_cr != -1 and i_c != -1 and i_cr > i_c:
        issues.append("order: <context_rules> must precede <context>")

    # output_expectations: 3-полевой JSON, без markdown fences.
    oe = _extract_block(prompt, "output_expectations")
    if oe is not None:
        if _has_real_markdown_fence(oe):        # ← было: "```" in oe
            issues.append("output_expectations: markdown fences present")
        for key in ('"value"', '"confidence"', '"location"'):
            if key not in oe:
                issues.append(f"output_expectations: missing {key} in example JSON")
        # грубая эвристика «обрезанных» JSON-примеров
        if "..." in oe and "confidence" not in oe:
            issues.append("output_expectations: truncated JSON example")

    return missing, issues


# ─────────────────────────────────────────────────────────────────────────
# RF — авто-детектируемые red-flags
# ─────────────────────────────────────────────────────────────────────────

def rf4_risk_words(prompt: str) -> list[str]:
    block = _extract_block(prompt, "edge_cases")
    if not block:
        return []
    return sorted({m.group(0).lower() for m in RISK_EVAL_RE.finditer(block)})


def rf7_dup_rules(prompt: str) -> list[str]:
    block = _extract_block(prompt, "context_rules")
    if not block:
        return []
    lines = [
        ln.strip().lstrip("-").strip()
        for ln in block.splitlines()
        if ln.strip().startswith("-")
    ]
    counter = Counter(lines)
    return [ln for ln, n in counter.items() if n > 1]


def rf8_mismatch(data: dict) -> bool:
    return data.get("severity") != data.get("severity_if_fail")


def rf9_contradiction(data: dict) -> bool:
    desc = data.get("description") or ""
    ext = data.get("extraction") or {}
    prompt = ext.get("llm_prompt_extraction") or ""
    if not desc or not prompt:
        return False
    return bool(RISK_IN_DESC_RE.search(desc)) and bool(
        RISK_FORBIDDEN_IN_ROLE_RE.search(prompt)
    )


def rf10_check(data: dict, prompt: str) -> tuple[bool, bool]:
    """
    RF10 применим, если у check'а есть поле с allowed_values, содержащее "no"
    (обычно `has_*`). Проблема — если в `<location_instructions>` нет правила
    о quote для `no`.
    """
    ext = data.get("extraction") or {}
    fields = ext.get("fields") or []
    has_no_field = any(
        isinstance(f, dict) and "no" in (f.get("allowed_values") or [])
        for f in fields
    )
    if not has_no_field:
        return False, False

    block = _extract_block(prompt, "location_instructions")
    if not block:
        return True, True
    return True, not bool(RF10_NO_QUOTE_RE.search(block))


# ─────────────────────────────────────────────────────────────────────────
# Per-file analysis
# ─────────────────────────────────────────────────────────────────────────

def analyse_file(path: Path) -> CheckReport:
    rep = CheckReport(path=str(path))
    try:
        data = load_yaml_first_doc(path)
    except Exception as e:
        rep.parse_error = f"{type(e).__name__}: {e}"
        return rep

    if not isinstance(data, dict):
        rep.parse_error = "root YAML node is not a mapping"
        return rep

    rep.check_id = str(data.get("id", ""))
    rep.group = str(data.get("group", ""))

    rep.struct_issues = check_structure(data)
    rep.has_presence_signal, rep.presence_signal_issues = check_presence_signal(data)
    (rep.signal_fields,
     rep.signal_fields_without_weight,
     rep.invalid_weights) = check_risk_weights(data)
    rep.prompt_missing_required, rep.prompt_issues = check_prompt(data)

    ext = data.get("extraction") or {}
    prompt = ext.get("llm_prompt_extraction") or ""
    rep.rf4_risk_words = rf4_risk_words(prompt)
    rep.rf7_dups = rf7_dup_rules(prompt)
    rep.rf8_mismatch = rf8_mismatch(data)
    rep.rf9_contradiction = rf9_contradiction(data)
    rep.rf10_applicable, rep.rf10_issue = rf10_check(data, prompt)

    # DEEP (v3)
    rep.placeholders = find_placeholders(prompt)
    rep.list_dups = find_list_dups(data)
    rep.context_rules_dups = find_context_rules_dups(prompt)
    rep.tag_order_ok = check_tag_order(prompt)
    rep.keyword_overlaps = find_keyword_overlaps(data)
    rep.typos = find_typos(prompt, data.get("description") or "")

    return rep


# ─────────────────────────────────────────────────────────────────────────
# Отчёт
# ─────────────────────────────────────────────────────────────────────────

SYMBOL = {"ok": "✅", "warn": "⚠️ ", "fail": "❌", "n/a": " · "}


def _short(s: str, width: int) -> str:
    return s if len(s) <= width else "…" + s[-(width - 1):]


def print_summary(reports: list[CheckReport], root: Path) -> None:
    print()
    print("═" * 100)
    print(f"  AUDIT GLOBAL CHECKS — предварительная оценка")
    print(f"  Root: {root}")
    print(f"  Checks: {len(reports)}")
    print("═" * 100)
    print()

    header = (
        f"{'FILE':<52} {'STRUCT':^8} {'PSIG':^8} {'RW':^8} "
        f"{'L2':^8} {'RF':^8} {'DEEP':^8} {'OVERALL':^10}"
    )
    print(header)
    print("─" * len(header))

    for r in reports:
        try:
            rel = str(Path(r.path).relative_to(root))
        except ValueError:
            rel = r.path
        name = _short(rel, 52)
        print(
            f"{name:<52} "
            f"{SYMBOL[r.grade_struct()]:^8} "
            f"{SYMBOL[r.grade_presence()]:^8} "
            f"{SYMBOL[r.grade_weights()]:^8} "
            f"{SYMBOL[r.grade_layer2()]:^8} "
            f"{SYMBOL[r.grade_rf()]:^8} "
            f"{SYMBOL[r.grade_deep()]:^8} "
            f"{SYMBOL[r.grade_overall()]:^10}"
        )

    print()
    # Сводка
    overall = Counter(r.grade_overall() for r in reports)
    print(
        f"  ИТОГО:  ✅ {overall.get('ok', 0):<3}  "
        f"⚠️  {overall.get('warn', 0):<3}  "
        f"❌ {overall.get('fail', 0):<3}"
    )
    print()
    print("  Легенда:")
    print("    STRUCT — Section 0 (структурные особенности global checks)")
    print("    PSIG   — presence_signal (Task A)")
    print("    RW     — risk_weight на signal-полях (Task B.1)")
    print("    L2     — Layer 2 custom prompt: <location_instructions>,")
    print("             <edge_cases>, <output_expectations>, <instructions>, …")
    print("    RF     — авто-detect RF4/RF7/RF8/RF9/RF10")
    print("    DEEP   — placeholder'ы, дубли списков, дубли context_rules,")
    print("             порядок тегов, опечатки (keywords overlap — info-only)")
    print()


def print_detail(reports: list[CheckReport], root: Path) -> None:
    for r in reports:
        try:
            rel = str(Path(r.path).relative_to(root))
        except ValueError:
            rel = r.path
        print("─" * 100)
        print(f"  {rel}")
        print(f"  check_id: {r.check_id}   group: {r.group}   "
              f"overall: {SYMBOL[r.grade_overall()]}")

        if r.parse_error:
            print(f"  ❌ PARSE ERROR: {r.parse_error}")
            print()
            continue

        def dump(label: str, items: list) -> None:
            if items:
                print(f"  {label}:")
                for x in items:
                    print(f"    - {x}")

        dump("STRUCT issues", r.struct_issues)

        if r.has_presence_signal:
            print(f"  presence_signal: ✅ present")
        else:
            print(f"  presence_signal: ❌ absent")
        dump("  presence_signal issues", r.presence_signal_issues)

        if r.signal_fields:
            print(f"  signal fields: {r.signal_fields}")
        dump("  signal fields without risk_weight", r.signal_fields_without_weight)
        dump("  invalid risk_weight values", r.invalid_weights)

        dump("Layer 2 prompt — missing blocks", r.prompt_missing_required)
        dump("Layer 2 prompt — issues", r.prompt_issues)

        rf_hits: list[str] = []
        if r.rf4_risk_words:
            rf_hits.append(f"RF4 (risk words in edge_cases): {r.rf4_risk_words}")
        if r.rf7_dups:
            rf_hits.append(f"RF7 (dup bullets in context_rules): {r.rf7_dups}")
        if r.rf8_mismatch:
            rf_hits.append("RF8 (severity_if_fail != severity) — [CONSIDER] as designed")
        if r.rf9_contradiction:
            rf_hits.append("RF9 (description обещает оценку риска, role запрещает) — [CONSIDER]")
        if r.rf10_applicable and r.rf10_issue:
            rf_hits.append("RF10 (location_instructions не описывает quote для `no`)")
        if rf_hits:
            print("  RF flags:")
            for x in rf_hits:
                print(f"    ⚠️  {x}")

        deep_hits: list[str] = []
        if r.placeholders:
            deep_hits.append(f"DEEP-placeholders: {r.placeholders}")
        if r.list_dups:
            deep_hits.append(f"DEEP-list_dups: {r.list_dups}")
        if r.context_rules_dups:
            deep_hits.append(f"DEEP-context_rules_dups: {r.context_rules_dups}")
        if not r.tag_order_ok:
            deep_hits.append("DEEP-tag_order: <context_rules> must precede <context>")
        if r.keyword_overlaps:
            deep_hits.append(f"DEEP-keyword_overlaps (info): {r.keyword_overlaps}")
        if r.typos:
            deep_hits.append(f"DEEP-typos: {r.typos}")
        if deep_hits:
            print("  DEEP flags:")
            for x in deep_hits:
                print(f"    ⚠️  {x}")
        print()


# ─────────────────────────────────────────────────────────────────────────
# Экспорт
# ─────────────────────────────────────────────────────────────────────────

def to_jsonable(r: CheckReport) -> dict:
    d = asdict(r)
    d["grades"] = {
        "struct": r.grade_struct(),
        "presence_signal": r.grade_presence(),
        "risk_weight": r.grade_weights(),
        "layer2": r.grade_layer2(),
        "rf": r.grade_rf(),
        "deep": r.grade_deep(),
        "overall": r.grade_overall(),
    }
    return d


def write_json(reports: list[CheckReport], path: Path) -> None:
    payload = [to_jsonable(r) for r in reports]
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"  → JSON: {path}")


def write_csv(reports: list[CheckReport], path: Path, root: Path) -> None:
    fieldnames = [
        "path", "check_id", "group",
        "grade_struct", "grade_presence_signal", "grade_risk_weight",
        "grade_layer2", "grade_rf", "grade_deep", "grade_overall",
        "n_struct_issues",
        "has_presence_signal", "n_presence_signal_issues",
        "n_signal_fields", "n_signal_fields_without_weight",
        "n_prompt_missing", "n_prompt_issues",
        "rf4", "rf7", "rf8", "rf9", "rf10",
        "n_placeholders", "n_list_dups", "n_context_rules_dups",
        "tag_order_ok", "n_keyword_overlaps", "n_typos",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in reports:
            try:
                rel = str(Path(r.path).relative_to(root))
            except ValueError:
                rel = r.path
            w.writerow({
                "path": rel,
                "check_id": r.check_id,
                "group": r.group,
                "grade_struct": r.grade_struct(),
                "grade_presence_signal": r.grade_presence(),
                "grade_risk_weight": r.grade_weights(),
                "grade_layer2": r.grade_layer2(),
                "grade_rf": r.grade_rf(),
                "grade_deep": r.grade_deep(),
                "grade_overall": r.grade_overall(),
                "n_struct_issues": len(r.struct_issues),
                "has_presence_signal": int(r.has_presence_signal),
                "n_presence_signal_issues": len(r.presence_signal_issues),
                "n_signal_fields": len(r.signal_fields),
                "n_signal_fields_without_weight": len(r.signal_fields_without_weight),
                "n_prompt_missing": len(r.prompt_missing_required),
                "n_prompt_issues": len(r.prompt_issues),
                "rf4": int(bool(r.rf4_risk_words)),
                "rf7": int(bool(r.rf7_dups)),
                "rf8": int(r.rf8_mismatch),
                "rf9": int(r.rf9_contradiction),
                "rf10": int(r.rf10_issue),
                "n_placeholders": len(r.placeholders),
                "n_list_dups": len(r.list_dups),
                "n_context_rules_dups": len(r.context_rules_dups),
                "tag_order_ok": int(r.tag_order_ok),
                "n_keyword_overlaps": len(r.keyword_overlaps),
                "n_typos": len(r.typos),
            })
    print(f"  → CSV:  {path}")


# ─────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────

def collect(root: Path, only: str | None) -> tuple[list[Path], list[Path]]:
    """Возвращает (candidates, non_field_extraction)."""
    candidates: list[Path] = []
    others: list[Path] = []

    for p in sorted(root.rglob("*.yaml")):
        if not p.is_file():
            continue
        if p.name in ETALON_FILES:
            continue
        if only and only not in str(p):
            continue
        try:
            data = load_yaml_first_doc(p)
        except Exception:
            # всё равно добавим, чтобы отчёт показал parse_error
            candidates.append(p)
            continue
        if isinstance(data, dict) and _is_field_extraction(data):
            candidates.append(p)
        else:
            others.append(p)

    return candidates, others


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Предварительная оценка GLOBAL checks (read-only)."
    )
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT,
                    help=f"Корень global_checks (default: {DEFAULT_ROOT})")
    ap.add_argument("--only", default=None,
                    help="Фильтр по подстроке пути (напр. 'liability/')")
    ap.add_argument("--json", type=Path, default=None,
                    help="Куда сохранить JSON-отчёт")
    ap.add_argument("--csv", type=Path, default=None,
                    help="Куда сохранить CSV-отчёт")
    ap.add_argument("--summary-only", action="store_true",
                    help="Только сводная таблица, без per-file деталей")
    ap.add_argument("--verbose", action="store_true",
                    help="Детализированный вывод по каждому check'у")
    args = ap.parse_args(argv)

    root: Path = args.root
    if not root.exists():
        print(f"ERROR: root does not exist: {root}", file=sys.stderr)
        return 2

    candidates, others = collect(root, args.only)

    print(f"  Root:        {root}")
    print(f"  Candidates:  {len(candidates)}")
    print(f"  Skipped:     {len(others)} (не field_extraction / эталон)")
    if others and args.verbose:
        print("  Skipped files:")
        for p in others:
            print(f"    · {p.relative_to(root) if root in p.parents else p}")

    reports = [analyse_file(p) for p in candidates]

    print_summary(reports, root)

    if args.verbose or (not args.summary_only and len(reports) <= 20):
        print_detail(reports, root)

    if args.json:
        write_json(reports, args.json)
    if args.csv:
        write_csv(reports, args.csv, root)

    # exit code: 0 если нет fail, 1 если есть
    if any(r.grade_overall() == "fail" for r in reports):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())