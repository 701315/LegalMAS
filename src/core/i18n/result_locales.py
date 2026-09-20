# src/core/i18n/result_locales.py

# src/core/i18n/result_locales.py

"""
Result output locale registry.

Reads shared/config/result_locales.json and exposes validation helpers
for the result-presentation translation pipeline.

IMPORTANT (Invariant #5): This registry is for OUTPUT locales of
translated check-result presentations. It is a SEPARATE axis from
UI locales (src/core/i18n/ui_locales.py). Never conflate the two.
"""

import json
from pathlib import Path
from typing import TypedDict, Set, Optional


class TranslationConfig(TypedDict, total=False):
    supported_source_locales: list[str]
    prompt_version: str
    quality_gate: str


class ResultLocaleDetail(TypedDict):
    code: str
    native_name: str
    english_name: str
    status: str
    is_default: bool
    direction: str
    translation: TranslationConfig


SHARED_CONFIG_PATH = (
    Path(__file__).resolve().parents[3]
    / "shared"
    / "config"
    / "result_locales.json"
)

_cached_config: dict | None = None


def _load_config() -> dict:
    """Load and cache result_locales.json with a safe fallback."""
    global _cached_config
    if _cached_config is None:
        try:
            with open(SHARED_CONFIG_PATH, "r", encoding="utf-8") as f:
                _cached_config = json.load(f)
        except Exception:
            _cached_config = {
                "schema_version": 1,
                "default_output_locale": "en",
                "default_output_policy": "match_analysis_language",
                "locales": [
                    {
                        "code": "en",
                        "native_name": "English",
                        "english_name": "English",
                        "status": "supported",
                        "is_default": True,
                        "direction": "ltr",
                        "translation": {
                            "supported_source_locales": ["ru", "en"],
                            "prompt_version": "v1",
                            "quality_gate": "basic",
                        },
                    },
                    {
                        "code": "ru",
                        "native_name": "Русский",
                        "english_name": "Russian",
                        "status": "supported",
                        "is_default": False,
                        "direction": "ltr",
                        "translation": {
                            "supported_source_locales": ["en", "ru"],
                            "prompt_version": "v1",
                            "quality_gate": "basic",
                        },
                    },
                ],
            }
    return _cached_config


def get_default_output_locale() -> str:
    """Return the default output locale for result presentations."""
    config = _load_config()
    return config.get("default_output_locale", "en")


def get_default_output_policy() -> str:
    """Return the default output policy identifier.

    Possible values (expanded in S2.7):
      - 'match_analysis_language'  (default)
      - 'match_ui_locale'
      - 'fixed'
    """
    config = _load_config()
    return config.get("default_output_policy", "match_analysis_language")


def get_supported_result_locales() -> Set[str]:
    """Return codes of all enabled result output locales."""
    config = _load_config()
    return {
        loc["code"]
        for loc in config.get("locales", [])
        if loc.get("status") in ("supported", "beta")
    }


def is_valid_result_locale(locale: Optional[str]) -> bool:
    """Check whether *locale* is a supported result output locale.

    Returns True for None/empty (caller decides fallback).
    """
    if not locale:
        return True
    normalized = locale.strip().lower()
    return normalized in get_supported_result_locales()


def get_supported_source_locales(target_locale: str) -> Set[str]:
    """Return source locales from which *target_locale* translation is supported.

    Returns empty set if target_locale is unknown.
    """
    config = _load_config()
    normalized = target_locale.strip().lower()
    for loc in config.get("locales", []):
        if loc.get("code") == normalized:
            return set(
                loc.get("translation", {}).get("supported_source_locales", [])
            )
    return set()


def is_translation_pair_supported(
    source_locale: str, target_locale: str
) -> bool:
    """Check whether the source→target translation pair is configured."""
    if not source_locale or not target_locale:
        return False
    return source_locale.strip().lower() in get_supported_source_locales(
        target_locale
    )


def get_all_result_locale_details() -> list[ResultLocaleDetail]:
    """Return full locale metadata for all configured result locales."""
    config = _load_config()
    return [
        ResultLocaleDetail(
            code=loc["code"],
            native_name=loc["native_name"],
            english_name=loc["english_name"],
            status=loc["status"],
            is_default=loc["is_default"],
            direction=loc["direction"],
            translation=loc.get("translation", {}),
        )
        for loc in config.get("locales", [])
    ]


    