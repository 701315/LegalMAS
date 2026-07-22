from __future__ import annotations

import hashlib
from datetime import datetime

from fastapi import Request, status

from api.errors import api_error


def build_etag(updated_at: datetime | None) -> str:
    if updated_at is None:
        return '"0"'
    raw = updated_at.isoformat(timespec="microseconds")
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f'"{digest}"'


def set_response_etag(response, updated_at: datetime | None) -> str:
    etag = build_etag(updated_at)
    response.headers["ETag"] = etag
    return etag


def require_if_match(request: Request) -> str:
    value = request.headers.get("if-match")
    if not value:
        raise api_error(
            status.HTTP_428_PRECONDITION_REQUIRED,
            "PRECONDITION_REQUIRED",
            "If-Match header is required for this operation.",
        )
    return value


def ensure_if_match(current_updated_at: datetime | None, if_match_value: str) -> str:
    current_etag = build_etag(current_updated_at)
    if if_match_value != current_etag:
        raise api_error(
            status.HTTP_412_PRECONDITION_FAILED,
            "PRECONDITION_FAILED",
            "Resource has changed since it was last fetched.",
            current_etag=current_etag,
        )
    return current_etag


