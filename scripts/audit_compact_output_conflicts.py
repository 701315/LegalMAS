#!/usr/bin/env python3
"""
READ-ONLY аудит конфликтов compact_output.

Ищет checks, где:
- extraction.enabled = true
- есть custom llm_prompt_extraction
- compact_output явно = true

Показывает:
- сколько таких конфликтов всего
- какие из них одновременно underbudget
- топ файлов по числу конфликтов
- приоритетные checks для ручной правки

Ничего не изменяет.
"""

from __future__ import annotations

import glob
import os
import sys
from collections import Counter, defaultdict

try:
    import yaml
except ImportError:
    print("ERROR: pip install pyyaml")
    sys.exit(1)

ROOTS = [
    "/srv/steloom-dev/playbooks/global_checks",
    "/srv/steloom-dev/playbooks/document_types",
]

# Те же эвристики, что и в основном audit
TOKENS_BY_PRESENTATION = {
    "diagnostic": 160,
    "summary": 120,
    "signal": 70,
    "fact": 90,
}
TOKENS_EVIDENCE_LIST = 50
TOKENS_JSON_OVERHEAD = 80
RESERVE_FACTOR = 1.25
ROUND_TO = 50

ENV_DEFAULT_EXTRACTION_TOKENS = 900


def round_up(n: int, step: int = ROUND_TO) -> int:
    r = n % step
    return n if r == 0 else n + step - r


def load_env_default() -> int:
    env_path = "/srv/steloom-dev/.env"
    value = ENV_DEFAULT_EXTRACTION_TOKENS
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("LLM_EXTRACTION_MAX_TOKENS="):
                    raw = line.split("=", 1)[1].strip().strip('"').strip("'")
                    value = int(raw)
                    break
    except Exception:
        pass
    return value


def compute_recommended(fields: list[dict]) -> int:
    if not fields:
        return 0
    raw = TOKENS_JSON_OVERHEAD
    for f in fields:
        ft = str(f.get("type") or "string").strip().lower()
        pr = str(f.get("presentation") or "fact").strip().lower()
        if ft == "evidence_list":
            raw += TOKENS_EVIDENCE_LIST
        else:
            raw += TOKENS_BY_PRESENTATION.get(pr, 90)
    return round_up(int(raw * RESERVE_FACTOR))


def parse_check(check: dict, filepath: str, source: str) -> dict | None:
    extraction = check.get("extraction")
    if not isinstance(extraction, dict):
        return None
    if not extraction.get("enabled"):
        return None

    fields = extraction.get("fields") or []
    compact_present = "compact_output" in extraction
    compact_value = extraction.get("compact_output")
    has_custom_prompt = bool(extraction.get("llm_prompt_extraction"))

    return {
        "check_id": check.get("id", "???"),
        "check_name": check.get("name", ""),
        "file": filepath,
        "source": source,
        "fields": fields,
        "fields_count": len(fields),
        "compact_present": compact_present,
        "compact_value": compact_value,
        "has_custom_prompt": has_custom_prompt,
        "yaml_llm_max_tokens": extraction.get("llm_max_tokens"),
    }


