#!/usr/bin/env python3
import sys
import json
from pathlib import Path

import yaml

ROOT = Path("/srv/steloom-dev/playbooks/global_checks")


def load_yaml(path: Path):
    text = path.read_text(encoding="utf-8")
    docs = list(yaml.safe_load_all(text))
    docs = [d for d in docs if d is not None]
    return docs


def norm_visible_fields(fields):
    result = []
    if not isinstance(fields, list):
        return result

    for f in fields:
        if not isinstance(f, dict):
            continue
        if f.get("display_in_grid") is True:
            result.append({
                "name": f.get("name"),
                "label": f.get("label"),
                "priority": f.get("display_priority"),
                "presentation": f.get("presentation"),
            })
    result.sort(key=lambda x: (x["priority"] is None, x["priority"]))
    return result


def extract_check(doc, path: Path):
    if not isinstance(doc, dict):
        return None

    check_id = doc.get("id")
    name = doc.get("name")

    # Это не похоже на global check
    if not check_id or not name:
        return None

    fields = doc.get("extraction", {}).get("fields", [])
    visible_fields = norm_visible_fields(fields)

    return {
        "id": check_id,
        "name": name,
        "group": doc.get("group"),
        "severity": doc.get("severity"),
        "detector_type": doc.get("detector_type"),
        "ui_mode": doc.get("ui_mode"),
        "doc_types": doc.get("doc_types"),
        "visible_fields_count": len(visible_fields),
        "visible_fields": visible_fields,
        "path": str(path),
    }


def main():
    if not ROOT.exists():
        print(f"ERROR: folder not found: {ROOT}", file=sys.stderr)
        sys.exit(1)

    rows = []
    errors = []

    for path in sorted(ROOT.rglob("*.y*ml")):
        try:
            docs = load_yaml(path)
        except Exception as e:
            errors.append((str(path), str(e)))
            continue

        for doc in docs:
            row = extract_check(doc, path)
            if row:
                rows.append(row)

    rows.sort(key=lambda x: ((x["group"] or ""), x["id"]))

    print("=" * 140)
    print(f"GLOBAL CHECKS FOUND: {len(rows)}")
    print("=" * 140)
    print()

    for i, row in enumerate(rows, 1):
        print(f"{i:>3}. {row['id']}")
        print(f"     name:           {row['name']}")
        print(f"     group:          {row['group']}")
        print(f"     severity:       {row['severity']}")
        print(f"     detector_type:  {row['detector_type']}")
        print(f"     ui_mode:        {row['ui_mode']}")
        print(f"     doc_types:      {row['doc_types']}")
        print(f"     path:           {row['path']}")
        print(f"     visible_fields: {row['visible_fields_count']}")

        for vf in row["visible_fields"]:
            print(
                f"       - {vf['name']} | label={vf['label']!r} | "
                f"priority={vf['priority']} | presentation={vf['presentation']}"
            )
        print()

    if errors:
        print("=" * 140)
        print("YAML PARSE ERRORS")
        print("=" * 140)
        for path, err in errors:
            print(f"- {path}: {err}")

    print("=" * 140)
    print("JSON SUMMARY")
    print("=" * 140)
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


    