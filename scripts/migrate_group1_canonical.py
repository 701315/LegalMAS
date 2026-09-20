#!/usr/bin/env python3
"""Migration: store_payload + унификация JSON-требования. DRY-RUN по умолчанию."""
import re
import sys
from pathlib import Path

CANON_JSON = (
    'Верни РОВНО один JSON-объект без какого-либо дополнительного текста '
    'до или после. Начни ответ сразу с открывающей фигурной скобки и закончи '
    'закрывающей. НЕ пиши Markdown, списки, код-фенсы. Ответ должен быть '
    'валидным JSON, пригодным для парсинга через json.loads без '
    'предварительной обработки.'
)
CANON_ANSWER = (
    'Ответь РОВНО одним JSON-объектом без какого-либо дополнительного текста '
    'до или после, со всеми ключами:'
)

PATS = [
    (re.compile(r'Верни\s+только\s+один\s+JSON-объект[.,]?\s*', re.I), CANON_JSON),
    (re.compile(r'Верни\s+только\s+JSON-объект[.,]?\s*', re.I), CANON_JSON),
    (re.compile(r'Верни\s+только\s+JSON[.,]?\s*', re.I), CANON_JSON),
    (re.compile(r'Ответь\s+строго\s+в\s+JSON[.:]?\s*', re.I), CANON_ANSWER + '\n'),
]

def add_sp(text):
    lines = text.split('\n')
    starts = []
    for i, l in enumerate(lines):
        m = re.match(r'^(\s*)- id:', l)
        if m:
            starts.append((i, m.group(1) + '  '))
    if not starts:
        return text, 0
    ins = []
    for k, (st, ind) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        key = ind + 'store_payload:'
        if not any(lines[j].startswith(key) for j in range(st, end)):
            ins.append((end, ind))
    for pos, ind in reversed(ins):
        lines.insert(pos, ind + 'store_payload: true')
    return '\n'.join(lines), len(ins)

def repl_json(text):
    n = 0
    for pat, rep in PATS:
        text, k = pat.subn(rep, text)
        n += k
    return text, n


def process(p, apply):
    orig = p.read_text(encoding='utf-8')
    t, nsp = add_sp(orig)
    t, njs = repl_json(t)
    if apply and t != orig:
        p.write_text(t, encoding='utf-8')
    return nsp, njs, t != orig

def main():
    args = sys.argv[1:]
    if not args:
        print('Usage: migrate_group1_canonical.py <path> [--apply]')
        return 1
    apply = '--apply' in args
    args = [a for a in args if a != '--apply']
    root = Path(args[0])
    files = [root] if root.is_file() else sorted(root.rglob('*.yaml'))
    tsp = tjs = ch = 0
    for f in files:
        try:
            nsp, njs, c = process(f, apply)
            tsp += nsp
            tjs += njs
            ch += int(c)
            print(f'{f.name}: store_payload+={nsp}, json_repl={njs}')
        except Exception as e:
            print(f'{f.name}: ERROR: {e}')
    print()
    print(f'Файлов: {len(files)}, изменено: {ch}')
    print(f'store_payload добавлено: {tsp}')
    print(f'JSON-замен: {tjs}')
    if not apply:
        print('\nDRY-RUN. Для записи: --apply')
    return 0


if __name__ == '__main__':
    sys.exit(main())
