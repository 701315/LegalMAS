#!/usr/bin/env python3
"""
Full YAML structural & formatting audit.

Generates:
- Top-level key order
- Nested key order
- Check structure blueprint
- Prompt formatting style
- Quoting style
- Multiline style
- Retrieval schema shape
- Extraction schema shape
"""

import re
import yaml
from pathlib import Path
from collections import OrderedDict, defaultdict

TARGET_FILE = Path(
    "/srv/steloom-dev/playbooks/document_types/group_1_ownership/contract_1.1_general_sale.yaml"
)

raw_text = TARGET_FILE.read_text(encoding="utf-8")
parsed = yaml.safe_load(raw_text)

print("=" * 80)
print("FILE:", TARGET_FILE)
print("=" * 80)

# -------------------------------------------------------------------
# 1️⃣ TOP LEVEL ORDER
# -------------------------------------------------------------------

print("\n🔹 TOP LEVEL KEY ORDER:")
top_level_keys = list(parsed.keys())
for i, k in enumerate(top_level_keys, 1):
    print(f"{i:02d}. {k}")

# -------------------------------------------------------------------
# 2️⃣ CHECK STRUCTURE ANALYSIS
# -------------------------------------------------------------------

def analyze_check_structure(check):
    return list(check.keys())

checks = parsed.get("checks_v8") or []
print("\n🔹 checks_v8 count:", len(checks))

if checks:
    print("\n🔹 FIELD ORDER INSIDE FIRST CHECK:")
    for i, k in enumerate(analyze_check_structure(checks[0]), 1):
        print(f"{i:02d}. {k}")

# -------------------------------------------------------------------
# 3️⃣ RETRIEVAL SHAPE
# -------------------------------------------------------------------

if checks and "retrieval" in checks[0]:
    print("\n🔹 retrieval KEYS:")
    for i, k in enumerate(checks[0]["retrieval"].keys(), 1):
        print(f"{i:02d}. {k}")

# -------------------------------------------------------------------
# 4️⃣ EXTRACTION SHAPE
# -------------------------------------------------------------------

if checks and "extraction" in checks[0]:
    extraction = checks[0]["extraction"]
    print("\n🔹 extraction KEYS:")
    for i, k in enumerate(extraction.keys(), 1):
        print(f"{i:02d}. {k}")

    fields = extraction.get("fields") or []
    if fields:
        print("\n🔹 extraction.fields KEYS:")
        for i, k in enumerate(fields[0].keys(), 1):
            print(f"{i:02d}. {k}")

# -------------------------------------------------------------------
# 5️⃣ PROMPT STYLE ANALYSIS
# -------------------------------------------------------------------

print("\n🔹 PROMPT STYLE ANALYSIS:")

prompt_blocks = re.findall(r"prompt_template:\s*\|([\s\S]+?)\n\s*[a-zA-Z_]", raw_text)

if prompt_blocks:
    sample_prompt = prompt_blocks[0]
    print("Uses block style (|): YES")
    print("Contains markers:")
    for marker in ["[КОНТЕКСТ]", "[ЗАДАЧА]", "[ПРАВИЛА]", "[ФОРМАТ ОТВЕТА]"]:
        print(f"  {marker}: {'YES' if marker in sample_prompt else 'NO'}")
else:
    print("Uses block style (|): NO")

# -------------------------------------------------------------------
# 6️⃣ QUOTING STYLE
# -------------------------------------------------------------------

print("\n🔹 QUOTING STYLE:")
double_quotes = len(re.findall(r'"[^"]*"', raw_text))
single_quotes = len(re.findall(r"'[^']*'", raw_text))

print("Double quoted strings:", double_quotes)
print("Single quoted strings:", single_quotes)

# -------------------------------------------------------------------
# 7️⃣ MULTILINE STYLE
# -------------------------------------------------------------------

print("\n🔹 MULTILINE STRING STYLE:")
pipe_count = raw_text.count("|")
folded_count = raw_text.count(">")

print("Literal blocks (|):", pipe_count)
print("Folded blocks (>):", folded_count)

# -------------------------------------------------------------------
# 8️⃣ LIST STYLE
# -------------------------------------------------------------------

print("\n🔹 LIST STYLE:")
dash_indents = re.findall(r"\n(\s+)-\s", raw_text)
if dash_indents:
    indent_lengths = sorted(set(len(i) for i in dash_indents))
    print("Dash indentation levels:", indent_lengths)

# -------------------------------------------------------------------
# 9️⃣ EMPTY LINE STYLE
# -------------------------------------------------------------------

print("\n🔹 EMPTY LINE FREQUENCY:")
empty_lines = len([l for l in raw_text.splitlines() if not l.strip()])
total_lines = len(raw_text.splitlines())
print(f"Empty lines: {empty_lines} / {total_lines}")

# -------------------------------------------------------------------
# 🔟 COMMENT STYLE
# -------------------------------------------------------------------

print("\n🔹 COMMENT STYLE:")
comment_lines = [l for l in raw_text.splitlines() if l.strip().startswith("#")]
print("Comment lines:", len(comment_lines))
if comment_lines:
    print("Sample comment:", comment_lines[0])

print("\n✅ Audit Complete")
print("=" * 80)

