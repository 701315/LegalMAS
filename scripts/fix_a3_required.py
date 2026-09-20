#!/usr/bin/env python3
"""
Fix A3: required: false → true для signal-полей.

Категории:
  • SAFE   — presentation=signal, allowed_values содержит "not_defined"
  • RISKY  — presentation=signal, allowed_values БЕЗ "not_defined"
             (обрабатываются только с флагом --fix-risky)

Не трогаются:
  • presentation=fact — required: false допустимо
  • presentation=list — массивы
  • presentation=diagnostic — служебные

READ-WRITE. Dry-run по умолчанию, --apply для применения.

Usage:
    python scripts/fix_a3_required.py                    # dry-run, только SAFE
    python scripts/fix_a3_required.py --fix-risky        # dry-run, SAFE + RISKY
    python scripts/fix_a3_required.py --apply            # apply SAFE
    python scripts/fix_a3_required.py --apply --fix-risky # apply SAFE + RISKY
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

import yaml

GROUPS = ["group_1_ownership", "group_2_use", "group_3_works",
          "group_4_services", "group_5_financial"]
BASE = Path("playbooks/document_types")


def find_check_bounds(text: str, check_id: str) -> tuple[int, int] | None:
    m = re.search(rf"^  - id: {re.escape(check_id)}\s*$", text, re.MULTILINE)
    if not m:
        return None
    start = m.start()
    m2 = re.search(r"^  - id: ", text[m.end():], re.MULTILINE)
    end = m.end() + m2.start() if m2 else len(text)
    return start, end


def flip_required_in_field(block: str, field_name: str) -> tuple[str, bool]:
    """
    В блоке check-а находит определение поля с данным name
    и меняет required: false → required: true внутри него.
    Возвращает (new_block, changed).
    """
    # Найти строку `- name: "FIELD"` с индентацией (обычно 8 пробелов)
    pat = re.compile(
        rf'(^[ \t]*- name:\s*["\']?{re.escape(field_name)}["\']?\s*$\n)',
        re.MULTILINE,
    )
    m = pat.search(block)
    if not m:
        return block, False

    field_start = m.start()
    # Найти конец блока поля: следующий `- name:` с такой же индентацией
    # или конец check-а
    indent = re.match(r"[ \t]*", m.group(0)).group(0)
    rest = block[m.end():]
    end_pat = re.compile(rf"^{re.escape(indent)}- name:", re.MULTILINE)
    end_m = end_pat.search(rest)
    field_end = m.end() + (end_m.start() if end_m else len(rest))
    field_block = block[field_start:field_end]

    # Проверить, что поле именно signal и required: false
    if not re.search(r'^\s*presentation:\s*["\']?signal["\']?\s*$', field_block, re.MULTILINE):
        return block, False
    if not re.search(r'^\s*required:\s*false\s*(?:#.*)?$', field_block, re.MULTILINE):
        return block, False

    # Флипнуть required
    new_field_block = re.sub(
        r'^(\s*required:\s*)false(\s*(?:#.*)?)$',
        r'\1true\2',
        field_block,
        count=1,
        flags=re.MULTILINE,
    )
    if new_field_block == field_block:
        return block, False
    return block[:field_start] + new_field_block + block[field_end:], True


def collect_safe_fields(fix_risky: bool) -> dict[tuple[str, str], list[str]]:
    """
    Возвращает {(rel_path, check_id): [field_name, ...]}.
    """
    targets: dict[tuple[str, str], list[str]] = {}
    for g in GROUPS:
        root = BASE / g
        if not root.exists():
            continue
        for p in sorted(root.rglob("*.yaml")):
            try:
                d = yaml.safe_load(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            rel = str(p.relative_to(BASE))
            for c in (d or {}).get("checks_v8") or []:
                ext = c.get("extraction") or {}
                cid = c.get("id", "?")
                for f in ext.get("fields") or []:
                    if not isinstance(f, dict):
                        continue
                    if f.get("presentation") != "signal":
                        continue
                    if f.get("required") is not False:
                        continue
                    allowed = f.get("allowed_values") or []
                    has_nd = "not_defined" in allowed
                    if has_nd or fix_risky:
                        targets.setdefault((rel, cid), []).append(f["name"])
    return targets


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--fix-risky", action="store_true",
                    help="также фиксить 10 RISKY полей")
    args = ap.parse_args()

    targets = collect_safe_fields(fix_risky=args.fix_risky)
    n_checks = len(targets)
    n_fields = sum(len(v) for v in targets.values())
    mode = "SAFE + RISKY" if args.fix_risky else "SAFE only"
    print(f"Режим: {mode}")
    print(f"Check-ов: {n_checks}, полей: {n_fields}")
    print()

    by_file: dict[Path, list[tuple[str, list[str]]]] = {}
    for (rel, cid), fields in targets.items():
        p = BASE / rel
        by_file.setdefault(p, []).append((cid, fields))

    total_fixed = 0
    warnings = 0
    changes: dict[Path, str] = {}

    for p, items in sorted(by_file.items()):
        raw = p.read_text(encoding="utf-8")
        original = raw
        file_fixed = 0

        for cid, fields in items:
            bounds = find_check_bounds(raw, cid)
            if not bounds:
                print(f"   ⚠️  {p.name}::{cid}: check не найден")
                warnings += 1
                continue
            start, end = bounds
            block = raw[start:end]
            for fname in fields:
                block, changed = flip_required_in_field(block, fname)
                if changed:
                    file_fixed += 1
                else:
                    print(f"   ⚠️  {p.name}::{cid}::{fname}: не удалось флипнуть")
                    warnings += 1
            raw = raw[:start] + block + raw[end:]

        if raw != original:
            # Pre-flight: YAML парсится
            try:
                d = yaml.safe_load(raw)
            except yaml.YAMLError as e:
                print(f"   ❌ {p.name}: YAML не парсится: {e}")
                warnings += 1
                continue
            # Проверка: число checks не изменилось
            orig_d = yaml.safe_load(original)
            orig_n = len(orig_d.get("checks_v8") or [])
            new_n = len(d.get("checks_v8") or [])
            if new_n != orig_n:
                print(f"   ❌ {p.name}: число checks изменилось {orig_n} → {new_n}")
                warnings += 1
                continue
            changes[p] = raw
            total_fixed += file_fixed
            print(f"   ✅ {p.name}: {file_fixed} полей")

    print(f"\n{'='*80}")
    if args.apply:
        for p, text in changes.items():
            backup = p.with_suffix(p.suffix + ".bak_fix_a3")
            if not backup.exists():
                shutil.copy(p, backup)
            p.write_text(text, encoding="utf-8")
        print(f"✅ APPLIED: {total_fixed} полей в {len(changes)} файлах, {warnings} warnings")
    else:
        print(f"🔵 DRY-RUN: {total_fixed} полей в {len(changes)} файлах, {warnings} warnings")
        print("   Если warnings = 0 — запусти с --apply")


if __name__ == "__main__":
    main()
    