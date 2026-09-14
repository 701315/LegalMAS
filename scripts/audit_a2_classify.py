#!/usr/bin/env python3
"""
READ-ONLY. Классифицирует 29 рассинхронов A2 по категориям A/B/C/D.

Для каждого check-а:
  M = len(extraction.fields)
  N = M + 1  (с evidence)
  • header: что стоит «следующие X полей» → X
  • CoVe: что стоит в строке с «ключей» → Y
  • llm.prompt_template: что стоит в строках с «ключей/полей» → список
"""
import re
from pathlib import Path
from collections import defaultdict

import yaml

GROUPS = ["group_1_ownership", "group_2_use", "group_3_works",
          "group_4_services", "group_5_financial"]
BASE = Path("playbooks/document_types")


def parse_counters(text: str) -> dict:
    """Находит все счётчики в тексте."""
    result = {
        "task_header": None,      # «следующие N полей»
        "task_has_plus_evidence": False,  # «(плюс evidence)»
        "cove_keys": [],          # все «N ключей» вне <task>
        "rules_fields": [],       # «N полей» вне <task>
    }
    # Разделить на секции
    m_task = re.search(r"<task>(.*?)</task>", text, re.DOTALL)
    task_body = m_task.group(1) if m_task else ""

    # Header
    m = re.search(r"следующие\s+(\d+)\s+полей\s*(\(плюс evidence\))?", task_body)
    if m:
        result["task_header"] = int(m.group(1))
        result["task_has_plus_evidence"] = bool(m.group(2))

    # CoVe и остальное
    non_task = text
    if m_task:
        non_task = text[:m_task.start()] + text[m_task.end():]

    for m in re.finditer(r"(\d+)\s+ключ", non_task):
        result["cove_keys"].append(int(m.group(1)))
    for m in re.finditer(r"(\d+)\s+полей", non_task):
        result["rules_fields"].append(int(m.group(1)))

    return result


def main() -> None:
    rows = []
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
                ext = c.get("extraction")
                if not isinstance(ext, dict):
                    continue
                fields = [f["name"] for f in (ext.get("fields") or [])
                          if isinstance(f, dict) and f.get("name")]
                if not fields:
                    continue
                pt = ext.get("llm_prompt_extraction") or ""
                if not isinstance(pt, str) or not pt.strip():
                    continue
                counters = parse_counters(pt)
                if counters["task_header"] is None:
                    continue
                M = len(fields)
                N = M + 1
                header = counters["task_header"]
                cove = counters["cove_keys"]
                if header == N and all(v == N for v in cove):
                    continue  # уже согласовано

                # Классифицировать
                if header == N and cove and all(v == N for v in cove):
                    category = "OK"  # не должно попасть
                elif header == N and not counters["task_has_plus_evidence"]:
                    category = "A"  # числа ОК, формулировка неканонична
                elif header == N and counters["task_has_plus_evidence"]:
                    category = "C"  # «N полей (плюс evidence)» → должно M + evidence = N
                elif header != N and cove and all(v == header for v in cove):
                    # header и CoVe согласованы между собой, но не с полями
                    if header == M:
                        category = "D_coherent_no_ev"  # нет evidence в счёте вообще
                    else:
                        category = "D_off"  # расходится
                elif header == M and cove and all(v == M for v in cove):
                    category = "D_no_ev"  # везде M без evidence — некорректно
                else:
                    category = "X"  # сложный случай

                rows.append({
                    "file": p.name,
                    "check_id": c.get("id", "?"),
                    "M": M,
                    "N": N,
                    "header": header,
                    "has_plus_ev": counters["task_has_plus_evidence"],
                    "cove": cove,
                    "rules_fields": counters["rules_fields"],
                    "category": category,
                })

    # Сводка
    print(f"Всего классифицировано: {len(rows)}\n")
    by_cat = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r)

    for cat in sorted(by_cat.keys()):
        items = by_cat[cat]
        print(f"\n{'='*110}")
        print(f"КАTЕГОРИЯ {cat}: {len(items)}")
        print(f"{'='*110}")
        print(f"{'FILE':<40} {'CHECK':<42} {'M':<4} {'N':<4} {'hdr':<5} {'+ev':<5} {'cove':<20}")
        for r in items:
            print(f"{r['file'][:38]:<40} {r['check_id'][:40]:<42} "
                  f"{r['M']:<4} {r['N']:<4} {r['header']:<5} "
                  f"{str(r['has_plus_ev'])[:4]:<5} {str(r['cove'])[:18]:<20}")


if __name__ == "__main__":
    main()

    