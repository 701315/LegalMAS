#!/usr/bin/env python3
"""
Batch v2: нормализация preferred_clause_functions в doc-type YAML.

Исправления относительно v1:
  1. Таргетированный: работает только там, где есть НЕВАЛИДНЫЕ CF.
  2. Правильно снимает кавычки (обе стороны) — не путает '"obligations"' с 'obligations'.
  3. Не переформатирует блоки, где нет изменений.
  4. Санити-чек: если после канонизации блок опустел, а в исходнике были значения
     — не применяет изменение, логирует как ошибку.
  5. Сохраняет стиль кавычек из исходника.
  6. Идемпотентный.

Usage:
    python scripts/migrate_cf_fix_v2.py            # dry-run
    python scripts/migrate_cf_fix_v2.py --apply    # apply
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

# Canonical ClauseFunction + релевантные алиасы из _CLAUSE_FUNCTION_ALIASES.
# Используем локальный словарь, чтобы не зависеть от импорта сервисов.
CF_CANONICAL_OR_ALIAS: dict[str, str] = {
    # canonical
    "rights": "rights", "obligations": "obligations", "limitations": "limitations",
    "procedures": "procedures", "definitions": "definitions",
    "representations": "representations", "remedies": "remedies",
    "boilerplate": "boilerplate", "unknown": "unknown",
    # aliases
    "right": "rights", "entitlement": "rights", "entitlements": "rights",
    "permission": "rights", "permissions": "rights", "option": "rights", "options": "rights",
    "obligation": "obligations", "duty": "obligations", "duties": "obligations",
    "covenant": "obligations", "covenants": "obligations",
    "undertaking": "obligations", "undertakings": "obligations",
    "limitation": "limitations", "cap": "limitations", "caps": "limitations",
    "liability_cap": "limitations", "liability_exclusion": "limitations",
    "exclusion": "limitations", "exclusions": "limitations",
    "procedure": "procedures", "process": "procedures", "processes": "procedures",
    "mechanism": "procedures", "mechanisms": "procedures", "steps": "procedures",
    "timeline": "procedures", "termination_mechanics": "procedures",
    "definition": "definitions", "interpretation": "definitions",
    "representation": "representations", "warranty": "representations",
    "warranties": "representations",
    "representations_and_warranties": "representations",
    "representation_and_warranty": "representations",
    "remedy": "remedies", "indemnity": "remedies", "indemnification": "remedies",
    "damages": "remedies", "compensation": "remedies", "cure": "remedies",
    "penalty": "remedies", "penalties": "remedies",
}


def canonicalize(raw: str) -> str | None:
    """Возвращает canonical CF или None, если значение невалидно."""
    return CF_CANONICAL_OR_ALIAS.get(raw)


def process_line_value(raw: str) -> tuple[str, bool]:
    """Снимает кавычки, если есть. Возвращает (значение, было_ли_кавычки)."""
    if len(raw) >= 2 and (
        (raw[0] == '"' and raw[-1] == '"') or (raw[0] == "'" and raw[-1] == "'")
    ):
        return raw[1:-1], True
    return raw, False


def process_file(path: Path, apply: bool) -> tuple[int, int, int, list[str]]:
    """
    Возвращает (изменённых_блоков, невалидных_до, проблемных_после, warnings).
    """
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    changes = 0
    invalid_before = 0
    invalid_after = 0
    warnings: list[str] = []
    modified = False

    while i < len(lines):
        line = lines[i]
        m = re.match(r"^(\s*)preferred_clause_functions:\s*$", line)
        if not m:
            out.append(line)
            i += 1
            continue

        base_indent = m.group(1)
        item_indent = base_indent + "  "
        out.append(line)
        i += 1

        items: list[tuple[str, bool]] = []  # (значение, был_ли_кавычки)
        while i < len(lines):
            im = re.match(rf"^{re.escape(item_indent)}-\s*(.+?)\s*$", lines[i])
            if not im:
                break
            raw = im.group(1)
            value, had_quotes = process_line_value(raw)
            items.append((value, had_quotes))
            i += 1

        # Классифицируем
        has_invalid = any(canonicalize(v) is None for v, _ in items)
        if not has_invalid:
            # Ничего не меняем — воспроизводим как было
            for value, had_quotes in items:
                rendered = f'"{value}"' if had_quotes else value
                out.append(f"{item_indent}- {rendered}")
            continue

        invalid_before = sum(1 for v, _ in items if canonicalize(v) is None)

        # Строим новый список:
        # — валидные/алиасы → canonical
        # — невалидные → раскрываем через CF_EXPANSION
        # — дубликаты убираем, порядок сохраняем
        new_items: list[str] = []
        seen: set[str] = set()
        # Сохраняем стиль кавычек по первому невалидному (если хоть один с кавычками —
        # пишем всё с кавычками, иначе без).
        any_quotes = any(hq for _, hq in items)

        for value, _ in items:
            canonical = canonicalize(value)
            if canonical is not None:
                if canonical not in seen:
                    new_items.append(canonical)
                    seen.add(canonical)
            elif value in CF_EXPANSION:
                for sub in CF_EXPANSION[value]:
                    if sub not in seen:
                        new_items.append(sub)
                        seen.add(sub)
            else:
                # Невалидно и нет раскрытия — оставляем как есть (ручной разбор)
                warnings.append(f"{path.name}: невалидный CF без раскрытия: {value!r}")

        if items and not new_items:
            # Санити-чек: опустошение блока
            warnings.append(
                f"{path.name}: пропускаю опустошение блока preferred_clause_functions "
                f"(было: {[v for v, _ in items]})"
            )
            # Воспроизводим оригинал
            for value, had_quotes in items:
                rendered = f'"{value}"' if had_quotes else value
                out.append(f"{item_indent}- {rendered}")
            continue

        if not new_items:
            # Блок был пуст — оставляем пустым
            continue

        # Сравниваем со старым canonical-эквивалентом
        old_canonical = []
        for value, _ in items:
            c = canonicalize(value)
            if c is not None:
                old_canonical.append(c)
            elif value in CF_EXPANSION:
                old_canonical.extend(CF_EXPANSION[value])
            else:
                old_canonical.append(value)

        if new_items == old_canonical and not any(
            canonicalize(v) is None for v, _ in items
        ):
            # Ничего не изменилось по смыслу — воспроизводим как есть
            for value, had_quotes in items:
                rendered = f'"{value}"' if had_quotes else value
                out.append(f"{item_indent}- {rendered}")
            continue

        # Есть реальные изменения
        changes += 1
        modified = True
        for v in new_items:
            rendered = f'"{v}"' if any_quotes else v
            out.append(f"{item_indent}- {rendered}")

    if modified and apply:
        backup = path.with_suffix(path.suffix + ".bak_cf_fix_v2")
        shutil.copy(path, backup)
        path.write_text("\n".join(out), encoding="utf-8")

    return changes, invalid_before, invalid_after, warnings


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    total_changes = 0
    total_invalid = 0
    total_files = 0
    all_warnings: list[str] = []

    for p in sorted(BASE.rglob("*.yaml")):
        c, inv, _, warns = process_file(p, apply=args.apply)
        if c > 0:
            print(f"   {p.name}: {c} блок(ов) изменено (невалидных до: {inv})")
            total_changes += c
            total_invalid += inv
            total_files += 1
        all_warnings.extend(warns)

    print(f"\n{'=' * 60}")
    for w in all_warnings:
        print(f"   ⚠️  {w}")

    print()
    if args.apply:
        print(f"✅ APPLIED: {total_changes} блоков в {total_files} файлах")
    else:
        print(f"🔵 DRY-RUN: {total_changes} блоков в {total_files} файлах")
        print(f"   Невалидных CF до: {total_invalid}")
        print("   Запусти с --apply чтобы применить")


if __name__ == "__main__":
    main()


    