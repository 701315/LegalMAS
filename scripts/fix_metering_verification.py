#!/usr/bin/env python3
"""
Правка №1: contract_1.5_energy_supply.yaml::metering_cluster.

Проблема: в extraction.fields есть verification_obligation_details,
но в <task> промпта этот пункт пропущен — LLM не знает о его существовании.
Решение: вставить пункт 9 в <task>, сдвинуть остальные.
"""
import shutil
import sys
from pathlib import Path

import yaml

PATH = Path("playbooks/document_types/group_1_ownership/contract_1.5_energy_supply.yaml")
CHECK_ID = "metering_cluster"

OLD_BLOCK = '''8. verification_obligation_status — "defined" или "not_defined".
9. seal_tampering_status — "defined" или "not_defined".
10. seal_tampering_details — последствия повреждения пломбы или вмешательства.'''

NEW_BLOCK = '''8. verification_obligation_status — "defined" или "not_defined".
9. verification_obligation_details — обязанность по поверке прибора учёта
   (кто, в какие сроки, за чей счёт) или "Данные не определены".
10. seal_tampering_status — "defined" или "not_defined".
11. seal_tampering_details — последствия повреждения пломбы или вмешательства.'''


def main() -> None:
    apply = "--apply" in sys.argv

    if not PATH.exists():
        raise SystemExit(f"❌ не найден {PATH}")

    text = PATH.read_text(encoding="utf-8")

    # Проверка 1: блок встречается РОВНО один раз
    count = text.count(OLD_BLOCK)
    if count == 0:
        raise SystemExit("❌ OLD_BLOCK не найден — возможно, уже пропатчен или структура иная")
    if count > 1:
        raise SystemExit(f"❌ OLD_BLOCK встречается {count} раз — нужен более точный якорь")

    new_text = text.replace(OLD_BLOCK, NEW_BLOCK, 1)

    # Pre-flight 1: YAML валиден
    try:
        d = yaml.safe_load(new_text)
    except yaml.YAMLError as e:
        raise SystemExit(f"❌ YAML не парсится после правки: {e}")

    # Pre-flight 2: check присутствует, fields не изменилось
    c = next((x for x in d["checks_v8"] if x["id"] == CHECK_ID), None)
    if c is None:
        raise SystemExit(f"❌ check {CHECK_ID} пропал после правки")
    fields = [f["name"] for f in c["extraction"]["fields"]]
    if "verification_obligation_details" not in fields:
        raise SystemExit("❌ verification_obligation_details пропало из fields")
    if len(fields) != 11:
        raise SystemExit(f"❌ в fields {len(fields)} полей вместо 11")

    # Pre-flight 3: пункт попал в промпт
    pt = c["extraction"]["llm_prompt_extraction"]
    if "verification_obligation_details" not in pt:
        raise SystemExit("❌ verification_obligation_details не найден в промпте после правки")

    print("--- Pre-flight OK ---")
    print(f"  YAML парсится, checks={len(d['checks_v8'])}, полей={len(fields)}")
    print(f"  verification_obligation_details: в fields ✓, в prompt ✓")

    if not apply:
        print("\n🔵 DRY-RUN. Запусти с --apply чтобы применить.")
        return

    backup = PATH.with_suffix(PATH.suffix + ".bak_fix_metering_verification")
    shutil.copy(PATH, backup)
    PATH.write_text(new_text, encoding="utf-8")
    print(f"\n✅ APPLIED. Backup: {backup.name}")


if __name__ == "__main__":
    main()
