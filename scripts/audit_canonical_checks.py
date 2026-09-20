#!/usr/bin/env python3
"""
Канонический валидатор check-ов в playbooks/document_types/.

READ-ONLY. Ничего не меняет.

Проверяет 10 категорий:
  1. STRUCTURE-SANITY       — extraction/retrieval/evidence/store_payload на top-level
  2. EXTRACTION-NESTING     — extraction: не пусто, дети на 6+ пробелах
  3. CONFIG-VALIDITY        — UT / CF / retrieval_profile валидны
  4. FIELDS-REQUIRED        — required: true у всех полей
  5. FIELDS-UNIQUE          — имена полей уникальны
  6. FIELDS-ATTRS           — name и type присутствуют
  7. NAMING-CONTRACT        — singleton vs paired
  8. DISPLAY-PRIORITY       — display_priority уникальны в пределах check-а
  9. PROMPT-STRUCTURE       — <task>, <rules>, [ФОРМАТ ОТВЕТА], canonical JSON
 10. LEGAL-REFS             — отменённые/неверные нормы, fake citations

Использование:
    python scripts/audit_canonical_checks.py
    python scripts/audit_canonical_checks.py --roots playbooks/document_types
    python scripts/audit_canonical_checks.py --output /tmp/canonical_report.txt
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, "src")
from services.structure.legal_unit_models import (  # noqa: E402
    LegalUnitType,
    normalize_clause_function_label,
)

VALID_UT = {m.value for m in LegalUnitType}
VALID_PROFILES_FILE = Path("src/engine/playbook/retrieval_profiles.py")

# ──────────────────────────────── DATA ────────────────────────────────


@dataclass
class Finding:
    severity: str  # "ERROR" | "WARNING" | "INFO"
    category: str
    file: str
    check_id: str
    message: str

    def __str__(self) -> str:
        return f"[{self.severity:7}] {self.category:25} {self.file}::{self.check_id}\n            {self.message}"


def load_valid_profiles() -> set[str]:
    """Извлекает profile_id из retrieval_profiles.py."""
    if not VALID_PROFILES_FILE.exists():
        return set()
    text = VALID_PROFILES_FILE.read_text(encoding="utf-8")
    return set(re.findall(r'profile_id\s*=\s*"([^"]+)"', text))


# ──────────────────────────────── VALIDATORS ────────────────────────────────


def check_structure(c: dict, fname: str) -> list[Finding]:
    """STRUCTURE-SANITY: extraction/retrieval/evidence/store_payload не под llm."""
    out: list[Finding] = []
    llm = c.get("llm") or {}
    bad = [k for k in ("extraction", "retrieval", "evidence", "store_payload") if k in llm]
    if bad:
        out.append(Finding(
            "ERROR", "STRUCTURE-SANITY", fname, c.get("id", "?"),
            f"{bad} находятся под llm — движок их не читает",
        ))
    return out


def check_extraction_nesting(c: dict, fname: str) -> list[Finding]:
    """EXTRACTION-NESTING: extraction: не пусто, дети на 6+ пробелах."""
    out: list[Finding] = []
    ext = c.get("extraction")
    if ext is None:
        # Проверим, есть ли top-level дети
        children = [k for k in ("enabled", "mode", "fields", "llm_prompt_extraction",
                                "llm_max_tokens", "compact_output") if k in c]
        if children:
            out.append(Finding(
                "ERROR", "EXTRACTION-NESTING", fname, c.get("id", "?"),
                f"extraction: пусто, дети на top-level: {children}",
            ))
        else:
            out.append(Finding(
                "WARNING", "EXTRACTION-NESTING", fname, c.get("id", "?"),
                "extraction: отсутствует (чек невидим в DD Grid)",
            ))
        return out
    if not isinstance(ext, dict):
        out.append(Finding(
            "ERROR", "EXTRACTION-NESTING", fname, c.get("id", "?"),
            f"extraction имеет тип {type(ext).__name__}, ожидался dict",
        ))
    return out


def check_configs(c: dict, fname: str) -> list[Finding]:
    """CONFIG-VALIDITY: UT / CF / retrieval_profile."""
    out: list[Finding] = []
    r = c.get("retrieval") or {}
    cid = c.get("id", "?")

    # UT
    for ut in r.get("preferred_unit_types") or []:
        if ut not in VALID_UT:
            out.append(Finding(
                "ERROR", "CONFIG-VALIDITY", fname, cid,
                f"невалидный preferred_unit_types: '{ut}' (нет в LegalUnitType)",
            ))
    for ut in r.get("excluded_unit_types") or []:
        if ut not in VALID_UT:
            out.append(Finding(
                "ERROR", "CONFIG-VALIDITY", fname, cid,
                f"невалидный excluded_unit_types: '{ut}'",
            ))

    # CF
    for cf in r.get("preferred_clause_functions") or []:
        if normalize_clause_function_label(cf) is None:
            out.append(Finding(
                "ERROR", "CONFIG-VALIDITY", fname, cid,
                f"невалидный preferred_clause_functions: '{cf}' (нет canonical + нет алиаса)",
            ))

    # EnrichmentHints CF
    eh = r.get("enrichment_hints") or {}
    for cf in eh.get("preferred_clause_functions") or []:
        if normalize_clause_function_label(cf) is None:
            out.append(Finding(
                "ERROR", "CONFIG-VALIDITY", fname, cid,
                f"невалидный enrichment_hints.preferred_clause_functions: '{cf}'",
            ))

    # retrieval_profile
    prof = r.get("retrieval_profile")
    if prof:
        valid_profiles = load_valid_profiles()
        if valid_profiles and prof not in valid_profiles:
            out.append(Finding(
                "WARNING", "CONFIG-VALIDITY", fname, cid,
                f"retrieval_profile '{prof}' не найден в retrieval_profiles.py",
            ))

    return out


def check_fields_required(c: dict, fname: str) -> list[Finding]:
    """FIELDS-REQUIRED: все поля required: true."""
    out: list[Finding] = []
    ext = c.get("extraction")
    if not isinstance(ext, dict):
        return out
    cid = c.get("id", "?")
    for f in ext.get("fields") or []:
        if not isinstance(f, dict):
            continue
        name = f.get("name", "?")
        if f.get("required") is not True:
            out.append(Finding(
                "WARNING", "FIELDS-REQUIRED", fname, cid,
                f"поле '{name}': required = {f.get('required')!r} (ожидалось True)",
            ))
    return out


def check_fields_unique(c: dict, fname: str) -> list[Finding]:
    """FIELDS-UNIQUE: имена полей не дублируются."""
    out: list[Finding] = []
    ext = c.get("extraction")
    if not isinstance(ext, dict):
        return out
    cid = c.get("id", "?")
    seen: dict[str, int] = {}
    for f in ext.get("fields") or []:
        if not isinstance(f, dict):
            continue
        name = f.get("name")
        if name:
            seen[name] = seen.get(name, 0) + 1
    for name, n in seen.items():
        if n > 1:
            out.append(Finding(
                "ERROR", "FIELDS-UNIQUE", fname, cid,
                f"дубликат имени поля: '{name}' встречается {n} раз",
            ))
    return out


def check_fields_attrs(c: dict, fname: str) -> list[Finding]:
    """FIELDS-ATTRS: у каждого поля есть name и type."""
    out: list[Finding] = []
    ext = c.get("extraction")
    if not isinstance(ext, dict):
        return out
    cid = c.get("id", "?")
    for i, f in enumerate(ext.get("fields") or []):
        if not isinstance(f, dict):
            out.append(Finding(
                "ERROR", "FIELDS-ATTRS", fname, cid,
                f"fields[{i}] не dict, а {type(f).__name__}",
            ))
            continue
        if not f.get("name"):
            out.append(Finding(
                "ERROR", "FIELDS-ATTRS", fname, cid,
                f"fields[{i}]: отсутствует 'name'",
            ))
        if not f.get("type"):
            out.append(Finding(
                "WARNING", "FIELDS-ATTRS", fname, cid,
                f"поле '{f.get('name', '?')}': отсутствует 'type'",
            ))
    return out


def check_naming_contract(c: dict, fname: str) -> list[Finding]:
    """NAMING-CONTRACT: singleton не совпадает с префиксом paired-полей."""
    out: list[Finding] = []
    ext = c.get("extraction")
    if not isinstance(ext, dict):
        return out
    cid = c.get("id", "?")
    names = {
        f.get("name") for f in (ext.get("fields") or [])
        if isinstance(f, dict) and f.get("name")
    }
    RESERVED = ("_status", "_details", "_value")
    for name in names:
        # Это singleton-имя? Проверим, нет ли одноимённого с суффиксом
        for suffix in RESERVED:
            if f"{name}{suffix}" in names:
                out.append(Finding(
                    "ERROR", "NAMING-CONTRACT", fname, cid,
                    f"singleton '{name}' конфликтует с '{name}{suffix}' "
                    f"(рекомендуется '{name}_code')",
                ))
                break
    return out


def check_display_priority(c: dict, fname: str) -> list[Finding]:
    """DISPLAY-PRIORITY: уникальны среди display_in_grid=true полей."""
    out: list[Finding] = []
    ext = c.get("extraction")
    if not isinstance(ext, dict):
        return out
    cid = c.get("id", "?")
    seen: dict[int, list[str]] = {}
    for f in ext.get("fields") or []:
        if not isinstance(f, dict):
            continue
        if f.get("display_in_grid") is True:
            prio = f.get("display_priority")
            if isinstance(prio, int):
                seen.setdefault(prio, []).append(f.get("name", "?"))
    for prio, names in seen.items():
        if len(names) > 1:
            out.append(Finding(
                "WARNING", "DISPLAY-PRIORITY", fname, cid,
                f"display_priority={prio} у нескольких полей: {names}",
            ))
    return out


def check_prompt_structure(c: dict, fname: str) -> list[Finding]:
    """PROMPT-STRUCTURE: task/rules/format/JSON/few-shot/counters."""
    out: list[Finding] = []
    ext = c.get("extraction")
    if not isinstance(ext, dict):
        return out
    cid = c.get("id", "?")
    pt = ext.get("llm_prompt_extraction")
    if not isinstance(pt, str) or not pt.strip():
        out.append(Finding(
            "INFO", "PROMPT-STRUCTURE", fname, cid,
            "llm_prompt_extraction пусто или отсутствует",
        ))
        return out

    # canonical JSON
    if "json.loads" not in pt:
        out.append(Finding(
            "WARNING", "PROMPT-STRUCTURE", fname, cid,
            "в промпте нет упоминания 'json.loads' (canonical JSON contract)",
        ))

    # <task>/<rules>
    for tag in ("<task>", "<rules>", "</task>", "</rules>"):
        if tag not in pt:
            out.append(Finding(
                "INFO", "PROMPT-STRUCTURE", fname, cid,
                f"в промпте нет '{tag}'",
            ))

    # [ФОРМАТ ОТВЕТА]
    if "[ФОРМАТ ОТВЕТА]" not in pt and "ФОРМАТ ОТВЕТА" not in pt:
        out.append(Finding(
            "INFO", "PROMPT-STRUCTURE", fname, cid,
            "в промпте нет '[ФОРМАТ ОТВЕТА]'",
        ))

    # COUNTER-CONSISTENCY: task count vs field count
    fields_count = len([
        f for f in (ext.get("fields") or [])
        if isinstance(f, dict) and f.get("name")
    ])
    # Ищем в промпте "N полей" или "N ключей"
    m_fields = re.search(r"следующие\s+(\d+)\s+полей", pt)
    m_keys = re.search(r"всего\s+(\d+)\s+ключей", pt)
    if m_fields:
        declared_n = int(m_fields.group(1))
        if declared_n != fields_count:
            out.append(Finding(
                "WARNING", "PROMPT-STRUCTURE", fname, cid,
                f"<task>: 'следующие {declared_n} полей', а в extraction.fields {fields_count}",
            ))
    if m_keys:
        declared_keys = int(m_keys.group(1))
        if declared_keys != fields_count + 1:
            out.append(Finding(
                "WARNING", "PROMPT-STRUCTURE", fname, cid,
                f"'всего {declared_keys} ключей', а полей+evidence = {fields_count + 1}",
            ))

    return out


# ─── LEGAL-REFS ───

LEGAL_BLACKLIST: list[tuple[str, str]] = [
    (r"ст\.?\s*829\s*ГК", "ст. 829 ГК РФ отменена с 01.06.2014 (замена: ст. 388–390)"),
    (r"ст\.?\s*1066\s*ГК", "ст. 1066 ГК РФ — про возмещение вреда здоровью (не о качестве)"),
    (r"ст\.?\s*894\s*ГК", "ст. 894 ГК РФ — про опасные свойства вещи (не универсальная норма)"),
    (r"ключев(ая|ой)\s+ставк[а-я]*\s+ЦБ\s+РФ\s+на\s+день\s+возврата",
     "устаревшая формулировка: 'ключевая ставка на день возврата'"),
    (r"ключев(ая|ой)\s+ставк[а-я]*\s+на\s+день\s+возврата",
     "устаревшая формулировка: 'ключевая ставка на день возврата'"),
]

FAKE_CITATION_RE = re.compile(
    r'(Письмо|Письма|Письмом)\s+'
    r'(Минфина|ФНС|Федеральной налоговой службы|Минэкономразвития|Банка России)'
    r'[^\n]{0,200}?№\s*[0-9]{2}-[0-9]{2}-[0-9]{2}/[0-9]+',
)


def check_legal_refs(c: dict, fname: str) -> list[Finding]:
    out: list[Finding] = []
    ext = c.get("extraction")
    if not isinstance(ext, dict):
        return out
    cid = c.get("id", "?")
    pt = ext.get("llm_prompt_extraction") or ""
    # Также проверим prompt_template
    pt_full = pt
    llm = c.get("llm") or {}
    if isinstance(llm.get("prompt_template"), str):
        pt_full = pt_full + "\n" + llm["prompt_template"]

    for pattern, reason in LEGAL_BLACKLIST:
        if re.search(pattern, pt_full, re.IGNORECASE):
            out.append(Finding(
                "WARNING", "LEGAL-REFS", fname, cid,
                f"подозрительная норма: {reason}",
            ))

    for m in FAKE_CITATION_RE.finditer(pt_full):
        out.append(Finding(
            "WARNING", "LEGAL-REFS", fname, cid,
            f"возможная fake-citation: '{m.group(0)[:80]}'",
        ))

    return out


# ──────────────────────────────── MAIN ────────────────────────────────


ALL_CHECKS = [
    check_structure,
    check_extraction_nesting,
    check_configs,
    check_fields_required,
    check_fields_unique,
    check_fields_attrs,
    check_naming_contract,
    check_display_priority,
    check_prompt_structure,
    check_legal_refs,
]


def process_file(path: Path) -> list[Finding]:
    try:
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        return [Finding("ERROR", "YAML-PARSE", str(path), "?", f"ошибка парсинга: {e}")]

    findings: list[Finding] = []
    for c in (d or {}).get("checks_v8") or []:
        if not isinstance(c, dict):
            continue
        for validator in ALL_CHECKS:
            try:
                findings.extend(validator(c, path.name))
            except Exception as e:
                findings.append(Finding(
                    "ERROR", "VALIDATOR-CRASH", path.name, c.get("id", "?"),
                    f"валидатор {validator.__name__} упал: {e}",
                ))
    return findings


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--roots", nargs="+", default=["playbooks/document_types"])
    ap.add_argument("--output", default="scripts/canonical_audit_report.txt")
    args = ap.parse_args()

    all_findings: list[Finding] = []
    n_files = 0
    n_checks = 0

    for root in args.roots:
        root_p = Path(root)
        if not root_p.exists():
            print(f"⚠️  нет папки: {root}")
            continue
        for p in sorted(root_p.rglob("*.yaml")):
            n_files += 1
            try:
                d = yaml.safe_load(p.read_text(encoding="utf-8"))
                n_checks += len((d or {}).get("checks_v8") or [])
            except Exception:
                pass
            all_findings.extend(process_file(p))

    by_severity: dict[str, list[Finding]] = {"ERROR": [], "WARNING": [], "INFO": []}
    for f in all_findings:
        by_severity.setdefault(f.severity, []).append(f)

    # Вывод в консоль
    print(f"Файлов: {n_files}")
    print(f"Check-ов: {n_checks}")
    print(f"ERRORS: {len(by_severity['ERROR'])}")
    print(f"WARNINGS: {len(by_severity['WARNING'])}")
    print(f"INFO: {len(by_severity['INFO'])}")
    print()

    for sev in ("ERROR", "WARNING", "INFO"):
        items = by_severity.get(sev, [])
        if not items:
            continue
        print("=" * 100)
        print(f"{sev}: {len(items)}")
        print("=" * 100)
        for f in items:
            print(f)
        print()

    # Запись в файл
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write(f"Файлов: {n_files}\nCheck-ов: {n_checks}\n")
        fh.write(f"ERRORS: {len(by_severity['ERROR'])}\n")
        fh.write(f"WARNINGS: {len(by_severity['WARNING'])}\n")
        fh.write(f"INFO: {len(by_severity['INFO'])}\n\n")
        for sev in ("ERROR", "WARNING", "INFO"):
            items = by_severity.get(sev, [])
            if not items:
                continue
            fh.write("=" * 100 + f"\n{sev}: {len(items)}\n" + "=" * 100 + "\n")
            for f in items:
                fh.write(str(f) + "\n")
            fh.write("\n")
    print(f"📄 Отчёт сохранён: {out_path}")


if __name__ == "__main__":
    main()

    