#!/usr/bin/env python3
"""v14b: вставка [ПРИМЕРЫ (FEW-SHOT)] и [CoVe] в 3 checks 3.3."""
import json
import re
import sys
from pathlib import Path

IND = '        '
DATA = Path('/tmp/group3_examples.json')


def section(title, body):
    lines = [IND + title, '']
    for l in body.strip().split('\n'):
        lines.append(IND + l if l.strip() else '')
    lines.append('')
    return '\n'.join(lines)


def process(path, data, apply):
    src = path.read_text(encoding='utf-8')
    n = 0
    for cid, blobs in data.items():
        m = re.search(r'^(  - id:\s*' + re.escape(cid) + r'\s*)$', src, re.M)
        if not m:
            print(f'  WARN: {cid} not found')
            continue
        start = m.start()
        nxt = re.search(r'^  - id:', src[start + 1:], re.M)
        end = start + 1 + nxt.start() if nxt else len(src)
        block = src[start:end]

        # CoVe
        if 'ПРОВЕРКА ПЕРЕД ОТВЕТОМ — CoVe' not in block:
            m_fa = re.search(r'^        \[ФОРМАТ ОТВЕТА\]', block, re.M)
            if m_fa:
                block = block[:m_fa.start()] + section(
                    '[ПРОВЕРКА ПЕРЕД ОТВЕТОМ — CoVe]', blobs['cove']
                ) + block[m_fa.start():]

        # Примеры
        if '[ПРИМЕРЫ (FEW-SHOT)]' not in block:
            m_cove = re.search(r'^        \[ПРОВЕРКА ПЕРЕД ОТВЕТОМ — CoVe\]', block, re.M)
            if not m_cove:
                m_cove = re.search(r'^        \[ФОРМАТ ОТВЕТА\]', block, re.M)
            if m_cove:
                block = block[:m_cove.start()] + section(
                    '[ПРИМЕРЫ (FEW-SHOT)]', blobs['examples']
                ) + block[m_cove.start():]

        src = src[:start] + block + src[end:]
        n += 1
    if apply and n:
        path.write_text(src, encoding='utf-8')
    return n


def main():
    root = Path('/srv/steloom-dev/playbooks/document_types/group_3_works')
    apply = '--apply' in sys.argv
    data = json.loads(DATA.read_text(encoding='utf-8'))
    f = root / 'contract_3.3_construction_contract.yaml'
    n = process(f, data, apply)
    print(f'{f.name}: checks_processed={n}')
    if not apply:
        print('DRY-RUN. Для записи: --apply')


if __name__ == '__main__':
    main()
