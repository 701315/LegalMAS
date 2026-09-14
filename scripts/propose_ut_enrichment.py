#!/usr/bin/env python3
"""
ТОЛЬКО АНАЛИЗ. Ничего не меняет.

Для check-ов с preferred_unit_types, состоящими только из old_5
(obligation, general_provision, definition, structural_anchor, technical_fragment),
предлагает добавить специфичные UT на основе ключевых слов в check_id и name.

По итогам — вывод с группировкой по предлагаемому UT и примерами.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import yaml

OLD_5 = {
    "obligation", "general_provision", "definition",
    "structural_anchor", "technical_fragment",
}

# Каждое правило: (список паттернов, предлагаемый UT, обоснование)
RULES = [
    (("parties", "party", "authority", "signatory", "identification", "requisites", "representatives"),
     "representations", "стороны и полномочия"),
    (("delivery", "transfer", "handover", "shipping", "return", "acceptance", "incoterms"),
     "title_transfer", "передача/возврат/приёмка"),
    (("payment", "price", "remuneration", "tariff", "fee", "cost", "prepayment", "refund", "advance"),
     "payment_term", "цена/оплата"),
    (("warranty", "quality", "defect", "completeness", "conformity", "hidden_defects"),
     "warranty", "качество/гарантия"),
    (("termination", "exit", "closeout", "revocation", "withdrawal", "cancellation"),
     "termination_provision", "расторжение"),
    (("liability", "penalty", "damages", "sanction", "remedy", "remedies", "default", "breach", "fine"),
     "liability_provision", "ответственность/санкции"),
    (("force_majeure", "circumstances", "emergency", "impediment"),
     "force_majeure", "форс-мажор"),
    (("confidential", "nda", "non_disclosure", "secrecy", "trade_secret"),
     "confidentiality", "конфиденциальность"),
    (("assignment", "cession", "succession", "transfer_of_claim"),
     "assignment", "уступка прав"),
    (("indemn", "hold_harmless"),
     "indemnification", "индемнити"),
    (("encumbrance", "lien", "pledge", "mortgage", "security", "collateral", "guarantee"),
     "liability_provision", "обеспечение"),
    (("jurisdiction", "arbitration", "court", "dispute", "claim"),
     "governing_law", "споры/юрисдикция"),
    (("governing_law", "applicable_law", "choice_of_law"),
     "governing_law", "применимое право"),
    (("notice", "notification", "communication"),
     "notice", "уведомления"),
    (("covenant", "undertaking"),
     "covenants", "ковенанты"),
    (("amendment", "modification", "change_order", "change_of"),
     "amendment", "изменения"),
    (("personal_data", "gdpr", "pdn", "pd_processing"),
     "personal_data", "персональные данные"),
    (("corporate", "governance", "approval", "board"),
     "governance", "корпоративное"),
    (("insurance", "insure"),
     "obligation", "страхование"),
    (("registration", "state_registration", "rosreestr", "egrn"),
     "governance", "регистрация"),
    (("conditions_precedent", "closing_conditions", "cp_"),
     "conditions_precedent", "условия закрытия"),
    (("effective_date", "effective_from"),
     "effective_date", "дата вступления"),
    (("severability",),
     "severability", "severability"),
    (("entire_agreement",),
     "entire_agreement", "entire agreement"),
]

GROUPS = ["group_1_ownership", "group_2_use", "group_3_works",
          "group_4_services", "group_5_financial"]

BASE = Path("playbooks/document_types")


def suggest_ut(check_id: str, name: str) -> list[tuple[str, str]]:
    haystack = f"{check_id} {name}".lower()
    out: list[tuple[str, str]] = []
    seen = set()
    for patterns, ut, reason in RULES:
        if ut in seen:
            continue
        for p in patterns:
            if p in haystack:
                out.append((ut, reason))
                seen.add(ut)
                break
    return out


def main() -> None:
    suggestions_by_ut: dict[str, list[tuple[str, str, str, list[str]]]] = defaultdict(list)
    total_old5 = 0
    total_suggested = 0

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
                r = c.get("retrieval") or {}
                pref = r.get("preferred_unit_types") or []
                if not pref or set(pref) - OLD_5:
                    continue
                total_old5 += 1
                cid = c.get("id", "?")
                name = c.get("name", "") or ""
                sugg = suggest_ut(cid, name)
                if not sugg:
                    continue
                total_suggested += 1
                for ut, reason in sugg:
                    suggestions_by_ut[ut].append((p.name, cid, name[:70], list(pref)))

    print("=" * 110)
    print(f"Всего check-ов «только old_5»: {total_old5}")
    print(f"Из них с предложением обогащения: {total_suggested}")
    print(f"Уникальных UT-предложений: {len(suggestions_by_ut)}")
    print("=" * 110)

    for ut, items in sorted(suggestions_by_ut.items(), key=lambda kv: -len(kv[1])):
        print(f"\n📌 UT = {ut}   ({len(items)} check-ов)")
        print("-" * 110)
        for fname, cid, name, pref in items[:10]:
            print(f"   {fname:<42} {cid:<50}")
            print(f"       name: {name}")
            print(f"       current: {pref}")
        if len(items) > 10:
            print(f"   ... ещё {len(items) - 10} check-ов этой категории")


if __name__ == "__main__":
    main()

    