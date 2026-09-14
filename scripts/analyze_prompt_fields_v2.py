#!/usr/bin/env python3
"""
Точная проверка PROMPT_FIELD_MISMATCH напрямую по YAML.

Логика:
  • whitelist = все field_name из extraction.fields во всех YAML
  • in_prompt = все идентификаторы из llm_prompt_extraction ∩ whitelist
  • declared   = все field_name в этом чеке (без metadata)
  • (a) = in_prompt - declared
  • (b) = declared - in_prompt
"""
import re
from pathlib import Path
from collections import Counter

import yaml

ROOTS = [Path("playbooks/document_types"), Path("playbooks/global_checks")]
IDENT_RE = re.compile(r"\b[a-z][a-z0-9_]{3,}\b")
METADATA = {"evidence", "clause_ref", "quote", "page", "reason", "explanation", "notes"}


def collect_whitelist() -> set[str]:
    names: set[str] = set()
    for root in ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*.yaml"):
            try:
                d = yaml.safe_load(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            for c in (d or {}).get("checks_v8") or []:
                for f in (c.get("extraction") or {}).get("fields") or []:
                    if isinstance(f, dict) and isinstance(f.get("name"), str):
                        names.add(f["name"])
    return names


def main() -> None:
    whitelist = collect_whitelist()
    print(f"Whitelist: {len(whitelist)} уникальных field_name\n")

    a_records = []  # in_prompt, нет в fields
    b_records = []  # в fields, нет в prompt

    for root in ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*.yaml"):
            try:
                d = yaml.safe_load(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            for c in (d or {}).get("checks_v8") or []:
                ext = c.get("extraction") or {}
                if not isinstance(ext, dict) or not ext.get("enabled"):
                    continue
                prompt = ext.get("llm_prompt_extraction")
                if not isinstance(prompt, str) or not prompt.strip():
                    continue
                fields = [
                    f["name"] for f in ext.get("fields") or []
                    if isinstance(f, dict) and isinstance(f.get("name"), str)
                    and f["name"] not in METADATA
                ]
                if not fields:
                    continue
                declared = set(fields)
                in_prompt = set(IDENT_RE.findall(prompt)) & whitelist

                for f in sorted(declared - in_prompt):
                    b_records.append((p.name, c["id"], f))
                for f in sorted(in_prompt - declared):
                    a_records.append((p.name, c["id"], f))

    print(f"=== (a) в prompt, нет в extraction.fields: {len(a_records)} ===")
    for fn, cid, f in a_records:
        print(f"  {fn:<42} {cid:<45} {f}")

    print(f"\n=== (b) в extraction.fields, нет в prompt: {len(b_records)} ===")
    for fn, cid, f in b_records:
        print(f"  {fn:<42} {cid:<45} {f}")

    # Сводка по файлам
    print(f"\n=== Сводка по файлам ===")
    for fn, cnt in Counter(r[0] for r in a_records + b_records).most_common():
        print(f"  {cnt:3d}  {fn}")


if __name__ == "__main__":
    main()
