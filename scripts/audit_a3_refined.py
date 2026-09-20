#!/usr/bin/env python3
"""
READ-ONLY. Уточнение A3: signal + required=false, разбитый по 3 группам:
  • SAFE_TO_FIX: allowed_values содержит "not_defined" — можно безопасно → required=true
  • RISKY:       allowed_values НЕ содержит "not_defined" — надо править enum или оставить false
  • NEEDS_REVIEW: не удалось определить (нет allowed_values)
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml

GROUPS = ["group_1_ownership", "group_2_use", "group_3_works",
          "group_4_services", "group_5_financial"]
BASE = Path("playbooks/document_types")


def main() -> None:
    safe: list[tuple[str, str, str, list]] = []
    risky: list[tuple[str, str, str, list]] = []
    review: list[tuple[str, str, str]] = []

    for g in GROUPS:
        root = BASE / g
        if not root.exists():
            continue
        for p in sorted(root.rglob("*.yaml")):
            try:
                d = yaml.safe_load(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            for c in (d or {}).get("checks_v8") or []:
                ext = c.get("extraction") or {}
                cid = c.get("id", "?")
                for f in ext.get("fields") or []:
                    if not isinstance(f, dict):
                        continue
                    if f.get("presentation") != "signal":
                        continue
                    if f.get("required") is not False:
                        continue
                    name = f.get("name", "?")
                    allowed = f.get("allowed_values")
                    if allowed is None:
                        review.append((p.name, cid, name))
                    elif "not_defined" in allowed:
                        safe.append((p.name, cid, name, allowed))
                    else:
                        risky.append((p.name, cid, name, allowed))

    print(f"{'='*100}")
    print(f"ИТОГИ по 992 signal + required=false")
    print(f"{'='*100}")
    print(f"  🟢 SAFE_TO_FIX (allowed_values содержит 'not_defined'):  {len(safe)}")
    print(f"  🔴 RISKY (allowed_values БЕЗ 'not_defined'):              {len(risky)}")
    print(f"  🟡 NEEDS_REVIEW (нет allowed_values):                      {len(review)}")

    print(f"\n{'='*100}")
    print(f"🟢 SAFE_TO_FIX — можно безопасно менять на required=true ({len(safe)})")
    print(f"{'='*100}")
    for fname, cid, field, allowed in safe[:30]:
        print(f"  {fname:<45} {cid:<45} {field}")
        print(f"     allowed: {allowed}")
    if len(safe) > 30:
        print(f"  ... ещё {len(safe) - 30}")

    print(f"\n{'='*100}")
    print(f"🔴 RISKY — надо править enum или оставить false ({len(risky)})")
    print(f"{'='*100}")
    # Сгруппировать по списку allowed_values, чтобы увидеть паттерны
    by_allowed: Counter = Counter()
    for _, _, _, allowed in risky:
        by_allowed[tuple(allowed)] += 1
    for allowed, n in by_allowed.most_common(20):
        print(f"  {n:4d}  allowed={list(allowed)}")
    print()
    for fname, cid, field, allowed in risky[:20]:
        print(f"  {fname:<45} {cid:<45} {field}  →  {allowed}")
    if len(risky) > 20:
        print(f"  ... ещё {len(risky) - 20}")

    print(f"\n{'='*100}")
    print(f"🟡 NEEDS_REVIEW — нет allowed_values ({len(review)})")
    print(f"{'='*100}")
    for fname, cid, field in review[:20]:
        print(f"  {fname:<45} {cid:<45} {field}")


if __name__ == "__main__":
    main()

    