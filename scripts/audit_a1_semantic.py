#!/usr/bin/env python3
"""
READ-ONLY. Семантический аудит 30 невалидных retrieval_profile.
Для каждого — все checks, их name и краткое описание.
"""
from collections import defaultdict
from pathlib import Path

import yaml

GROUPS = ["group_1_ownership", "group_2_use", "group_3_works",
          "group_4_services", "group_5_financial"]
BASE = Path("playbooks/document_types")

# Невалидные (из предыдущего аудита)
INVALID = {
    "generic_check", "compliance_check", "default_remedy_check",
    "litigation_warranty_check", "form_requirement_check",
    "risk_allocation_check", "reinstatement_check", "rent_free_check",
    "consumer_rights_check", "buyout_check", "reporting_check",
    "regulatory_check", "environmental_check", "safety_check",
    "site_security_check", "site_prep_check", "surveys_check",
    "financial_security_check", "additional_works_check",
    "site_access_check", "coordination_check", "quality_check",
    "deposit_subject_check", "aml_compliance_check",
    "unauthorized_debit_check", "dbs_security_check",
    "overdraft_check", "deposit_insurance_check",
    "account_closure_check", "payment_allocation_check",
}

by_profile: dict[str, list[tuple[str, str, str, str]]] = defaultdict(list)

for g in GROUPS:
    root = BASE / g
    if not root.exists():
        continue
    for p in sorted(root.rglob("*.yaml")):
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
        for c in (d or {}).get("checks_v8") or []:
            r = c.get("retrieval") or {}
            prof = r.get("retrieval_profile")
            if prof in INVALID:
                name = (c.get("name") or "")[:100]
                desc = (c.get("description") or "")[:150].replace("\n", " ")
                q = (r.get("retrieval_query") or "")[:100]
                by_profile[prof].append((p.name, c["id"], name, q))

# Сортировка по количеству
for prof, items in sorted(by_profile.items(), key=lambda kv: -len(kv[1])):
    print(f"\n{'='*120}")
    print(f"❌ {prof}  ({len(items)} checks)")
    print(f"{'='*120}")
    for fname, cid, name, q in items[:15]:
        print(f"\n  📄 {fname}")
        print(f"     CHECK: {cid}")
        print(f"     NAME:  {name}")
        print(f"     QUERY: {q}")
    if len(items) > 15:
        print(f"\n  ... ещё {len(items) - 15} checks")
        