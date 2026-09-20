#!/usr/bin/env python3
"""
READ-ONLY. Аудит A3: required: false в 5 группах.

Классификация:
  • signal + required=false → ПОДОЗРИТЕЛЬНО (обычно должно быть true)
  • fact + required=false   → ДОПУСТИМО (условные поля)
  • signal + required=true  → OK
  • fact + required=true    → OK
  • нет presentation        → проверить вручную
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

import yaml

GROUPS = ["group_1_ownership", "group_2_use", "group_3_works",
          "group_4_services", "group_5_financial"]
BASE = Path("playbooks/document_types")


def main() -> None:
    stats: dict[str, Counter] = {
        "signal": Counter(), "fact": Counter(), "list": Counter(),
        "no_pres": Counter(), "other": Counter(),
    }

    # Детали по подозрительным
    suspect: list[tuple[str, str, str, str]] = []  # file, check, field, presentation
    fact_false: list[tuple[str, str, str]] = []

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
                    pres = f.get("presentation") or "no_pres"
                    req = f.get("required")
                    name = f.get("name", "?")
                    stats.setdefault(pres, Counter())[str(req)] += 1
                    if req is False:
                        if pres == "signal":
                            suspect.append((p.name, cid, name, pres))
                        elif pres == "fact":
                            fact_false.append((p.name, cid, name))

    print(f"{'='*100}")
    print(f"РАСПРЕДЕЛЕНИЕ required ПО presentation")
    print(f"{'='*100}")
    for pres, counter in stats.items():
        total = sum(counter.values())
        if total == 0:
            continue
        print(f"\n  presentation={pres!r}  ({total} полей)")
        for req_val, n in sorted(counter.items()):
            print(f"     required={req_val:<8} → {n}")

    print(f"\n{'='*100}")
    print(f"🔴 ПОДОЗРИТЕЛЬНО: signal + required=false ({len(suspect)})")
    print(f"{'='*100}")
    for fname, cid, field, _ in suspect[:50]:
        print(f"  {fname:<45} {cid:<45} {field}")
    if len(suspect) > 50:
        print(f"  ... ещё {len(suspect) - 50}")

    print(f"\n{'='*100}")
    print(f"🟡 fact + required=false ({len(fact_false)}) — обычно ДОПУСТИМО")
    print(f"{'='*100}")
    for fname, cid, field in fact_false[:20]:
        print(f"  {fname:<45} {cid:<45} {field}")
    if len(fact_false) > 20:
        print(f"  ... ещё {len(fact_false) - 20}")

    # Уникальные presentation
    print(f"\n{'='*100}")
    print(f"ВСЕ presentation значения: {sorted(stats.keys())}")
    print(f"{'='*100}")


if __name__ == "__main__":
    main()


    