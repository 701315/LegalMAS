#!/usr/bin/env python3
"""Mass-fix FAIL:D2 + WARN:D2 — приводит fact.description к v3:
   - если отсутствует "Fallback:" — добавляет шаблонную строку;
   - если длина > 80 и не folded — оборачивает в folded `>`.
   Сохраняет форматирование через ruamel.yaml.
"""
from pathlib import Path
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import FoldedScalarString

LEN_THRESHOLD = 80
DEFAULT_FALLBACK = 'Fallback: "Не установлено" / "Не удалось определить".'
SPECIAL_FALLBACKS = {
    # если у поля string_list
    "string_list": 'Fallback: [] / "Не удалось определить".',
}


def needs_d2(desc, ftype):
    """Определяет, нужно ли править."""
    if not isinstance(desc, str) or isinstance(desc, FoldedScalarString):
        return False
    if "Fallback:" in desc:
        # fallback есть, но desc может быть длинным и не folded
        return len(desc) > LEN_THRESHOLD
    return True


def fix_fact_field(field):
    desc = field.get("description")
    ftype = field.get("type", "string")
    if not needs_d2(desc, ftype):
        return False

    text = (desc or "").rstrip()
    if "Fallback:" not in text:
        fb = SPECIAL_FALLBACKS.get(ftype, DEFAULT_FALLBACK)
        if not text.endswith("."):
            text += "."
        # Склейка через \n — БЕЗ пустой строки; Fallback следующей строкой
        text = f"{text} {fb}"
    # Гарантируем ровно один trailing \n → ruamel выберет `>` (clip), не `>-`
    text = text.rstrip() + "\n"

    field["description"] = FoldedScalarString(text)
    return True


def process_file(path, yaml):
    doc = yaml.load(path)
    checks = doc.get("checks_v8") or doc.get("checks") or []
    count = 0
    for check in checks:
        extraction = check.get("extraction") or {}
        for f in extraction.get("fields") or []:
            if f.get("presentation") == "fact":
                if fix_fact_field(f):
                    count += 1
    if count:
        yaml.dump(doc, path)
    return count


def main(root=Path("playbooks/document_types")):
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)
    total_files, total_fixes = 0, 0
    for path in sorted(root.rglob("*.yaml")):
        try:
            n = process_file(path, yaml)
        except Exception as e:
            print(f"  !! {path}: {e}")
            continue
        if n:
            total_files += 1
            total_fixes += n
            print(f"  {path}: {n}")
    print(f"\nИтого: {total_fixes} полей в {total_files} файлах.")


if __name__ == "__main__":
    main()

