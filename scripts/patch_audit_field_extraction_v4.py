#!/usr/bin/env python3
"""
Patch v4: filter backend-only fields (*_display) из declared,
и отсеивать известный enum-мусор из in_prompt.

Применяется к audit_prompt_field_sync, не меняет extract_field_names_from_prompt.
"""
import re
import shutil
from pathlib import Path

PATH = Path("scripts/audit_dd_grid_full.py")
MARKER = "# PATCHED: sync v4"

OLD_BLOCK = '''def audit_prompt_field_sync(*, file_path: Path, check_node: dict[str, Any]) -> list[Finding]:
    extraction = check_node.get("extraction")
    if not isinstance(extraction, dict) or extraction.get("enabled") is False:
        return []
    fields = normalize_fields(extraction.get("fields"))
    if not fields:
        return []
    prompt_text = extraction.get("llm_prompt_extraction")
    if not isinstance(prompt_text, str) or not prompt_text.strip():
        return []
    cid, cn = _check_meta(check_node)
    declared = {f.name for f in fields} - KNOWN_METADATA_FIELD_NAMES
    in_prompt = extract_field_names_from_prompt(prompt_text)
'''

NEW_BLOCK = '''# PATCHED: sync v4
# Поля, которые backend формирует сам (из *_code), не должны быть в промпте.
_BACKEND_ONLY_SUFFIXES = ("_display",)
# Явный мусор, который регулярка может поймать в тексте, но это не поля.
_PROMPT_NOISE = frozenset({
    "clause_ref", "quote", "page", "evidence", "evidence_items",
    "reason", "explanation", "notes", "fallback", "status", "term",
    "agent", "regime", "charter", "personal",
})


def _is_backend_only(name: str) -> bool:
    return any(name.endswith(s) for s in _BACKEND_ONLY_SUFFIXES)


def audit_prompt_field_sync(*, file_path: Path, check_node: dict[str, Any]) -> list[Finding]:
    extraction = check_node.get("extraction")
    if not isinstance(extraction, dict) or extraction.get("enabled") is False:
        return []
    fields = normalize_fields(extraction.get("fields"))
    if not fields:
        return []
    prompt_text = extraction.get("llm_prompt_extraction")
    if not isinstance(prompt_text, str) or not prompt_text.strip():
        return []
    cid, cn = _check_meta(check_node)
    # declared: убираем metadata + backend-only (*_display)
    declared = {
        f.name for f in fields
        if not _is_backend_only(f.name)
    } - KNOWN_METADATA_FIELD_NAMES
    # in_prompt: убираем backend-only и явный мусор
    in_prompt = extract_field_names_from_prompt(prompt_text)
    in_prompt = {
        n for n in in_prompt
        if not _is_backend_only(n) and n not in _PROMPT_NOISE
    }
'''


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    if MARKER in text:
        print("✅ Патч v4 уже применён.")
        return
    if OLD_BLOCK not in text:
        raise SystemExit("❌ Не найден исходный блок audit_prompt_field_sync")

    new_text = text.replace(OLD_BLOCK, NEW_BLOCK)

    backup = PATH.with_suffix(PATH.suffix + ".bak_audit_patch_v3")
    shutil.copy(PATH, backup)
    PATH.write_text(new_text, encoding="utf-8")
    print(f"✅ Патч v4 применён. Backup: {backup.name}")


if __name__ == "__main__":
    main()
