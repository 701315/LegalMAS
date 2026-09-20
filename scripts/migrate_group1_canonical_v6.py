#!/usr/bin/env python3
"""v6-fixed: разделить <rules> на <context_rules> + <output_expectations>,
сохраняя исходный отступ (8 пробелов в YAML block scalar)."""
import re
import sys
from pathlib import Path

CANON_JSON_LINE = (
    'Верни РОВНО один JSON-объект без какого-либо дополнительного текста '
    'до или после. Начни ответ сразу с открывающей фигурной скобки и закончи '
    'закрывающей. НЕ пиши Markdown, списки, код-фенсы. Ответ должен быть '
    'валидным JSON, пригодным для парсинга через json.loads без '
    'предварительной обработки.'
)

DEFAULT_OE_LINES = [
    '- Не используй markdown fences.',
    '- Не добавляй пояснения до или после JSON.',
    '- Верни все ключи, перечисленные в task, без пропусков.',
    '- Не используй null, None или пустые строки.',
    '- Для статусных полей используй только значения из allowed_values '
    'или "not_defined".',
    '- Для текстовых полей при отсутствии данных используй '
    '"Данные не определены" / "Не удалось определить" / "Не применимо" — '
    'согласно правилам выше.',
]


def split_rules(rules_body):
    lines = [l for l in rules_body.split('\n') if l.strip()]
    split_idx = None
    for i, l in enumerate(lines):
        if 'Верни РОВНО один JSON-объект' in l:
            split_idx = i
            break
    if split_idx is None:
        return lines, []
    return lines[:split_idx], lines[split_idx:]


def normalize_with_indent(body_lines, indent):
    """У каждой непустой строки — ровно indent ведущих пробелов."""
    out = []
    for l in body_lines:
        s = l.strip()
        if not s:
            continue
        out.append(indent + s)
    return out


def process_text(text):
    pattern = re.compile(r'^([ \t]*)<rules>(.*?)</rules>', re.M | re.S)
    n = 0

    def repl(m):
        nonlocal n
        n += 1
        indent = m.group(1)
        ctx, oe = split_rules(m.group(2))
        ctx = normalize_with_indent(ctx, indent)
        if not oe:
            oe = [indent + '- ' + CANON_JSON_LINE] + [
                indent + l for l in DEFAULT_OE_LINES
            ]
        else:
            oe = normalize_with_indent(oe, indent)

        ctx_block = (
            indent + '<context_rules>\n'
            + '\n'.join(ctx) + '\n'
            + indent + '</context_rules>'
        )
        oe_block = (
            indent + '<output_expectations>\n'
            + '\n'.join(oe) + '\n'
            + indent + '</output_expectations>'
        )
        return ctx_block + '\n\n' + oe_block

    new_text = pattern.sub(repl, text)
    return new_text, n


def process(p, apply):
    orig = p.read_text(encoding='utf-8')
    t, n = process_text(orig)
    if apply and t != orig:
        p.write_text(t, encoding='utf-8')
    return n, t != orig


def main():
    args = sys.argv[1:]
    if not args:
        print('Usage: migrate_group1_canonical_v6.py <path> [--apply]')
        return 1
    apply = '--apply' in args
    args = [a for a in args if a != '--apply']
    root = Path(args[0])
    files = [root] if root.is_file() else sorted(root.rglob('*.yaml'))
    tn = ch = 0
    for f in files:
        try:
            n, c = process(f, apply)
            tn += n
            ch += int(c)
            if n:
                print(f'{f.name}: rules->ctx+oe={n}')
        except Exception as e:
            print(f'{f.name}: ERROR: {e}')
    print()
    print(f'Файлов: {len(files)}, изменено: {ch}')
    print(f'<rules> преобразовано: {tn}')
    if not apply:
        print('\nDRY-RUN. Для записи: --apply')
    return 0


if __name__ == '__main__':
    sys.exit(main())
