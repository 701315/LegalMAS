from __future__ import annotations

from fastapi import HTTPException


def api_error(status_code: int, code: str, message: str, **extra) -> HTTPException:
    detail = {
        "code": code,
        "message": message,
        **extra,
    }
    return HTTPException(status_code=status_code, detail=detail)


