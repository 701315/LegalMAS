#!/usr/bin/env python3
"""Полу-механическое добавление risk_weight для signal-полей.

Эвристика основана на эталоне contract_1.1_general_sale.yaml:
  - presence (агрегатное) → info (уже есть, не трогаем)
  - основной status/moment substantive-темы → high
  - вторичный status (mode/type/basis/method/scope) → medium
  - вспомогательный status (accessory/document/notice) → low

Скрипт трогает ТОЛЬКО signal-поля, у которых risk_weight отсутствует.

  python3 scripts/fix_risk_weight.py --dry-run
  python3 scripts/fix_risk_weight.py --dry-run > /tmp/rw_proposals.txt
  # После подтверждения:
  python3 scripts/fix_risk_weight.py
"""
import argparse, sys
from pathlib import Path
import yaml


# Ключевые слова для high risk_weight (substantive-темы)
HIGH_KEYWORDS = [
    "payment", "price", "subject", "quantity", "delivery", "transfer",
    "title", "acceptance", "warranty", "liability", "penalty", "termination",
    "consent", "obligation", "risk", "damages", "indemnity", "cap",
    "consequences", "breach", "default", "suspension", "solvency",
    "notarization", "deadline", "period", "amount", "sum", "value",
    "rate", "interest", "commission", "deposit", "withdrawal", "refund",
    "repayment", "overdraft", "insurance", "pledge", "mortgage",
    "encumbrance", "preemptive", "approval", "clearance", "escrow",
    "covenant", "restriction", "compliance", "sanction", "disclosure",
    "notification", "notice", "form", "registration",
]

# Ключевые слова для medium risk_weight (вторичные status)
MEDIUM_KEYWORDS = [
    "mode", "type", "basis", "method", "scope", "model", "alignment",
    "code", "category", "kind", "structure", "mechanism", "procedure",
    "process", "regime", "framework", "criteria", "allocation",
    "distribution", "priority", "proportion",
]

# Ключевые слова для low risk_weight (вспомогательные status)
LOW_KEYWORDS = [
    "accessory", "document", "marker", "label", "tag", "flag",
]


def infer_risk_weight(field_name: str) -> tuple[str, str]:
    """Предлагает risk_weight + обоснование."""
    name = field_name.lower()

    for kw in HIGH_KEYWORDS:
        if kw in name:
            return "high", f"keyword '{kw}' → high"

    for kw in MEDIUM_KEYWORDS:
        if kw in name:
            return "medium", f"keyword '{kw}' → medium"

    for kw in LOW_KEYWORDS:
        if kw in name:
            return "low", f"keyword '{kw}' → low"

    # Fallback
    if name.endswith("_status"):
        return "medium", "default for *_status"
    if name.endswith("_code") or name.endswith("_type"):
        return "medium", "default for *_code/*_type"
    return "medium", "default fallback"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="playbooks/document_types")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    files = sorted(Path(a.root).rglob("*.yaml"))
    proposals = []  # [(file, check_id, field_name, proposed_rw, reason)]

    for p in files:
        try:
            doc = yaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        checks = doc.get("checks_v8") or doc.get("checks") or []
        for c in checks:
            ex = c.get("extraction") or {}
            ps = ex.get("presence_signal") or {}
            pfield = ps.get("field") if isinstance(ps, dict) else None
            fields = ex.get("fields") or []
            for f in fields:
                if f.get("presentation") != "signal":
                    continue
                if f.get("risk_weight") is not None:
                    continue  # уже есть
                name = f.get("name", "")
                if name == pfield:
                    continue  # presence, пропускаем
                rw, reason = infer_risk_weight(name)
                proposals.append((str(p), c.get("id"), name, rw, reason))

    # Выводим таблицу
    print(f"{'Файл':<75} {'Check':<50} {'Поле':<45} {'RW':<8} Обоснование")
    print("=" * 200)
    for file, check, field, rw, reason in proposals:
        print(f"{file:<75} {check:<50} {field:<45} {rw:<8} {reason}")

    # Сводка по распределению
    from collections import Counter
    dist = Counter(rw for _, _, _, rw, _ in proposals)
    print(f"\n=== РАСПРЕДЕЛЕНИЕ ===")
    for rw in ["high", "medium", "low"]:
        print(f"  {rw:8} {dist.get(rw, 0)}")
    print(f"  {'TOTAL':8} {len(proposals)}")

    if a.dry_run:
        print("\nРЕЖИМ DRY-RUN. Изменений не внесено.")
        print("Чтобы применить: python3 scripts/fix_risk_weight.py")
    else:
        # Применяем правки
        by_file = {}
        for file, check, field, rw, _ in proposals:
            by_file.setdefault(file, []).append((check, field, rw))

        for file, items in by_file.items():
            p = Path(file)
            doc = yaml.safe_load(p.read_text(encoding="utf-8"))
            checks = doc.get("checks_v8") or doc.get("checks") or []
            for c in checks:
                for check, field, rw in items:
                    if c.get("id") == check:
                        for f in c.get("extraction", {}).get("fields", []):
                            if f.get("name") == field:
                                f["risk_weight"] = rw
            with open(p, "w", encoding="utf-8") as f:
                yaml.dump(doc, f, allow_unicode=True, sort_keys=False, width=1000)
            print(f"[OK] {file}")

        print(f"\nГОТОВО. Внесено {len(proposals)} исправлений.")


if __name__ == "__main__":
    main()



    