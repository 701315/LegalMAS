# src/core/i18n/export_translator.py

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from core.i18n.ui_locales import get_default_ui_locale, is_valid_ui_locale

_SHARED_LOCALES_DIR = Path(__file__).resolve().parents[3] / "shared" / "locales"

_cached_translations: Dict[str, Dict[str, Any]] = {}


def _load_locale_dict(locale: str) -> Dict[str, Any]:
    if locale in _cached_translations:
        return _cached_translations[locale]

    file_path = _SHARED_LOCALES_DIR / locale / "export.json"
    if not file_path.is_file():
        _cached_translations[locale] = {}
        return {}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            _cached_translations[locale] = data
            return data
    except Exception:
        _cached_translations[locale] = {}
        return {}


def _resolve_nested_key(data: Dict[str, Any], key: str) -> str | None:
    parts = key.split(".")
    curr: Any = data
    for part in parts:
        if isinstance(curr, dict) and part in curr:
            curr = curr[part]
        else:
            return None
    if isinstance(curr, str):
        return curr
    return None


def normalize_export_locale(locale: str | None) -> str:
    if not locale:
        return get_default_ui_locale()

    normalized = locale.strip().lower().replace("_", "-").split("-")[0]
    if is_valid_ui_locale(normalized):
        return normalized
    return get_default_ui_locale()


def t_export(key: str, locale: str = "en", **kwargs: Any) -> str:
    """
    Translates export keys using shared/locales/{locale}/export.json.

    Fallback strategy:
      1. Requested target locale (e.g., 'ru', 'tr', 'es')
      2. Canonical default locale ('en')
      3. Raw key itself
    """
    target_locale = normalize_export_locale(locale)
    default_locale = get_default_ui_locale()

    # 1. Try target locale
    target_dict = _load_locale_dict(target_locale)
    template = _resolve_nested_key(target_dict, key)

    # 2. Fallback to default canonical locale (en) if missing
    if template is None and target_locale != default_locale:
        default_dict = _load_locale_dict(default_locale)
        template = _resolve_nested_key(default_dict, key)

    # 3. Fallback to raw key
    if template is None:
        template = key

    if kwargs:
        try:
            return template.format(**kwargs)
        except Exception:
            return template

    return template


    