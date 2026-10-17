#!/usr/bin/env python3
"""Fix WARN:P5 — добавляет суффикс «Внутреннее агрегатное signal-поле.»
к presence.description, где его нет."""
from pathlib import Path
from ruamel.yaml import YAML

SUFFIX = "Внутреннее агрегатное signal-поле."


def fix_presence(check):
    ext = check.get("extraction") or {}
    ps = ext.get("presence_signal") or {}
    pfield = ps.get("field")
    if not pfield:
        return False
    for f in ext.get("fields") or []:
        if f.get("name") == pfield:
            desc = str(f.get("description") or "").rstrip()
            dl = desc.lower()
            if "signal-поле" in dl and "агрегатное" in dl:
                return False
            if not desc:
                new = SUFFIX
            elif desc.endswith("."):
                new = desc + " " + SUFFIX
            else:
                new = desc + ". " + SUFFIX
            f["description"] = new
            return True
    return False


def process_file(path, yaml):
    doc = yaml.load(path)
    count = 0
    for c in (doc.get("checks_v8") or doc.get("checks") or []):
        if fix_presence(c):
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
    print(f"\nИтого: {tx} presence в {tf} файлах.")


if __name__ == "__main__":
    main()
