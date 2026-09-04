# src/core/i18n/ui_locales.py

import json
from pathlib import Path
from typing import TypedDict, Set, Optional


class LocaleDetail(TypedDict):
    code: str
    native_name: str
    english_name: str
    status: str
    is_default: bool
    direction: str


SHARED_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "shared" / "config" / "ui_locales.json"
)

_cached_config: dict | None = None


def _load_config() -> dict:
    global _cached_config
    if _cached_config is None:
        try:
            with open(SHARED_CONFIG_PATH, "r", encoding="utf-8") as f:
                _cached_config = json.load(f)
        except Exception:
            _cached_config = {
                "default_locale": "en",
                "locales": [
                    {
                        "code": "en",
                        "native_name": "English",
                        "english_name": "English",
                        "status": "supported",
                        "is_default": True,
                        "direction": "ltr",
                    },
                    {
                        "code": "ru",
                        "native_name": "Русский",
                        "english_name": "Russian",
                        "status": "supported",
                        "is_default": False,
                        "direction": "ltr",
                    },
                ],
            }
    return _cached_config


def get_default_ui_locale() -> str:
    config = _load_config()
    return config.get("default_locale", "en")


def get_supported_ui_locales() -> Set[str]:
    config = _load_config()
    return {
        loc["code"]
        for loc in config.get("locales", [])
        if loc.get("status") in ("supported", "beta")
    }


def is_valid_ui_locale(locale: Optional[str]) -> boolean: # type: ignore
    if not locale:
        return True
    return locale in get_supported_ui_locales()


    