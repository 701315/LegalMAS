#!/usr/bin/env python3
"""v10c: удалить top-level '    store_payload:' из checks."""
import re
import sys
from pathlib import Path


def process_text(text):
    n = 0
    text, k = re.subn(
        r'^    store_payload:[ \t]*\S+[ \t]*\n',
        '', text, flags=re.M
    )
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
        print('Usage: v10c <path> [--apply]')
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
                print(f'{f.name}: store_payload_removed={n}')
        except Exception as e:
            print(f'{f.name}: ERROR: {e}')
    print()
    print(f'Файлов: {len(files)}, изменено: {ch}')
    print(f'store_payload удалено: {tn}')
    if not apply:
        print('DRY-RUN. Для записи: --apply')
    return 0


if __name__ == '__main__':
    sys.exit(main())
