#!/usr/bin/env python3
"""
READ-ONLY. Показывает ТОЧНЫЙ текст (repr) всех счётчиков
в 5 целевых check-ах A2.
"""
from pathlib import Path
import yaml

TARGETS = [
    ("group_5_financial/contract_5.2_credit_agreement.yaml",
     "forced_services_and_insurance_check"),
    ("group_5_financial/contract_5.2_credit_agreement.yaml",
     "conditions_precedent_check"),
    ("group_5_financial/contract_5.2_credit_agreement.yaml",
     "non_financial_covenants_check"),
    ("group_3_works/contract_3.4_design_survey.yaml",
     "additional_works_procedure"),
    ("group_5_financial/contract_5.3_factoring.yaml",
     "collection_costs_allocation_check"),
]

BASE = Path("playbooks/document_types")

for rel, cid in TARGETS:
    p = BASE / rel
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    c = next((x for x in d["checks_v8"] if x.get("id") == cid), None)
    if not c:
        print(f"❌ {rel}::{cid}")
        continue

    ext = c.get("extraction") or {}
    fields = [f["name"] for f in (ext.get("fields") or []) if isinstance(f, dict)]
    pt = ext.get("llm_prompt_extraction") or ""
    ptt = (c.get("llm") or {}).get("prompt_template") or ""

    print(f"\n{'='*100}")
    print(f"{rel}::{cid}  |  M={len(fields)}  N={len(fields)+1}")
    print(f"{'='*100}")

    # Точный header <task>
    import re
    m = re.search(r"<task>(.*?)</task>", pt, re.DOTALL)
    if m:
        body = m.group(1)
        # первые 3 непустые строки
        non_empty = [ln for ln in body.split("\n") if ln.strip()][:3]
        print("\n--- <task> первые 3 непустые строки (repr) ---")
        for ln in non_empty:
            print(f"  {ln!r}")

    # Все счётчики в pt (вне <task>)
    non_task = pt
    if m:
        non_task = pt[:m.start()] + pt[m.end():]
    print("\n--- счётчики в pt вне <task> (repr) ---")
    for line in non_task.split("\n"):
        if re.search(r"\d+\s+ключ", line) or re.search(r"со всеми \d+", line):
            print(f"  {line!r}")

    # Счётчики в prompt_template
    if ptt:
        print("\n--- счётчики в llm.prompt_template (repr) ---")
        for line in ptt.split("\n"):
            if re.search(r"\d+\s+ключ", line) or re.search(r"Все ли \d+", line):
                print(f"  {line!r}")
                