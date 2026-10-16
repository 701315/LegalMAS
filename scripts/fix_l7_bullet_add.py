#!/usr/bin/env python3
"""Fix L7: добавляет первый bullet про агрегацию presence в <context_rules>.
Работает только для чеков, где отсутствует ссылка на правило из п.0 task.
Сохраняет форматирование через ruamel.yaml."""
import re
import sys
from pathlib import Path
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString


def fix_check(check):
    ext = check.get("extraction") or {}
    ps = ext.get("presence_signal") or {}
    pfield = ps.get("field")
    if not pfield:
        return False

    prompt = ext.get("llm_prompt_extraction")
    if not isinstance(prompt, str):
        return False

    m = re.search(r"(<context_rules>\n)(.*?)(\n\s*</context_rules>)", prompt, re.DOTALL)
    if not m:
        return False

    block = m.group(2)
    if "по правилу из пункта 0" in block:
        return False

    new_bullet = f"- Перед остальными полями заполни {pfield} по правилу из пункта 0 task."

    first_line = block.split("\n")[0]
    indent = first_line[:len(first_line) - len(first_line.lstrip())]

    new_block = indent + new_bullet + "\n" + block
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
    count = 0
    for c in (doc.get("checks_v8") or doc.get("checks") or []):
        if fix_check(c):
            count += 1
            print(f"  ✓ {c.get('id')}")

    if count:
        yaml.dump(doc, path)
        print(f"\nИсправлено: {count}")
    else:
        print("Нет чеков, требующих правки")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python3 fix_l7.py <file.yaml>")
        sys.exit(1)
    main(sys.argv[1])
