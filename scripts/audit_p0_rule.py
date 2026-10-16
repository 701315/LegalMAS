#!/usr/bin/env python3
"""Аудит пункта 0 (правило агрегации presence) во всех doc-type чеках.

  python3 scripts/audit_p0_rule.py
"""
import re, sys
from pathlib import Path
from collections import defaultdict
import yaml


def extract_p0_block(llm_prompt: str) -> str | None:
    """Извлекает блок пункта 0 из <task> до начала пункта 1."""
    task_match = re.search(r"<task>(.*?)</task>", llm_prompt, re.S)
    if not task_match:
        return None
    task_text = task_match.group(1)
    
    # Ищем "0. <presence_field>:" до "1. "
    m = re.search(r"(?m)^\s*0\.\s+[\w_]+\s*:.*?(?=^\s*1\.\s|\Z)", task_text, re.S | re.M)
    return m.group(0).strip() if m else None


def normalize(block: str) -> str:
    """Нормализует блок для сравнения: убирает имена полей и лишние пробелы."""
    s = re.sub(r"[\w_]+_presence", "<PRESENCE_FIELD>", block)
    s = re.sub(r"[\w_]+_status", "<STATUS_FIELD>", s)
    s = re.sub(r"[\w_]+_details", "<DETAILS_FIELD>", s)
    s = re.sub(r"[\w_]+_display", "<DISPLAY_FIELD>", s)
    s = re.sub(r"[\w_]+_value", "<VALUE_FIELD>", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def main():
    root = Path("playbooks/document_types")
    variants = defaultdict(list)  # normalized_block -> [(file, check_id, raw_block)]
    missing_p0 = []
    missing_task = []
    
    for p in sorted(root.rglob("*.yaml")):
        try:
            doc = yaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[ERR] {p}: {e}", file=sys.stderr)
            continue
        checks = doc.get("checks_v8") or doc.get("checks") or []
        for c in checks:
            ex = c.get("extraction") or {}
            l2 = ex.get("llm_prompt_extraction") or ""
            p0 = extract_p0_block(l2)
            if p0 is None:
                if "<task>" not in l2:
                    missing_task.append((str(p), c.get("id")))
                else:
                    missing_p0.append((str(p), c.get("id")))
                continue
            variants[normalize(p0)].append((str(p), c.get("id"), p0))
    
    print("=" * 80)
    print(f"УНИКАЛЬНЫХ ВАРИАНТОВ ПУНКТА 0 (после нормализации): {len(variants)}")
    print("=" * 80)
    
    for i, (norm, items) in enumerate(sorted(variants.items(), key=lambda x: -len(x[1])), 1):
        print(f"\n--- ВАРИАНТ #{i} ({len(items)} чеков) ---")
        print(f"Нормализованная сигнатура (первые 400 символов):\n  {norm[:400]}...")
        print(f"\nПример сырого блока (первый чек):")
        print("  " + items[0][2].replace("\n", "\n  "))
        print(f"\nЧеки этого варианта:")
        for f, cid, _ in items:
            print(f"  - {cid:50}  {f}")
    
    print("\n" + "=" * 80)
    print(f"ЧЕКИ БЕЗ ПУНКТА 0 (FAIL:L6): {len(missing_p0)}")
    print("=" * 80)
    for f, cid in missing_p0:
        print(f"  - {cid:50}  {f}")
    
    print(f"\nЧЕКИ БЕЗ <task> ВООБЩЕ (FAIL:L1): {len(missing_task)}")
    for f, cid in missing_task:
        print(f"  - {cid:50}  {f}")


if __name__ == "__main__":
    main()


    