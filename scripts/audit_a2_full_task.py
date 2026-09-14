#!/usr/bin/env python3
"""READ-ONLY. Показывает ПОЛНЫЙ <task> для 5 целевых чеков."""
import re
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
    ext = c.get("extraction") or {}
    fields = [f["name"] for f in (ext.get("fields") or []) if isinstance(f, dict)]
    pt = ext.get("llm_prompt_extraction") or ""

    m = re.search(r"<task>(.*?)</task>", pt, re.DOTALL)
    body = m.group(1) if m else ""

    print(f"\n{'='*110}")
    print(f"{p.name}::{cid}  |  M={len(fields)}  N={len(fields)+1}")
    print(f"{'='*110}")
    print("--- ПОЛНЫЙ <task> ---")
    for i, line in enumerate(body.split("\n")):
        print(f"{i:4d}| {line}")
        