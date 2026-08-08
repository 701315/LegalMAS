#!/usr/bin/env python3
"""
LegalMAS Playbook Audit v2
Auto-classifies architecture level of each file
and audits according to appropriate standard.
"""

import yaml
import re
from pathlib import Path
from collections import defaultdict

ROOT = Path("/srv/steloom-dev/playbooks/document_types")

# ─────────────────────────────────────────────────────────────
# ARCHITECTURE DETECTION
# ─────────────────────────────────────────────────────────────

def detect_layer(data):
    checks = data.get("checks_v8", [])

    if not checks:
        return "NO_CHECKS"

    sample = checks[0]

    # Strict v8.1
    if (
        "retrieval" in sample
        and "extraction" in sample
        and "enrichment_hints" in sample
        and "llm" in sample
        and "[КОНТЕКСТ]" in (sample.get("llm", {}).get("prompt_template", ""))
    ):
        return "LAYER_A_V8_1_STRICT"

    # Hybrid v8 (no strict markers)
    if "retrieval" in sample and "extraction" in sample:
        return "LAYER_B_HYBRID_V8"

    # Hybrid legacy
    if sample.get("detector_type") == "hybrid":
        return "LAYER_C_HYBRID_LEGACY"

    # Rules only
    if sample.get("detector_type") == "rules":
        return "LAYER_D_RULES_ONLY"

    return "UNKNOWN"


# ─────────────────────────────────────────────────────────────
# AUDIT RULES PER LAYER
# ─────────────────────────────────────────────────────────────

def audit_layer_a(path, data):
    issues = []
    for check in data.get("checks_v8", []):
        cid = check.get("id", "UNKNOWN")

        # ✅ Skip rules-only checks
        if check.get("detector_type") == "rules":
            continue

        # Strict v8.1 validation only for hybrid checks
        if "[КОНТЕКСТ]" not in check.get("llm", {}).get("prompt_template", ""):
            issues.append(("ERROR", f"{cid}: missing prompt markers"))

        if "corpus_scope" not in check.get("retrieval", {}):
            issues.append(("ERROR", f"{cid}: incomplete retrieval schema"))

        if "llm_prompt_extraction" not in check.get("extraction", {}):
            issues.append(("ERROR", f"{cid}: missing llm_prompt_extraction"))

    return issues


def audit_layer_b(path, data):
    issues = []
    for check in data.get("checks_v8", []):
        cid = check.get("id", "UNKNOWN")

        if "retrieval" not in check:
            issues.append(("ERROR", f"{cid}: missing retrieval block"))

        if "extraction" not in check:
            issues.append(("ERROR", f"{cid}: missing extraction block"))

    return issues


def audit_layer_c(path, data):
    issues = []
    for check in data.get("checks_v8", []):
        cid = check.get("id", "UNKNOWN")

        if "rules" not in check and "llm" not in check:
            issues.append(("ERROR", f"{cid}: no detection logic"))

    return issues


def audit_layer_d(path, data):
    return []  # rules-only — minimal validation


# ─────────────────────────────────────────────────────────────
# MAIN AUDIT
# ─────────────────────────────────────────────────────────────

layer_summary = defaultdict(int)
file_issues = defaultdict(list)

for path in ROOT.rglob("*.yaml"):
    try:
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)

        layer = detect_layer(data)
        layer_summary[layer] += 1

        if layer == "LAYER_A_V8_1_STRICT":
            issues = audit_layer_a(path, data)
        elif layer == "LAYER_B_HYBRID_V8":
            issues = audit_layer_b(path, data)
        elif layer == "LAYER_C_HYBRID_LEGACY":
            issues = audit_layer_c(path, data)
        elif layer == "LAYER_D_RULES_ONLY":
            issues = audit_layer_d(path, data)
        else:
            issues = [("WARNING", "Unknown architecture")]

        if issues:
            file_issues[str(path)] = issues

    except Exception as e:
        file_issues[str(path)].append(("FATAL", str(e)))

# ─────────────────────────────────────────────────────────────
# REPORT
# ─────────────────────────────────────────────────────────────

print("=" * 100)
print("LEGALMAS PLAYBOOK AUDIT v2 — ARCHITECTURE SUMMARY")
print("=" * 100)

for layer, count in layer_summary.items():
    print(f"{layer}: {count} files")

print("\n" + "=" * 100)
print("FILES WITH ISSUES")
print("=" * 100)

total_errors = 0
total_warnings = 0

for file, issues in file_issues.items():
    print(f"\n📄 {file}")
    for level, msg in issues:
        print(f"  [{level}] {msg}")
        if level == "ERROR":
            total_errors += 1
        if level == "WARNING":
            total_warnings += 1

print("\n" + "=" * 100)
print(f"TOTAL ERRORS: {total_errors}")
print(f"TOTAL WARNINGS: {total_warnings}")
print("=" * 100)


