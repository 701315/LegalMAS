#!/usr/bin/env python3
"""
Агрегированная сводка по результатам audit_extraction_token_budget.
"""
import glob
import os
import sys
from collections import Counter
try:
    import yaml
except ImportError:
    sys.exit(1)

_ENV_DEFAULT = 900
try:
    with open("/srv/steloom-dev/.env", encoding="utf-8") as f:
        for line in f:
            if line.startswith("LLM_EXTRACTION_MAX_TOKENS="):
                _ENV_DEFAULT = int(line.split("=", 1)[1].strip().strip('"\''))
except Exception:
    pass

_W = { "diagnostic": 160, "summary": 120, "signal": 70, "fact": 90 }

def compute(fields):
    if not fields: return 0
    raw = 80
    for f in fields:
        ft = str(f.get("type", "")).lower()
        pr = str(f.get("presentation", "fact")).lower()
        raw += 50 if ft == "evidence_list" else _W.get(pr, 90)
    res = int(raw * 1.25)
    return res if res % 50 == 0 else res + 50 - (res % 50)

def parse(check, fp, src):
    ext = check.get("extraction")
    if not isinstance(ext, dict) or not ext.get("enabled"): return None
    fl = ext.get("fields") or []
    return {
        "id": check.get("id", ""), "file": fp, "fields": len(fl),
        "yaml_tok": ext.get("llm_max_tokens"),
        "custom": bool(ext.get("llm_prompt_extraction")),
        "compact": ext.get("compact_output"), "fl_raw": fl
    }

records = []
for d in ["/srv/steloom-dev/playbooks/global_checks", "/srv/steloom-dev/playbooks/document_types"]:
    if not os.path.isdir(d): continue
    for fp in glob.glob(os.path.join(d, "**/*.yaml"), recursive=True):
        try:
            with open(fp, encoding="utf-8") as f: data = yaml.safe_load(f)
        except Exception: continue
        if not isinstance(data, dict): continue
        if "extraction" in data and isinstance(data["extraction"], dict):
            r = parse(data, fp, "global")
            if r: records.append(r)
            continue
        for sec in ("checks_v8", "doc_type_checks", "compliance_rules"):
            if isinstance(data.get(sec), list):
                for chk in data[sec]:
                    if isinstance(chk, dict):
                        r = parse(chk, fp, sec)
                        if r: records.append(r)

for r in records:
    r["rec"] = compute(r["fl_raw"])
    cur = r["yaml_tok"] or _ENV_DEFAULT
    r["cur"] = cur
    r["env"] = r["yaml_tok"] is None
    r["crit"] = cur < r["rec"]
    r["conf"] = r["custom"] and r["compact"] is True

tot = len(records)
crit = [r for r in records if r["crit"]]
conf = sum(1 for r in records if r["conf"])
env_c = sum(1 for r in crit if r["env"])
yml_c = len(crit) - env_c

print("="*80)
print(f"  СВОДКА (LLM_EXTRACTION_MAX_TOKENS = {_ENV_DEFAULT})")
print(f"  Всего: {tot}  |  Критичных: {len(crit)}  |  Конфликтов: {conf}")
print("-" * 80)
print(f"  От .env: {env_c}  |  От YAML: {yml_c}")
if crit:
    print("-" * 80)
    print("  Топ файлов с критичными чеками:")
    for fp, c in Counter(r["file"] for r in crit).most_common(5):
        print(f"  {c:>3}  {fp.replace('/srv/steloom-dev/', '')}")
    print("-" * 80)
    print("  Самые большие чеки (16+ полей):")
    for r in sorted([r for r in records if r["fields"] >= 16], key=lambda x: -x["fields"]):
        print(f"  {r['fields']:>2} полей | рек: {r['rec']} | {r['id']}")
print("="*80)
