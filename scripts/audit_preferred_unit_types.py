#!/usr/bin/env python3
"""
Диагностика preferred_unit_types / excluded_unit_types
в playbooks/document_types/group_1..5.

Только читает. Ничего не меняет.

Показывает:
  1. Число файлов / check-ов в каждой папке.
  2. Распределение preferred_unit_types по значениям.
  3. Какие значения НЕвалидны по 29 LegalUnitType (если есть).
  4. Сколько check-ов используют ТОЛЬКО «старые 5» значений
     (obligation, general_provision, definition, structural_anchor, technical_fragment)
     — это кандидаты на обогащение специфичными типами.
  5. Список примеров таких check-ов (по 5 на папку).
  6. Распределение excluded_unit_types.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import yaml

# source of truth
sys.path.insert(0, "src")
from services.structure.legal_unit_models import LegalUnitType  # noqa: E402

VALID_UT = {m.value for m in LegalUnitType}

OLD_5 = {
    "obligation", "general_provision", "definition",
    "structural_anchor", "technical_fragment",
}

GROUPS = [
    "group_1_ownership",
    "group_2_use",
    "group_3_works",
    "group_4_services",
    "group_5_financial",
]

BASE = Path("playbooks/document_types")


def iter_checks(path: Path):
    try:
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ⚠️  parse error: {path.name}: {e}")
        return
    for c in (d or {}).get("checks_v8") or []:
        yield c


def analyze_group(group: str) -> dict:
    root = BASE / group
    if not root.exists():
        return {"error": f"нет папки {root}"}

    files = list(root.rglob("*.yaml"))
    n_checks = 0
    pref_counter: Counter[str] = Counter()
    excl_counter: Counter[str] = Counter()
    invalid: list[tuple[str, str, str]] = []
    only_old5: list[tuple[str, str]] = []
    only_one: list[tuple[str, str]] = []
    no_ut: list[tuple[str, str]] = []
    has_specific: int = 0

    for p in files:
        for c in iter_checks(p):
            n_checks += 1
            cid = c.get("id", "?")
            r = c.get("retrieval") or {}
            pref = r.get("preferred_unit_types") or []
            excl = r.get("excluded_unit_types") or []

            for v in pref:
                pref_counter[v] += 1
                if v not in VALID_UT:
                    invalid.append((p.name, cid, v))
            for v in excl:
                excl_counter[v] += 1

            if not pref:
                no_ut.append((p.name, cid))
            else:
                s = set(pref)
                if s <= OLD_5:
                    only_old5.append((p.name, cid))
                else:
                    has_specific += 1
                if len(s) == 1:
                    only_one.append((p.name, cid))

    return {
        "group": group,
        "n_files": len(files),
        "n_checks": n_checks,
        "pref_counter": pref_counter,
        "excl_counter": excl_counter,
        "invalid": invalid,
        "only_old5": only_old5,
        "only_one": only_one,
        "no_ut": no_ut,
        "has_specific": has_specific,
    }


def main() -> None:
    print(f"Valid LegalUnitType values: {len(VALID_UT)}")
    print(sorted(VALID_UT))
    print()
    print("=" * 100)

    results = []
    for g in GROUPS:
        print(f"\n📁 {g}")
        print("-" * 100)
        res = analyze_group(g)
        results.append(res)

        if "error" in res:
            print(f"  ❌ {res['error']}")
            continue

        print(f"  Файлов: {res['n_files']}   |   Check-ов: {res['n_checks']}")
        print(f"  Со специфичными UT:   {res['has_specific']}")
        print(f"  Только old_5:         {len(res['only_old5'])}")
        print(f"  Один UT:              {len(res['only_one'])}")
        print(f"  Без preferred_ut:     {len(res['no_ut'])}")
        print(f"  Невалидных UT:        {len(res['invalid'])}")

        print("\n  preferred_unit_types — частоты:")
        for v, n in res["pref_counter"].most_common():
            mark = "" if v in VALID_UT else "   ⚠️ NOT VALID"
            print(f"    {n:4d}  {v}{mark}")

        print("\n  excluded_unit_types — частоты:")
        for v, n in res["excl_counter"].most_common():
            mark = "" if v in VALID_UT else "   ⚠️ NOT VALID"
            print(f"    {n:4d}  {v}{mark}")

        if res["invalid"]:
            print("\n  ⚠️ Невалидные значения:")
            for f, cid, v in res["invalid"][:20]:
                print(f"    {f:<42} {cid:<45} {v}")

        if res["no_ut"]:
            print("\n  🔸 Check-и без preferred_unit_types:")
            for f, cid in res["no_ut"][:20]:
                print(f"    {f:<42} {cid}")

    # ─── Сводка по всем группам ───
    print("\n" + "=" * 100)
    print("\n📊 СВОДКА ПО 5 ГРУППАМ")
    print("-" * 100)
    total_checks = sum(r.get("n_checks", 0) for r in results)
    total_has_specific = sum(r.get("has_specific", 0) for r in results)
    total_only_old5 = sum(len(r.get("only_old5", [])) for r in results)
    total_only_one = sum(len(r.get("only_one", [])) for r in results)
    total_no_ut = sum(len(r.get("no_ut", [])) for r in results)
    total_invalid = sum(len(r.get("invalid", [])) for r in results)
    print(f"  Всего check-ов:       {total_checks}")
    print(f"  Со специфичными UT:   {total_has_specific}")
    print(f"  Только old_5:         {total_only_old5}")
    print(f"  Один UT:              {total_only_one}")
    print(f"  Без preferred_ut:     {total_no_ut}")
    print(f"  Невалидных UT:        {total_invalid}")

    # ─── Общие частоты по всем группам ───
    all_pref: Counter[str] = Counter()
    for r in results:
        if "pref_counter" in r:
            all_pref.update(r["pref_counter"])
    print("\n  preferred_unit_types во всех 5 группах:")
    for v, n in all_pref.most_common():
        mark = "" if v in VALID_UT else "   ⚠️ NOT VALID"
        print(f"    {n:4d}  {v}{mark}")

    # ─── Примеры кандидатов на обогащение ───
    print("\n" + "=" * 100)
    print("\n🎯 ПРИМЕРЫ кандидатов на обогащение (только old_5), по 5 на папку:")
    print("-" * 100)
    for r in results:
        if "only_old5" not in r or not r["only_old5"]:
            continue
        print(f"\n📁 {r['group']}  ({len(r['only_old5'])} шт., показаны первые 5)")
        for f, cid in r["only_old5"][:5]:
            print(f"    {f:<42} {cid}")


if __name__ == "__main__":
    main()
    