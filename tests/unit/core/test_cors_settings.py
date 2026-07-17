"""
Tests for CORS settings parsing and validation.

Покрывает:
- CSV parsing для origins/methods/headers
- upper-case normalization для methods
- fail-fast validation при wildcard origin + credentials=true
- защиту от пустых CORS списков
"""

from __future__ import annotations

import pytest

from core.config import Settings


def test_cors_csv_values_are_parsed_correctly() -> None:
    cfg = Settings(
        CORS_ALLOW_ORIGINS="http://localhost:5173, https://app.example.com",
        CORS_ALLOW_METHODS="get,post,options",
        CORS_ALLOW_HEADERS="Authorization, Content-Type",
        CORS_ALLOW_CREDENTIALS=True,
    )

    assert cfg.cors_allow_origins_list == [
        "http://localhost:5173",
        "https://app.example.com",
    ]
    assert cfg.cors_allow_methods_list == ["GET", "POST", "OPTIONS"]
    assert cfg.cors_allow_headers_list == ["Authorization", "Content-Type"]


def test_cors_wildcard_origin_with_credentials_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match=r"CORS_ALLOW_ORIGINS cannot contain '\*' when CORS_ALLOW_CREDENTIALS=true",
    ):
        Settings(
            CORS_ALLOW_ORIGINS="*",
            CORS_ALLOW_CREDENTIALS=True,
            CORS_ALLOW_METHODS="*",
            CORS_ALLOW_HEADERS="*",
        )


def test_cors_wildcard_origin_without_credentials_is_allowed() -> None:
    cfg = Settings(
        CORS_ALLOW_ORIGINS="*",
        CORS_ALLOW_CREDENTIALS=False,
        CORS_ALLOW_METHODS="*",
        CORS_ALLOW_HEADERS="*",
    )

    assert cfg.cors_allow_origins_list == ["*"]
    assert cfg.CORS_ALLOW_CREDENTIALS is False


def test_empty_cors_origins_are_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="CORS_ALLOW_ORIGINS must contain at least one origin",
    ):
        Settings(
            CORS_ALLOW_ORIGINS="",
            CORS_ALLOW_METHODS="*",
            CORS_ALLOW_HEADERS="*",
        )


def test_empty_cors_methods_are_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="CORS_ALLOW_METHODS must contain at least one method or '\\*'",
    ):
        Settings(
            CORS_ALLOW_ORIGINS="http://localhost:5173",
            CORS_ALLOW_METHODS="",
            CORS_ALLOW_HEADERS="*",
        )


def test_empty_cors_headers_are_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="CORS_ALLOW_HEADERS must contain at least one header or '\\*'",
    ):
        Settings(
            CORS_ALLOW_ORIGINS="http://localhost:5173",
            CORS_ALLOW_METHODS="*",
            CORS_ALLOW_HEADERS="",
        )


        