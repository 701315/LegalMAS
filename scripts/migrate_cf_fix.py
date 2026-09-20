#!/usr/bin/env python3
"""
Batch: нормализация preferred_clause_functions в doc-type YAML.

Проблема: значения 'security', 'conditions', 'tax', 'payment_terms',
'termination_provisions' не входят в ClauseFunction и не имеют алиасов —
отбрасываются валидатором с warning. Заменяем на canonical CF.

Затрагивает блоки retrieval.preferred_clause_functions во всех
checks_v8 в playbooks/document_types.

Обработка:
  • canonical-значения + известные алиасы → canonical (dedup)
  • невалидные → раскрытие в 1–2 canonical значения
  • дубликаты в пределах блока удаляются (валидатор сам их не удаляет)

Usage:
    python scripts/migrate_cf_fix.py            # dry-run
    python scripts/migrate_cf_fix.py --apply    # apply
"""
from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

BASE = Path("playbooks/document_types")

# Невалидные CF → раскрытие в canonical (в порядке приоритета)
CF_EXPANSION: dict[str, list[str]] = {
    "security":                ["limitations", "obligations"],
    "conditions":              ["procedures", "obligations"],
    "tax":                     ["obligations", "procedures"],
    "payment_terms":           ["procedures", "obligations"],
    "termination_provisions":  ["procedures", "obligations"],
}

# Алиасы (из _CLAUSE_FUNCTION_ALIASES), релевантные для миграции
CF_ALIASES: dict[str, str] = {
    "procedure": "procedures", "remedy": "remedies",
    "covenants": "obligations", "covenant": "obligations",
    "warranty": "representations", "warranties": "representations",
    "indemnification": "remedies", "indemnity": "remedies",
    "dispute_resolution": "boilerplate",
    "right": "rights", "rights": "rights",
    "obligation": "obligations", "obligations": "obligations",
    "limitation": "limitations", "limitations": "limitations",
    "procedure": "procedures", "procedures": "procedures",
    "definition": "definitions", "definitions": "definitions",
    "representation": "representations", "representations": "representations",
    "remedies": "remedies", "boilerplate": "boilerplate",
    "unknown": "unknown",
}


def canonicalize(items: list[str]) -> list[str]:
    """Раскрывает + нормализует + дедуплицирует список CF."""
    result: list[str] = []
    for item in items:
        if item in CF_EXPANSION:
            for sub in CF_EXPANSION[item]:
                if sub not in result:
                    result.append(sub)
        elif item in CF_ALIASES:
            c = CF_ALIASES[item]
            if c not in result:
                result.append(c)
        # невалидное и не в CF_EXPANSION → дропаем
    return result


def process_file(path: Path, apply: bool) -> tuple[int, bool]:
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    changes = 0
    modified = False

    while i < len(lines):
        line = lines[i]
        m = re.match(r"^(\s*)preferred_clause_functions:\s*$", line)
        if not m:
            out.append(line)
            i += 1
            continue

        base_indent = m.group(1)
        item_indent = base_indent + "  "  # YAML: 2 пробела на вложенный уровень
        out.append(line)
        i += 1

        items: list[str] = []
        while i < len(lines):
            im = re.match(rf"^{re.escape(item_indent)}-\s*(\S+)\s*$", lines[i])
            if not im:
                break
            items.append(im.group(1))
            i += 1

        new_items = canonicalize(items)

        if new_items != items:
            changes += 1
            modified = True
            print(f"   {path.name}: {items} → {new_items}")
        else:
            print(f"   {path.name}: OK ({items})")

        for it in new_items:
            out.append(f"{item_indent}- {it}")

    if modified and apply:
        backup = path.with_suffix(path.suffix + ".bak_cf_fix")
        shutil.copy(path, backup)
        path.write_text("\n".join(out), encoding="utf-8")

    return changes, modified


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    total_changes = 0
    total_files = 0

    for p in sorted(BASE.rglob("*.yaml")):
        c, mod = process_file(p, apply=args.apply)
        if mod:
            total_changes += c
            total_files += 1

    print(f"\n{'=' * 60}")
    if args.apply:
        print(f"✅ APPLIED: {total_changes} блоков в {total_files} файлах")
    else:
        print(f"🔵 DRY-RUN: {total_changes} блоков в {total_files} файлах")
        print("   Запусти с --apply чтобы применить")


if __name__ == "__main__":
    main()

    