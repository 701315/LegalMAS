#!/usr/bin/env python3
"""
Compare structure-stage outcomes for multiple documents using:
- MinIO artifacts
- local source-code contract drift inspection

Purpose:
- show which document successfully produced structure artifacts
- show which document failed before artifacts were persisted
- explain why a latent schema-drift bug can hit one document but not another

This script is read-only.
It does NOT mutate DB, MinIO, or project state.

Example:
    python scripts/compare_structure_outcomes.py \
      --deal-id 9ad8266c-c279-4f14-89b9-24321ba566fb \
      --doc-id eaba58e0-862b-4e4d-bf42-0ab05c24cc2b \
      --doc-id 6769e354-493a-4507-b45b-d861e6843e78
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from minio import Minio


DEFAULT_MINIO_ENDPOINT = "localhost:9000"
DEFAULT_MINIO_ACCESS_KEY = "minioadmin"
DEFAULT_MINIO_SECRET_KEY = "minioadmin123"
DEFAULT_MINIO_BUCKET = "mas-artifacts"
DEFAULT_SRC_ROOT = Path("/home/vladi/projects/LegalMAS/src")


ROOT_NUMERIC_RE = re.compile(r"^\s*(\d+)\.?\s+\S")
HEADINGISH_ELEMENT_TYPES = {
    "heading_candidate",
    "section_heading",
    "subsection_heading",
    "appendix_heading",
}


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def safe_read_json_bytes(data: bytes) -> Any:
    return json.loads(data.decode("utf-8"))


def list_objects(client: Minio, bucket: str, prefix: str) -> list[str]:
    return [obj.object_name for obj in client.list_objects(bucket, prefix=prefix, recursive=True)]


def get_json(client: Minio, bucket: str, object_name: str) -> Any | None:
    try:
        resp = client.get_object(bucket, object_name)
        try:
            return safe_read_json_bytes(resp.read())
        finally:
            resp.close()
            resp.release_conn()
    except Exception:
        return None


def iter_dicts(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from iter_dicts(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_dicts(item)


def summarize_layout(layout_obj: Any) -> dict[str, Any]:
    elements: list[dict[str, Any]] = []
    for d in iter_dicts(layout_obj):
        if "text" in d and any(k in d for k in ("page", "element_id", "element_type", "type")):
            elements.append(d)

    # dedupe loosely
    seen = set()
    unique_elements = []
    for el in elements:
        sig = (el.get("element_id"), el.get("page"), el.get("text"))
        if sig in seen:
            continue
        seen.add(sig)
        unique_elements.append(el)

    pages = {
        int(el.get("page"))
        for el in unique_elements
        if str(el.get("page", "")).isdigit()
    }

    root_numeric_lines = 0
    headingish_lines = 0
    element_type_counts = Counter()

    for el in unique_elements:
        text = normalize_text(el.get("text"))
        if ROOT_NUMERIC_RE.match(text):
            root_numeric_lines += 1

        element_type = str(el.get("element_type") or "").strip().lower()
        if element_type:
            element_type_counts[element_type] += 1
        if element_type in HEADINGISH_ELEMENT_TYPES or str(el.get("type") or "").strip().lower() == "heading":
            headingish_lines += 1

    return {
        "elements_count": len(unique_elements),
        "page_count": len(pages),
        "max_page": max(pages) if pages else None,
        "root_numeric_lines": root_numeric_lines,
        "headingish_lines": headingish_lines,
        "element_type_top": element_type_counts.most_common(10),
    }


def summarize_file_graph(file_graph_obj: Any) -> dict[str, Any]:
    if not isinstance(file_graph_obj, dict):
        return {"segments_count": 0, "segments": []}

    segments = file_graph_obj.get("segments") or []
    result_segments = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        result_segments.append(
            {
                "segment_order": seg.get("segment_order"),
                "segment_type": seg.get("segment_type"),
                "page_start": seg.get("page_start"),
                "page_end": seg.get("page_end"),
                "scope_name": seg.get("scope_name"),
                "segment_title": normalize_text(seg.get("segment_title")),
            }
        )

    return {
        "segments_count": len(result_segments),
        "primary_segment_id": file_graph_obj.get("primary_segment_id"),
        "degraded": file_graph_obj.get("degraded"),
        "structural_confidence": file_graph_obj.get("structural_confidence"),
        "segments": result_segments,
    }


def summarize_structure_objects(object_names: list[str]) -> dict[str, Any]:
    file_graphs = [x for x in object_names if x.endswith("/file_graph.json")]
    clause_trees = [x for x in object_names if x.endswith("/clause_tree.json")]
    chunk_plans = [x for x in object_names if x.endswith("/chunk_plan.json")]
    chunk_manifests = [x for x in object_names if x.endswith("/chunks_manifest_v2.json")]
    artifact_manifests = [x for x in object_names if x.endswith("/artifact_manifest.json")]
    segment_jsons = [x for x in object_names if "/segment_" in x and x.endswith(".json")]
    chunk_jsons = [x for x in object_names if "/chunks_" in x and x.endswith(".json")]
    legal_unit_jsons = [x for x in object_names if "/legal_units_" in x and x.endswith(".json")]
    versions = sorted(
        {
            parts[i + 1]
            for name in object_names
            for parts in [name.split("/")]
            for i, part in enumerate(parts[:-1])
            if part == "versions"
        }
    )

    return {
        "versions": versions,
        "file_graphs": file_graphs,
        "clause_trees": clause_trees,
        "chunk_plans": chunk_plans,
        "chunk_manifests": chunk_manifests,
        "artifact_manifests": artifact_manifests,
        "segment_jsons": segment_jsons,
        "chunk_jsons": chunk_jsons,
        "legal_unit_jsons": legal_unit_jsons,
    }


def inspect_contract_drift(src_root: Path) -> dict[str, Any]:
    range_logic = src_root / "services/structure/_hierarchy_builder/_range_logic.py"
    constants = src_root / "services/structure/_models/_constants.py"

    range_logic_text = range_logic.read_text(encoding="utf-8")
    constants_text = constants.read_text(encoding="utf-8")

    producer_emits_soft_reason = "soft_next_root_from_layout" in range_logic_text
    contract_allows_soft_reason = "soft_next_root_from_layout" in constants_text

    valid_reasons = sorted(set(re.findall(r'"([a-z_]+)"', constants_text)))
    valid_reasons = [x for x in valid_reasons if x in {
        "first_child",
        "next_same_or_higher",
        "segment_end",
        "fallback_boundary",
        "unbounded_error",
        "segment_end_recovered",
        "fallback_boundary_recovered",
        "soft_next_root_from_layout",
    }]

    return {
        "producer_emits_soft_reason": producer_emits_soft_reason,
        "contract_allows_soft_reason": contract_allows_soft_reason,
        "valid_range_end_reasons_detected": valid_reasons,
        "schema_drift_active": producer_emits_soft_reason and not contract_allows_soft_reason,
    }


def explain_doc_status(
    *,
    doc_id: str,
    layout_summary: dict[str, Any] | None,
    structure_summary: dict[str, Any],
    file_graph_summary: dict[str, Any] | None,
    contract_drift: dict[str, Any],
) -> list[str]:
    lines: list[str] = []

    has_structure_outputs = bool(
        structure_summary["file_graphs"]
        or structure_summary["clause_trees"]
        or structure_summary["chunk_plans"]
        or structure_summary["segment_jsons"]
    )

    if has_structure_outputs:
        lines.append("structure artifacts exist → structure stage completed at least once")
    else:
        lines.append("no structure artifacts found → structure stage likely failed before artifact persistence")

    if layout_summary is not None:
        lines.append(
            "layout summary: "
            f"pages={layout_summary['page_count']}, "
            f"elements={layout_summary['elements_count']}, "
            f"root_numeric_lines={layout_summary['root_numeric_lines']}, "
            f"headingish_lines={layout_summary['headingish_lines']}"
        )

    if file_graph_summary and file_graph_summary["segments_count"] > 0:
        seg_types = Counter(seg["segment_type"] for seg in file_graph_summary["segments"])
        lines.append(
            "file_graph built with segments: "
            + ", ".join(f"{k}={v}" for k, v in sorted(seg_types.items()))
        )

    if contract_drift["schema_drift_active"]:
        lines.append(
            "current source contains schema drift: producer emits "
            "'soft_next_root_from_layout' but VALID_RANGE_END_REASONS does not allow it"
        )

    if not has_structure_outputs and contract_drift["schema_drift_active"]:
        lines.append(
            "most likely explanation: this document triggered the soft root fallback path, "
            "which leaked a non-canonical range_end_reason and caused structure validation to fail"
        )

    if has_structure_outputs and contract_drift["schema_drift_active"]:
        lines.append(
            "most likely explanation: this document did NOT trigger the soft root fallback path, "
            "so the latent contract bug remained dormant and structure build completed"
        )

    return lines


def print_header(title: str) -> None:
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deal-id", required=True)
    parser.add_argument("--doc-id", action="append", required=True, dest="doc_ids")
    parser.add_argument("--tenant-id", help="Optional explicit tenant id. Defaults to deal-id.")
    parser.add_argument("--minio-endpoint", default=DEFAULT_MINIO_ENDPOINT)
    parser.add_argument("--minio-access-key", default=DEFAULT_MINIO_ACCESS_KEY)
    parser.add_argument("--minio-secret-key", default=DEFAULT_MINIO_SECRET_KEY)
    parser.add_argument("--minio-bucket", default=DEFAULT_MINIO_BUCKET)
    parser.add_argument("--minio-secure", action="store_true")
    parser.add_argument("--src-root", default=str(DEFAULT_SRC_ROOT))
    args = parser.parse_args()

    tenant_id = args.tenant_id or args.deal_id
    src_root = Path(args.src_root)

    client = Minio(
        args.minio_endpoint,
        access_key=args.minio_access_key,
        secret_key=args.minio_secret_key,
        secure=bool(args.minio_secure),
    )

    contract_drift = inspect_contract_drift(src_root)

    print_header("GLOBAL SOURCE CONTRACT DRIFT CHECK")
    print(json.dumps(contract_drift, ensure_ascii=False, indent=2))

    results = []

    for doc_id in args.doc_ids:
        print_header(f"DOCUMENT {doc_id}")

        layout_prefix = f"tenants/{tenant_id}/deals/{args.deal_id}/layouts/{doc_id}/"
        structure_prefix = f"tenants/{tenant_id}/deals/{args.deal_id}/structures/{doc_id}/"

        layout_objects = list_objects(client, args.minio_bucket, layout_prefix)
        structure_objects = list_objects(client, args.minio_bucket, structure_prefix)

        print("layout_objects:")
        for name in layout_objects:
            print("  -", name)

        print("\nstructure_objects:")
        if structure_objects:
            for name in structure_objects:
                print("  -", name)
        else:
            print("  <none>")

        layout_summary = None
        primary_sanitized = f"{layout_prefix}primary_sanitized.json"
        if primary_sanitized in layout_objects:
            layout_obj = get_json(client, args.minio_bucket, primary_sanitized)
            if layout_obj is not None:
                layout_summary = summarize_layout(layout_obj)

        structure_summary = summarize_structure_objects(structure_objects)

        file_graph_summary = None
        if structure_summary["file_graphs"]:
            latest_file_graph = sorted(structure_summary["file_graphs"])[-1]
            file_graph_obj = get_json(client, args.minio_bucket, latest_file_graph)
            if file_graph_obj is not None:
                file_graph_summary = summarize_file_graph(file_graph_obj)

        print("\nlayout_summary:")
        print(json.dumps(layout_summary, ensure_ascii=False, indent=2) if layout_summary else "  <none>")

        print("\nstructure_summary:")
        print(json.dumps(structure_summary, ensure_ascii=False, indent=2))

        print("\nfile_graph_summary:")
        print(json.dumps(file_graph_summary, ensure_ascii=False, indent=2) if file_graph_summary else "  <none>")

        explanation = explain_doc_status(
            doc_id=doc_id,
            layout_summary=layout_summary,
            structure_summary=structure_summary,
            file_graph_summary=file_graph_summary,
            contract_drift=contract_drift,
        )

        print("\nexplanation:")
        for line in explanation:
            print("  -", line)

        results.append(
            {
                "doc_id": doc_id,
                "has_structure_outputs": bool(
                    structure_summary["file_graphs"]
                    or structure_summary["clause_trees"]
                    or structure_summary["chunk_plans"]
                    or structure_summary["segment_jsons"]
                ),
                "layout_summary": layout_summary,
                "structure_summary": structure_summary,
                "file_graph_summary": file_graph_summary,
                "explanation": explanation,
            }
        )

    print_header("FINAL COMPARISON")
    for row in results:
        status = "PASSED_STRUCTURE" if row["has_structure_outputs"] else "FAILED_OR_NOT_PERSISTED"
        print(f"- {row['doc_id']}: {status}")

    if contract_drift["schema_drift_active"]:
        print(
            "\nConclusion: documents differ not because the bug is random, but because the bug is "
            "data-dependent. Only documents that trigger the soft root fallback path hit the "
            "non-canonical range_end_reason contract violation."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


    