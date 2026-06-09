#!/usr/bin/env python3
"""
Trace segmenter boundary path for selected pages of a real document.

Read-only diagnostic tool.

Shows for each appendix/amendment-like line on selected pages:
- whether suppression_context suppresses it
- whether match_boundary_marker detects it
- whether infer_boundary_family/type detect it
- whether is_boundary_position accepts it
- whether local swarm/listing guards reject it
- whether it survives validation

Usage:
    PYTHONPATH=src python scripts/trace_segmenter_boundary_path.py \
      --deal-id b1186179-0669-43ed-848b-1cd586aebafd \
      --doc-id 721e6c10-79b4-46e5-8b40-e3ddf2133e4c \
      --pages 8,11,13
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from minio import Minio

from services.structure._segmenter.artifacts import detect_repeated_page_artifacts
from services.structure._segmenter.candidates import (
    _is_part_of_local_swarm,
    collect_boundary_candidates,
    validate_boundary_candidates,
)
from services.structure._segmenter.heuristics import (
    detect_body_internal_boundary_listing,
    is_boundary_position,
    looks_like_non_boundary_block,
)
from services.structure._segmenter.patterns import (
    infer_boundary_family_from_text,
    infer_segment_type_from_text,
    match_boundary_marker,
)
from services.structure._segmenter.toc_suppression import (
    build_boundary_suppression_context,
)
from services.structure.heading_patterns import normalize_spaces

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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deal-id", required=True)
    parser.add_argument("--doc-id", required=True)
    parser.add_argument("--pages", required=True, help="Comma-separated pages, e.g. 8,11,13")
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
        print(f"ERROR: failed to load {layout_key}")
        return 2

    elements = collect_elements(layout_obj)
    elements.sort(key=lambda el: (safe_page(el), str(el.get("element_id") or "")))

    artifacts = detect_repeated_page_artifacts(elements)
    suppression_context = build_boundary_suppression_context(
        elements,
        resolve_boundary_family=infer_boundary_family_from_text,
    )
    collected = collect_boundary_candidates(
        elements,
        artifacts=artifacts,
        suppression_context=suppression_context,
    )
    validated = validate_boundary_candidates(elements, collected)

    collected_indexes = {c.element_index for c in collected}
    validated_indexes = {c.element_index for c in validated}

    print("=" * 120)
    print(f"DOCUMENT {args.doc_id}")
    print("=" * 120)
    print(f"layout_key={layout_key}")
    print(f"pages={sorted(pages)}")
    print(f"suppressed_pages={sorted(suppression_context.suppressed_appendix_pages)}")
    print("suppressed_boundary_families_by_page=")
    print(json.dumps(suppression_context.to_dict().get("suppressed_boundary_families_by_page", {}), ensure_ascii=False, indent=2))

    for idx, el in enumerate(elements):
        page = safe_page(el)
        if page not in pages:
            continue

        text = normalize_spaces(str(el.get("text") or ""))
        if not text:
            continue

        boundary_family = infer_boundary_family_from_text(text)
        marker = match_boundary_marker(text)
        seg_type = infer_segment_type_from_text(text)

        # Интересуют только потенциальные boundary-like строки.
        if not marker and not boundary_family:
            continue

        suppressed = suppression_context.suppresses_boundary_family(page, boundary_family)
        non_boundary_block = looks_like_non_boundary_block(text)
        boundary_position = is_boundary_position(elements, idx, text)
        swarm = bool(boundary_family and _is_part_of_local_swarm(elements, idx, boundary_family))
        listing_guard = detect_body_internal_boundary_listing(
            elements=elements,
            candidate_index=idx,
            boundary_family=boundary_family,
        )

        print("\n" + "-" * 120)
        print(f"idx={idx} page={page} element_id={el.get('element_id')!r}")
        print(f"text={text!r}")
        print(f"marker={marker!r} boundary_family={boundary_family!r} seg_type={seg_type!r}")
        print(f"suppressed_by_page_context={suppressed}")
        print(f"is_non_boundary_block={non_boundary_block}")
        print(f"is_boundary_position={boundary_position}")
        print(f"swarm_rule={swarm}")
        print(f"listing_guard={'YES' if listing_guard else 'NO'}")
        if listing_guard:
            print("listing_guard_details=" + json.dumps(listing_guard, ensure_ascii=False))
        print(f"in_collected_candidates={idx in collected_indexes}")
        print(f"in_validated_candidates={idx in validated_indexes}")

    print("\n" + "=" * 120)
    print("COLLECTED CANDIDATES ON TARGET PAGES")
    print("=" * 120)
    for c in collected:
        if c.page in pages:
            print({
                "element_index": c.element_index,
                "page": c.page,
                "segment_type": c.segment_type,
                "confidence_score": c.confidence_score,
                "reasons": list(c.reasons),
                "text": c.text,
            })

    print("\n" + "=" * 120)
    print("VALIDATED CANDIDATES ON TARGET PAGES")
    print("=" * 120)
    for c in validated:
        if c.page in pages:
            print({
                "element_index": c.element_index,
                "page": c.page,
                "segment_type": c.segment_type,
                "confidence_score": c.confidence_score,
                "reasons": list(c.reasons),
                "text": c.text,
            })

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


