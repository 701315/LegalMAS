#!/usr/bin/env python3
"""
Read-only boundary audit for segmented documents.

Purpose:
- load file_graph.json and primary_sanitized.json from MinIO
- show produced segments
- for each non-primary segment, inspect the likely boundary region
- print nearby appendix/amendment marker-like lines
- help determine whether the segment boundary is legitimate or false positive

Usage:
    PYTHONPATH=src python scripts/audit_segment_boundaries.py \
      --deal-id 2e9069a8-788e-4c0b-8803-5ad03728012e \
      --doc-id d3dd68a4-9bb4-41f2-9435-50c0dddd2e18 \
      --doc-id f7d83fb3-a98b-49b2-9f47-2e3b3be80b21
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any

from minio import Minio

from services.structure._segmenter.patterns import (
    infer_boundary_family_from_text,
    match_boundary_marker,
)
from services.structure.heading_patterns import normalize_spaces


DEFAULT_MINIO_ENDPOINT = "localhost:9000"
DEFAULT_MINIO_ACCESS_KEY = "minioadmin"
DEFAULT_MINIO_SECRET_KEY = "minioadmin123"
DEFAULT_MINIO_BUCKET = "mas-artifacts"


@dataclass
class DocArtifacts:
    layout_obj: Any | None
    file_graph_obj: Any | None
    layout_key: str | None
    file_graph_key: str | None


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
    result: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any, Any]] = set()

    for d in iter_dicts(layout_obj):
        if not isinstance(d, dict):
            continue
        if "text" not in d:
            continue
        if not any(k in d for k in ("page", "element_id", "type", "element_type")):
            continue

        sig = (d.get("element_id"), d.get("page"), d.get("text"))
        if sig in seen:
            continue
        seen.add(sig)
        result.append(d)

    def sort_key(el: dict[str, Any]):
        try:
            page = int(el.get("page") or 0)
        except Exception:
            page = 0
        return (page, str(el.get("element_id") or ""))

    return sorted(result, key=sort_key)


def collect_segments(file_graph_obj: Any) -> list[dict[str, Any]]:
    if not isinstance(file_graph_obj, dict):
        return []
    segments = file_graph_obj.get("segments") or []
    if not isinstance(segments, list):
        return []
    return [s for s in segments if isinstance(s, dict)]


def find_elements_on_pages(
    elements: list[dict[str, Any]],
    pages: set[int],
) -> list[tuple[int, dict[str, Any]]]:
    rows = []
    for i, el in enumerate(elements):
        try:
            page = int(el.get("page") or 0)
        except Exception:
            page = 0
        if page in pages:
            rows.append((i, el))
    return rows


def find_title_match_indexes(
    elements: list[dict[str, Any]],
    page_start: int,
    segment_title: str,
) -> list[int]:
    title_norm = normalize_text(segment_title).lower()
    if not title_norm:
        return []

    result = []
    for i, el in enumerate(elements):
        try:
            page = int(el.get("page") or 0)
        except Exception:
            page = 0

        if page < max(1, page_start - 1) or page > page_start + 1:
            continue

        text = normalize_text(el.get("text")).lower()
        if not text:
            continue

        if title_norm in text or text in title_norm:
            result.append(i)

    return result


def marker_like_rows(
    elements: list[dict[str, Any]],
    page_start: int,
    page_end: int | None = None,
    page_window: int = 1,
) -> list[dict[str, Any]]:
    left = max(1, page_start - page_window)
    right = (page_end if page_end is not None else page_start) + page_window
    rows = []

    for i, el in enumerate(elements):
        try:
            page = int(el.get("page") or 0)
        except Exception:
            page = 0

        if page < left or page > right:
            continue

        text = normalize_text(el.get("text"))
        if not text:
            continue

        family = infer_boundary_family_from_text(text)
        marker = match_boundary_marker(text)
        if family or marker:
            rows.append(
                {
                    "index": i,
                    "page": page,
                    "element_id": el.get("element_id"),
                    "element_type": el.get("element_type"),
                    "raw_type": el.get("type"),
                    "boundary_family": family,
                    "marker": marker,
                    "text": text,
                }
            )

    return rows


def print_window(elements: list[dict[str, Any]], center_index: int, radius: int = 8) -> None:
    left = max(0, center_index - radius)
    right = min(len(elements), center_index + radius + 1)

    print("\n  --- boundary context window ---")
    for i in range(left, right):
        el = elements[i]
        marker = ">>" if i == center_index else "  "
        print(
            f"{marker} idx={i:04d} "
            f"page={el.get('page')!r} "
            f"element_id={el.get('element_id')!r} "
            f"element_type={el.get('element_type')!r} "
            f"type={el.get('type')!r} "
            f"text={normalize_text(el.get('text'))!r}"
        )


def print_page_excerpt(elements: list[dict[str, Any]], page_start: int, page_window: int = 1, max_rows: int = 40) -> None:
    pages = set(range(max(1, page_start - page_window), page_start + page_window + 1))
    rows = find_elements_on_pages(elements, pages)

    print("\n  --- page excerpt around boundary pages ---")
    for idx, el in rows[:max_rows]:
        print(
            f"  idx={idx:04d} "
            f"page={el.get('page')!r} "
            f"element_id={el.get('element_id')!r} "
            f"element_type={el.get('element_type')!r} "
            f"type={el.get('type')!r} "
            f"text={normalize_text(el.get('text'))!r}"
        )
    if len(rows) > max_rows:
        print(f"  ... {len(rows) - max_rows} more rows")


def audit_document(
    client: Minio,
    bucket: str,
    deal_id: str,
    tenant_id: str,
    doc_id: str,
) -> None:
    layout_prefix = f"tenants/{tenant_id}/deals/{deal_id}/layouts/{doc_id}/"
    structure_prefix = f"tenants/{tenant_id}/deals/{deal_id}/structures/{doc_id}/"

    layout_keys = list_keys(client, bucket, layout_prefix)
    structure_keys = list_keys(client, bucket, structure_prefix)

    layout_key = f"{layout_prefix}primary_sanitized.json"
    file_graph_candidates = [k for k in structure_keys if k.endswith("/file_graph.json")]
    file_graph_key = sorted(file_graph_candidates)[-1] if file_graph_candidates else None

    layout_obj = load_json(client, bucket, layout_key) if layout_key in layout_keys else None
    file_graph_obj = load_json(client, bucket, file_graph_key) if file_graph_key else None

    print("\n" + "=" * 120)
    print(f"DOCUMENT {doc_id}")
    print("=" * 120)
    print(f"layout_key: {layout_key if layout_obj is not None else '<missing>'}")
    print(f"file_graph_key: {file_graph_key if file_graph_obj is not None else '<missing>'}")

    if layout_obj is None:
        print("ERROR: primary_sanitized.json not found or failed to load")
        return

    if file_graph_obj is None:
        print("ERROR: file_graph.json not found or failed to load")
        return

    elements = collect_elements(layout_obj)
    segments = collect_segments(file_graph_obj)

    print(f"\nelements_count={len(elements)}")
    print(f"segments_count={len(segments)}")

    print("\nsegments:")
    for seg in segments:
        print(
            f"  - order={seg.get('segment_order')!r} "
            f"type={seg.get('segment_type')!r} "
            f"pages={seg.get('page_start')}-{seg.get('page_end')} "
            f"scope={seg.get('scope_name')!r} "
            f"title={normalize_text(seg.get('segment_title'))!r}"
        )

    appendix_like_segments = [
        seg for seg in segments
        if str(seg.get("segment_type") or "").strip().lower() in {"appendix", "amendment"}
    ]

    if not appendix_like_segments:
        print("\nNo appendix/amendment segments to audit.")
        return

    for seg in appendix_like_segments:
        page_start = int(seg.get("page_start") or 0)
        page_end = int(seg.get("page_end") or page_start)
        title = normalize_text(seg.get("segment_title"))
        seg_type = seg.get("segment_type")
        scope_name = seg.get("scope_name")

        print("\n" + "-" * 120)
        print(
            f"AUDIT SEGMENT type={seg_type!r} scope={scope_name!r} "
            f"pages={page_start}-{page_end} title={title!r}"
        )

        matches = find_title_match_indexes(elements, page_start, title)

        if matches:
            print(f"  title_match_indexes={matches[:10]}")
            print_window(elements, matches[0], radius=10)
        else:
            print("  title_match_indexes=[]")
            print_page_excerpt(elements, page_start, page_window=1, max_rows=50)

        marker_rows = marker_like_rows(elements, page_start=page_start, page_end=page_end, page_window=1)
        print("\n  --- nearby boundary-family marker-like rows ---")
        if not marker_rows:
            print("  <none>")
        else:
            for row in marker_rows[:40]:
                print(
                    f"  idx={row['index']:04d} "
                    f"page={row['page']} "
                    f"family={row['boundary_family']!r} "
                    f"marker={row['marker']!r} "
                    f"element_type={row['element_type']!r} "
                    f"type={row['raw_type']!r} "
                    f"text={row['text']!r}"
                )
            if len(marker_rows) > 40:
                print(f"  ... {len(marker_rows) - 40} more marker-like rows")

        print("\n  --- heuristic note ---")
        if title:
            if "приложени" in title.lower() or "appendix" in title.lower():
                print("  title is appendix-like")
            else:
                print("  title is NOT clearly appendix-like → likely suspicious")
        else:
            print("  empty / missing segment title → suspicious")


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

    for doc_id in args.doc_ids:
        audit_document(
            client=client,
            bucket=args.minio_bucket,
            deal_id=args.deal_id,
            tenant_id=tenant_id,
            doc_id=doc_id,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


    