def load_all_checks() -> list[dict]:
    out: list[dict] = []

    for root in ROOTS:
        if not os.path.isdir(root):
            continue

        for fp in sorted(glob.glob(os.path.join(root, "**/*.yaml"), recursive=True)):
            try:
                with open(fp, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
            except Exception:
                continue

            if not isinstance(data, dict):
                continue

            # global check format
            if "extraction" in data and isinstance(data["extraction"], dict):
                rec = parse_check(data, fp, "global_check")
                if rec:
                    out.append(rec)
                continue

            # doc-type format
            for section in ("checks_v8", "doc_type_checks", "compliance_rules"):
                checks = data.get(section)
                if not isinstance(checks, list):
                    continue
                for check in checks:
                    if not isinstance(check, dict):
                        continue
                    rec = parse_check(check, fp, f"doc_type/{section}")
                    if rec:
                        out.append(rec)

    return out


def relpath(path: str) -> str:
    return path.replace("/srv/steloom-dev/", "")


def main() -> None:
    env_default = load_env_default()
    all_checks = load_all_checks()

    # Конфликт = custom prompt + compact_output явно задан и == true
    conflicts = [
        c for c in all_checks
        if c["has_custom_prompt"] and c["compact_present"] and c["compact_value"] is True
    ]

    for c in conflicts:
        c["recommended_tokens"] = compute_recommended(c["fields"])
        c["current_tokens"] = c["yaml_llm_max_tokens"] or env_default
        c["token_deficit"] = c["recommended_tokens"] - c["current_tokens"]
        c["underbudget"] = c["current_tokens"] < c["recommended_tokens"]

    total = len(conflicts)
    underbudget = [c for c in conflicts if c["underbudget"]]
    ok_budget = [c for c in conflicts if not c["underbudget"]]

    print("=" * 110)
    print("АУДИТ COMPACT_OUTPUT КОНФЛИКТОВ")
    print(f"Platform default LLM_EXTRACTION_MAX_TOKENS = {env_default}")
    print(f"Всего конфликтов: {total}")
    print(f"Из них underbudget: {len(underbudget)}")
    print(f"Из них budget OK: {len(ok_budget)}")
    print("=" * 110)
    print()

    # Сводка по source
    by_source = Counter(c["source"] for c in conflicts)
    print("По источнику:")
    for src, cnt in by_source.most_common():
        print(f"  {src:<24} {cnt:>4}")
    print()

    # Топ файлов
    print("TOP-15 файлов по числу конфликтов:")
    file_counts = Counter(c["file"] for c in conflicts)
    for fp, cnt in file_counts.most_common(15):
        print(f"  {cnt:>3}  {relpath(fp)}")
    print()

    # Распределение по полям
    buckets = {
        "1-4":  lambda n: 1 <= n <= 4,
        "5-7":  lambda n: 5 <= n <= 7,
        "8-11": lambda n: 8 <= n <= 11,
        "12-15": lambda n: 12 <= n <= 15,
        "16+":  lambda n: n >= 16,
    }
    print("Распределение конфликтов по числу полей:")
    for label, pred in buckets.items():
        bucket = [c for c in conflicts if pred(c["fields_count"])]
        print(f"  {label:<6} {len(bucket):>4}")
    print()

    # Самые критичные конфликты: conflict + underbudget + biggest deficit
    print("TOP-40 приоритетных конфликтов (custom prompt + compact_output=true + underbudget):")
    print("-" * 110)
    print(f"{'check_id':<42} {'полей':>5} {'тек.':>6} {'рек.':>6} {'δ':>6}  файл")
    print("-" * 110)
    for c in sorted(underbudget, key=lambda x: x["token_deficit"], reverse=True)[:40]:
        print(
            f"{c['check_id']:<42} "
            f"{c['fields_count']:>5} "
            f"{c['current_tokens']:>6} "
            f"{c['recommended_tokens']:>6} "
            f"{c['token_deficit']:>6}  "
            f"{relpath(c['file'])}"
        )
    print()

    # Конфликты с нормальным budget — отдельно
    print("TOP-20 конфликтов, где budget уже достаточен (требуют только review compact_output=true):")
    print("-" * 110)
    print(f"{'check_id':<42} {'полей':>5} {'тек.':>6} {'рек.':>6} {'запас':>6}  файл")
    print("-" * 110)
    for c in sorted(ok_budget, key=lambda x: (x["current_tokens"] - x["recommended_tokens"]))[:20]:
        margin = c["current_tokens"] - c["recommended_tokens"]
        print(
            f"{c['check_id']:<42} "
            f"{c['fields_count']:>5} "
            f"{c['current_tokens']:>6} "
            f"{c['recommended_tokens']:>6} "
            f"{margin:>6}  "
            f"{relpath(c['file'])}"
        )
    print()

    # Сводка по файлам для wave planning
    print("Wave-1 кандидаты (файлы с >= 5 конфликтами):")
    wave1 = [(fp, cnt) for fp, cnt in file_counts.most_common() if cnt >= 5]
    for fp, cnt in wave1:
        print(f"  {cnt:>3}  {relpath(fp)}")
    print()

    print("=" * 110)
    print("ИНТЕРПРЕТАЦИЯ")
    print("- compact_output=true здесь задан ЯВНО при наличии custom prompt.")
    print("- Такие случаи надо проверить вручную: нужен ли footer на самом деле.")
    print("- Если одновременно есть underbudget, сначала корректируем llm_max_tokens,")
    print("  потом решаем оставлять ли compact_output=true.")
    print("=" * 110)


if __name__ == "__main__":
    main()
