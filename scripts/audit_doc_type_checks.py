#!/usr/bin/env python3
"""v3-auditor для playbooks/document_types/*. Только чтение. Версия 2 (исправлена).

  python3 scripts/audit_doc_type_checks.py
  python3 scripts/audit_doc_type_checks.py --only contract_1.1 --verbose
  python3 scripts/audit_doc_type_checks.py --json > /tmp/audit_v2.json
"""
from __future__ import annotations
import argparse, json, re, sys
from collections import Counter
from pathlib import Path
import yaml

FINAL_LINE = ("Технический формат JSON (value / confidence / location) задан "
              "отдельным контрактом — соблюдай его, но не описывай здесь.")
TAGS = ["<role>", "<context>", "<task>", "<context_rules>", "<edge_cases>", "<output_expectations>"]
RWS = {"high", "medium", "low", "info"}
PLACEHOLDER = re.compile(r"<[A-Z][A-Z_]{2,}>")
TYPOS = ["без markdown.без markdown.", ".без markdown."]


def blocks(raw: str):
    out = []
    for p in re.split(r"(?m)^(?=\s*- id:\s)", raw):
        m = re.match(r"\s*- id:\s*[\"']?([\w.\-]+)", p)
        if m:
            out.append((m.group(1), p))
    return out


def sect(text: str, tag: str) -> str:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.S)
    return m.group(1) if m else ""


def field_raw(raw: str, name: str) -> str:
    m = re.search(rf'(?m)^\s*-\s*name:\s*["\']?{re.escape(name)}["\']?\s*$([\s\S]*?)'
                  rf'(?=^\s*-\s*name:|\Z)', raw, re.M)
    return m.group(1) if m else ""


