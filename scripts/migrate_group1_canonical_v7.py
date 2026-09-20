#!/usr/bin/env python3
"""v7: top.order + rules.regex_patterns + retrieval.position_bias."""
import re
import sys
from pathlib import Path

CANON_ORDER = [
    'id', 'name', 'description', 'triggers', 'ui_mode',
    'severity', 'severity_if_pass', 'severity_if_fail', 'severity_if_unclear',
    'origin', 'detector_type', 'rules', 'llm',
    'retrieval', 'enrichment_hints', 'evidence', 'extraction',
]


def reorder_top_level_keys(text):
    lines = text.split('\n')
    out = []
    i = 0
    n = 0
    while i < len(lines):
        if not re.match(r'^  - id:', lines[i]):
            out.append(lines[i])
            i += 1
            continue
        # find end of check
        j = i + 1
        while j < len(lines):
            l = lines[j]
            if re.match(r'^  - id:', l) or re.match(r'^  #', l):
                break
            if l and not l.startswith('  '):
                break
            j += 1
        block = lines[i:j]
        # collect top-level key starts
        key_starts = [(0, 'id')]
        for k in range(1, len(block)):
            m2 = re.match(r'^    ([a-zA-Z_][a-zA-Z0-9_]*):(\s|$)', block[k])
            if m2:
                key_starts.append((k, m2.group(1)))
        segments = {}
        for idx, (k, key) in enumerate(key_starts):
            end = key_starts[idx + 1][0] if idx + 1 < len(key_starts) else len(block)
            segments[key] = block[k:end]
        actual = [k for _, k in key_starts]
        desired = [k for k in CANON_ORDER if k in actual]
        if actual == desired:
            out.extend(block)
            i = j
            continue
        new_block = []
        for key in CANON_ORDER:
            if key in segments:
                new_block.extend(segments[key])
        emitted = set(k for k in CANON_ORDER if k in segments)
        for key in actual:
            if key not in emitted:
                new_block.extend(segments[key])
        out.extend(new_block)
        n += 1
        i = j
    return '\n'.join(out), n


def add_regex_patterns(text):
    lines = text.split('\n')
    out = []
    i = 0
    n = 0
    while i < len(lines):
        l = lines[i]
        out.append(l)
        if re.match(r'^    rules:\s*$', l):
            # find end of rules block
            j = i + 1
            has_rp = False
            while j < len(lines):
                l2 = lines[j]
                if re.match(r'^    \S', l2):
                    break
                if re.match(r'^      regex_patterns\s*:', l2):
                    has_rp = True
                j += 1
            if not has_rp:
                out.append('      regex_patterns: []')
                n += 1
        i += 1
    return '\n'.join(out), n


def add_position_bias(text):
    lines = text.split('\n')
    out = []
    i = 0
    n = 0
    while i < len(lines):
        l = lines[i]
        out.append(l)
        if re.match(r'^    retrieval:\s*$', l):
            j = i + 1
            has_pb = False
            while j < len(lines):
                l2 = lines[j]
                if re.match(r'^    \S', l2):
                    break
                if re.match(r'^      position_bias\s*:', l2):
                    has_pb = True
                j += 1
            if not has_pb:
                out.append('      position_bias:')
                out.append('        preferred_range: [0.3, 0.75]')
                out.append('        boost: 0.15')
                out.append('        scope: segment')
                n += 1
        i += 1
    return '\n'.join(out), n


def process(p, apply):
    orig = p.read_text(encoding='utf-8')
    t = orig
    t, n_ord = reorder_top_level_keys(t)
    t, n_rp = add_regex_patterns(t)
    t, n_pb = add_position_bias(t)
    if apply and t != orig:
        p.write_text(t, encoding='utf-8')
    return n_ord, n_rp, n_pb, t != orig


def main():
    args = sys.argv[1:]
    if not args:
        print('Usage: migrate_group1_canonical_v7.py <path> [--apply]')
        return 1
    apply = '--apply' in args
    args = [a for a in args if a != '--apply']
    root = Path(args[0])
    files = [root] if root.is_file() else sorted(root.rglob('*.yaml'))
    t_ord = t_rp = t_pb = ch = 0
    for f in files:
        try:
            n_ord, n_rp, n_pb, c = process(f, apply)
            t_ord += n_ord
            t_rp += n_rp
            t_pb += n_pb
            ch += int(c)
            if n_ord or n_rp or n_pb:
                print(f'{f.name}: order={n_ord}, regex={n_rp}, pos_bias={n_pb}')
        except Exception as e:
            print(f'{f.name}: ERROR: {e}')
    print()
    print(f'Файлов: {len(files)}, изменено: {ch}')
    print(f'order переставлен: {t_ord}')
    print(f'regex_patterns добавлен: {t_rp}')
    print(f'position_bias добавлен: {t_pb}')
    if not apply:
        print('\nDRY-RUN. Для записи: --apply')
    return 0


if __name__ == '__main__':
    sys.exit(main())
