#!/usr/bin/env python3
"""READ-ONLY. Показывает raw-строки файла вокруг llm_prompt_extraction
для 3 проблемных check-ов."""
from pathlib import Path

PATH = Path("playbooks/document_types/group_5_financial/contract_5.2_credit_agreement.yaml")
CHECK_IDS = [
    "forced_services_and_insurance_check",
    "conditions_precedent_check",
    "non_financial_covenants_check",
]

text = PATH.read_text(encoding="utf-8")
lines = text.split("\n")

for cid in CHECK_IDS:
    # Найти начало check-а
    start = None
    for i, line in enumerate(lines):
        if line.strip() == f"- id: {cid}":
            start = i
            break
    if start is None:
        print(f"❌ {cid}")
        continue

    # Найти llm_prompt_extraction в этом check-е
    prompt_start = None
    end_of_check = start + 1
    for i in range(start + 1, min(start + 800, len(lines))):
        if lines[i].startswith("  - id:"):
            end_of_check = i
            break
        if "llm_prompt_extraction" in lines[i]:
            prompt_start = i
            break

    print(f"\n{'='*100}")
    print(f"{cid}  (check начинается на строке {start+1})")
    print(f"{'='*100}")

    if prompt_start is None:
        print("  ❌ llm_prompt_extraction не найден")
        continue

    print(f"  llm_prompt_extraction на строке {prompt_start+1}")
    # Показать 40 строк, начиная с prompt_start, с repr для невидимых символов
    for j in range(prompt_start, min(prompt_start + 45, end_of_check, len(lines))):
        line = lines[j]
        # показать длину строки + первые 90 символов
        shown = line[:100]
        print(f"{j+1:5d}| len={len(line):3d} | {shown!r}")
        if "Заполни" in line:
            print(f"        ↳ ВОТ ЭТА СТРОКА: {line!r}")

            