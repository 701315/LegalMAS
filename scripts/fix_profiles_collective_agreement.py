#!/usr/bin/env python3
"""
Замена/удаление retrieval_profile в group_9_special/contract_9.2_collective_agreement.yaml:
  - registration_check для amendment_control_registration_check
  - dispute_resolution_check для dispute_resolution_liability_check
  - employment_schedule_check для working_conditions_safety_check
  - удалить general_provisions_check из:
      no_worsening_principle_check, union_activity_guarantees_check, multiple_unions_check

Идемпотентно, targeted, dry-run по умолчанию.
"""
import re
import sys
from pathlib import Path

TARGET_FILE = Path(
    "playbooks/document_types/group_9_special/contract_9.2_collective_agreement.yaml"
)
OLD_LINE = '      retrieval_profile: "general_provisions_check"\n'

# check_id -> new_profile (None = удалить строку)
MAPPING = {
    "amendment_control_registration_check": "registration_check",
    "dispute_resolution_liability_check": "dispute_resolution_check",
    "working_conditions_safety_check": "employment_schedule_check",
    "no_worsening_principle_check": None,
    "union_activity_guarantees_check": None,
    "multiple_unions_check": None,
}


def find_check_block(raw: str, check_id: str):
    pattern = re.compile(
        rf"(?ms)^  - id: {re.escape(check_id)}\n.*?(?=^  - id: |\Z)"
    )
    return pattern.search(raw)


def main(apply: bool):
    raw = TARGET_FILE.read_text(encoding="utf-8")
    original = raw
    changed = 0

    for check_id, new_profile in MAPPING.items():
        m = find_check_block(raw, check_id)
        if not m:
            print(f"⚠️  чек не найден: {check_id}")
            continue
        block = m.group(0)

        if new_profile is None:
            if OLD_LINE not in block:
                print(f"ℹ️  уже без профиля: {check_id}")
                continue
            new_block = block.replace(OLD_LINE, "", 1)
            print(f"✅  {check_id}: профиль удалён")
        else:
            if OLD_LINE not in block:
                print(f"ℹ️  {check_id}: линия {OLD_LINE.strip()!r} не найдена (уже мигрирован?)")
                continue
            new_line = f'      retrieval_profile: "{new_profile}"\n'
            new_block = block.replace(OLD_LINE, new_line, 1)
            print(f"✅  {check_id}: → {new_profile}")

        raw = raw[: m.start()] + new_block + raw[m.end():]
        changed += 1

    if raw == original:
        print("\nНечего менять.")
        return

    if not apply:
        print(f"\n[DRY-RUN] Будет изменено {changed} чеков. Запусти с --apply.")
        return

    backup = TARGET_FILE.with_suffix(
        TARGET_FILE.suffix + ".bak_profile_fix"
    )
    backup.write_text(original, encoding="utf-8")
    TARGET_FILE.write_text(raw, encoding="utf-8")
    print(f"\n[APPLY] Изменено {changed} чеков. Backup: {backup}")


if __name__ == "__main__":
    main("--apply" in sys.argv)

    