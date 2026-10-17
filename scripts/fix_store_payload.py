#!/usr/bin/env python3
"""Fix store_payload:
- гарантирует наличие store_payload: true в extraction;
- переносит его в конец (последним ключом).
"""
from pathlib import Path
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap


def fix_ext(ext):
    if ext is None:
        return False
    keys = list(ext.keys())
    # Уже правильно?
    if "store_payload" in ext and ext.get("store_payload") is True and keys[-1] == "store_payload":
        return False
    # Пересобираем: всё кроме store_payload — в исходном порядке, store_payload в конец
    new = CommentedMap()
    for k in keys:
        if k == "store_payload":
            continue
        new[k] = ext[k]
    new["store_payload"] = True
    ext.clear()
    for k, v in new.items():
        ext[k] = v
    return True


def main(root=Path("playbooks/document_types")):
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)
    fixed = 0
    for p in sorted(root.rglob("*.yaml")):
        try:
            doc = yaml.load(p)
        except Exception as e:
            print(f"  !! {p}: {e}")
            continue
        local = 0
        for c in (doc.get("checks_v8") or doc.get("checks") or []):
            if fix_ext(c.get("extraction")):
                local += 1
                print(f"  ✓ {p.name}:{c['id']}")
        if local:
            yaml.dump(doc, p)
            fixed += local
    print(f"\nИсправлено: {fixed}")


if __name__ == "__main__":
    main()
