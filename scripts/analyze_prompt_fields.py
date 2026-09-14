#!/usr/bin/env python3
"""
Post-filter dd_grid_audit_INFO.txt по whitelist всех field_name.
"""
import re
from collections import Counter
from pathlib import Path

import yaml

ROOTS = [Path("playbooks/document_types"), Path("playbooks/global_checks")]
AUDIT_INFO = Path("scripts/dd_grid_audit_INFO.txt")


def collect_whitelist() -> set[str]:
    names: set[str] = set()
    for root in ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*.yaml"):
            try:
                d = yaml.safe_load(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            for c in (d or {}).get("checks_v8") or []:
                for f in (c.get("extraction") or {}).get("fields") or []:
                    if isinstance(f, dict) and isinstance(f.get("name"), str):
                        names.add(f["name"])
    return names


def parse_audit(text: str):
    # file + check идёт перед каждой записью
    # Собираем все (file, check, field, kind) через общий regex
    file_re = re.compile(r"ФАЙЛ:\s*(\S+)")
    check_re = re.compile(r"ЧЕК:\s*(\S+)")
    # Одна запись: `поле "X"` + на следующей строке пояснение
    rec_re = re.compile(
        r'поле "([^"]+)"\s*\n\s+Поле "[^"]+"\s+'
        r'(упомянуто в llm_prompt_extraction, но НЕ объявлено|'
        r'объявлено в extraction\.fields, но НЕ найдено)'
    )

    # Разбиваем текст на блоки по ФАЙЛ/ЧЕК
    records = []
    cur_file = None
    cur_check = None
    pos = 0
    # Находим все маркеры file/check с их позициями
    markers = []
    for m in file_re.finditer(text):
        markers.append((m.start(), "file", m.group(1)))
    for m in check_re.finditer(text):
        markers.append((m.start(), "check", m.group(1)))
    markers.sort()

    # Для каждой записи rec_re — найти предшествующий file и check
    for m in rec_re.finditer(text):
        field, direction = m.group(1), m.group(2)
        kind = "a" if "упомянуто" in direction else "b"
        # Последний file и check до позиции m.start()
        cur_file = None
        cur_check = None
        for pos2, kind2, val in markers:
            if pos2 > m.start():
                break
            if kind2 == "file":
                cur_file = val
            elif kind2 == "check":
                cur_check = val
        records.append((cur_file, cur_check, field, kind))
    return records


def main() -> None:
    text = AUDIT_INFO.read_text(encoding="utf-8")
    records = parse_audit(text)

    whitelist = collect_whitelist()
    print(f"Whitelist: {len(whitelist)} уникальных field_name из YAML")
    print(f"Записей в аудите: {len(records)}\n")

    a_all = [r for r in records if r[3] == "a"]
    a_real = [r for r in a_all if r[2] in whitelist]
    b_all = [r for r in records if r[3] == "b"]

    print(f"=== (a) только в prompt ===")
    print(f"  Всего: {len(a_all)},  реальных (в whitelist): {len(a_real)}\n")
    if a_real:
        print(f"  {'CHECK':<45} {'FIELD':<40} {'FILE'}")
        for f, c, name, _ in sorted(a_real):
            f_short = (f or "").split("/")[-1]
            print(f"  {(c or '')[:43]:<45} {name[:38]:<40} {f_short}")

    print(f"\n=== (b) только в fields ===")
    print(f"  Всего: {len(b_all)}\n")
    if b_all:
        print(f"  {'CHECK':<45} {'FIELD':<40} {'FILE'}")
        for f, c, name, _ in sorted(b_all):
            f_short = (f or "").split("/")[-1]
            print(f"  {(c or '')[:43]:<45} {name[:38]:<40} {f_short}")

    a_noise = Counter(r[2] for r in a_all if r[2] not in whitelist)
    print(f"\n=== (a) отсеяно как шум (топ-20) ===")
    for name, n in a_noise.most_common(20):
        print(f"  {n:4d}  {name}")


if __name__ == "__main__":
    main()
