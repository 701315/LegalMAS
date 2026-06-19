#!/usr/bin/env python3
"""
Inspect document layout artifact in MinIO and search for element_id / clause_uid.

Usage:
  python3 scripts/inspect_document_layout_artifact.py \
    --document-id 3c90865f-3cb4-4d4d-82cc-14af76246554 \
    --element-id eebe80efd5f \
    --clause-uid main_contract:1.8

Optional:
  --use sanitized   # default
  --use raw
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://mas:mas_dev_password@localhost:5432/mas_dd"
).replace("postgresql+asyncpg://", "postgresql://")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "mas-artifacts")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"


def get_args():
    p = argparse.ArgumentParser(description="Inspect layout artifact for a document")
    p.add_argument("--document-id", required=True)
    p.add_argument("--element-id", required=False)
    p.add_argument("--clause-uid", required=False)
    p.add_argument("--use", choices=["raw", "sanitized"], default="sanitized")
    return p.parse_args()


def get_latest_document_version(document_id: str) -> dict[str, Any]:
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT
            id,
            document_id,
            created_at,
            text_layout_raw_ref,
            text_layout_sanitized_ref
        FROM document_versions
        WHERE document_id = %s
        ORDER BY created_at DESC
        LIMIT 1
    """, (document_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        raise RuntimeError(f"No document_versions found for document_id={document_id}")

    return dict(row)

def _split_s3_ref(ref: str) -> tuple[str, str]:
    """
    Нормализовать ref до (bucket, object_name).

    Поддерживаем:
    - s3://bucket/key
    - bucket/key
    - просто key (тогда bucket берём из MINIO_BUCKET)
    """
    if not ref:
        raise ValueError("Empty artifact ref")

    ref = ref.strip()

    # Формат: s3://bucket/key
    if ref.startswith("s3://"):
        no_scheme = ref[len("s3://"):]
        parts = no_scheme.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid s3 ref: {ref}")
        bucket = parts[0]
        object_name = parts[1]
        return bucket, object_name

    # Формат: bucket/key
    prefix = MINIO_BUCKET + "/"
    if ref.startswith(prefix):
        return MINIO_BUCKET, ref[len(prefix):]

    # Формат: просто key
    return MINIO_BUCKET, ref

def load_artifact_json(ref: str) -> Any:
    from minio import Minio

    bucket, object_name = _split_s3_ref(ref)

    client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )

    response = client.get_object(bucket, object_name)
    try:
        payload = response.read()
    finally:
        response.close()
        response.release_conn()

    return json.loads(payload.decode("utf-8"))


def node_text_preview(node: Any) -> str | None:
    if isinstance(node, dict):
        for key in ("text", "content", "body", "value", "normalized_text"):
            val = node.get(key)
            if isinstance(val, str) and val.strip():
                return val[:800]
    return None


def find_matches(
    obj: Any,
    *,
    element_id: str | None,
    clause_uid: str | None,
    path: str = "$",
    out: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if out is None:
        out = []

    if isinstance(obj, dict):
        matched = False

        possible_element_ids = [
            obj.get("element_id"),
            obj.get("id"),
        ]
        possible_clause_ids = [
            obj.get("clause_uid"),
            obj.get("effective_uid"),
        ]

        if element_id and any(str(v) == element_id for v in possible_element_ids if v is not None):
            matched = True

        if clause_uid and any(str(v) == clause_uid for v in possible_clause_ids if v is not None):
            matched = True

        if matched:
            out.append({
                "path": path,
                "keys": list(obj.keys()),
                "element_id": obj.get("element_id") or obj.get("id"),
                "clause_uid": obj.get("clause_uid") or obj.get("effective_uid"),
                "page": obj.get("page") or obj.get("start_page"),
                "segment_id": obj.get("segment_id"),
                "segment_type": obj.get("segment_type"),
                "text_preview": node_text_preview(obj),
                "node": obj,
            })

        for k, v in obj.items():
            find_matches(
                v,
                element_id=element_id,
                clause_uid=clause_uid,
                path=f"{path}.{k}",
                out=out,
            )

    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            find_matches(
                item,
                element_id=element_id,
                clause_uid=clause_uid,
                path=f"{path}[{i}]",
                out=out,
            )

    return out


def main():
    args = get_args()

    version = get_latest_document_version(args.document_id)

    ref = (
        version["text_layout_sanitized_ref"]
        if args.use == "sanitized"
        else version["text_layout_raw_ref"]
    )

    print("=" * 88)
    print("DOCUMENT VERSION")
    print("=" * 88)
    print(json.dumps(version, ensure_ascii=False, indent=2, default=str))

    if not ref:
        print(f"\n[ERROR] No {args.use} layout ref for this document version")
        sys.exit(1)

    print("\n" + "=" * 88)
    print("LOADING ARTIFACT")
    print("=" * 88)

    bucket, object_name = _split_s3_ref(ref)
    print(f"bucket: {bucket}")
    print(f"object: {object_name}")

    data = load_artifact_json(ref)

    print("\n" + "=" * 88)
    print("SEARCH")
    print("=" * 88)
    print(f"element_id={args.element_id!r}")
    print(f"clause_uid={args.clause_uid!r}")

    matches = find_matches(
        data,
        element_id=args.element_id,
        clause_uid=args.clause_uid,
    )

    print(f"\nFound matches: {len(matches)}")

    for idx, m in enumerate(matches, 1):
        print("\n" + "-" * 88)
        print(f"Match #{idx}")
        print("-" * 88)
        print(f"path:        {m['path']}")
        print(f"element_id:  {m['element_id']}")
        print(f"clause_uid:  {m['clause_uid']}")
        print(f"page:        {m['page']}")
        print(f"segment_id:  {m['segment_id']}")
        print(f"segment_type:{m['segment_type']}")
        print(f"keys:        {m['keys']}")
        if m["text_preview"]:
            print("\ntext_preview:")
            print(m["text_preview"])
        else:
            print("\ntext_preview: (none)")

    if not matches:
        print("\n[WARN] No direct node match found.")
        print("Possible reasons:")
        print("- element_id / clause_uid live under another key structure")
        print("- artifact shape is different than expected")
        print("- sanitized artifact dropped some ids")
        print("- нужно попробовать --use raw")


if __name__ == "__main__":
    main()


