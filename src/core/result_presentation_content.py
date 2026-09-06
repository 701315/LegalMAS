# src/core/result_presentation_content.py

"""
Canonical source payload and deterministic fingerprinting for localized
CheckResult presentations.

The functions in this module operate only on user-facing canonical fields.
They never translate content and never mutate CheckResult records.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any


PRESENTATION_CONTENT_VERSION_V1 = "v1"


def _normalize_text(value: str | None) -> str | None:
    """Normalize text for deterministic content hashing."""
    if value is None:
        return None

    return unicodedata.normalize("NFC", value)


def build_presentation_source_payload(
    *,
    check_name: str,
    display_text: str | None,
    review_message: str | None,
    dd_request_text: str | None = None,
    content_version: str = PRESENTATION_CONTENT_VERSION_V1,
) -> dict[str, Any]:
    """
    Build the immutable source payload for one localized presentation.

    This intentionally excludes evidence, page, clause, bbox, structured data,
    execution status, severity, and QC state. Those fields remain canonical
    CheckResult data and are not translated by this presentation layer.
    """
    normalized_version = content_version.strip()

    if not normalized_version:
        raise ValueError("content_version must be a non-empty string")

    normalized_check_name = _normalize_text(check_name)

    if normalized_check_name is None or not normalized_check_name.strip():
        raise ValueError("check_name must be a non-empty string")

    return {
        "content_version": normalized_version,
        "check_name": normalized_check_name,
        "display_text": _normalize_text(display_text),
        "review_message": _normalize_text(review_message),
        "dd_request_text": _normalize_text(dd_request_text),
    }


def build_presentation_source_hash(
    *,
    check_name: str,
    display_text: str | None,
    review_message: str | None,
    dd_request_text: str | None = None,
    content_version: str = PRESENTATION_CONTENT_VERSION_V1,
) -> str:
    """
    Return the SHA-256 fingerprint of canonical presentation source content.

    Equal normalized source payloads always produce the same hash. Any change
    to source text or content version produces another hash and therefore
    makes an older locale-specific presentation distinguishable from a new one.
    """
    payload = build_presentation_source_payload(
        check_name=check_name,
        display_text=display_text,
        review_message=review_message,
        dd_request_text=dd_request_text,
        content_version=content_version,
    )

    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
