#!/usr/bin/env python3
"""
READ-ONLY. Показывает точный текст header <task>, CoVe, <rules> для 29 check-ов A2.
"""
import re
from pathlib import Path

import yaml

TARGETS = [
    ("group_2_use/contract_2.4_leasing.yaml", "leasing_early_buyout"),
    ("group_3_works/contract_3.3_construction_contract.yaml", "construction_site_safety"),
    ("group_3_works/contract_3.4_design_survey.yaml", "additional_works_procedure"),
    ("group_3_works/contract_3.4_design_survey.yaml", "warranty_period_for_documentation"),
    ("group_5_financial/contract_5.2_credit_agreement.yaml", "conditions_precedent_check"),
    ("group_5_financial/contract_5.2_credit_agreement.yaml", "forced_services_and_insurance_check"),
    ("group_5_financial/contract_5.3_factoring.yaml", "financing_and_fee_structure_check"),
    ("group_5_financial/contract_5.3_factoring.yaml", "collection_costs_allocation_check"),
    ("group_5_financial/contract_5.3_factoring.yaml", "debtor_notification_check"),
]

BASE = Path("playbooks/document_types")


for rel, cid in TARGETS:
    p = BASE / rel
    if not p.exists():
        print(f"❌ {p}")
        continue
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    c = next((x for x in d.get("checks_v8") or [] if x.get("id") == cid), None)
    if not c:
        print(f"❌ {rel}::{cid}")
        continue
    ext = c.get("extraction") or {}
    fields = [f["name"] for f in ext.get("fields") or [] if isinstance(f, dict)]
    pt = ext.get("llm_prompt_extraction") or ""

    print(f"\n{'='*100}")
    print(f"{p.name}::{cid}")
    print(f"  fields ({len(fields)}): {fields}")
    print(f"{'='*100}")

    # 1. Header <task>
    m = re.search(r"<task>(.*?)</task>", pt, re.DOTALL)
    if m:
        task_body = m.group(1)
        # Показать первые 15 строк <task>
        print("--- <task> (первые 20 строк) ---")
        for i, line in enumerate(task_body.split("\n")[:20]):
            print(f"  {line}")

    # 2. CoVe — найти строку про "ключей"
    print("--- CoVe / строки про 'ключей' ---")
    for line in pt.split("\n"):
        if "ключ" in line.lower() or "CoVe" in line or "Проверь, что все" in line:
            print(f"  {line.strip()}")

    # 3. <rules> / [ПРАВИЛА] — искать "N полей" / "N ключей"
    print("--- Другие упоминания счётчика ---")
    for line in pt.split("\n"):
        if re.search(r"\d+\s+(полей|ключей)", line):
            print(f"  {line.strip()}")

    # 4. llm.prompt_template — может содержать свой счётчик
    llm = c.get("llm") or {}
    ptt = llm.get("prompt_template") or ""
    if ptt:
        cnt = 0
        for line in ptt.split("\n"):
            if re.search(r"\d+\s+(полей|ключей)", line):
                print(f"  [llm.prompt_template] {line.strip()}")
                cnt += 1
        if cnt == 0:
            print("  [llm.prompt_template] — счётчиков нет")

            