#!/usr/bin/env python3
"""
Вставляет safeguard-фразу в <context_rules> для 4 checks,
где её не хватает. Использует presence_signal.field как <STATUS_FIELD>.

Использование:
    cd /srv/steloom-dev
    python scripts/diagnostics/add_safeguard_to_4_checks.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FILES = [
    "playbooks/global_checks/assignment_transfer/assignment_transfer_consent.yaml",
    "playbooks/global_checks/assignment_transfer/assignment_transfer_consequences.yaml",
    "playbooks/global_checks/coc/coc_consent_terms.yaml",
    "playbooks/global_checks/coc/coc_consequences.yaml",
]

SAFEGUARD_MARKER = 'Не использовать "unclear" при полном отсутствии'
CTX_RE = re.compile(r"<context_rules>([\s\S]*?)</context_rules>")
PS_FIELD_RE = re.compile(r'presence_signal:\s*\n\s*field:\s*"([^"]+)"')


def main() -> int:
    for rel in FILES:
        path = Path(rel)
        if not path.exists():
            print(f"WARN: не найден {rel}", file=sys.stderr)
            continue

        text = path.read_text(encoding="utf-8")

        if SAFEGUARD_MARKER in text:
            print(f"SKIP: {rel} — safeguard уже есть")
            continue

        m = PS_FIELD_RE.search(text)
        if not m:
            print(f"WARN: не найден presence_signal.field в {rel}", file=sys.stderr)
            continue
        status_field = m.group(1)

        cm = CTX_RE.search(text)
        if not cm:
            print(f"WARN: не найден <context_rules> в {rel}", file=sys.stderr)
            continue

        inner = cm.group(1)

        # Определяем отступ по последней строке блока
        indent_match = re.search(r"\n(\s+)-\s", inner)
        indent = indent_match.group(1) if indent_match else "    "

        safeguard_line = (
            f"{indent}- Если ни один фрагмент не содержит информации по теме — "
            f"{status_field} = \"missing\", location = null. "
            f"Не использовать \"unclear\" при полном отсутствии "
            f"релевантных фрагментов.\n"
        )

        # Вставляем перед закрывающим </context_rules>
        new_inner = inner.rstrip() + "\n" + safeguard_line
        new_text = text[:cm.start(1)] + new_inner + text[cm.end(1):]
        path.write_text(new_text, encoding="utf-8")
        print(f"OK: {rel} — вставлено со STATUS_FIELD = {status_field}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

    