#!/usr/bin/env python3
"""
scripts/cleanup_yaml_artifacts.py (v2 — safe, line-based)

Убирает дубли в плоских списках retrieval.* / enrichment_hints.* / rules.*.
Каждая строка сохраняется как есть; дубликат просто НЕ пишется в output.
Плюс: заменяет ".без markdown." -> ". Без markdown." в Layer 1.

Не трогает форматирование, промпты, комментарии, порядок ключей.
Не работает через PyYAML round-trip — только построчная фильтрация.

Запуск:
    python scripts/cleanup_yaml_artifacts.py <file.yaml> [...] [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEDUP_FIELDS = {
    "preferred_unit_types", "excluded_unit_types",
    "preferred_clause_functions", "negative_keywords", "levels",
    "preferred_segment_types", "excluded_segment_types",
    "keywords", "regex_patterns",
}

LAYER1_ARTIFACT_RE = re.compile(r"\.без markdown\.")
FIELD_HEADER_RE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*):\s*$")
LIST_ITEM_RE = re.compile(r"^(\s*)- (.*)$")


def process_file(path: Path, dry_run: bool) -> list[str]:
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)

    out: list[str] = []
    changes: list[str] = []
    in_target = False
    target_indent: int | None = None
    seen: set[str] = set()

    for i, raw_line in enumerate(lines):
        stripped = raw_line.rstrip("\n")

        m_field = FIELD_HEADER_RE.match(stripped)
        if m_field:
            field_name = m_field.group(2)
            new_indent = len(m_field.group(1))
            if field_name in DEDUP_FIELDS:
                in_target = True
                target_indent = new_indent
                seen = set()
                out.append(raw_line)
                continue
            if in_target and target_indent is not None and new_indent <= target_indent:
                in_target = False
            out.append(raw_line)
            continue

        if in_target:
            m_item = LIST_ITEM_RE.match(stripped)
            if m_item and target_indent is not None and len(m_item.group(1)) > target_indent:
                key = m_item.group(2).strip()
                if key in seen:
                    changes.append(f"  L{i + 1}: дубль '{key[:60]}'")
                    continue  # пропускаем дубликат
                seen.add(key)
                out.append(raw_line)
                continue
            in_target = False

        out.append(raw_line)

    new_text = "".join(out)
    if LAYER1_ARTIFACT_RE.search(new_text):
        n = len(LAYER1_ARTIFACT_RE.findall(new_text))
        new_text = LAYER1_ARTIFACT_RE.sub(". Без markdown.", new_text)
        changes.append(f"  Layer 1: '.без markdown.' × {n} → '. Без markdown.'")

    if not dry_run and changes:
        backup = path.with_suffix(path.suffix + ".bak")
        if not backup.exists():
            backup.write_text(original, encoding="utf-8")
        path.write_text(new_text, encoding="utf-8")

    return changes


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    for p in args.paths:
        if not p.exists():
            print(f"[SKIP] {p} — не существует")
            continue
        print(f"[FILE] {p}")
        changes = process_file(p, dry_run=args.dry_run)
        if changes:
            print("\n".join(changes))
            if not args.dry_run:
                print(f"  → записано. Бэкап: {p.with_suffix(p.suffix + '.bak')}")
        else:
            print("  (изменений нет)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))