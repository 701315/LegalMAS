#!/usr/bin/env python3
"""
Compare segmentation on raw sanitized layout vs classified elements.

Purpose:
- prove whether pre-segmentation element classification changes
  segmentation outcome;
- inspect how appendix headings are labeled after classification.

Usage:
    PYTHONPATH=src python scripts/compare_raw_vs_classified_segmentation.py \
      --deal-id b1186179-0669-43ed-848b-1cd586aebafd \
      --doc-id 721e6c10-79b4-46e5-8b40-e3ddf2133e4c \
      --pages 8,11,13
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from minio import Minio

from services.structure.element_classifier import classify_elements
from services.structure.heading_patterns import normalize_spaces
from services.structure.segmenter import segment_elements

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


def iter_dicts(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from iter_dicts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from iter_dicts(v)


def collect_elements(layout_obj: Any) -> list[dict[str, Any]]:
    if isinstance(layout_obj, dict):
        direct = layout_obj.get("elements")
        if isinstance(direct, list):
            return [el for el in direct if isinstance(el, dict)]

    rows: list[dict[str, Any]] = []
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
        rows.append(d)
    return rows


def safe_page(el: dict[str, Any]) -> int:
    try:
        return int(el.get("page") or 0)
    except Exception:
        return 0


def print_segments(label: str, segments: list[Any]) -> None:
    print("\n" + "=" * 100)
    print(label)
    print("=" * 100)
    for seg in segments:
        print(
            {
                "segment_order": getattr(seg, "segment_order", None),
                "segment_type": getattr(seg, "segment_type", None),
                "page_start": getattr(seg, "page_start", None),
                "page_end": getattr(seg, "page_end", None),
                "scope_name": getattr(seg, "scope_name", None),
                "segment_title": getattr(seg, "segment_title", None),
            }
        )


def print_page_rows(label: str, elements: list[dict[str, Any]], pages: set[int]) -> None:
    print("\n" + "=" * 100)
    print(label)
    print("=" * 100)
    for i, el in enumerate(elements):
        page = safe_page(el)
        if page not in pages:
            continue
        text = normalize_spaces(el.get("text"))
        if not text:
            continue
        if "прилож" not in text.lower():
            continue
        print(
            f"idx={i:04d} "
            f"page={page} "
            f"type={el.get('type')!r} "
            f"element_type={el.get('element_type')!r} "
            f"text={text!r}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deal-id", required=True)
    parser.add_argument("--doc-id", required=True)
    parser.add_argument("--pages", default="8,11,13")
    parser.add_argument("--tenant-id", help="Optional tenant id; defaults to deal id")
    parser.add_argument("--minio-endpoint", default=DEFAULT_MINIO_ENDPOINT)
    parser.add_argument("--minio-access-key", default=DEFAULT_MINIO_ACCESS_KEY)
    parser.add_argument("--minio-secret-key", default=DEFAULT_MINIO_SECRET_KEY)
    parser.add_argument("--minio-bucket", default=DEFAULT_MINIO_BUCKET)
    parser.add_argument("--minio-secure", action="store_true")
    args = parser.parse_args()

    tenant_id = args.tenant_id or args.deal_id
    pages = {int(x.strip()) for x in args.pages.split(",") if x.strip()}

    client = Minio(
        args.minio_endpoint,
        access_key=args.minio_access_key,
        secret_key=args.minio_secret_key,
        secure=bool(args.minio_secure),
    )

    layout_key = (
        f"tenants/{tenant_id}/deals/{args.deal_id}/layouts/{args.doc_id}/primary_sanitized.json"
    )
    layout_obj = load_json(client, args.minio_bucket, layout_key)
    if layout_obj is None:
        print(f"ERROR: cannot load {layout_key}")
        return 2

    raw_elements = collect_elements(layout_obj)
    classified_elements = classify_elements(raw_elements, document_id=args.doc_id)

    print(f"elements_count_raw={len(raw_elements)}")
    print(f"elements_count_classified={len(classified_elements)}")

    raw_segments = segment_elements(document_id=args.doc_id, elements=raw_elements)
    classified_segments = segment_elements(document_id=args.doc_id, elements=classified_elements)

    print_segments("RAW SEGMENTATION", raw_segments)
    print_segments("CLASSIFIED SEGMENTATION", classified_segments)

    print_page_rows("RAW APPENDIX-LIKE ROWS", raw_elements, pages)
    print_page_rows("CLASSIFIED APPENDIX-LIKE ROWS", classified_elements, pages)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


