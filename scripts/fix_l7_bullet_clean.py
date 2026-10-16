#!/usr/bin/env python3
"""Fix L7 v3: удаляет висящие строки 'present'/'missing'/'unclear'
после bullet про presence в <context_rules>.
Работает поверх v2-правок."""
import re
import sys
from pathlib import Path
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString


def is_orphan_presence_line(line):
    """Висящая строка — начинается с пробелов, потом кавычка, содержит 'present'/'missing'/'unclear' в начале."""
    stripped = line.lstrip()
    if not stripped or stripped.startswith("-"):
        return False
    if not stripped.startswith('"'):
        return False
    return ('"present"' in stripped or '"missing"' in stripped or '"unclear"' in stripped)


def fix_check(check):
    ext = check.get("extraction") or {}
    ps = ext.get("presence_signal") or {}
    pfield = ps.get("field")
    if not pfield:
        return None

    prompt = ext.get("llm_prompt_extraction")
    if not isinstance(prompt, str):
        return None

    m = re.search(r"(<context_rules>\n)(.*?)(\n\s*</context_rules>)", prompt, re.DOTALL)
    if not m:
        return None

    block = m.group(2)
    lines = block.split("\n")

    # Проходим: если текущая строка — bullet про presence,
    # следующие N висящих строк удаляем.
    new_lines = []
    skip_orphans = False
    for line in lines:
        if skip_orphans and is_orphan_presence_line(line):
            continue
        skip_orphans = False
        if line.strip().startswith("-") and pfield in line:
            skip_orphans = True
        new_lines.append(line)

    new_block = "\n".join(new_lines)
    if new_block == block:
        return False

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
        print("Использование: python3 fix_l7_v3.py <file.yaml>")
        sys.exit(1)
    main(sys.argv[1])
