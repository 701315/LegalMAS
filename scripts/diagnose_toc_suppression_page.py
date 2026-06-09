#!/usr/bin/env python3
"""
Read-only diagnostic script for TOC / catalog suppression page analysis.

Purpose:
- inspect how current deterministic suppression logic sees a specific page;
- print page-level suppression diagnostics;
- print per-line local signals:
  * toc_header
  * toc_line_like
  * catalog_header_family
  * boundary_family
  * substantive_body
- help design a universal suppression pattern without document-specific hacks.

This script is generic and can be used for any document/page.

Usage:
    PYTHONPATH=src python scripts/diagnose_toc_suppression_page.py \
      --deal-id 2e9069a8-788e-4c0b-8803-5ad03728012e \
      --doc-id d3dd68a4-9bb4-41f2-9435-50c0dddd2e18 \
      --page 2
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from typing import Any

from minio import Minio

from services.structure.heading_patterns import normalize_spaces
from services.structure._segmenter.patterns import (
    extract_appendix_number,
    infer_boundary_family_from_text,
)
from services.structure._segmenter.toc_suppression import (
    _count_compact_catalog_entry_pairs,
    _detect_catalog_header_family,
    _is_toc_line_like,
    _looks_like_substantive_body_line,
    _looks_like_toc_header,
    build_boundary_suppression_context,
)

DEFAULT_MINIO_ENDPOINT = "localhost:9000"
DEFAULT_MINIO_ACCESS_KEY = "minioadmin"
DEFAULT_MINIO_SECRET_KEY = "minioadmin123"
DEFAULT_MINIO_BUCKET = "mas-artifacts"


def load_json(client: Minio, bucket: str, key: str) -> Any | None:
    try:
        resp = client.get_object(bucket, key)
        try:
            return json.loads(resp.read().decode("utf-8"))
        finally:
            resp.close()
            resp.release_conn()
    except Exception:
        return None


def list_keys(client: Minio, bucket: str, prefix: str) -> list[str]:
    return [obj.object_name for obj in client.list_objects(bucket, prefix=prefix, recursive=True)]


def normalize_text(value: Any) -> str:
    return normalize_spaces(str(value or ""))


def iter_dicts(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from iter_dicts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from iter_dicts(v)


def collect_elements(layout_obj: Any) -> list[dict[str, Any]]:
    # Предпочитаем canonical layout["elements"], если он есть.
    if isinstance(layout_obj, dict):
        direct = layout_obj.get("elements")
        if isinstance(direct, list):
            return [el for el in direct if isinstance(el, dict)]

    # Fallback: recursive extraction.
    result: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any, Any]] = set()

    for d in iter_dicts(layout_obj):
        if not isinstance(d, dict):
            continue
        if "text" not in d or "page" not in d:
            continue

        sig = (d.get("element_id"), d.get("page"), d.get("text"))
        if sig in seen:
            continue
        seen.add(sig)
        result.append(d)

    return result


def latest_file_graph_key(keys: list[str]) -> str | None:
    candidates = sorted([k for k in keys if k.endswith("/file_graph.json")])
    return candidates[-1] if candidates else None


def collect_segments(file_graph_obj: Any) -> list[dict[str, Any]]:
    if not isinstance(file_graph_obj, dict):
        return []
    segments = file_graph_obj.get("segments") or []
    if not isinstance(segments, list):
        return []
    return [seg for seg in segments if isinstance(seg, dict)]


def print_segments(segments: list[dict[str, Any]]) -> None:
    print("\n=== FILE GRAPH SEGMENTS ===")
    if not segments:
        print("<none>")
        return
    for seg in segments:
        print(
            f"- order={seg.get('segment_order')!r} "
            f"type={seg.get('segment_type')!r} "
            f"pages={seg.get('page_start')}-{seg.get('page_end')} "
            f"scope={seg.get('scope_name')!r} "
            f"title={normalize_text(seg.get('segment_title'))!r}"
        )


def diagnose_page(elements: list[dict[str, Any]], page_num: int) -> None:
    suppression_context = build_boundary_suppression_context(
        elements,
        resolve_boundary_family=infer_boundary_family_from_text,
    )

    print("\n=== GLOBAL SUPPRESSION CONTEXT ===")
    print(json.dumps(suppression_context.to_dict(), ensure_ascii=False, indent=2))

    page_rows: list[tuple[int, dict[str, Any]]] = []
    for idx, el in enumerate(elements):
        try:
            page = int(el.get("page") or 0)
        except Exception:
            page = 0
        if page == page_num:
            page_rows.append((idx, el))

    print(f"\n=== PAGE {page_num} SUMMARY ===")
    print(f"rows_on_page={len(page_rows)}")
    print(
        f"suppressed_families={sorted(suppression_context.suppressed_boundary_families_by_page.get(page_num, frozenset()))}"
    )
    print(f"page_reasons={list(suppression_context.page_reasons.get(page_num, ())) or []}")
    print(
        "page_diagnostics="
        + json.dumps(
            suppression_context.page_diagnostics.get(page_num, {}),
            ensure_ascii=False,
            indent=2,
        )
    )

    page_texts: list[str] = []
    family_positions: dict[str, list[int]] = defaultdict(list)
    family_entry_counts: dict[str, int] = defaultdict(int)
    family_header_counts: dict[str, int] = defaultdict(int)

    derived_toc_header_count = 0
    derived_toc_line_like_count = 0
    derived_substantive_body_count = 0

    print(f"\n=== PAGE {page_num} ROWS ===")
    if not page_rows:
        print("<no rows>")
        return

    for local_pos, (global_idx, el) in enumerate(page_rows):
        text = normalize_text(el.get("text"))
        element_type = str(el.get("element_type") or "").strip().lower()
        raw_type = str(el.get("type") or "").strip().lower()

        is_toc_header = _looks_like_toc_header(text=text, element_type=element_type)
        is_toc_line_like = _is_toc_line_like(text=text, element_type=element_type)
        catalog_header_family = _detect_catalog_header_family(text)
        boundary_family = infer_boundary_family_from_text(text)
        substantive_body = (
            not is_toc_header
            and not is_toc_line_like
            and catalog_header_family is None
            and boundary_family is None
            and _looks_like_substantive_body_line(text)
        )

        appendix_number = extract_appendix_number(text)

        if text:
            page_texts.append(text)

        if is_toc_header:
            derived_toc_header_count += 1
        if is_toc_line_like:
            derived_toc_line_like_count += 1
        if catalog_header_family:
            family_header_counts[catalog_header_family] += 1
        if boundary_family:
            family_entry_counts[boundary_family] += 1
            family_positions[boundary_family].append(local_pos)
        if substantive_body:
            derived_substantive_body_count += 1

        flags: list[str] = []
        if is_toc_header:
            flags.append("toc_header")
        if is_toc_line_like:
            flags.append("toc_line_like")
        if catalog_header_family:
            flags.append(f"catalog_header:{catalog_header_family}")
        if boundary_family:
            flags.append(f"boundary_family:{boundary_family}")
        if substantive_body:
            flags.append("substantive_body")
        if appendix_number is not None:
            flags.append(f"appendix_num:{appendix_number}")

        print(
            f"idx={global_idx:04d} "
            f"local={local_pos:02d} "
            f"type={raw_type!r} "
            f"element_type={element_type!r} "
            f"flags={flags} "
            f"text={text!r}"
        )

    print(f"\n=== PAGE {page_num} DERIVED COUNTS ===")
    print(f"derived_toc_header_count={derived_toc_header_count}")
    print(f"derived_toc_line_like_count={derived_toc_line_like_count}")
    print(f"derived_substantive_body_count={derived_substantive_body_count}")

    print(f"\n=== PAGE {page_num} FAMILY COUNTS ===")
    for family in sorted(set(family_entry_counts) | set(family_header_counts)):
        positions = family_positions.get(family, [])
        compact_pairs = _count_compact_catalog_entry_pairs(
            page_texts=page_texts,
            entry_positions=positions,
        )
        print(
            json.dumps(
                {
                    "family": family,
                    "entry_count": family_entry_counts.get(family, 0),
                    "header_count": family_header_counts.get(family, 0),
                    "entry_positions_local": positions,
                    "compact_entry_pairs": compact_pairs,
                },
                ensure_ascii=False,
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deal-id", required=True)
    parser.add_argument("--doc-id", required=True)
    parser.add_argument("--page", required=True, type=int)
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

    layout_prefix = f"tenants/{tenant_id}/deals/{args.deal_id}/layouts/{args.doc_id}/"
    structure_prefix = f"tenants/{tenant_id}/deals/{args.deal_id}/structures/{args.doc_id}/"

    layout_keys = list_keys(client, args.minio_bucket, layout_prefix)
    structure_keys = list_keys(client, args.minio_bucket, structure_prefix)

    layout_key = f"{layout_prefix}primary_sanitized.json"
    file_graph_key = latest_file_graph_key(structure_keys)

    layout_obj = load_json(client, args.minio_bucket, layout_key) if layout_key in layout_keys else None
    file_graph_obj = load_json(client, args.minio_bucket, file_graph_key) if file_graph_key else None

    print("=" * 120)
    print(f"DOCUMENT {args.doc_id} PAGE {args.page}")
    print("=" * 120)
    print(f"layout_key={layout_key if layout_obj is not None else '<missing>'}")
    print(f"file_graph_key={file_graph_key if file_graph_obj is not None else '<missing>'}")

    if layout_obj is None:
        print("ERROR: primary_sanitized.json missing or unreadable")
        return 2

    elements = collect_elements(layout_obj)
    print(f"elements_count={len(elements)}")

    segments = collect_segments(file_graph_obj)
    print_segments(segments)

    diagnose_page(elements, args.page)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


    