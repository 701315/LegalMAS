#!/usr/bin/env python3
"""v9: triggers: ~ или пусто → triggers: {}."""
import re
import sys
from pathlib import Path


def process_text(text):
    n = 0
    text, k = re.subn(r'^(    triggers):[ \t]*(~|null)[ \t]*$', r'\1: {}', text, flags=re.M)
    n += k
    text, k = re.subn(r'^(    triggers):[ \t]*\n', r'\1: {}\n', text, flags=re.M)
    n += k
    return text, n


def process(p, apply):
    orig = p.read_text(encoding='utf-8')
    t, n = process_text(orig)
    if apply and t != orig:
        p.write_text(t, encoding='utf-8')
    return n, t != orig


def main():
    args = sys.argv[1:]
    if not args:
        print('Usage: v9 <path> [--apply]')
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
                print(f'{f.name}: triggers_fixed={n}')
        except Exception as e:
            print(f'{f.name}: ERROR: {e}')
    print()
    print(f'Файлов: {len(files)}, изменено: {ch}')
    print(f'triggers исправлено: {tn}')
    if not apply:
        print('DRY-RUN. Для записи: --apply')
    return 0


if __name__ == '__main__':
    sys.exit(main())
