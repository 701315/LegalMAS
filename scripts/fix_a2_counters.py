#!/usr/bin/env python3
"""
Fix A2 counters v5 — финальный добор: Case 4 и Case 5.
Cases 1–3 уже починены в v4.

Usage:
    python scripts/fix_a2_counters.py            # dry-run
    python scripts/fix_a2_counters.py --apply
"""
from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

import yaml

BASE = Path("playbooks/document_types")
INDENT = "        "  # 8 пробелов — отступ содержимого block scalar

FIXES: list[dict] = [
    # ─────── CASE 4: additional_works_procedure (M=12, N=13) ───────
    {
        "file": "group_3_works/contract_3.4_design_survey.yaml",
        "check_id": "additional_works_procedure",
        "M": 12, "N": 13,
        "reps": [
            {
                "old": r"Заполни строго следующие 11 полей \(плюс evidence\):",
                "new": "Заполни строго следующие 12 полей + evidence (всего 13 ключей):",
                "tag": "header",
            },
            {
                "old": r'(12\. suspension_right_display — "Да, право приостановить предусмотрено" / "Нет, право не предусмотрено" / "Данные не определены" / "Не применимо"\.)',
                "new": r"\1\n" + INDENT + "13. evidence — массив цитат из текста договора.",
                "tag": "+evidence",
                "is_backref": True,
            },
            {
                "old": r"- Верни строго валидный JSON\. Все 11 ключей \+ evidence обязаны присутствовать\.",
                "new": "- Верни строго валидный JSON. Все 13 ключей (12 полей + evidence) обязаны присутствовать.",
                "tag": "cove",
            },
            {
                "old": r"7\. Все ли 11 ключей присутствуют в JSON \(6 enum \+ 5 display\)\?",
                "new": "7. Все ли 13 ключей присутствуют в JSON (12 полей + evidence)?",
                "tag": "template",
            },
        ],
    },
    # ─────── CASE 5: collection_costs_allocation_check (M=5, N=6) ───────
    {
        "file": "group_5_financial/contract_5.3_factoring.yaml",
        "check_id": "collection_costs_allocation_check",
        "M": 5, "N": 6,
        "reps": [
            {
                "old": r"Заполни строго следующие 7 полей \(все ключи должны присутствовать\s+в ответе, даже если значение — fallback\):",
                "new": "Заполни строго следующие 5 полей + evidence (всего 6 ключей):",
                "tag": "header",
            },
            {
                "old": r"со всеми 7 ключами",
                "new": "со всеми 6 ключами",
                "tag": "cove (pt + template)",
                # 1 в pt + 2 в template = 3 совпадения
            },
        ],
    },
]


def find_check_bounds(text: str, check_id: str) -> tuple[int, int] | None:
    m = re.search(rf"^  - id: {re.escape(check_id)}\s*$", text, re.MULTILINE)
    if not m:
        return None
    start = m.start()
    m2 = re.search(r"^  - id: ", text[m.end():], re.MULTILINE)
    end = m.end() + m2.start() if m2 else len(text)
    return start, end


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    files: dict[Path, str] = {}
    for fix in FIXES:
        p = BASE / fix["file"]
        if p.exists():
            files.setdefault(p, p.read_text(encoding="utf-8"))

    total = 0
    warnings = 0

    for fix in FIXES:
        p = BASE / fix["file"]
        if not p.exists():
            print(f"\n❌ {p}")
            continue
        print(f"\n{'='*80}")
        print(f"{fix['file']}::{fix['check_id']}  (M={fix['M']}, N={fix['N']})")
        print(f"{'='*80}")

        raw = files[p]
        bounds = find_check_bounds(raw, fix["check_id"])
        if not bounds:
            print(f"   ❌ check не найден")
            warnings += 1
            continue
        start, end = bounds
        block = raw[start:end]

        for r in fix["reps"]:
            pattern = re.compile(r["old"], re.DOTALL)
            n = len(pattern.findall(block))
            if n == 0:
                print(f"   ⚠️  [{r['tag']}] OLD не найден")
                warnings += 1
                continue
            block = pattern.sub(r["new"], block)
            print(f"   ✅ [{r['tag']}] {n} замен")
            total += n

        new_raw = raw[:start] + block + raw[end:]

        # Pre-flight
        try:
            d = yaml.safe_load(new_raw)
        except yaml.YAMLError as e:
            print(f"   ❌ YAML не парсится: {e}")
            print(f"   ⟵ ОТКАТ, files[{p.name}] не изменён")
            warnings += 1
            continue

        c = next((x for x in d.get("checks_v8") or [] if x.get("id") == fix["check_id"]), None)
        if not c:
            print(f"   ❌ check пропал — ОТКАТ")
            warnings += 1
            continue
        M = len([f for f in (c["extraction"]["fields"] or []) if isinstance(f, dict)])
        if M != fix["M"]:
            print(f"   ❌ M={M}, ожидалось {fix['M']} — ОТКАТ")
            warnings += 1
            continue

        files[p] = new_raw
        print(f"   ✅ pre-flight OK (M={M})")

    print(f"\n{'='*80}")
    if args.apply:
        for p, text in files.items():
            backup = p.with_suffix(p.suffix + ".bak_fix_a2_v5")
            if not backup.exists():
                shutil.copy(p, backup)
            p.write_text(text, encoding="utf-8")
        print(f"✅ APPLIED: {total} замен, {warnings} warnings")
    else:
        print(f"🔵 DRY-RUN: {total} замен, {warnings} warnings")
        print("   Если warnings = 0 — запусти с --apply")


if __name__ == "__main__":
    main()