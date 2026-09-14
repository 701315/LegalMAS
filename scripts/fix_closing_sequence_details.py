#!/usr/bin/env python3
import shutil
from pathlib import Path

import yaml

PATH = Path("playbooks/document_types/group_1_ownership/contract_1.11_shares_sale.yaml")

# Вставка closing_sequence_details перед closing_deliverables_status
ANCHOR = '        - name: "closing_deliverables_status"'
INSERT = (
    '        - name: "closing_sequence_details"\n'
    '          type: "string"\n'
    '          presentation: "fact"\n'
    '          label: "Closing sequence"\n'
    '          description: "Формулировка о последовательности действий при закрытии."\n'
    '          required: false\n'
    '          display_in_grid: true\n'
    '          display_priority: 3\n'
)

text = PATH.read_text(encoding="utf-8")

# 1) уже есть? ничего не делаем
if '"closing_sequence_details"' in text:
    print("ℹ️  closing_sequence_details уже есть — ничего не делаем")
    raise SystemExit(0)

# 2) якорь должен быть ровно один
count = text.count(ANCHOR)
if count != 1:
    raise SystemExit(f"❌ Якорь встречается {count} раз (ожидалось 1)")

new_text = text.replace(ANCHOR, INSERT + ANCHOR, 1)

# 3) Pre-flight
d = yaml.safe_load(new_text)
c = next(x for x in d["checks_v8"] if x["id"] == "closing_conditions_and_payment_mechanics_check")
names = [f["name"] for f in c["extraction"]["fields"]]
assert "closing_sequence_details" in names, "не попал в fields"
assert len(names) == 14, f"fields = {len(names)}, ожидалось 14"
print(f"✅ Pre-flight OK: {len(names)} полей")
print(f"   последние 4: {names[-4:]}")

# 4) Apply
shutil.copy(PATH, PATH.with_suffix(PATH.suffix + ".bak_fix_closing_sequence"))
PATH.write_text(new_text, encoding="utf-8")
print("✅ APPLIED")