def audit(raw_chk: str, c: dict):
    f = []
    add = lambda code, lvl, msg: f.append((code, lvl, msg))

    if c.get("origin") != "DOCUMENT_TYPE":
        add("S1", "FAIL", "origin != DOCUMENT_TYPE")
    if "triggers" not in c:
        add("S2", "FAIL", "нет triggers")
    if c.get("ui_mode") != "field_extraction":
        add("S3", "FAIL", f"ui_mode={c.get('ui_mode')!r}")
    
    kw = (c.get("rules") or {}).get("keywords")
    if not isinstance(kw, list) or any(not isinstance(x, str) for x in (kw or [])):
        add("S4", "FAIL", "rules.keywords не flat list[str]")
    
    pt = (c.get("llm") or {}).get("prompt_template")
    if not isinstance(pt, str) or not pt.strip():
        add("S5", "FAIL", "llm.prompt_template не inline")
    elif "<role>" in pt:
        add("S5", "FAIL", "Layer-1 содержит XML-теги Layer-2")

    ex = c.get("extraction") or {}
    ps, fields = ex.get("presence_signal"), ex.get("fields") or []
    names = [x.get("name") for x in fields]
    pfield = ps.get("field") if isinstance(ps, dict) else None
    
    # --- P: Presence Signal Checks ---
    if not isinstance(ps, dict):
        add("P1", "FAIL", "нет extraction.presence_signal")
    else:
        if not names or names[0] != pfield:
            add("P2", "FAIL", f"presence не первое поле: {names[:1]} vs {pfield!r}")
        
        g = [set(ps.get(k) or []) for k in ("present_values", "missing_values", "unclear_values")]
        if any(g[i] & g[j] for i in range(3) for j in range(i + 1, 3)):
            add("P3", "FAIL", "группы presence не disjoint")
            
        pf = next((x for x in fields if x.get("name") == pfield), None)
        if pf is None:
            add("P3", "FAIL", f"поле {pfield!r} не объявлено в fields")
        else:
            if set().union(*g) != set(pf.get("allowed_values") or []):
                add("P3", "FAIL", "union != allowed_values")
            for k, v in (("presentation", "signal"), ("risk_weight", "info"),
                         ("display_in_grid", False), ("required", True)):
                if pf.get(k) != v:
                    add("P4", "FAIL", f"{pfield}.{k}={pf.get(k)!r} (ожид. {v!r})")
            
            desc = (pf.get("description") or "").lower()
            if "внутренн" not in desc or "signal" not in desc:
                add("P5", "WARN", "presence.description: нет описания 'Внутреннее ... signal-поле'")
                
        keys = list(ex.keys())
        if "presence_signal" in keys:
            i = keys.index("presence_signal")
            lo = keys.index("compact_output") if "compact_output" in keys else -1
            hi = keys.index("llm_prompt_extraction") if "llm_prompt_extraction" in keys else len(keys)
            if not (lo < i < hi):
                add("P6", "FAIL", f"presence_signal не между compact_output и llm_prompt_extraction: {keys}")

    # --- R: Risk Weight Checks ---
    sig = [x for x in fields if x.get("presentation") == "signal"]
    for x in sig:
        rw = x.get("risk_weight")
        if rw is None:
            add("R1", "FAIL", f"{x.get('name')}: нет risk_weight")
        elif rw not in RWS:
            add("R3", "FAIL", f"{x.get('name')}: risk_weight={rw!r}")
    if sig and all(x.get("risk_weight") == "info" for x in sig):
        add("R2", "WARN", "все signal-поля = info (нарушение дифференциации B1)")

    # --- L: Layer 2 Prompt Checks ---
    l2 = ex.get("llm_prompt_extraction") or ""
    idx = [(t, l2.find(t)) for t in TAGS]
    if any(i < 0 for _, i in idx):
        add("L1", "FAIL", f"нет тегов: {[t for t, i in idx if i < 0]}")
    elif [i for _, i in idx] != sorted(i for _, i in idx):
        add("L1", "FAIL", f"порядок тегов нарушен: {[t for t, _ in idx]}")
        
    if "<location_instructions>" in l2:
        add("L2", "FAIL", "есть <location_instructions> (RF10)")
        
    n = len(re.findall(r"(?m)^\s*\d+\.\s", sect(l2, "edge_cases")))
    if n != 4:
        add("L3", "FAIL", f"edge_cases: {n} сценариев (ожид. 4)")
        
    if not sect(l2, "output_expectations").rstrip().endswith(FINAL_LINE):
        add("L4", "FAIL", "нет финальной строки output_expectations")
        
    if pfield and not re.search(rf"(?m)^\s*0\.\s*{re.escape(pfield)}\s*:", sect(l2, "task")):
        add("L6", "FAIL", f"в <task> нет п.0 «0. {pfield}:»")
        
    cr = sect(l2, "context_rules")
    if "по правилу из пункта 0" not in cr and "пункт 0" not in cr.lower():
        add("L7", "FAIL", "в <context_rules> нет ссылки на правило агрегации из п.0")

    # --- D: Description Format Checks ---
    if "description: >" not in raw_chk.split("triggers:")[0]:
        add("D1", "WARN", "check.description не использует folded `>`")
        
    for x in fields:
        d, pres, nm = (x.get("description") or ""), x.get("presentation"), x.get("name")
        d_lower = d.lower()
        
        if pres == "fact":
            if "fallback" not in d_lower:
                add("D2", "WARN", f"{nm}: fact.description без упоминания Fallback")
            raw_f = field_raw(raw_chk, nm)
            if raw_f and "description: >" not in raw_f and "description: |" not in raw_f:
                # Допускаем однострочные fact, если они короткие, но предупреждаем
                if len(d) > 80:
                    add("D2", "FAIL", f"{nm}: длинное fact.description не использует folded `>` или `|`")
        elif pres == "signal" and nm != pfield:
            if "enum" not in d_lower or "внутренн" not in d_lower:
                add("D3", "WARN", f"{nm}: signal.description не содержит 'внутренн... enum'")

    pri = [x.get("display_priority") for x in fields if x.get("display_in_grid") and x.get("display_priority") is not None]
    if pri and pri != list(range(1, len(pri) + 1)):
        add("D4", "FAIL", f"display_priority нарушен или имеет пропуски: {pri}")

    # --- X: Deep Audit Checks ---
    blob = l2 + " " + str(pt or "")
    if (ph := sorted(set(PLACEHOLDER.findall(blob)))):
        add("X1", "FAIL", f"placeholder'ы: {ph}")
    for t in TYPOS:
        if t in blob:
            add("X2", "WARN", f"опечатка: {t!r}")
            
    # Безопасная проверка списков retrieval и enrichment_hints
    for sec_name, parent_key in [("preferred_unit_types", "retrieval"), 
                                 ("preferred_clause_functions", "retrieval"),
                                 ("excluded_unit_types", "retrieval"),
                                 ("preferred_segment_types", "enrichment_hints"),
                                 ("excluded_segment_types", "enrichment_hints")]:
        parent = c.get(parent_key)
        if isinstance(parent, dict):
            v = parent.get(sec_name)
            if isinstance(v, list) and len(v) != len(set(v)):
                add("X4", "WARN", f"{parent_key}.{sec_name}: есть дубликаты")

    if ex.get("compact_output") is False:
        add("X5", "CONSIDER", "compact_output: false (необычное значение)")
        
    if c.get("severity_if_fail") not in (None, c.get("severity")):
        add("X6", "CONSIDER", "RF8: severity_if_fail != severity")
        
    if "риск" in (c.get("description") or "").lower() and "не оценивай риск" in blob.lower():
        add("X7", "CONSIDER", "RF9: возможное противоречие description vs role")
        
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="playbooks/document_types")
    ap.add_argument("--only", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    
    files = sorted(p for p in Path(a.root).rglob("*.yaml") if not a.only or a.only in p.name)
    report, codes = [], Counter()
    
    for p in files:
        raw = p.read_text(encoding="utf-8")
        try:
            doc = yaml.safe_load(raw)
        except Exception as e:
            report.append({"file": str(p), "error": str(e)}); codes["FAIL:ERR"] += 1; continue
            
        checks = doc.get("checks_v8") or doc.get("checks") or []
        raws = dict(blocks(raw))
        
        rows = [{"id": c.get("id"),
                 "findings": [{"code": x, "level": l, "msg": m} for x, l, m in audit(raws.get(c.get("id"), ""), c)]}
                for c in checks]
                
        for r in rows:
            for x in r["findings"]:
                codes[f"{x['level']}:{x['code']}"] += 1
                
        report.append({"file": str(p), "n_checks": len(checks), "checks": rows})
        
        if not a.json:
            nf = sum(1 for r in rows if any(x["level"] == "FAIL" for x in r["findings"]))
            if nf > 0 or a.verbose:
                print(f"\n{p}  checks={len(checks)}  с_FAIL={nf}")
                for r in rows:
                    if a.verbose or any(x["level"] == "FAIL" for x in r["findings"]):
                        for x in r["findings"]:
                            print(f"   [{x['level']:8}] {x['code']:3} {r['id']}: {x['msg']}")
                            
    if a.json:
        json.dump(report, sys.stdout, ensure_ascii=False, indent=1)
        
    print("\n=== СВОДКА ===")
    for k, v in sorted(codes.items()):
        print(f"  {k:12} {v}")
        
    return 1 if any(k.startswith("FAIL") for k in codes) else 0


if __name__ == "__main__":
    sys.exit(main())

