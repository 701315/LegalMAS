#!/usr/bin/env python3
"""v10-struct: retrieval/evidence/extraction/enrichment_hints out of llm."""
import re
import sys
from pathlib import Path

MOVE_KEYS = {'retrieval', 'evidence', 'extraction', 'enrichment_hints'}
MOVE_ORDER = ['retrieval', 'enrichment_hints', 'evidence', 'extraction']


def transform_block(block):
    llm_idx = None
    for k, l in enumerate(block):
        if re.match(r'^    llm:\s*$', l):
            llm_idx = k
            break
    if llm_idx is None:
        return block, 0
    llm_end = llm_idx + 1
    while llm_end < len(block):
        l = block[llm_end]
        if l.startswith('  - id:') or re.match(r'^    [a-zA-Z_][a-zA-Z0-9_]*:', l):
            break
        llm_end += 1
    llm_content = block[llm_idx + 1:llm_end]
    to_move = []
    for l in llm_content:
        m = re.match(r'^      ([a-zA-Z_][a-zA-Z0-9_]*):', l)
        if m and m.group(1) in MOVE_KEYS:
            to_move.append(m.group(1))
    if not to_move:
        return block, 0
    segments = []
    cur_key, cur_lines = None, []
    for l in llm_content:
        m = re.match(r'^      ([a-zA-Z_][a-zA-Z0-9_]*):', l)
        if m:
            if cur_key is not None:
                segments.append((cur_key, cur_lines))
            cur_key, cur_lines = m.group(1), [l]
        else:
            cur_lines.append(l)
    if cur_key is not None:
        segments.append((cur_key, cur_lines))
    kept, moved = [], {}
    for key, lines_seg in segments:
        if key in MOVE_KEYS:
            moved[key] = lines_seg
        else:
            kept.extend(lines_seg)
    new_llm = ['    llm:'] + kept
    new_moved = []
    for key in MOVE_ORDER:
        if key in moved:
            for l in moved[key]:
                new_moved.append(l[2:] if l.startswith('  ') else l)
    new_block = block[:llm_idx] + new_llm + new_moved + block[llm_end:]
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
        print('Usage: v10-struct <path> [--apply]')
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
                print(f'{f.name}: checks_refactored={n}')
        except Exception as e:
            print(f'{f.name}: ERROR: {e}')
    print()
    print(f'Файлов: {len(files)}, изменено: {ch}')
    print(f'checks отрефакторено: {tn}')
    if not apply:
        print('DRY-RUN. Для записи: --apply')
    return 0


if __name__ == '__main__':
    sys.exit(main())
