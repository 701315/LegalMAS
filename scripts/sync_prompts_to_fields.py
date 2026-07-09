#!/usr/bin/env python3
import re
import yaml
from pathlib import Path

ROOT = Path("/home/vladi/projects/LegalMAS/playbooks/document_types")
KNOWN_META = {"evidence", "evidence_items", "reason", "explanation", "notes"}

def fix_file(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
        docs = list(yaml.safe_load_all(text))
    except Exception:
        return False

    replacements = set()

    def walk(v):
        if isinstance(v, dict):
            if "id" in v and "extraction" in v:
                process_check(v)
            for child in v.values():
                walk(child)
        elif isinstance(v, list):
            for child in v:
                walk(child)

    def process_check(check):
        ext = check.get("extraction", {})
        if not isinstance(ext, dict): return
        fields = ext.get("fields", [])
        if not isinstance(fields, list): return
        
        # 1. Declared fields
        declared = {f.get("name") for f in fields if isinstance(f, dict) and f.get("name")}

        # 2. Prompt fields
        prompt_fields = set()
        t1 = check.get("llm", {}).get("prompt_template", "")
        t2 = ext.get("llm_prompt_extraction", "")
        for t in (t1, t2):
            if not t: continue
            for m in re.finditer(r'^\s*\d+\.\s+([a-z][a-z0-9_]*)\b', t, re.MULTILINE):
                prompt_fields.add(m.group(1))
            for m in re.finditer(r'"([a-z][a-z0-9_]*)":\s', t):
                prompt_fields.add(m.group(1))
        
        prompt_fields -= KNOWN_META

        # 3. Find mismatches
        in_fields_not_prompt = declared - prompt_fields
        in_prompt_not_fields = prompt_fields - declared

        # 4. Pair old -> new
        for old in in_prompt_not_fields:
            for suffix in ("_value", "_code", "_details", "_status"):
                candidate = old + suffix
                if candidate in in_fields_not_prompt:
                    replacements.add((old, candidate))
                    break

    for doc in docs:
        walk(doc)

    if not replacements:
        return False

    # Apply replacements
    new_text = text
    for old, new in replacements:
        # JSON keys: "old": -> "new":
        new_text = re.sub(rf'(?<![a-zA-Z0-9_])"{re.escape(old)}"(\s*:)', f'"{new}"\\1', new_text)
        # Numbered lists: 1. old — -> 1. new —
        new_text = re.sub(rf'(\d+\.\s+){re.escape(old)}(\s+[-—:])', rf'\1{new}\2', new_text)
        # Bullet list edge cases: - old: -> - new:
        new_text = re.sub(rf'(?m)^(\s*-\s*){re.escape(old)}(\s*:)', rf'\1{new}\2', new_text)

    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        print(f"\n✅ {path.name} (обновлено пар: {len(replacements)})")
        for o, n in sorted(replacements):
            print(f"    '{o}' → '{n}'")
        return True

    return False

def main():
    changed = 0
    for p in ROOT.rglob("*.yaml"):
        if fix_file(p):
            changed += 1
    for p in ROOT.rglob("*.yml"):
        if fix_file(p):
            changed += 1
            
    print(f"\nВсего исправлено файлов: {changed}")

if __name__ == "__main__":
    main()


    