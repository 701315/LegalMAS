#!/usr/bin/env python3
"""
Read-only diagnostic script for structure/chunking health.

Checks for each document:
- whether structure artifacts exist in MinIO;
- file_graph summary (segments, confidence, degraded);
- clause_tree presence;
- chunk_plan summary;
- chunks_manifest summary;
- per-chunk-file statistics;
- heuristic suspicious chunking signals.

IMPORTANT:
This is a diagnostic heuristic tool.
It does NOT guarantee semantic correctness.
It highlights likely problem areas for manual review.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from minio import Minio


DEFAULT_MINIO_ENDPOINT = "localhost:9000"
DEFAULT_MINIO_ACCESS_KEY = "minioadmin"
DEFAULT_MINIO_SECRET_KEY = "minioadmin123"
DEFAULT_MINIO_BUCKET = "mas-artifacts"


TOP_LEVEL_HEADING_RE = re.compile(r"(?m)^\s*(\d+)\s+\S")
SUBCLAUSE_UID_RE = re.compile(r"(?<!\d)(\d+\.\d+)(?!\d)")
ANY_UID_RE = re.compile(r"(?<!\d)(\d+(?:\.\d+)+)(?!\d)")


@dataclass
class ObjectMeta:
    name: str
    last_modified: str | None
    size: int | None


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def iter_dicts(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from iter_dicts(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_dicts(item)


def load_json(client: Minio, bucket: str, object_name: str) -> Any | None:
    try:
        resp = client.get_object(bucket, object_name)
        try:
            return json.loads(resp.read().decode("utf-8"))
        finally:
            resp.close()
            resp.release_conn()
    except Exception:
        return None


def list_objects(client: Minio, bucket: str, prefix: str) -> list[ObjectMeta]:
    result: list[ObjectMeta] = []
    for obj in client.list_objects(bucket, prefix=prefix, recursive=True):
        result.append(
            ObjectMeta(
                name=obj.object_name,
                last_modified=str(obj.last_modified) if obj.last_modified else None,
                size=int(obj.size) if obj.size is not None else None,
            )
        )
    return result


def latest_matching(objects: list[ObjectMeta], suffix: str) -> ObjectMeta | None:
    matches = [o for o in objects if o.name.endswith(suffix)]
    if not matches:
        return None
    return sorted(matches, key=lambda o: (o.last_modified or "", o.name))[-1]


def matching_regex(objects: list[ObjectMeta], pattern: str) -> list[ObjectMeta]:
    rx = re.compile(pattern)
    return [o for o in objects if rx.search(o.name)]


def extract_text_from_chunk(chunk: dict[str, Any]) -> str:
    for key in ("exact_text", "retrieval_text", "text", "content", "body", "chunk_text", "summary"):
        value = chunk.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def extract_chunk_kind(chunk: dict[str, Any]) -> str:
    for key in ("kind", "level", "chunk_kind", "role"):
        value = chunk.get(key)
        if value:
            return str(value)
    return "unknown"


def is_chunk_like_dict(d: dict[str, Any]) -> bool:
    text = extract_text_from_chunk(d)
    if not text:
        return False
    if any(k in d for k in ("chunk_id", "display_title", "kind", "level", "chunk_kind")):
        return True
    return False


def collect_chunk_dicts(payload: Any) -> list[dict[str, Any]]:
    chunks_root = payload.get("chunks") if isinstance(payload, dict) else payload
    result: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    for d in iter_dicts(chunks_root):
        if not isinstance(d, dict):
            continue
        if not is_chunk_like_dict(d):
            continue

        text = extract_text_from_chunk(d)
        sig = (
            d.get("chunk_id"),
            d.get("display_title"),
            extract_chunk_kind(d),
            text[:160],
        )
        if sig in seen:
            continue
        seen.add(sig)
        result.append(d)

    return result


def summarize_file_graph(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        return {}

    segments = obj.get("segments") or []
    out_segments = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        out_segments.append(
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
        "degraded": obj.get("degraded"),
        "structural_confidence": obj.get("structural_confidence"),
        "primary_segment_id": obj.get("primary_segment_id"),
        "segments_count": len(out_segments),
        "segment_types": dict(Counter(seg["segment_type"] for seg in out_segments)),
        "segments": out_segments,
    }


def summarize_chunk_plan(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        return {}

    segment_plans = obj.get("segment_plans") or []
    return {
        "segment_count": obj.get("segment_count"),
        "overall_retrieval_safe": obj.get("overall_retrieval_safe"),
        "any_layout_fallback": obj.get("any_layout_fallback"),
        "all_segments_full_fallback": obj.get("all_segments_full_fallback"),
        "mode_decision": obj.get("mode_decision"),
        "segment_plans_count": len(segment_plans) if isinstance(segment_plans, list) else None,
    }


def summarize_manifest(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        return {}

    segments = obj.get("segments") or []
    totals = obj.get("totals") or {}
    return {
        "degraded": obj.get("degraded"),
        "degradation_reason": obj.get("degradation_reason"),
        "primary_segment_id": obj.get("primary_segment_id"),
        "segments_count": len(segments) if isinstance(segments, list) else None,
        "totals": totals,
    }


def summarize_clause_tree(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        return {}

    node_like = 0
    for d in iter_dicts(obj):
        if not isinstance(d, dict):
            continue
        if any(k in d for k in ("effective_uid", "raw_uid", "node_kind", "title", "heading_text")):
            node_like += 1

    return {
        "degraded": obj.get("degraded"),
        "structure_confidence": obj.get("structure_confidence"),
        "segment_type": obj.get("segment_type"),
        "scope_name": obj.get("scope_name"),
        "node_like_count": node_like,
    }


def summarize_chunk_file(obj: Any, object_name: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        return {"object_name": object_name, "error": "not_a_dict"}

    chunk_dicts = collect_chunk_dicts(obj)
    kind_counts = Counter()
    suspicious: list[dict[str, Any]] = []

    top_level_segment = obj.get("segment") if isinstance(obj.get("segment"), dict) else {}
    degraded = obj.get("degraded")
    degradation_reason = obj.get("degradation_reason")
    built_at = obj.get("built_at")

    for chunk in chunk_dicts:
        kind = extract_chunk_kind(chunk)
        kind_counts[kind] += 1

        text = extract_text_from_chunk(chunk)
        text_len = len(text)

        top_level_heads = sorted(set(TOP_LEVEL_HEADING_RE.findall(text)))
        sub_uids = sorted(set(SUBCLAUSE_UID_RE.findall(text)))
        all_uids = sorted(set(ANY_UID_RE.findall(text)))

        reasons: list[str] = []
        if text_len >= 12000:
            reasons.append("very_large_text")
        if len(top_level_heads) >= 2:
            reasons.append("multiple_top_level_headings")
        if len(sub_uids) >= 8:
            reasons.append("many_subclause_uids")
        if len(all_uids) >= 14:
            reasons.append("many_numbered_uids")

        if reasons:
            suspicious.append(
                {
                    "chunk_id": chunk.get("chunk_id"),
                    "kind": kind,
                    "display_title": normalize_text(chunk.get("display_title")),
                    "text_len": text_len,
                    "top_level_headings": top_level_heads[:10],
                    "subclause_uid_count": len(sub_uids),
                    "all_uid_count": len(all_uids),
                    "reasons": reasons,
                    "preview": normalize_text(text)[:240],
                }
            )

    return {
        "object_name": object_name,
        "built_at": built_at,
        "degraded": degraded,
        "degradation_reason": degradation_reason,
        "segment": {
            "segment_id": top_level_segment.get("segment_id"),
            "segment_type": top_level_segment.get("segment_type"),
            "page_start": top_level_segment.get("page_start"),
            "page_end": top_level_segment.get("page_end"),
            "scope_name": top_level_segment.get("scope_name"),
            "segment_title": normalize_text(top_level_segment.get("segment_title")),
        },
        "chunk_count": len(chunk_dicts),
        "kind_counts": dict(kind_counts),
        "suspicious_count": len(suspicious),
        "suspicious": suspicious[:15],
    }


def print_block(title: str, payload: Any) -> None:
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deal-id", required=True)
    parser.add_argument("--doc-id", action="append", required=True, dest="doc_ids")
    parser.add_argument("--tenant-id", help="Optional tenant id; defaults to deal id")
    parser.add_argument("--minio-endpoint", default=DEFAULT_MINIO_ENDPOINT)
    parser.add_argument("--minio-access-key", default=DEFAULT_MINIO_ACCESS_KEY)
    parser.add_argument("--minio-secret-key", default=DEFAULT_MINIO_SECRET_KEY)
    parser.add_argument("--minio-bucket", default=DEFAULT_MINIO_BUCKET)
    parser.add_argument("--minio-secure", action="store_true")
    args = parser.parse_args()

    tenant_id = args.tenant_id or args.deal_id

    client = Minio(
        args.minio_endpoint,
        access_key=args.minio_access_key,
        secret_key=args.minio_secret_key,
        secure=bool(args.minio_secure),
    )

    final_rows = []

    for doc_id in args.doc_ids:
        layout_prefix = f"tenants/{tenant_id}/deals/{args.deal_id}/layouts/{doc_id}/"
        structure_prefix = f"tenants/{tenant_id}/deals/{args.deal_id}/structures/{doc_id}/"

        layout_objects = list_objects(client, args.minio_bucket, layout_prefix)
        structure_objects = list_objects(client, args.minio_bucket, structure_prefix)

        latest_file_graph = latest_matching(structure_objects, "/file_graph.json")
        latest_clause_tree = latest_matching(structure_objects, "/clause_tree.json")
        latest_chunk_plan = latest_matching(structure_objects, "/chunk_plan.json")
        latest_manifest = latest_matching(structure_objects, "/chunks_manifest_v2.json")
        segment_files = matching_regex(structure_objects, r"/segment_[^/]+\.json$")
        chunk_files = [
            o for o in matching_regex(structure_objects, r"/chunks_[^/]+\.json$")
            if not o.name.endswith("chunks_manifest_v2.json")
        ]

        file_graph_summary = None
        clause_tree_summary = None
        chunk_plan_summary = None
        manifest_summary = None
        chunk_summaries = []

        if latest_file_graph:
            obj = load_json(client, args.minio_bucket, latest_file_graph.name)
            file_graph_summary = summarize_file_graph(obj) if obj is not None else {"error": "load_failed"}

        if latest_clause_tree:
            obj = load_json(client, args.minio_bucket, latest_clause_tree.name)
            clause_tree_summary = summarize_clause_tree(obj) if obj is not None else {"error": "load_failed"}

        if latest_chunk_plan:
            obj = load_json(client, args.minio_bucket, latest_chunk_plan.name)
            chunk_plan_summary = summarize_chunk_plan(obj) if obj is not None else {"error": "load_failed"}

        if latest_manifest:
            obj = load_json(client, args.minio_bucket, latest_manifest.name)
            manifest_summary = summarize_manifest(obj) if obj is not None else {"error": "load_failed"}

        for chunk_file in sorted(chunk_files, key=lambda o: (o.last_modified or "", o.name)):
            obj = load_json(client, args.minio_bucket, chunk_file.name)
            if obj is None:
                chunk_summaries.append({"object_name": chunk_file.name, "error": "load_failed"})
            else:
                chunk_summaries.append(summarize_chunk_file(obj, chunk_file.name))

        artifact_presence = {
            "layout_objects_count": len(layout_objects),
            "structure_objects_count": len(structure_objects),
            "has_file_graph": latest_file_graph is not None,
            "has_clause_tree": latest_clause_tree is not None,
            "has_chunk_plan": latest_chunk_plan is not None,
            "has_chunks_manifest": latest_manifest is not None,
            "segment_files_count": len(segment_files),
            "chunk_files_count": len(chunk_files),
        }

        print_block(f"DOCUMENT {doc_id} :: ARTIFACT PRESENCE", artifact_presence)

        if file_graph_summary is not None:
            print_block(f"DOCUMENT {doc_id} :: FILE_GRAPH SUMMARY", file_graph_summary)
        if clause_tree_summary is not None:
            print_block(f"DOCUMENT {doc_id} :: CLAUSE_TREE SUMMARY", clause_tree_summary)
        if chunk_plan_summary is not None:
            print_block(f"DOCUMENT {doc_id} :: CHUNK_PLAN SUMMARY", chunk_plan_summary)
        if manifest_summary is not None:
            print_block(f"DOCUMENT {doc_id} :: CHUNKS MANIFEST SUMMARY", manifest_summary)

        print_block(f"DOCUMENT {doc_id} :: CHUNK FILE SUMMARIES", chunk_summaries)

        suspicious_total = sum(int(row.get("suspicious_count", 0)) for row in chunk_summaries if isinstance(row, dict))
        verdict = {
            "doc_id": doc_id,
            "artifacts_built": bool(
                artifact_presence["has_file_graph"]
                and artifact_presence["has_clause_tree"]
                and artifact_presence["has_chunk_plan"]
                and artifact_presence["segment_files_count"] > 0
                and artifact_presence["chunk_files_count"] > 0
            ),
            "suspicious_chunk_signals_total": suspicious_total,
            "heuristic_status": (
                "LOOKS_OK"
                if suspicious_total == 0 and artifact_presence["chunk_files_count"] > 0
                else "REVIEW_SUSPICIOUS_CHUNKS"
            ),
        }
        print_block(f"DOCUMENT {doc_id} :: VERDICT", verdict)
        final_rows.append(verdict)

    print_block("FINAL SUMMARY", final_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


    