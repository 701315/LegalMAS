#!/usr/bin/env python3
"""
Audit YAML playbooks for DD Grid naming contract conflicts.

Checks the specific conflict pattern that previously produced errors like:
- singleton 'buyer_details' conflicts with paired ['buyer_details_status']
- singleton 'object_type' conflicts with paired ['object_type_details']
- singleton 'mortgage_amount' conflicts with paired ['mortgage_amount_status']

Naming contract being audited:
- suffixes _status / _details / _value are reserved for paired fields;
- if a field named "<prefix>" exists together with "<prefix>_status" or
  "<prefix>_details" or "<prefix>_value", then "<prefix>" is an invalid singleton
  and must be renamed.

What the script reports:
- YAML file path
- check_id / check_name
- conflicting singleton field
- conflicting paired fields
- suggested rename
- approximate locations inside the check block
- example replacements

Usage:
    python scripts/audit_dd_grid_naming_contract.py

Optional:
    python scripts/audit_dd_grid_naming_contract.py \
      --output-json /tmp/dd_grid_naming_contract_report.json

    python scripts/audit_dd_grid_naming_contract.py \
      --roots \
        /home/vladi/projects/LegalMAS/playbooks/document_types \
        /home/vladi/projects/LegalMAS/playbooks/global_checks
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
except ImportError as exc:  # pragma: no cover - startup failure
    raise SystemExit(
        "PyYAML is required. Install it in the project venv: pip install pyyaml"
    ) from exc


DEFAULT_ROOTS: tuple[Path, ...] = (
    Path("/home/vladi/projects/LegalMAS/playbooks/document_types"),
    Path("/home/vladi/projects/LegalMAS/playbooks/global_checks"),
)

YAML_EXTENSIONS: frozenset[str] = frozenset({".yml", ".yaml"})
RESERVED_SUFFIXES: tuple[str, ...] = ("_status", "_details", "_value")


@dataclass(slots=True)
class FieldMeta:
    """Normalized field metadata extracted from extraction.fields."""

    name: str
    field_type: str | None
    presentation: str | None
    allowed_values: list[Any] | None
    required: bool | None
    display_in_grid: bool | None
    raw_index: int


@dataclass(slots=True)
class LocationHit:
    """Approximate source location inside the YAML file."""

    line_no: int
    section: str
    text: str


@dataclass(slots=True)
class ConflictFinding:
    """One naming-contract conflict inside one check."""

    file_path: str
    check_id: str
    check_name: str | None
    conflict_field: str
    paired_fields: list[str]
    suggested_name: str
    suggestion_reason: str
    field_type: str | None
    presentation: str | None
    occurrences: list[LocationHit] = field(default_factory=list)
    example_replacements: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParseIssue:
    """YAML parse/load issue."""

    file_path: str
    error: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit YAML playbooks for DD Grid naming contract conflicts."
    )
    parser.add_argument(
        "--roots",
        nargs="*",
        type=Path,
        default=list(DEFAULT_ROOTS),
        help="Root folders to scan recursively.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path to save machine-readable JSON report.",
    )
    parser.add_argument(
        "--max-occurrences-per-field",
        type=int,
        default=20,
        help="Limit reported line hits per conflict field.",
    )
    return parser.parse_args()


def iter_yaml_files(roots: Iterable[Path]) -> list[Path]:
    """Collect YAML files recursively from given roots."""
    files: list[Path] = []

    for root in roots:
        if not root.exists():
            print(f"[WARN] Root does not exist: {root}", file=sys.stderr)
            continue
        if root.is_file() and root.suffix.lower() in YAML_EXTENSIONS:
            files.append(root)
            continue
        if root.is_dir():
            files.extend(
                sorted(
                    path
                    for path in root.rglob("*")
                    if path.is_file() and path.suffix.lower() in YAML_EXTENSIONS
                )
            )

    return sorted(set(files))


def safe_load_yaml_documents(path: Path) -> tuple[list[Any], str | None]:
    """Load one YAML file into a list of documents."""
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [], f"read error: {exc}"

    try:
        docs = list(yaml.safe_load_all(raw_text))
    except yaml.YAMLError as exc:
        return [], f"yaml parse error: {exc}"

    return docs, None


def collect_check_nodes(node: Any) -> list[dict[str, Any]]:
    """
    Recursively collect dict nodes that look like playbook checks.

    Heuristic:
    - dict
    - has "id"
    - and at least one of extraction / llm / rules / origin / detector_type
    """
    found: list[dict[str, Any]] = []

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            if "id" in value and any(
                key in value for key in ("extraction", "llm", "rules", "origin", "detector_type")
            ):
                found.append(value)
            for child in value.values():
                _walk(child)
        elif isinstance(value, list):
            for child in value:
                _walk(child)

    _walk(node)
    return found


def normalize_field_meta(fields: Any) -> list[FieldMeta]:
    """Normalize extraction.fields list into typed metadata."""
    if not isinstance(fields, list):
        return []

    normalized: list[FieldMeta] = []
    for idx, item in enumerate(fields):
        if not isinstance(item, dict):
            continue
        name_raw = item.get("name")
        if not isinstance(name_raw, str) or not name_raw.strip():
            continue

        allowed_values = item.get("allowed_values")
        if not isinstance(allowed_values, list):
            allowed_values = None

        normalized.append(
            FieldMeta(
                name=name_raw.strip(),
                field_type=item.get("type") if isinstance(item.get("type"), str) else None,
                presentation=item.get("presentation")
                if isinstance(item.get("presentation"), str)
                else None,
                allowed_values=allowed_values,
                required=item.get("required") if isinstance(item.get("required"), bool) else None,
                display_in_grid=item.get("display_in_grid")
                if isinstance(item.get("display_in_grid"), bool)
                else None,
                raw_index=idx,
            )
        )

    return normalized


def build_paired_prefix_map(field_names: set[str]) -> dict[str, list[str]]:
    """
    Build prefix -> paired field names for reserved suffixes.

    Example:
      seller_details_status -> prefix seller_details
      object_type_details   -> prefix object_type
    """
    prefix_map: dict[str, list[str]] = {}

    for field_name in field_names:
        for suffix in RESERVED_SUFFIXES:
            if field_name.endswith(suffix) and len(field_name) > len(suffix):
                prefix = field_name[: -len(suffix)]
                prefix_map.setdefault(prefix, []).append(field_name)

    for prefix, fields in prefix_map.items():
        fields.sort()

    return prefix_map


def choose_suggested_name(field_meta: FieldMeta, existing_names: set[str]) -> tuple[str, str]:
    """
    Heuristic rename suggestion.

    Rules:
    - signal / enum-like field -> *_code
    - other fields -> *_value
    - if candidate already exists, use fallback variants
    """
    looks_like_code = (
        field_meta.presentation == "signal"
        or bool(field_meta.allowed_values)
    )

    preferred_suffix = "_code" if looks_like_code else "_value"
    reason = (
        "signal/enum-like field → prefer *_code"
        if looks_like_code
        else "fact/scalar field → prefer *_value"
    )

    candidates = [
        f"{field_meta.name}{preferred_suffix}",
        f"{field_meta.name}_value",
        f"{field_meta.name}_code",
        f"{field_meta.name}_text",
        f"{field_meta.name}_label",
        f"{field_meta.name}_raw",
    ]

    for candidate in candidates:
        if candidate not in existing_names:
            return candidate, reason

    # Defensive fallback
    index = 2
    while True:
        candidate = f"{field_meta.name}{preferred_suffix}_{index}"
        if candidate not in existing_names:
            return candidate, f"{reason}; fallback unique suffix used"
        index += 1


def find_conflicts_for_check(
    *,
    file_path: Path,
    check_node: dict[str, Any],
    raw_text: str,
    max_occurrences_per_field: int,
) -> list[ConflictFinding]:
    """Detect naming-contract conflicts inside one check."""
    extraction = check_node.get("extraction")
    if not isinstance(extraction, dict):
        return []

    fields_meta = normalize_field_meta(extraction.get("fields"))
    if not fields_meta:
        return []

    field_names = {field.name for field in fields_meta}
    prefix_map = build_paired_prefix_map(field_names)

    check_id = str(check_node.get("id", "")).strip()
    check_name_raw = check_node.get("name")
    check_name = check_name_raw.strip() if isinstance(check_name_raw, str) else None

    findings: list[ConflictFinding] = []

    for field_meta in fields_meta:
        paired_fields = prefix_map.get(field_meta.name)
        if not paired_fields:
            continue

        suggested_name, suggestion_reason = choose_suggested_name(field_meta, field_names)
        occurrences = find_occurrences_in_check_block(
            raw_text=raw_text,
            check_id=check_id,
            token=field_meta.name,
            max_hits=max_occurrences_per_field,
        )

        findings.append(
            ConflictFinding(
                file_path=str(file_path),
                check_id=check_id,
                check_name=check_name,
                conflict_field=field_meta.name,
                paired_fields=paired_fields,
                suggested_name=suggested_name,
                suggestion_reason=suggestion_reason,
                field_type=field_meta.field_type,
                presentation=field_meta.presentation,
                occurrences=occurrences,
                example_replacements=build_example_replacements(
                    old_name=field_meta.name,
                    new_name=suggested_name,
                ),
            )
        )

    return findings


def find_occurrences_in_check_block(
    *,
    raw_text: str,
    check_id: str,
    token: str,
    max_hits: int,
) -> list[LocationHit]:
    """
    Find approximate line hits for a token inside one check block.

    The function:
    - locates the block starting at '- id: <check_id>'
    - searches until the next '- id: ...'
    - classifies hits roughly into:
      * extraction.fields
      * llm.prompt_template
      * extraction.llm_prompt_extraction
      * check_block
    """
    lines = raw_text.splitlines()
    block = locate_check_block(lines, check_id)
    if block is None:
        return []

    start_idx, end_idx = block
    hits: list[LocationHit] = []

    token_regex = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])")
    multiline_section: str | None = None
    multiline_indent: int | None = None

    for idx in range(start_idx, end_idx):
        line = lines[idx]
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))

        if multiline_section is not None and multiline_indent is not None:
            # If indentation returns to block level, multiline section ended.
            if stripped and indent <= multiline_indent:
                multiline_section = None
                multiline_indent = None

        section = "check_block"
        if re.match(r'^\s*-\s+name:\s*["\']?.+["\']?\s*$', line):
            section = "extraction.fields"
        elif multiline_section is not None:
            section = multiline_section

        if token_regex.search(line):
            hits.append(
                LocationHit(
                    line_no=idx + 1,
                    section=section,
                    text=line.rstrip(),
                )
            )
            if len(hits) >= max_hits:
                break

        if stripped.startswith("prompt_template: |"):
            multiline_section = "llm.prompt_template"
            multiline_indent = indent
        elif stripped.startswith("llm_prompt_extraction: |"):
            multiline_section = "extraction.llm_prompt_extraction"
            multiline_indent = indent

    return hits


def locate_check_block(lines: list[str], check_id: str) -> tuple[int, int] | None:
    """Locate line range for one YAML check block."""
    start_pattern = re.compile(
        rf'^\s*-\s+id:\s*["\']?{re.escape(check_id)}["\']?\s*$'
    )
    next_check_pattern = re.compile(r'^\s*-\s+id:\s*["\']?.+["\']?\s*$')

    start_idx: int | None = None
    for idx, line in enumerate(lines):
        if start_pattern.match(line):
            start_idx = idx
            break

    if start_idx is None:
        return None

    end_idx = len(lines)
    for idx in range(start_idx + 1, len(lines)):
        if next_check_pattern.match(lines[idx]):
            end_idx = idx
            break

    return start_idx, end_idx


def build_example_replacements(*, old_name: str, new_name: str) -> list[str]:
    """Build generic replacement examples for human review."""
    return [
        f'extraction.fields:   - name: "{old_name}"  ->  - name: "{new_name}"',
        f'JSON keys in prompts: "{old_name}": ...  ->  "{new_name}": ...',
        f'task/format lines:    {old_name} — ...    ->  {new_name} — ...',
    ]


def render_text_report(
    *,
    files_scanned: int,
    checks_scanned: int,
    parse_issues: list[ParseIssue],
    findings: list[ConflictFinding],
) -> str:
    """Render human-readable report."""
    lines: list[str] = []

    files_with_conflicts = len({finding.file_path for finding in findings})
    checks_with_conflicts = len({(finding.file_path, finding.check_id) for finding in findings})

    lines.append("DD GRID NAMING CONTRACT AUDIT")
    lines.append("=" * 80)
    lines.append(f"Files scanned         : {files_scanned}")
    lines.append(f"Checks scanned        : {checks_scanned}")
    lines.append(f"Files with conflicts  : {files_with_conflicts}")
    lines.append(f"Checks with conflicts : {checks_with_conflicts}")
    lines.append(f"Conflict fields total : {len(findings)}")
    lines.append(f"Parse issues          : {len(parse_issues)}")
    lines.append("")

    if parse_issues:
        lines.append("PARSE ISSUES")
        lines.append("-" * 80)
        for issue in parse_issues:
            lines.append(f"[PARSE-ERROR] {issue.file_path}")
            lines.append(f"  {issue.error}")
        lines.append("")

    if not findings:
        lines.append("No naming-contract conflicts found.")
        return "\n".join(lines)

    current_file: str | None = None
    current_check_key: tuple[str, str] | None = None

    sorted_findings = sorted(
        findings,
        key=lambda item: (item.file_path, item.check_id, item.conflict_field),
    )

    for finding in sorted_findings:
        if finding.file_path != current_file:
            current_file = finding.file_path
            lines.append(f"FILE: {finding.file_path}")
            lines.append("-" * 80)

        check_key = (finding.file_path, finding.check_id)
        if check_key != current_check_key:
            current_check_key = check_key
            lines.append(
                f'  CHECK: {finding.check_id}'
                + (f' | {finding.check_name}' if finding.check_name else "")
            )

        lines.append(
            f'    CONFLICT: singleton "{finding.conflict_field}" '
            f'conflicts with paired {finding.paired_fields}'
        )
        lines.append(
            f'    SUGGESTED: "{finding.conflict_field}" -> "{finding.suggested_name}" '
            f'({finding.suggestion_reason})'
        )
        lines.append(
            f"    FIELD META: type={finding.field_type!r}, "
            f"presentation={finding.presentation!r}"
        )

        if finding.occurrences:
            lines.append("    LOCATIONS:")
            for hit in finding.occurrences:
                lines.append(
                    f"      - line {hit.line_no:>4} [{hit.section}] {hit.text}"
                )
        else:
            lines.append("    LOCATIONS: not found in raw check block (manual review needed)")

        lines.append("    EXAMPLE FIXES:")
        for example in finding.example_replacements:
            lines.append(f"      - {example}")

        lines.append("")

    return "\n".join(lines)


def build_json_report(
    *,
    files_scanned: int,
    checks_scanned: int,
    parse_issues: list[ParseIssue],
    findings: list[ConflictFinding],
) -> dict[str, Any]:
    """Build machine-readable report."""
    return {
        "summary": {
            "files_scanned": files_scanned,
            "checks_scanned": checks_scanned,
            "files_with_conflicts": len({finding.file_path for finding in findings}),
            "checks_with_conflicts": len({(finding.file_path, finding.check_id) for finding in findings}),
            "conflict_fields_total": len(findings),
            "parse_issues_total": len(parse_issues),
        },
        "parse_issues": [asdict(issue) for issue in parse_issues],
        "findings": [
            {
                **asdict(finding),
                "occurrences": [asdict(hit) for hit in finding.occurrences],
            }
            for finding in findings
        ],
    }


def main() -> int:
    args = parse_args()

    yaml_files = iter_yaml_files(args.roots)
    parse_issues: list[ParseIssue] = []
    findings: list[ConflictFinding] = []
    checks_scanned = 0

    for yaml_file in yaml_files:
        docs, error = safe_load_yaml_documents(yaml_file)
        raw_text = ""
        try:
            raw_text = yaml_file.read_text(encoding="utf-8")
        except OSError as exc:
            parse_issues.append(ParseIssue(file_path=str(yaml_file), error=f"read error: {exc}"))
            continue

        if error is not None:
            parse_issues.append(ParseIssue(file_path=str(yaml_file), error=error))
            continue

        for doc in docs:
            for check_node in collect_check_nodes(doc):
                checks_scanned += 1
                try:
                    findings.extend(
                        find_conflicts_for_check(
                            file_path=yaml_file,
                            check_node=check_node,
                            raw_text=raw_text,
                            max_occurrences_per_field=args.max_occurrences_per_field,
                        )
                    )
                except Exception as exc:  # pragma: no cover - defensive
                    parse_issues.append(
                        ParseIssue(
                            file_path=str(yaml_file),
                            error=(
                                f"unexpected audit error in check_id={check_node.get('id')!r}: {exc}"
                            ),
                        )
                    )

    text_report = render_text_report(
        files_scanned=len(yaml_files),
        checks_scanned=checks_scanned,
        parse_issues=parse_issues,
        findings=findings,
    )
    print(text_report)

    if args.output_json is not None:
        report = build_json_report(
            files_scanned=len(yaml_files),
            checks_scanned=checks_scanned,
            parse_issues=parse_issues,
            findings=findings,
        )
        try:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_json.write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print("")
            print(f"[INFO] JSON report saved to: {args.output_json}")
        except OSError as exc:
            print(f"[ERROR] Failed to write JSON report: {exc}", file=sys.stderr)
            return 2

    return 1 if findings or parse_issues else 0


if __name__ == "__main__":
    raise SystemExit(main())



    