#!/usr/bin/env python3
"""Fix L7 v2: заменяет существующий bullet про presence на корректный,
либо добавляет новый, если старого нет. Сохраняет formatting через ruamel."""
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
        return None

    prompt = ext.get("llm_prompt_extraction")
    if not isinstance(prompt, str):
        return None

    m = re.search(r"(<context_rules>\n)(.*?)(\n\s*</context_rules>)", prompt, re.DOTALL)
    if not m:
        return None

    block = m.group(2)
    lines = block.split("\n")

    # Ищем любую строку, начинающуюся с bullet и содержащую <pfield>
    # (это либо старый bullet про presence, либо уже правильный)
    correct_line = f"- Перед остальными полями заполни {pfield} по правилу из пункта 0 task."

    def is_presence_bullet(line):
        stripped = line.strip()
        return stripped.startswith("-") and pfield in stripped

    found = False
    new_lines = []
    for line in lines:
        if is_presence_bullet(line):
            if found:
                # второй bullet про presence — удаляем (дубликат)
                continue
            if correct_line.strip() in line.strip():
                # уже правильный — оставляем как есть
                new_lines.append(line)
                found = True
            else:
                # старый/неправильный — заменяем (сохраняя indent)
                indent = line[:len(line) - len(line.lstrip())]
                new_lines.append(indent + correct_line)
                found = True
        else:
            new_lines.append(line)

    if not found:
        # Бullet'а про presence вообще не было — добавляем в начало
        first_line = lines[0] if lines else ""
        indent = first_line[:len(first_line) - len(first_line.lstrip())] or ""
        new_lines = [indent + correct_line] + lines

    new_block = "\n".join(new_lines)
    if new_block == block:
        return False  # ничего не менялось

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
        r = fix_check(c)
        if r:
            count += 1
            print(f"  ✓ {c.get('id')}")

    if count:
        yaml.dump(doc, path)
        print(f"\nИсправлено: {count}")
    else:
        print("Нет чеков, требующих правки")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python3 fix_l7_v2.py <file.yaml>")
        sys.exit(1)
    main(sys.argv[1])
