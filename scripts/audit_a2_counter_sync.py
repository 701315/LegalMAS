#!/usr/bin/env python3
"""
Детальный аудит A2: рассинхрон счётчиков <task> ↔ extraction.fields.

READ-ONLY. Ничего не меняет.

Для каждого check-а, где в <task> указано «следующие N полей»:
  • Считает реальное число полей в extraction.fields
  • Парсит поля из <task> (нумерованный список)
  • Показывает diff, недостающие/лишние поля
  • Классифицирует по паттернам
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

import yaml

GROUPS = [
    "group_1_ownership",
    "group_2_use",
    "group_3_works",
    "group_4_services",
    "group_5_financial",
]
BASE = Path("playbooks/document_types")


def parse_task_fields(prompt_text: str) -> list[tuple[int, str]]:
    """
    Возвращает [(N, field_name), ...] — поля, перечисленные в <task>
    как 'N. field_name' или 'N. field_a / field_b'.
    """
    m = re.search(r"<task>(.*?)</task>", prompt_text, re.DOTALL)
    if not m:
        return []
    body = m.group(1)
    fields: list[tuple[int, str]] = []
    for line in body.split("\n"):
        # N. field_name
        m2 = re.match(r"\s*(\d+)\.\s*([a-zA-Z][a-zA-Z0-9_]*)", line)
        if m2:
            fields.append((int(m2.group(1)), m2.group(2)))
            # paired: field_a / field_b
            pair = re.search(r"/\s*([a-zA-Z][a-zA-Z0-9_]*)", line)
            if pair:
                fields.append((int(m2.group(1)), pair.group(1)))
    return fields


def collect():
    findings: list[dict] = []

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
                pt = ext.get("llm_prompt_extraction")
                if not isinstance(pt, str) or not pt.strip():
                    continue

                fields = [
                    f["name"] for f in (ext.get("fields") or [])
                    if isinstance(f, dict) and f.get("name")
                ]
                if not fields:
                    continue

                # Ищем «N полей»
                m = re.search(r"следующие\s+(\d+)\s+полей", pt)
                if not m:
                    continue
                declared = int(m.group(1))
                actual = len(fields)
                if declared == actual:
                    continue

                # Парсим <task>
                task_fields = parse_task_fields(pt)
                task_names = [n for _, n in task_fields]

                in_task_not_fields = sorted(set(task_names) - set(fields))
                in_fields_not_task = sorted(set(fields) - set(task_names))

                # Номера в task — последний
                last_num = max((n for n, _ in task_fields), default=0)

                findings.append({
                    "file": p.name,
                    "check_id": c.get("id", "?"),
                    "declared": declared,
                    "actual": actual,
                    "diff": declared - actual,
                    "task_field_count": len(task_fields),
                    "last_task_num": last_num,
                    "in_task_not_fields": in_task_not_fields,
                    "in_fields_not_task": in_fields_not_task,
                    "fields": fields,
                    "task_names": task_names,
                })

    return findings


def main() -> None:
    findings = collect()
    print(f"Найдено рассинхронов: {len(findings)}\n")

    # Сводная таблица
    print(f"{'FILE':<38} {'CHECK':<48} {'decl':<5} {'act':<5} {'diff':<5} {'task_n':<7} {'last_#':<7}")
    print("-" * 125)
    for f in sorted(findings, key=lambda x: (x["file"], x["check_id"])):
        print(
            f"{f['file'][:36]:<38} {f['check_id'][:46]:<48} "
            f"{f['declared']:<5} {f['actual']:<5} {f['diff']:<+5} "
            f"{f['task_field_count']:<7} {f['last_task_num']:<7}"
        )

    # Паттерны diff
    print("\n\n=== ПАТТЕРНЫ diff (declared - actual) ===")
    diffs = Counter(f["diff"] for f in findings)
    for d, n in diffs.most_common():
        print(f"  diff = {d:+d}: {n} случаев")

    # Паттерны task_field_count vs actual
    print("\n=== ПАТТЕРНЫ (task_field_count - actual) ===")
    tfc = Counter(f["task_field_count"] - f["actual"] for f in findings)
    for d, n in tfc.most_common():
        print(f"  task содержит на {d:+d} полей, чем actual: {n} случаев")

    # Детали по каждому
    print("\n\n=== ДЕТАЛИ (первые 40) ===")
    for f in findings[:40]:
        print(f"\n--- {f['file']}::{f['check_id']} ---")
        print(f"  declared={f['declared']}  actual={f['actual']}  diff={f['diff']:+d}")
        print(f"  task_field_count={f['task_field_count']}  last_task_num={f['last_task_num']}")
        if f["in_task_not_fields"]:
            print(f"  ⚠️  в task, но нет в fields: {f['in_task_not_fields']}")
        if f["in_fields_not_task"]:
            print(f"  ⚠️  в fields, но нет в task: {f['in_fields_not_task']}")
        # Показать поля в порядке, для понимания
        print(f"  fields:       {f['fields']}")
        print(f"  task:         {f['task_names']}")


if __name__ == "__main__":
    main()
    