#!/usr/bin/env python3
"""
Full LegalMAS Playbook Audit
Checks:
- File-level style structure
- Check structure compliance
- Retrieval schema compliance
- Extraction schema compliance
- Prompt structure compliance
- Advanced check quality signals
"""

import yaml
import re
from pathlib import Path
from collections import defaultdict

ROOT = Path("/srv/steloom-dev/playbooks/document_types")

# ─────────────────────────────────────────────────────────────────────────────
# ✅ BLUEPRINT DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────

TOP_LEVEL_ORDER = [
    "type",
    "name",
    "version",
    "parent",
    "description",
    "metadata",
    "classification_runtime_v1",
    "trigger_definitions",
    "shared_patterns",
    "compliance_rules",
    "checks_v8",
    "dd_request_templates",
]

CHECK_ORDER = [
    "id",
    "name",
    "description",
    "triggers",
    "ui_mode",
    "severity",
    "severity_if_pass",
    "severity_if_fail",
    "severity_if_unclear",
    "origin",
    "detector_type",
    "rules",
    "llm",
    "retrieval",
    "enrichment_hints",
    "evidence",
    "extraction",
]

RETRIEVAL_ORDER = [
    "corpus_scope",
    "levels",
    "required_kind",
    "retrieval_query",
    "preferred_unit_types",
    "excluded_unit_types",
    "preferred_clause_functions",
    "negative_keywords",
    "position_bias",
    "retrieval_profile",
    "context_k",
    "max_chunks",
    "rerank",
]

EXTRACTION_ORDER = [
    "enabled",
    "mode",
    "llm_max_tokens",
    "compact_output",
    "llm_prompt_extraction",
    "fields",
    "store_payload",
]

FIELD_ORDER = [
    "name",
    "type",
    "presentation",
    "allowed_values",
    "description",
    "required",
]

PROMPT_MARKERS = [
    "[КОНТЕКСТ]",
    "[ЗАДАЧА]",
    "[ПРАВИЛА]",
    "[ФОРМАТ ОТВЕТА]",
]

# ─────────────────────────────────────────────────────────────────────────────
# ✅ AUDIT LOGIC
# ─────────────────────────────────────────────────────────────────────────────

def check_order(actual, expected):
    return actual == expected[:len(actual)]

def has_prompt_markers(prompt):
    return all(marker in prompt for marker in PROMPT_MARKERS)

def analyze_file(path):
    report = []
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)

    # ───────────── FILE STRUCTURE
    top_keys = list(data.keys())
    if not check_order(top_keys, TOP_LEVEL_ORDER):
        report.append(("ERROR", "Top-level key order mismatch"))

    # ───────────── CHECKS
    checks = data.get("checks_v8", [])
    for check in checks:

        cid = check.get("id", "UNKNOWN")

        # Check order
        if not check_order(list(check.keys()), CHECK_ORDER):
            report.append(("ERROR", f"{cid}: check key order mismatch"))

        # Retrieval
        retrieval = check.get("retrieval", {})
        if retrieval:
            if not check_order(list(retrieval.keys()), RETRIEVAL_ORDER):
                report.append(("ERROR", f"{cid}: retrieval key order mismatch"))

        # Extraction
        extraction = check.get("extraction", {})
        if extraction:
            if not check_order(list(extraction.keys()), EXTRACTION_ORDER):
                report.append(("ERROR", f"{cid}: extraction key order mismatch"))

            fields = extraction.get("fields", [])
            for f in fields:
                if not check_order(list(f.keys()), FIELD_ORDER):
                    report.append(("ERROR", f"{cid}: field key order mismatch"))

        # Prompt validation
        llm = check.get("llm", {})
        prompt = llm.get("prompt_template", "")
        if not has_prompt_markers(prompt):
            report.append(("ERROR", f"{cid}: missing prompt markers"))

        # Advanced quality checks
        if "FEW-SHOT" in prompt and len(prompt) > 4000:
            report.append(("WARNING", f"{cid}: very large prompt with few-shot"))

        if "CoVe" not in prompt and "ПРОВЕРКА ПЕРЕД ОТВЕТОМ" not in prompt:
            report.append(("WARNING", f"{cid}: missing CoVe block"))

        # Retrieval completeness
        required_retrieval_fields = {"corpus_scope", "levels", "required_kind", "retrieval_query"}
        if not required_retrieval_fields.issubset(retrieval.keys()):
            report.append(("ERROR", f"{cid}: incomplete retrieval schema"))

        # Enrichment hints
        if "enrichment_hints" not in check:
            report.append(("WARNING", f"{cid}: missing enrichment_hints"))

    return report

# ─────────────────────────────────────────────────────────────────────────────
# ✅ RUN AUDIT
# ─────────────────────────────────────────────────────────────────────────────

all_reports = defaultdict(list)

for path in ROOT.rglob("*.yaml"):
    try:
        report = analyze_file(path)
        if report:
            all_reports[str(path)] = report
    except Exception as e:
        all_reports[str(path)].append(("FATAL", str(e)))

# ─────────────────────────────────────────────────────────────────────────────
# ✅ PRINT REPORT
# ─────────────────────────────────────────────────────────────────────────────

print("=" * 100)
print("LEGALMAS FULL PLAYBOOK AUDIT REPORT")
print("=" * 100)

total_errors = 0
total_warnings = 0

for file, issues in all_reports.items():
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


