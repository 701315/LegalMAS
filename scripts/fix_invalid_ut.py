#!/usr/bin/env python3
"""
Фикс 3 невалидных preferred_unit_types.

Невалидные значения (тихо отбрасываются движком):
  • remedy     — не в LegalUnitType, заменить на liability_provision
  • procedure  — не в LegalUnitType, заменить на payment_term / obligation

Замена:
  contract_1.2_retail_sale::prepayment_and_refund_cluster
      procedure → payment_term
  contract_1.2_retail_sale::late_payment_consequences_cluster
      remedy → liability_provision
  contract_1.12_accord::creditor_refusal_and_default_remedy_check
      remedy → liability_provision

Usage:
    python scripts/fix_invalid_ut.py            # dry-run
    python scripts/fix_invalid_ut.py --apply    # apply
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import yaml

sys.path.insert(0, "src")
from services.structure.legal_unit_models import LegalUnitType  # noqa: E402

VALID_UT = {m.value for m in LegalUnitType}

TARGETS = [
    # (relative_path, check_id, invalid, replacement)
    ("group_1_ownership/contract_1.2_retail_sale.yaml",
     "prepayment_and_refund_cluster", "procedure", "payment_term"),
    ("group_1_ownership/contract_1.2_retail_sale.yaml",
     "late_payment_consequences_cluster", "remedy", "liability_provision"),
    ("group_1_ownership/contract_1.12_accord.yaml",
     "creditor_refusal_and_default_remedy_check", "remedy", "liability_provision"),
]

BASE = Path("playbooks/document_types")


def process_file(path: Path, replacements: list[tuple[str, str, str]], apply: bool) -> int:
    """Возвращает число изменений."""
    text = path.read_text(encoding="utf-8")

    # Найти блоки по check_id и заменить значения внутри preferred_unit_types
    # Работаем построчно: ищем строку `- name: "<check_id>"`, потом идём до `retrieval:` -> `preferred_unit_types:`
    # и меняем YAML-строки с `- invalid` → `- replacement`
    # Проще: заменить точечно через regex внутри блока check-а.

    import re
    changes = 0
    for check_id, invalid, replacement in replacements:
        # Границы check-а
        m = re.search(rf"^(\s*)-\s+id:\s*{re.escape(check_id)}\s*$", text, re.MULTILINE)
        if not m:
            print(f"   ⚠️  {path.name}::{check_id} — check не найден")
            continue
        indent = m.group(1)
        start = m.start()
        # Конец — следующий `  - id:` или конец файла
        nxt = re.search(rf"^{indent}-\s+id:\s*\S+", text[m.end():], re.MULTILINE)
        end = m.end() + nxt.start() if nxt else len(text)

        block = text[start:end]

        # Ищем в блоке: `- invalid` внутри preferred_unit_types
        # Паттерн: `- <invalid>` на отдельной строке
        pat = re.compile(rf"^(\s*-\s*){re.escape(invalid)}\s*$", re.MULTILINE)

        # Проверим, что invalid внутри preferred_unit_types (а не excluded)
        pref_m = re.search(
            r"preferred_unit_types:\s*\n((?:\s*-\s*\S+\s*\n)+)",
            block, re.MULTILINE
        )
        if not pref_m:
            print(f"   ⚠️  {path.name}::{check_id} — preferred_unit_types не найден")
            continue
        pref_block = pref_m.group(0)
        if not pat.search(pref_block):
            print(f"   ⚠️  {path.name}::{check_id} — '{invalid}' не найден в preferred_unit_types")
            continue

        # Заменить `- invalid` → `- replacement` в пределах preferred_unit_types
        # Проверить, нет ли уже replacement в списке
        has_repl = re.search(rf"^\s*-\s*{re.escape(replacement)}\s*$", pref_block, re.MULTILINE)

        if has_repl:
            # Просто удаляем `- invalid` строку
            new_pref = pat.sub("", pref_block)
            action = f"removed '{invalid}' (replacement '{replacement}' already present)"
        else:
            # Заменяем invalid → replacement
            new_pref = pat.sub(lambda mm: f"{mm.group(1)}{replacement}", pref_block)
            action = f"'{invalid}' → '{replacement}'"

        # Заменим в блоке
        block_new = block.replace(pref_block, new_pref, 1)
        text = text[:start] + block_new + text[end:]

        print(f"   ✅ {path.name}::{check_id}: {action}")
        changes += 1

    if changes and apply:
        backup = path.with_suffix(path.suffix + ".bak_fix_invalid_ut")
        shutil.copy(path, backup)
        path.write_text(text, encoding="utf-8")

    return changes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    # Сгруппировать по файлу
    by_file: dict[Path, list[tuple[str, str, str]]] = {}
    for rel, cid, invalid, repl in TARGETS:
        if repl not in VALID_UT:
            raise SystemExit(f"❌ Replacement '{repl}' не в LegalUnitType")
        path = BASE / rel
        if not path.exists():
            raise SystemExit(f"❌ файл не найден: {path}")
        by_file.setdefault(path, []).append((cid, invalid, repl))

    total = 0
    for path, reps in by_file.items():
        print(f"\n📄 {path.relative_to(BASE)}")
        total += process_file(path, reps, apply=args.apply)

    print()
    print("=" * 60)
    if args.apply:
        print(f"✅ APPLIED: {total} замен")
    else:
        print(f"🔵 DRY-RUN: {total} замен")
        print("   Запусти с --apply чтобы применить")


if __name__ == "__main__":
    main()

    