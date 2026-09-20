#!/usr/bin/env python3
"""
Batch: переименование singleton-полей, конфликтующих с paired-полями
(DD Grid naming contract). Источник — scripts/dd_grid_audit_ERRORS.txt.

Переименование выполняется во всех 3 местах:
  • extraction.fields[].name
  • llm.prompt_template (JSON-примеры, [ФОРМАТ ОТВЕТА])
  • extraction.llm_prompt_extraction (<task>, <rules>, [ФОРМАТ ОТВЕТА])

Word-boundary regex гарантирует, что "risk_allocation" не заменится
внутри "risk_allocation_status".

Usage:
    python scripts/migrate_dd_grid_naming_fix.py            # dry-run
    python scripts/migrate_dd_grid_naming_fix.py --apply    # apply
"""
from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

BASE = Path("playbooks/document_types")

# (relative_path, old, new)
RENAMES: list[tuple[str, str, str]] = [
    ("group_2_use/contract_2.1_lease.yaml",                 "risk_allocation",       "risk_allocation_code"),
    ("group_7_ip/contract_7.2_license.yaml",                "license_type",          "license_type_code"),
    ("group_7_ip/contract_7.4_nda.yaml",                    "definition_type",       "definition_type_code"),
    ("group_7_ip/contract_7.4_nda.yaml",                    "dispute_method",        "dispute_method_code"),
    ("group_7_ip/contract_7.4_nda.yaml",                    "nda_type",              "nda_type_code"),
    ("group_9_special/contract_9.2_collective_agreement.yaml", "reorganization_action", "reorganization_action_code"),
    ("group_9_special/contract_9.2_collective_agreement.yaml", "sout_status",           "sout_status_code"),
]


def rename_word(text: str, old: str, new: str) -> tuple[str, int]:
    """
    Заменяет old на new по границам слова.
    Благодаря \\b (в Python \\w включает _) 'risk_allocation' НЕ заменится
    внутри 'risk_allocation_status'.
    """
    pattern = rf"\b{re.escape(old)}\b"
    matches = re.findall(pattern, text)
    return re.sub(pattern, new, text), len(matches)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    by_file: dict[str, list[tuple[str, str]]] = {}
    for fname, old, new in RENAMES:
        by_file.setdefault(fname, []).append((old, new))

    total_renames = 0
    total_files = 0

    for fname, mappings in by_file.items():
        path = BASE / fname
        if not path.exists():
            print(f"❌ NOT FOUND: {path}")
            continue

        text = path.read_text(encoding="utf-8")
        original = text
        print(f"\n📄 {path}")

        for old, new in mappings:
            text, count = rename_word(text, old, new)
            if count == 0:
                print(f"   ⚠️  '{old}' → '{new}': не найдено")
            else:
                print(f"   ✅ '{old}' → '{new}': {count} вхождений")
                total_renames += count

        if text != original:
            total_files += 1
            if args.apply:
                backup = path.with_suffix(path.suffix + ".bak_naming_fix")
                shutil.copy(path, backup)
                path.write_text(text, encoding="utf-8")
                print(f"   💾 записано; backup: {backup.name}")
            else:
                print("   [dry-run]")

    print(f"\n{'=' * 60}")
    if args.apply:
        print(f"✅ APPLIED: {total_renames} переименований в {total_files} файлах")
    else:
        print(f"🔵 DRY-RUN: {total_renames} переименований в {total_files} файлах")
        print("   Запусти с --apply чтобы применить")


if __name__ == "__main__":
    main()

    