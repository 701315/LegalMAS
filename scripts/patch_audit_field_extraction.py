#!/usr/bin/env python3
"""Patch audit_dd_grid_full.py: extract_field_names_from_prompt.

Bug: regex charset [a-z] не пропускает заглавные буквы (party_A_*, good_A_*,
object_A_*, vehicle_A_*). Все эти поля ошибочно попадают в (b) как
"не найдены в промпте".

Fix:
  • расширен charset до [a-zA-Z]
  • добавлены паттерны для <task> bullet-формата (`- field:` и `field —`)
  • фильтр enum-шума: поля без `_` и короткие токены отсеиваются
"""
import re
import shutil
from pathlib import Path

PATH = Path("scripts/audit_dd_grid_full.py")
MARKER = "# PATCHED: field extraction v2"

NEW_FUNC = '''# PATCHED: field extraction v2
_ENUM_NOISE = frozenset({
    "yes", "no", "not_defined", "unclear", "mixed", "present", "missing",
    "not_specified", "not_applicable", "not_mentioned", "not_required",
    "required", "optional", "true", "false", "defined", "partial",
    "general", "prohibited", "specified", "excluded", "preserved",
    "restricted", "other", "shared", "none", "unknown", "absent",
    "applicable", "included", "cash", "gost", "tu", "na", "n_a",
})


def _looks_like_field(name: str) -> bool:
    """Отсеиваем короткие токены и enum-значения."""
    if name in _ENUM_NOISE:
        return False
    if "_" not in name and len(name) < 6:
        return False
    return True


def extract_field_names_from_prompt(prompt_text: str | None) -> set[str]:
    if not prompt_text:
        return set()
    names: set[str] = set()
    CHARS = r"[a-zA-Z][a-zA-Z0-9_]*"
    # 1. `N. field_name` (нумерованный список) — charset расширен
    for match in re.finditer(rf"^\\s*\\d+\\.\\s+({CHARS})\\b", prompt_text, re.MULTILINE):
        names.add(match.group(1))
    # 2. `"field_name": ` (JSON-пример) — charset расширен
    for match in re.finditer(rf'"({CHARS})":\\s', prompt_text):
        names.add(match.group(1))
    # 3. `- field_name:` / `- field_name =` (bullet)
    for match in re.finditer(rf"^\\s*-\\s+({CHARS})\\s*[:=]", prompt_text, re.MULTILINE):
        names.add(match.group(1))
    # 4. `field_name — ...` (тире в <task>)
    for match in re.finditer(rf"^\\s*({CHARS})\\s+—", prompt_text, re.MULTILINE):
        names.add(match.group(1))
    # 5. `field_name: ` без дефиса и номера
    for match in re.finditer(rf"^\\s*({CHARS}):\\s", prompt_text, re.MULTILINE):
        names.add(match.group(1))

    names = {n for n in names if _looks_like_field(n)}
    names -= KNOWN_METADATA_FIELD_NAMES
    return names
'''


def main() -> None:
    text = PATH.read_text(encoding="utf-8")

    if MARKER in text:
        print("✅ Патч уже применён.")
        return

    # Старая функция extract_field_names_from_prompt
    pattern = re.compile(
        r"def extract_field_names_from_prompt\(prompt_text: str \| None\) -> set\[str\]:\n"
        r"(?:    .*\n)+",
        re.MULTILINE,
    )
    m = pattern.search(text)
    if not m:
        raise SystemExit("❌ Не найдена исходная extract_field_names_from_prompt")

    new_text = text[:m.start()] + NEW_FUNC + text[m.end():]

    backup = PATH.with_suffix(PATH.suffix + ".bak_audit_patch")
    shutil.copy(PATH, backup)
    PATH.write_text(new_text, encoding="utf-8")
    print(f"✅ Патч применён. Backup: {backup.name}")


if __name__ == "__main__":
    main()

    