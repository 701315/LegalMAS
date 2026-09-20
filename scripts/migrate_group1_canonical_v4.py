#!/usr/bin/env python3
"""Migration v4: только унификация JSON-требования. DRY-RUN by default."""
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
    'до или после, со всеми ключами. Ответ должен быть валидным JSON, '
    'пригодным для парсинга через json.loads без предварительной обработки:'
)
PATS = [
    (re.compile(r'Верни\s+только\s+один\s+JSON-объект[.,:]?[ \t]*', re.I), CANON_JSON),
    (re.compile(r'Верни\s+только\s+JSON-объект[.,:]?[ \t]*', re.I), CANON_JSON),
    (re.compile(r'Верни\s+только\s+JSON[.,:]?[ \t]*', re.I), CANON_JSON),
    (re.compile(r'Ответь\s+строго\s+в\s+JSON[.:]?[ \t]*', re.I), CANON_ANSWER),
]


def repl_json(text):
    n = 0
    for pat, rep in PATS:
        text, k = pat.subn(rep, text)
        n += k
    return text, n


def process(p, apply):
    orig = p.read_text(encoding='utf-8')
    t, n = repl_json(orig)
    if apply and t != orig:
        p.write_text(t, encoding='utf-8')
    return n, t != orig


def main():
    args = sys.argv[1:]
    if not args:
        print('Usage: migrate_group1_canonical_v4.py <path> [--apply]')
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
