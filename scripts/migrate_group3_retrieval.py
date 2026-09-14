#!/usr/bin/env python3
"""v12: добавить preferred_clause_functions и excluded_unit_types в retrieval."""
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
        out.append(l)
        if re.match(r'^    retrieval:\s*$', l):
            # Найти конец блока retrieval
            j = i + 1
            has_pcf = False
            has_eut = False
            while j < len(lines):
                nl = lines[j]
                if re.match(r'^    [a-zA-Z_][a-zA-Z0-9_]*:', nl):
                    break
                if re.match(r'^      preferred_clause_functions\s*:', nl):
                    has_pcf = True
                if re.match(r'^      excluded_unit_types\s*:', nl):
                    has_eut = True
                j += 1
            additions = []
            if not has_eut:
                additions.append('      excluded_unit_types:')
                additions.append('        - definition')
                additions.append('        - structural_anchor')
                additions.append('        - technical_fragment')
            if not has_pcf:
                additions.append('      preferred_clause_functions:')
                additions.append('        - obligations')
                additions.append('        - procedures')
            if additions:
                # вставить перед концом блока (перед строкой, начинающейся с 4 пробела)
                for k, al in enumerate(additions):
                    out.append(al)
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
        print('Usage: v12 <path> [--apply]')
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
                print(f'{f.name}: retrieval_keys_added={n}')
        except Exception as e:
            print(f'{f.name}: ERROR: {e}')
    print()
    print(f'Файлов: {len(files)}, изменено: {ch}')
    print(f'checks с добавленными ключами: {tn}')
    if not apply:
        print('DRY-RUN. Для записи: --apply')
    return 0


if __name__ == '__main__':
    sys.exit(main())
