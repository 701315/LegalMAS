#!/usr/bin/env python3
"""
READ-ONLY. Аудит retrieval.profile:
  • список валидных профилей из retrieval_profiles.py
  • все вхождения profile в 5 группах
  • невалидные значения с распределением по файлам
  • есть ли соответствие с валидными (по нормализованному имени)
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

import yaml

GROUPS = [
    "group_1_ownership", "group_2_use", "group_3_works",
    "group_4_services", "group_5_financial",
]
BASE = Path("playbooks/document_types")
PROFILES_FILE = Path("src/engine/playbook/retrieval_profiles.py")


def load_valid_profiles() -> set[str]:
    if not PROFILES_FILE.exists():
        return set()
    text = PROFILES_FILE.read_text(encoding="utf-8")
    return set(re.findall(r'profile_id\s*=\s*"([^"]+)"', text))


def main() -> None:
    valid = load_valid_profiles()
    print(f"Валидных профилей в retrieval_profiles.py: {len(valid)}\n")
    print("Их список (для справки):")
    for i, v in enumerate(sorted(valid), 1):
        print(f"  {i:2d}. {v}")

    # ─── Собираем все profile из YAML ───
    all_profiles: Counter[str] = Counter()
    by_profile: dict[str, list[tuple[str, str]]] = defaultdict(list)
    no_profile: list[tuple[str, str]] = []

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
                cid = c.get("id", "?")
                r = c.get("retrieval") or {}
                prof = r.get("retrieval_profile")
                if prof is None:
                    no_profile.append((p.name, cid))
                elif isinstance(prof, str) and prof.strip():
                    all_profiles[prof] += 1
                    by_profile[prof].append((p.name, cid))

    # ─── Классификация ───
    valid_used: list[tuple[str, int]] = []
    invalid_used: list[tuple[str, int]] = []
    for prof, n in all_profiles.most_common():
        if prof in valid:
            valid_used.append((prof, n))
        else:
            invalid_used.append((prof, n))

    print(f"\n{'='*100}")
    print(f"ИТОГИ")
    print(f"{'='*100}")
    print(f"  Всего вхождений retrieval_profile: {sum(all_profiles.values())}")
    print(f"  Валидных значений: {len(valid_used)} уникальных, {sum(n for _, n in valid_used)} вхождений")
    print(f"  НЕвалидных значений: {len(invalid_used)} уникальных, {sum(n for _, n in invalid_used)} вхождений")
    print(f"  Checks без retrieval_profile: {len(no_profile)}")

    # ─── Валидные — короткая сводка ───
    print(f"\n{'='*100}")
    print(f"ВАЛИДНЫЕ профили (используются в YAML)")
    print(f"{'='*100}")
    for prof, n in valid_used:
        print(f"  {n:4d}  {prof}")

    # ─── Невалидные — детально ───
    if invalid_used:
        print(f"\n{'='*100}")
        print(f"❌ НЕВАЛИДНЫЕ профили")
        print(f"{'='*100}")
        for prof, n in invalid_used:
            print(f"\n  {n:4d}  {prof!r}")
            # предполагаемая замена: нормализовать и искать среди valid
            norm = prof.replace("_check", "").replace("_", " ")
            candidates = [v for v in valid if any(
                word in v for word in norm.split() if len(word) > 3
            )]
            if candidates:
                print(f"        похожие валидные: {candidates[:3]}")
            else:
                print(f"        похожих нет — вероятно, надо удалить или добавить профиль")
            # примеры
            print(f"        примеры:")
            for fname, cid in by_profile[prof][:5]:
                print(f"          {fname:<45} {cid}")
            if len(by_profile[prof]) > 5:
                print(f"          ... ещё {len(by_profile[prof]) - 5}")


if __name__ == "__main__":
    main()
    