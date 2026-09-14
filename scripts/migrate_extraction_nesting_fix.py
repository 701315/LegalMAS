#!/usr/bin/env python3
"""
Fix broken indentation for extraction blocks in
contract_4.2_cargo_transportation.yaml.

Symptom: `extraction:` alone at 4-space; its children (`enabled`, `mode`,
`llm_max_tokens`, `compact_output`, `llm_prompt_extraction`, `fields`)
also at 4-space — siblings instead of children.

Fix: shift every non-empty line from `enabled:` up to (but not including)
`store_payload:` by +2 spaces. Shift entire range atomically, including
multiline content of `llm_prompt_extraction: |` and the `fields:` list.

Usage:
    python scripts/migrate_extraction_nesting_fix.py            # dry-run
    python scripts/migrate_extraction_nesting_fix.py --apply
"""
from __future__ import annotations

import argparse
import difflib
import re
import shutil
from pathlib import Path

import yaml

PATH = Path("playbooks/document_types/group_4_services/contract_4.2_cargo_transportation.yaml")
CHECK_IDS = {"cargo_and_route", "loading_unloading_obligations"}


def fix_block(block: list[str]) -> tuple[list[str], bool, str | None]:
    ext_idx = None
    for k, l in enumerate(block):
        if re.match(r"^    extraction:\s*$", l):
            ext_idx = k
            break
    if ext_idx is None:
        return block, False, "no bare 'extraction:' — skip"

    enabled_idx = None
    for k in range(ext_idx + 1, len(block)):
        if re.match(r"^    enabled:\s", block[k]):
            enabled_idx = k
            break
    if enabled_idx is None:
        return block, False, "no top-level 'enabled:' — skip"

    if re.match(r"^      enabled:", block[enabled_idx]):
        return block, False, "already fixed"

    end_idx = len(block)
    for k in range(enabled_idx + 1, len(block)):
        if re.match(r"^    store_payload:", block[k]):
            end_idx = k
            break
        if re.match(r"^  - id: ", block[k]):
            end_idx = k
            break

    has_fields = any(re.match(r"^    fields:\s*$", block[k]) for k in range(enabled_idx, end_idx))
    if not has_fields:
        return block, False, "no 'fields:' in range — skip"

    new_block = block[:enabled_idx]
    for l in block[enabled_idx:end_idx]:
        if l.strip():
            new_block.append("  " + l)
        else:
            new_block.append(l)
    new_block.extend(block[end_idx:])
    return new_block, True, f"shifted {end_idx - enabled_idx} lines"


def process(text: str) -> tuple[str, int, list[str]]:
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    fixed = 0
    msgs: list[str] = []

    while i < len(lines):
        m = re.match(r"^  - id: (\S+)\s*$", lines[i])
        if not m or m.group(1) not in CHECK_IDS:
            out.append(lines[i])
            i += 1
            continue

        j = i + 1
        while j < len(lines) and not re.match(r"^  - id: ", lines[j]) and not re.match(r"^\S", lines[j]):
            j += 1
        block = lines[i:j]
        new_block, was_fixed, diag = fix_block(block)
        if was_fixed:
            fixed += 1
            msgs.append(f"   ✅ {m.group(1)}: {diag}")
        elif diag:
            msgs.append(f"   ⚠️  {m.group(1)}: {diag}")
        out.extend(new_block)
        i = j

    return "\n".join(out), fixed, msgs


def preflight(new_text: str) -> None:
    try:
        data = yaml.safe_load(new_text)
    except yaml.YAMLError as e:
        raise SystemExit(f"❌ YAML не парсится: {e}")

    for cid in CHECK_IDS:
        c = next((x for x in data.get("checks_v8", []) if x.get("id") == cid), None)
        if c is None:
            raise SystemExit(f"❌ {cid} не найден после правки")
        ext = c.get("extraction")
        if not isinstance(ext, dict):
            raise SystemExit(f"❌ {cid}: extraction не dict ({type(ext).__name__})")
        if ext.get("enabled") is not True:
            raise SystemExit(f"❌ {cid}: extraction.enabled != true ({ext.get('enabled')!r})")
        if not ext.get("fields"):
            raise SystemExit(f"❌ {cid}: extraction.fields пуст")
        print(f"   ✅ {cid}: extraction OK ({len(ext['fields'])} полей)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if not PATH.exists():
        raise SystemExit(f"❌ не найден: {PATH}")

    text = PATH.read_text(encoding="utf-8")
    new_text, fixed, msgs = process(text)

    for m in msgs:
        print(m)

    if fixed == 0:
        print("🔵 Изменений нет.")
        return

    if not args.apply:
        diff = difflib.unified_diff(
            text.split("\n"), new_text.split("\n"),
            lineterm="", n=2, fromfile="before", tofile="after",
        )
        print()
        print("\n".join(diff))
        print(f"\n🔵 DRY-RUN: {fixed} блок(ов). Запусти с --apply.")
        return

    print("\n--- Pre-flight ---")
    preflight(new_text)

    backup = PATH.with_suffix(PATH.suffix + ".bak_extraction_nesting_fix")
    shutil.copy(PATH, backup)
    PATH.write_text(new_text, encoding="utf-8")
    print(f"\n✅ APPLIED: {fixed} блок(ов). Backup: {backup.name}")


if __name__ == "__main__":
    main()
