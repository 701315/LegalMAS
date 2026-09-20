#!/usr/bin/env python3
"""v10b: enrichment_hints из retrieval на top-level."""
import re
import sys
from pathlib import Path


def transform_block(block):
    # Найти '    retrieval:' (4 пробела)
    ret_idx = None
    for k, l in enumerate(block):
        if re.match(r'^    retrieval:\s*$', l):
            ret_idx = k
            break
    if ret_idx is None:
        return block, 0

    # Найти конец блока retrieval — следующий top-level ключ check-а
    ret_end = ret_idx + 1
    while ret_end < len(block):
        l = block[ret_end]
        if l.startswith('  - id:'):
            break
        if re.match(r'^    [a-zA-Z_][a-zA-Z0-9_]*:', l):
            break
        ret_end += 1

    ret_content = block[ret_idx + 1:ret_end]

    # Найти enrichment_hints внутри (6 пробелов)
    enr_start = None
    for k, l in enumerate(ret_content):
        if re.match(r'^      enrichment_hints:\s*$', l):
            enr_start = k
            break
    if enr_start is None:
        return block, 0

    # Конец enrichment_hints — следующий ключ на 6 пробелах
    enr_end = enr_start + 1
    while enr_end < len(ret_content):
        l = ret_content[enr_end]
        if re.match(r'^      [a-zA-Z_][a-zA-Z0-9_]*:', l):
            break
        enr_end += 1

    enr_block = ret_content[enr_start:enr_end]
    # Де-инденить на 2: было 6 → станет 4
    enr_block_top = [
        (l[2:] if l.startswith('  ') else l) for l in enr_block
    ]

    # Новый retrieval без enrichment_hints
    ret_new = ret_content[:enr_start] + ret_content[enr_end:]

    new_block = (
        block[:ret_idx + 1]
        + ret_new
        + enr_block_top
        + block[ret_end:]
    )
    return new_block, 1


def process_file(path, apply):
    text = path.read_text(encoding='utf-8')
    lines = text.split('\n')
    out, i, n = [], 0, 0
    while i < len(lines):
        l = lines[i]
        if re.match(r'^  - id:', l):
            j = i + 1
            while j < len(lines):
                if re.match(r'^  - id:', lines[j]):
                    break
                if lines[j] and not lines[j].startswith('  '):
                    break
                j += 1
            block = lines[i:j]
            new_block, changed = transform_block(block)
            n += changed
            out.extend(new_block)
            i = j
        else:
            out.append(l)
            i += 1
    new_text = '\n'.join(out)
    if apply and new_text != text:
        path.write_text(new_text, encoding='utf-8')
    return n, new_text != text


def main():
    args = sys.argv[1:]
    if not args:
        print('Usage: v10b <path> [--apply]')
        return 1
    apply = '--apply' in args
    args = [a for a in args if a != '--apply']
    root = Path(args[0])
    files = [root] if root.is_file() else sorted(root.rglob('*.yaml'))
    tn = ch = 0
    for f in files:
        try:
            n, c = process_file(f, apply)
            tn += n
            ch += int(c)
            if n:
                print(f'{f.name}: enrichment_moved={n}')
        except Exception as e:
            print(f'{f.name}: ERROR: {e}')
    print()
    print(f'Файлов: {len(files)}, изменено: {ch}')
    print(f'enrichment_hints перемещено: {tn}')
    if not apply:
        print('DRY-RUN. Для записи: --apply')
    return 0


if __name__ == '__main__':
    sys.exit(main())
