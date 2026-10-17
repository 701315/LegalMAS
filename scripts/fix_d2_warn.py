#!/usr/bin/env python3
"""Fix WARN:D2 — добавляет Fallback к fact.description, где его нет.
Не зависит от длины, обрабатывает и уже-folded описания."""
import sys
from pathlib import Path
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import FoldedScalarString

DEFAULT_FB = 'Fallback: "Не установлено" / "Не удалось определить".'
LIST_FB = 'Fallback: [] / "Не удалось определить".'


def fix_fact_field(field):
    desc = field.get("description")
    text = str(desc) if desc is not None else ""
    if "fallback:" in text.lower():
        return False
    ftype = field.get("type", "string")
    fb = LIST_FB if ftype in ("string_list", "array") else DEFAULT_FB
    text = text.rstrip()
    if text and not text.endswith("."):
        text += "."
    new_text = (text + " " + fb).strip() + "\n"
    field["description"] = FoldedScalarString(new_text)
    return True


def process_file(path, yaml):
    doc = yaml.load(path)
    count = 0
    for c in (doc.get("checks_v8") or doc.get("checks") or []):
        ext = c.get("extraction") or {}
        for f in ext.get("fields") or []:
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
    tf, tx = 0, 0
    for p in sorted(root.rglob("*.yaml")):
        try:
            n = process_file(p, yaml)
        except Exception as e:
            print(f"  !! {p}: {e}")
            continue
        if n:
            tf += 1
            tx += n
            print(f"  {p.name}: {n}")
    print(f"\nИтого: {tx} полей в {tf} файлах.")


if __name__ == "__main__":
    main()
