#!/usr/bin/env python3
"""
Check DD Grid naming-contract violations only for playbooks/document_types.

Target pattern:
A singleton field named "<prefix>" is invalid if there is also any paired field:
- "<prefix>_status"
- "<prefix>_details"
- "<prefix>_value"

Example invalid combinations:
- buyer_details + buyer_details_status
- object_type + object_type_details
- mortgage_amount + mortgage_amount_status

The script scans only:
    /home/vladi/projects/LegalMAS/playbooks/document_types

Output:
- total files scanned
- total checks scanned
- all naming-contract errors found

Exit codes:
- 0: no errors
- 1: errors found
- 2: runtime/parsing problem
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:
    raise SystemExit(
        "PyYAML is required. Install it in the project venv: pip install pyyaml"
    ) from exc


ROOT = Path("/home/vladi/projects/LegalMAS/playbooks/document_types")
YAML_EXTENSIONS = {".yaml", ".yml"}
RESERVED_SUFFIXES = ("_status", "_details", "_value")


@dataclass(slots=True)
class NamingViolation:
    file_path: str
    check_id: str
    check_name: str | None
    field_name: str
    paired_fields: list[str]
    suggested_name: str


def iter_yaml_files(root: Path) -> list[Path]:
    """Recursively collect YAML files under the given root."""
    if not root.exists():
        return []
    return sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in YAML_EXTENSIONS
    )


def safe_load_yaml(path: Path) -> tuple[list[Any], str | None]:
    """Load YAML file as list of documents."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [], f"read error: {exc}"

    try:
        docs = list(yaml.safe_load_all(raw))
    except yaml.YAMLError as exc:
        return [], f"yaml parse error: {exc}"

    return docs, None


def collect_check_nodes(node: Any) -> list[dict[str, Any]]:
    """
    Recursively collect dict nodes that look like checks.
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


def build_paired_prefix_map(field_names: set[str]) -> dict[str, list[str]]:
    """
    Build prefix -> list[paired_fields].

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

    for prefix, paired in prefix_map.items():
        paired.sort()

    return prefix_map


def choose_suggested_name(
    field_name: str,
    field_meta: dict[str, Any],
    existing_names: set[str],
) -> str:
    """
    Suggest a safe rename based on field semantics.

    Heuristic:
    - signal / enum-like -> *_code
    - other fields -> *_value
    """
    presentation = field_meta.get("presentation")
    allowed_values = field_meta.get("allowed_values")

    is_code_like = presentation == "signal" or bool(allowed_values)

    candidates: list[str]
    if is_code_like:
        candidates = [
            f"{field_name}_code",
            f"{field_name}_value",
            f"{field_name}_text",
        ]
    else:
        candidates = [
            f"{field_name}_value",
            f"{field_name}_text",
            f"{field_name}_raw",
        ]

    for candidate in candidates:
        if candidate not in existing_names:
            return candidate

    index = 2
    while True:
        candidate = f"{field_name}_value_{index}"
        if candidate not in existing_names:
            return candidate
        index += 1


def detect_naming_violations_in_check(check_node: dict[str, Any], file_path: Path) -> list[NamingViolation]:
    """
    Detect naming-contract violations in one check.
    """
    extraction = check_node.get("extraction")
    if not isinstance(extraction, dict):
        return []

    fields = extraction.get("fields")
    if not isinstance(fields, list) or not fields:
        return []

    field_meta_map: dict[str, dict[str, Any]] = {}
    field_names: set[str] = set()

    for item in fields:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str):
            continue
        normalized_name = name.strip()
        if not normalized_name:
            continue
        field_names.add(normalized_name)
        field_meta_map[normalized_name] = item

    if not field_names:
        return []

    prefix_map = build_paired_prefix_map(field_names)

    check_id_raw = check_node.get("id")
    check_name_raw = check_node.get("name")

    check_id = str(check_id_raw).strip() if check_id_raw is not None else ""
    check_name = str(check_name_raw).strip() if isinstance(check_name_raw, str) else None

    violations: list[NamingViolation] = []

    for field_name in sorted(field_names):
        paired_fields = prefix_map.get(field_name)
        if not paired_fields:
            continue

        suggested_name = choose_suggested_name(
            field_name=field_name,
            field_meta=field_meta_map[field_name],
            existing_names=field_names,
        )

        violations.append(
            NamingViolation(
                file_path=str(file_path),
                check_id=check_id,
                check_name=check_name,
                field_name=field_name,
                paired_fields=paired_fields,
                suggested_name=suggested_name,
            )
        )

    return violations


def main() -> int:
    if not ROOT.exists():
        print(f"[ERROR] Directory not found: {ROOT}", file=sys.stderr)
        return 2

    yaml_files = iter_yaml_files(ROOT)
    total_checks_scanned = 0
    violations: list[NamingViolation] = []
    parse_errors: list[str] = []

    for yaml_file in yaml_files:
        docs, error = safe_load_yaml(yaml_file)
        if error is not None:
            parse_errors.append(f"{yaml_file}: {error}")
            continue

        for doc in docs:
            check_nodes = collect_check_nodes(doc)
            total_checks_scanned += len(check_nodes)

            for check_node in check_nodes:
                violations.extend(detect_naming_violations_in_check(check_node, yaml_file))

    print("DD GRID NAMING CONTRACT CHECK — document_types")
    print("=" * 72)
    print(f"Root directory         : {ROOT}")
    print(f"Files scanned          : {len(yaml_files)}")
    print(f"Checks scanned         : {total_checks_scanned}")
    print(f"Parse errors           : {len(parse_errors)}")
    print(f"Naming violations      : {len(violations)}")
    print()

    if parse_errors:
        print("PARSE ERRORS:")
        for err in parse_errors:
            print(f"  - {err}")
        print()

    if not violations:
        print("No naming-contract violations found.")
        return 1 if parse_errors else 0

    print("VIOLATIONS:")
    current_file: str | None = None

    for idx, violation in enumerate(violations, start=1):
        if violation.file_path != current_file:
            current_file = violation.file_path
            print()
            print(f"FILE: {current_file}")

        check_name_part = f" | {violation.check_name}" if violation.check_name else ""
        print(
            f"  [{idx}] {violation.check_id}{check_name_part}"
        )
        print(
            f'      field="{violation.field_name}" '
            f'conflicts with {violation.paired_fields} '
            f'-> suggested rename: "{violation.suggested_name}"'
        )

    return 1


if __name__ == "__main__":
    raise SystemExit(main())



    