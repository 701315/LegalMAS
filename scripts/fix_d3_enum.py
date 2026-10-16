#!/usr/bin/env python3
"""Mass-fix WARN:D3 — добавляет "Внутреннее enum-поле." к signal.description,
   если в описании нет обоих маркеров ('внутренн' и 'enum').
   Пропускает presence-поле (у него отдельное правило P5).
"""
from pathlib import Path
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import FoldedScalarString

SUFFIX = "Внутреннее enum-поле."


def fix_signal_field(field, pfield_name):
    name = field.get("name")
    if name == pfield_name:
        return False
    desc = field.get("description") or ""
    dl = desc.lower()
    if "внутренн" in dl and "enum" in dl:
        return False

    text = desc.rstrip()
    if not text:
        text = f"{SUFFIX}"
    elif text.endswith("."):
        text = f"{text} {SUFFIX}"
    else:
        text = f"{text}. {SUFFIX}"
    field["description"] = text
    return True


def process_file(path, yaml):
    doc = yaml.load(path)
    checks = doc.get("checks_v8") or doc.get("checks") or []
    count = 0
    for check in checks:
        extraction = check.get("extraction") or {}
        ps = extraction.get("presence_signal") or {}
        pfield = ps.get("field")
        for f in extraction.get("fields") or []:
            if f.get("presentation") == "signal":
                if fix_signal_field(f, pfield):
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

    