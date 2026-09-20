#!/usr/bin/env python3
"""
Откат: возврат валидных preferred_unit_types в 3 storage-check-ах,
ошибочно удалённых в ходе рефакторинга (использовался устаревший
список из 5 значений; реально LegalUnitType содержит 29 значений).

Затрагивает: playbooks/document_types/group_4_services/contract_4.4_storage.yaml

Usage:
    python scripts/migrate_storage_ut_revert.py            # dry-run
    python scripts/migrate_storage_ut_revert.py --apply    # apply
"""
from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

STORAGE_FILE = Path("playbooks/document_types/group_4_services/contract_4.4_storage.yaml")

# (check_id, ut_to_restore) — вставляем в начало списка preferred_unit_types
REVERTS: list[tuple[str, str]] = [
    ("professional_custodian_liability", "liability_provision"),
    ("exclusions_from_liability", "liability_provision"),
    ("pretension_order", "dispute_resolution"),
]


def check_block_bounds(text: str, check_id: str) -> tuple[int, int] | None:
    """Возвращает (start, end) блока check-а с данным id, либо None."""
    m = re.search(rf"^  - id: {re.escape(check_id)}\s*$", text, re.MULTILINE)
    if not m:
        return None
    nxt = re.search(r"^  - id: ", text[m.end():], re.MULTILINE)
    end = m.end() + nxt.start() if nxt else len(text)
    return m.start(), end


def insert_ut(text: str, check_id: str, new_ut: str) -> tuple[str, bool]:
    """Вставляет new_ut первым элементом в preferred_unit_types внутри check-а."""
    bounds = check_block_bounds(text, check_id)
    if bounds is None:
        print(f"   ⚠️  check не найден: {check_id}")
        return text, False
    start, end = bounds
    block = text[start:end]

    m = re.search(
        r"(^\s*preferred_unit_types:\s*\n)((?:\s+-\s+\S+\s*\n)+)",
        block,
        re.MULTILINE,
    )
    if not m:
        print(f"   ⚠️  preferred_unit_types не найден в блоке {check_id}")
        return text, False

    prefix, items = m.group(1), m.group(2)

    if re.search(rf"^\s+-\s+{re.escape(new_ut)}\s*$", items, re.MULTILINE):
        print(f"   ✅ {check_id}: '{new_ut}' уже присутствует")
        return text, False

    first_item = re.match(r"(\s+)-\s+", items)
    if not first_item:
        print(f"   ⚠️  не определён отступ в {check_id}")
        return text, False
    indent = first_item.group(1)

    new_items = f"{indent}- {new_ut}\n" + items
    new_block = block[: m.start()] + prefix + new_items + block[m.end():]
    new_text = text[:start] + new_block + text[end:]
    print(f"   ✅ {check_id}: '{new_ut}' вставлен")
    return new_text, True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="применить изменения (по умолчанию dry-run)")
    args = ap.parse_args()

    if not STORAGE_FILE.exists():
        raise SystemExit(f"❌ файл не найден: {STORAGE_FILE}")

    text = STORAGE_FILE.read_text(encoding="utf-8")
    original = text

    print(f"📄 {STORAGE_FILE}")
    for check_id, ut in REVERTS:
        text, _ = insert_ut(text, check_id, ut)

    if text == original:
        print("\n🔵 Изменений нет")
        return

    if args.apply:
        backup = STORAGE_FILE.with_suffix(STORAGE_FILE.suffix + ".bak_ut_revert")
        shutil.copy(STORAGE_FILE, backup)
        STORAGE_FILE.write_text(text, encoding="utf-8")
        print(f"\n✅ APPLIED. Backup: {backup.name}")
    else:
        print("\n🔵 DRY-RUN. Запусти с --apply чтобы применить")


if __name__ == "__main__":
    main()