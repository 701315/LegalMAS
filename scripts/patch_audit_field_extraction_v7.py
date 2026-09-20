#!/usr/bin/env python3
"""Patch v7: CHARS должен включать заглавные (party_A_*, good_A_*, object_A_*)."""
import re
import shutil
from pathlib import Path

PATH = Path("scripts/audit_dd_grid_full.py")
MARKER = "# PATCHED: field extraction v7"


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    if MARKER in text:
        print("✅ Патч v7 уже применён.")
        return

    # Заменяем CHARS на версию с заглавными
    old = '    CHARS = r"[a-z][a-z0-9_]*"\n'
    new = '    CHARS = r"[a-zA-Z][a-zA-Z0-9_]*"  # PATCHED: field extraction v7\n'
    if old not in text:
        raise SystemExit("❌ Не найден CHARS в v6")

    text = text.replace(old, new, 1)

    backup = PATH.with_suffix(PATH.suffix + ".bak_audit_patch_v6")
    shutil.copy(PATH, backup)
    PATH.write_text(text, encoding="utf-8")
    print(f"✅ Патч v7 применён. Backup: {backup.name}")


if __name__ == "__main__":
    main()
