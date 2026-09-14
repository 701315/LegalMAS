#!/usr/bin/env python3
"""v14a-fixed: опечатка + опциональный хвост 'со всеми N ключами' с сохранением indent."""
import re
import sys
from pathlib import Path


def fix_typo(text):
    text, n = re.subn(r'\[ПРИМЕР3\s+\(FEW-SHOT\)\]',
                      '[ПРИМЕРЫ (FEW-SHOT)]', text)
    return text, n


def fix_concat_tail(text):
    """Хвост 'обработки.со всеми N ключами.[.]' → с переносом и indent."""
    n = 0

    def repl(m):
        nonlocal n
        n += 1
        indent = m.group(1)
        prefix = m.group(2)
        num = m.group(3)
        return f'{indent}{prefix}\n{indent}со всеми {num} ключами.'

    text = re.sub(
        r'(?m)^(        )((?:.*?)без предварительной обработки\.)со всеми\s+(\d+)\s+ключами\.?',
        repl, text
    )
    return text, n


def process(p, apply):
    orig = p.read_text(encoding='utf-8')
    t = orig
    t, n1 = fix_typo(t)
    t, n2 = fix_concat_tail(t)
    if apply and t != orig:
        p.write_text(t, encoding='utf-8')
    return n1, n2, t != orig


def main():
    args = sys.argv[1:]
    if not args:
        print('Usage: v14a <path> [--apply]')
        return 1
    apply = '--apply' in args
    args = [a for a in args if a != '--apply']
    root = Path(args[0])
    files = [root] if root.is_file() else sorted(root.rglob('*.yaml'))
    t1 = t2 = ch = 0
    for f in files:
        try:
            n1, n2, c = process(f, apply)
            t1 += n1
            t2 += n2
            ch += int(c)
            if n1 or n2:
                print(f'{f.name}: typo={n1}, tail={n2}')
        except Exception as e:
            print(f'{f.name}: ERROR: {e}')
    print()
    print(f'Файлов: {len(files)}, изменено: {ch}')
    print(f'опечаток: {t1}')
    print(f'хвостов: {t2}')
    if not apply:
        print('DRY-RUN. Для записи: --apply')
    return 0


if __name__ == '__main__':
    sys.exit(main())
