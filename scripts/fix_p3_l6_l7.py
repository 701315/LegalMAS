#!/usr/bin/env python3
"""Fix P3 + L6 + L7 в одном проходе.

P3: presence_signal.present/missing/unclear -> *_values: [...]
L6: "0. Сначала определи X_presence:" -> "0. X_presence:"
L7: добавить bullet про п.0 в <context_rules>
"""
import re
import sys
from pathlib import Path
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.scalarstring import LiteralScalarString


def fix_presence(check):
    ext = check.get("extraction") or {}
    ps = ext.get("presence_signal")
    if not ps:
        return False
    if "present_values" in ps and "missing_values" in ps and "unclear_values" in ps:
        return False
    if "present" in ps or "missing" in ps or "unclear" in ps:
        new_ps = CommentedMap()
        new_ps["field"] = ps.get("field")
        new_ps["present_values"] = ["present"]
        new_ps["missing_values"] = ["missing"]
        new_ps["unclear_values"] = ["unclear"]
        ext["presence_signal"] = new_ps
        return True
    return False


def fix_l6(check):
    ext = check.get("extraction") or {}
    ps = ext.get("presence_signal") or {}
    pfield = ps.get("field")
    if not pfield:
        return False
    prompt = ext.get("llm_prompt_extraction")
    if not isinstance(prompt, str):
        return False
    if f"0. {pfield}:" in prompt:
        return False
    old = f"0. Сначала определи {pfield}:"
    if old in prompt:
        new_prompt = prompt.replace(old, f"0. {pfield}:", 1)
        ext["llm_prompt_extraction"] = LiteralScalarString(new_prompt)
        return True
    return False


def fix_l7(check):
    ext = check.get("extraction") or {}
    ps = ext.get("presence_signal") or {}
    pfield = ps.get("field")
    if not pfield:
        return False
    prompt = ext.get("llm_prompt_extraction")
    if not isinstance(prompt, str):
        return False
    if "по правилу из пункта 0" in prompt:
        return False
    m = re.search(r"(<context_rules>\n)(.*?)(\n\s*</context_rules>)", prompt, re.DOTALL)
    if not m:
        return False
    block = m.group(2)
    first_line = block.split("\n")[0]
    indent = first_line[:len(first_line) - len(first_line.lstrip())]
    bullet = f"- Перед остальными полями заполни {pfield} по правилу из пункта 0 task."
    new_block = indent + bullet + "\n" + block
    new_prompt = prompt[:m.start(2)] + new_block + prompt[m.end(2):]
    ext["llm_prompt_extraction"] = LiteralScalarString(new_prompt)
    return True


def main(path_str):
    path = Path(path_str)
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)

    doc = yaml.load(path)
    p3 = l6 = l7 = 0
    for c in (doc.get("checks_v8") or doc.get("checks") or []):
        cid = c.get("id")
        if fix_presence(c):
            p3 += 1
            print(f"  ✓ P3 {cid}")
        if fix_l6(c):
            l6 += 1
            print(f"  ✓ L6 {cid}")
        if fix_l7(c):
            l7 += 1
            print(f"  ✓ L7 {cid}")

    if p3 or l6 or l7:
        yaml.dump(doc, path)
        print(f"\nИтого: P3={p3}  L6={l6}  L7={l7}")
    else:
        print("Нет чеков, требующих правки")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python3 fix_p3_l6_l7.py <file.yaml>")
        sys.exit(1)
    main(sys.argv[1])
