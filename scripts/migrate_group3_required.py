#!/usr/bin/env python3
"""v11: добавить required: true в fields, где required отсутствует."""
import re
import sys
from pathlib import Path


def process_text(text):
    lines = text.split('\n')
    out = []
    i = 0
    n = 0
    while i < len(lines):
        l = lines[i]
        if re.match(r'^        - name:', l):
            # Начало поля — найти конец
            j = i + 1
            while j < len(lines):
                nl = lines[j]
                if re.match(r'^        - name:', nl):
                    break
                if nl and not nl.startswith('        '):
                    break
                j += 1
            field_lines = lines[i:j]
            has_required = any(re.match(r'^\s+required\s*:', fl) for fl in field_lines)
            if not has_required:
                # Вставить 'required: true' в конец блока (перед последней непустой+1)
                # Найти позицию конца — последняя строка блока с отступом 8+ или 10+
                insert_at = len(field_lines)
                while insert_at > 0 and (
                    field_lines[insert_at - 1].strip() == '' or
                    field_lines[insert_at - 1].lstrip().startswith('#')
                ):
                    insert_at -= 1
                # Определить отступ — по «type:» или «presentation:» строке
                indent = '          '  # 10 пробелов — дефолт для свойств поля
                for fl in field_lines[1:]:
                    m = re.match(r'^(\s+)[a-zA-Z_]', fl)
                    if m:
                        indent = m.group(1)
                        break
                field_lines.insert(insert_at, indent + 'required: true')
                n += 1
            out.extend(field_lines)
            i = j
        else:
            out.append(l)
            i += 1
    return '\n'.join(out), n


def process(p, apply):
    orig = p.read_text(encoding='utf-8')
    t, n = process_text(orig)
    if apply and t != orig:
        p.write_text(t, encoding='utf-8')
    return n, t != orig


def main():
    args = sys.argv[1:]
    if not args:
        print('Usage: v11 <path> [--apply]')
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
                print(f'{f.name}: required_added={n}')
        except Exception as e:
            print(f'{f.name}: ERROR: {e}')
    print()
    print(f'Файлов: {len(files)}, изменено: {ch}')
    print(f'required добавлено: {tn}')
    if not apply:
        print('DRY-RUN. Для записи: --apply')
    return 0


if __name__ == '__main__':
    sys.exit(main())
