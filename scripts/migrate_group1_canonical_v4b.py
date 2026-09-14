#!/usr/bin/env python3
"""v4b: закрыть варианты JSON-требования с 'ровно' (нижний регистр)."""
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
PATS = [
    (re.compile(
        r'Верни\s+ровно\s+один\s+JSON-объект\s+без\s+markdown\s+и\s+пояснений\.?[ \t]*',
        re.I), CANON_JSON),
    (re.compile(
        r'Верни\s+ровно\s+один\s+JSON-объект\.?[ \t]*',
        re.I), CANON_JSON),
]


def repl_json(text):
    """Обрабатываем только строки без json.loads (канон уже там)."""
    n = 0
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if 'json.loads' in line:
            continue
        for pat, rep in PATS:
            new_line, k = pat.subn(rep, line)
            if k:
                lines[i] = new_line
                n += k
                break
    return '\n'.join(lines), n


def process(p, apply):
    orig = p.read_text(encoding='utf-8')
    t, n = repl_json(orig)
    if apply and t != orig:
        p.write_text(t, encoding='utf-8')
    return n, t != orig


def main():
    args = sys.argv[1:]
    if not args:
        print('Usage: migrate_group1_canonical_v4b.py <path> [--apply]')
        return 1
    apply = '--apply' in args
    args = [a for a in args if a != '--apply']
    root = Path(args[0])
    files = [root] if root.is_file() else sorted(root.rglob('*.yaml'))
    tj = ch = 0
    for f in files:
        try:
            nj, c = process(f, apply)
            tj += nj
            ch += int(c)
            if nj:
                print(f'{f.name}: json_repl={nj}')
        except Exception as e:
            print(f'{f.name}: ERROR: {e}')
    print()
    print(f'Файлов: {len(files)}, изменено: {ch}')
    print(f'JSON-замен: {tj}')
    if not apply:
        print('\nDRY-RUN. Для записи: --apply')
    return 0


if __name__ == '__main__':
    sys.exit(main())
