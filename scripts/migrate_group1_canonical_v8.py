#!/usr/bin/env python3
"""v8: вставить [ПРИМЕРЫ (FEW-SHOT)] в 7 checks. Читает /tmp/examples_v8.json."""
import json
import re
import sys
from pathlib import Path

IND = '        '
EXAMPLES_PATH = Path('/tmp/examples_v8.json')


def make_block(body):
    lines = [IND + '[ПРИМЕРЫ (FEW-SHOT)]', '']
    for line in body.strip().split('\n'):
        lines.append(IND + line if line.strip() else '')
    lines.append('')
    return '\n'.join(lines)


def process_file(path, ids, examples):
    src = path.read_text(encoding='utf-8')
    n = 0
    for cid in ids:
        id_pat = re.compile(r'^(  - id:\s*' + re.escape(cid) + r'\s*)$', re.M)
        m = id_pat.search(src)
        if not m:
            print(f'  WARN: check {cid} not found')
            continue
        start = m.start()
        nxt = re.search(r'^  - id:', src[start + 1:], re.M)
        end = start + 1 + nxt.start() if nxt else len(src)
        block = src[start:end]
        if '[ПРИМЕРЫ (FEW-SHOT)]' in block:
            print(f'  SKIP {cid}: already present')
            continue
        cove = re.search(r'^        \[ПРОВЕРКА ПЕРЕД ОТВЕТОМ — CoVe\]', block, re.M)
        if not cove:
            print(f'  WARN {cid}: CoVe section missing')
            continue
        key = f'{path.name}::{cid}'
        body = examples.get(key)
        if not body:
            print(f'  WARN {cid}: no example prepared')
            continue
        block_new = block[:cove.start()] + make_block(body) + block[cove.start():]
        src = src[:start] + block_new + src[end:]
        n += 1
    path.write_text(src, encoding='utf-8')
    return n


def main():
    root = Path('/srv/steloom-dev/playbooks/document_types/group_1_ownership')
    apply = '--apply' in sys.argv
    examples = json.loads(EXAMPLES_PATH.read_text(encoding='utf-8'))
    plan = {
        'contract_1.4_contract_farming.yaml': [
            'perennial_crops_risk_allocation',
            'production_support_obligations_check',
        ],
        'contract_1.5_energy_supply.yaml': [
            'energy_quality_requirements_check',
            'limitation_procedure_check',
            'liability_for_interruptions_check',
            'unauthorized_consumption_check',
            'industrial_consumer_protection_check',
        ],
    }
    total = 0
    for fname, ids in plan.items():
        f = root / fname
        if not f.exists():
            print(f'WARN: {fname} not found')
            continue
        if apply:
            n = process_file(f, ids, examples)
        else:
            # dry-run — просто проверяем, что examples готовы
            n = sum(1 for cid in ids if f'{fname}::{cid}' in examples)
        total += n
        print(f'{fname}: {n}')
    print()
    print(f'Всего: {total}')
    if not apply:
        print('DRY-RUN (только проверка). Для записи: --apply')


if __name__ == '__main__':
    main()
