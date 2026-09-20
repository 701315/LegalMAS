#!/usr/bin/env python3
"""v5: добавить retrieval_profile в блок retrieval (отступы 4/6)."""
import re
import sys
from pathlib import Path

DEFAULT = 'generic_check'


def process_text(text):
    lines = text.split('\n')
    out = []
    i = 0
    n = 0
    while i < len(lines):
        out.append(lines[i])
        # retrieval: на 4 пробелах (sibling check-а)
        if re.match(r'^    retrieval:\s*$', lines[i]):
            j = i + 1
            has_rp = False
            while j < len(lines):
                l = lines[j]
                # следующий top-level ключ check-а — 4 пробела
                if re.match(r'^    \S', l):
                    break
                if re.match(r'^      retrieval_profile\s*:', l):
                    has_rp = True
                j += 1
            if not has_rp:
                out.append(f'      retrieval_profile: "{DEFAULT}"')
                n += 1
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
        print('Usage: migrate_group1_canonical_v5.py <path> [--apply]')
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
                print(f'{f.name}: retrieval_profile+={n}')
        except Exception as e:
            print(f'{f.name}: ERROR: {e}')
    print()
    print(f'Файлов: {len(files)}, изменено: {ch}')
    print(f'retrieval_profile добавлено: {tn}')
    if not apply:
        print('\nDRY-RUN. Для записи: --apply')
    return 0


if __name__ == '__main__':
    sys.exit(main())
