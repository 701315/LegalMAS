#!/usr/bin/env python3
"""Patch 2: ещё строже фильтр полей в extract_field_names_from_prompt."""
import re
import shutil
from pathlib import Path

PATH = Path("scripts/audit_dd_grid_full.py")
MARKER_V2 = "# PATCHED: field extraction v2"
MARKER_V3 = "# PATCHED: field extraction v3"

NEW_BLOCK = '''# PATCHED: field extraction v3
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
    "detailed", "custom", "market", "receiver", "guarantee",
})

_META_FIELDS = frozenset({
    "clause_ref", "quote", "page", "evidence", "evidence_items",
    "reason", "explanation", "notes",
})


def _looks_like_field(name: str) -> bool:
    """Поле должно содержать _, начинаться с lowercase, не быть метаданными
    или enum-значением, и не быть _display-полем (backend формирует их)."""
    if name in _ENUM_NOISE:
        return False
    if name in _META_FIELDS:
        return False
    if name.endswith("_display"):
        return False
    if "_" not in name:
        return False
    if name and name[0].isupper():
        return False
    if len(name) < 4:
        return False
    return True


def extract_field_names_from_prompt(prompt_text: str | None) -> set[str]:
    if not prompt_text:
        return set()
    names: set[str] = set()
    CHARS = r"[a-zA-Z][a-zA-Z0-9_]*"
    for match in re.finditer(rf"^\\s*\\d+\\.\\s+({CHARS})\\b", prompt_text, re.MULTILINE):
        names.add(match.group(1))
    for match in re.finditer(rf'"({CHARS})":\\s', prompt_text):
        names.add(match.group(1))
    for match in re.finditer(rf"^\\s*-\\s+({CHARS})\\s*[:=]", prompt_text, re.MULTILINE):
        names.add(match.group(1))
    for match in re.finditer(rf"^\\s*({CHARS})\\s+—", prompt_text, re.MULTILINE):
        names.add(match.group(1))
    for match in re.finditer(rf"^\\s*({CHARS}):\\s", prompt_text, re.MULTILINE):
        names.add(match.group(1))
    names = {n for n in names if _looks_like_field(n)}
    names -= KNOWN_METADATA_FIELD_NAMES
    return names
'''


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    if MARKER_V3 in text:
        print("✅ Патч v3 уже применён.")
        return
    if MARKER_V2 not in text:
        raise SystemExit("❌ Не найден маркер v2 — сначала запусти patch_audit_field_extraction.py")

    # Заменяем всё от маркера v2 до `def _check_meta`
    pattern = re.compile(
        r"# PATCHED: field extraction v2.*?(?=def _check_meta\()",
        re.DOTALL,
    )
    m = pattern.search(text)
    if not m:
        raise SystemExit("❌ Не найден блок v2 до _check_meta")

    new_text = text[:m.start()] + NEW_BLOCK + "\n\n" + text[m.end():]

    backup = PATH.with_suffix(PATH.suffix + ".bak_audit_patch_v2")
    shutil.copy(PATH, backup)
    PATH.write_text(new_text, encoding="utf-8")
    print(f"✅ Патч v3 применён. Backup: {backup.name}")


if __name__ == "__main__":
    main()
