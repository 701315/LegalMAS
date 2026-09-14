#!/usr/bin/env python3
"""
Patch v5: whitelist-based filter.

1. Собираем все field_name из extraction.fields всех YAML (один раз).
2. Фильтруем in_prompt: только токены, которые встречаются как field_name
   хотя бы в одном чеке.
3. declared остаётся как в v4 (без *_display и metadata).
4. Fallback-регистр: upper-case токены отбрасываются.
"""
import re
import shutil
from pathlib import Path

PATH = Path("scripts/audit_dd_grid_full.py")
MARKER = "# PATCHED: whitelist v5"

WHITELIST_HELPER = '''# PATCHED: whitelist v5
_ALL_FIELD_NAMES_CACHE: set[str] | None = None


def _build_all_field_names_whitelist(root_paths: tuple[Path, ...]) -> set[str]:
    """Один раз собирает все field_name из extraction.fields всех YAML."""
    global _ALL_FIELD_NAMES_CACHE
    if _ALL_FIELD_NAMES_CACHE is not None:
        return _ALL_FIELD_NAMES_CACHE
    names: set[str] = set()
    try:
        import yaml as _yaml
    except ImportError:
        _ALL_FIELD_NAMES_CACHE = names
        return names
    for root in root_paths:
        root = Path(root)
        if not root.exists():
            continue
        for p in root.rglob("*.yaml"):
            try:
                d = _yaml.safe_load(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            for c in (d or {}).get("checks_v8") or []:
                fields = (c.get("extraction") or {}).get("fields") or []
                for f in fields:
                    if isinstance(f, dict) and isinstance(f.get("name"), str):
                        names.add(f["name"])
    _ALL_FIELD_NAMES_CACHE = names
    return names
'''

# Найти конец блока v4
V4_MARKER = "# PATCHED: sync v4"


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    if MARKER in text:
        print("✅ Патч v5 уже применён.")
        return
    if V4_MARKER not in text:
        raise SystemExit("❌ Не найден v4 — сначала примени patch_audit_field_extraction_v4.py")

    # 1. Вставить whitelist-helper перед `def audit_prompt_field_sync`
    target = "def audit_prompt_field_sync("
    if target not in text:
        raise SystemExit("❌ Не найден audit_prompt_field_sync")
    text = text.replace(target, WHITELIST_HELPER + "\n\n" + target, 1)

    # 2. Изменить сбор in_prompt внутри audit_prompt_field_sync
    old = """    # in_prompt: убираем backend-only и явный мусор
    in_prompt = extract_field_names_from_prompt(prompt_text)
    in_prompt = {
        n for n in in_prompt
        if not _is_backend_only(n) and n not in _PROMPT_NOISE
    }
"""
    new = """    # in_prompt: фильтр по whitelist всех field_name
    in_prompt = extract_field_names_from_prompt(prompt_text)
    in_prompt = {
        n for n in in_prompt
        if not _is_backend_only(n) and n not in _PROMPT_NOISE
    }
    # whitelist: оставляем только токены, встречающиеся как field_name где-либо в YAML
    whitelist = _build_all_field_names_whitelist(
        tuple(Path(r) for r in (getattr(file_path, "_roots", None) or []))
    )
    if whitelist:
        in_prompt &= whitelist
"""
    if old not in text:
        raise SystemExit("❌ Не найден блок in_prompt из v4")
    text = text.replace(old, new, 1)

    backup = PATH.with_suffix(PATH.suffix + ".bak_audit_patch_v4")
    shutil.copy(PATH, backup)
    PATH.write_text(text, encoding="utf-8")
    print(f"✅ Патч v5 применён. Backup: {backup.name}")


if __name__ == "__main__":
    main()
