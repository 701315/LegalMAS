#!/usr/bin/env python3
"""Fix L3: конвертирует bullet-список в <edge_cases> в нумерованный (1.-4.).
Если bullet'ов >4 — оставляет первые 4.
Если <4 — дополняет дефолтными.
"""
import re
import sys
from pathlib import Path
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString

DEFAULT_4 = [
    "Полное отсутствие темы. Если фрагментов по теме нет, все status-поля = \"not_defined\", все details = \"Данные не определены\".",
    "Неполное раскрытие. Общая фраза или отсылка без конкретики; соответствующие status-поля = \"not_defined\".",
    "Противоречие между фрагментами. presence = \"unclear\"; соответствующие details = \"Не удалось определить\".",
    "Специфика темы. Прямое исключение или отсылка на внешний документ; статусы = \"not_defined\".",
]


def split_bullets(block):
    lines = block.split("\n")
    bullets = []
    current = None
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("- ") or stripped.startswith("* "):
            if current is not None:
                bullets.append(current)
            indent = line[:len(line) - len(stripped)]
            current = {"indent": indent, "lines": [stripped[2:]]}
        elif current is not None:
            current["lines"].append(line)
    if current is not None:
        bullets.append(current)
    return bullets


def renumber_bullets(block):
    if re.search(r"^\s*1\.", block, re.MULTILINE):
        return None
    bullets = split_bullets(block)
    if not bullets:
        return None

    indent = bullets[0]["indent"] if bullets else ""

    result = []
    for i, b in enumerate(bullets[:4], start=1):
        b_indent = b["indent"] or indent
        text_lines = b["lines"]
        if not text_lines:
            continue
        result.append(f"{b_indent}{i}. {text_lines[0].rstrip()}")
        for cont in text_lines[1:]:
            result.append(cont.rstrip())

    for i in range(len(bullets), 4):
        result.append("")
        result.append(f"{indent}{i+1}. {DEFAULT_4[i]}")

    return "\n".join(result)


def fix_check(check):
    ext = check.get("extraction") or {}
    prompt = ext.get("llm_prompt_extraction")
    if not isinstance(prompt, str):
        return False

    m = re.search(r"(<edge_cases>\n)(.*?)(\n\s*</edge_cases>)", prompt, re.DOTALL)
    if not m:
        return False

    old_block = m.group(2)
    new_block = renumber_bullets(old_block)
    if not new_block or new_block == old_block:
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
        print(f"\nИсправлено L3: {count}")
    else:
        print("Нет чеков, требующих правки")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python3 fix_l3_bullet_to_number.py <file.yaml>")
        sys.exit(1)
    main(sys.argv[1])
