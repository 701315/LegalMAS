#!/usr/bin/env python3
"""Patch v6: правильный regex для extract_field_names_from_prompt.

Проблемы v1-v4:
  • `\d+\.\s+` требует пробел после точки — теряет `3.field_name`
  • НЕ ловит второй `field2` в `field1 / field2`
  • НЕ ловит `field — описание` без номера
"""
import re
import shutil
from pathlib import Path

PATH = Path("scripts/audit_dd_grid_full.py")
MARKER = "# PATCHED: field extraction v6"

NEW_FUNC = '''# PATCHED: field extraction v6
_ENUM_NOISE = frozenset({
    "yes", "no", "not_defined", "unclear", "mixed", "present", "missing",
    "not_specified", "not_applicable", "not_mentioned", "not_required",
    "required", "optional", "true", "false", "defined", "partial",
    "general", "prohibited", "specified", "excluded", "preserved",
    "restricted", "other", "shared", "none", "unknown", "absent",
    "applicable", "included", "cash", "gost", "tu", "na", "n_a",
    "allowed", "allowed_with_consent", "explicitly_none", "consent_present",
    "consent_required", "not_married_confirmed", "contract_specified",
    "percent_per_day", "fixed_amount", "third_party", "specific",
    "limited", "movable", "real_estate", "listed", "perpetual", "notarized",
    "detailed", "custom", "market", "receiver", "guarantee", "fallback",
    "restriction_scope", "full_ban",
})

_METADATA = frozenset({
    "evidence", "clause_ref", "quote", "page", "reason", "explanation", "notes",
})


def _looks_like_field(name: str) -> bool:
    if name in _ENUM_NOISE or name in _METADATA:
        return False
    if name.endswith("_display"):
        return False
    if "_" not in name:
        return False
    if name and name[0].isupper():
        return False
    return True


def extract_field_names_from_prompt(prompt_text: str | None) -> set[str]:
    if not prompt_text:
        return set()
    names: set[str] = set()
    CHARS = r"[a-z][a-z0-9_]*"
    # 1. `N. field_name` или `N.field_name` (пробел после точки — опционален)
    for m in re.finditer(rf"^\\s*\\d+\\.\\s*({CHARS})\\b", prompt_text, re.MULTILINE):
        names.add(m.group(1))
    # 2. `N. field_a / field_b` — второй через /
    for m in re.finditer(rf"^\\s*\\d+\\.\\s*{CHARS}\\s*/\\s*({CHARS})\\b",
                         prompt_text, re.MULTILINE):
        names.add(m.group(1))
    # 3. `- field_name:` / `- field_name —` / `- field_name =`
    for m in re.finditer(rf"^\\s*-\\s*({CHARS})\\s*[:=—]", prompt_text, re.MULTILINE):
        names.add(m.group(1))
    # 4. `"field_name":` (JSON-пример) — с любым регистром внутри
    for m in re.finditer(rf'"([a-zA-Z][a-zA-Z0-9_]*)"\\s*:', prompt_text):
        names.add(m.group(1))
    # 5. `field_name — описание` (без номера)
    for m in re.finditer(rf"^\\s*({CHARS})\\s+—", prompt_text, re.MULTILINE):
        names.add(m.group(1))

    names = {n for n in names if _looks_like_field(n)}
    names -= KNOWN_METADATA_FIELD_NAMES
    return names
'''


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    if MARKER in text:
        print("✅ Патч v6 уже применён.")
        return

    # Заменяем от начала v2/v3-блока (если есть) до `def _check_meta(`
    pattern = re.compile(
        r"(# PATCHED: field extraction v[23].*?\n)?def extract_field_names_from_prompt"
        r"\([^)]*\)[^:]*:\n(?:[ \t]+.*\n|\n)*?(?=\ndef |\n# ─|class )",
        re.MULTILINE,
    )
    m = pattern.search(text)
    if not m:
        raise SystemExit("❌ Не найден extract_field_names_from_prompt")

    new_text = text[:m.start()] + NEW_FUNC + "\n" + text[m.end():]

    backup = PATH.with_suffix(PATH.suffix + ".bak_audit_patch_v5")
    shutil.copy(PATH, backup)
    PATH.write_text(new_text, encoding="utf-8")
    print(f"✅ Патч v6 применён. Backup: {backup.name}")


if __name__ == "__main__":
    main()
