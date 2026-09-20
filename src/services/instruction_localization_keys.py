# src/services/instruction_localization_keys.py

"""
Stable Localization Key Generation System (Sprint 4.2).

Provides deterministic dot-separated string keys for static and dynamic
entities requiring localization within the DD Grid and Playbook.

Key namespaces:
- playbook.check.{id}.name          — check display title
- playbook.check.{id}.description   — check tooltip
- dd_grid.column.{id}.label         — column header
- dd_grid.column.{id}.fallback      — empty cell placeholder
- dd_grid.field.{name}.enum.{val}   — enum value label
- dd_grid.system.{name}             — system UI labels (ungrouped, error, etc.)
"""

from __future__ import annotations

import re

_KEY_PATTERN = re.compile(
    r"^(?:"
    r"(?:playbook\.check\.[a-zA-Z0-9_-]+\.(?:name|description))|"
    r"(?:dd_grid\.column\.[a-zA-Z0-9_-]+\.(?:label|fallback))|"
    r"(?:dd_grid\.field\.[a-zA-Z0-9_-]+\.enum\.[a-zA-Z0-9_-]+)|"
    r"(?:dd_grid\.system\.[a-zA-Z0-9_-]+)"
    r")$"
)


class LocalizationKeyBuilder:
    """Deterministic factory for presentation localization keys."""

    # ── Playbook checks ─────────────────────────────────────────

    @staticmethod
    def check_name_key(check_id: str) -> str:
        return f"playbook.check.{check_id.strip().lower()}.name"

    @staticmethod
    def check_description_key(check_id: str) -> str:
        return f"playbook.check.{check_id.strip().lower()}.description"

    # ── DD Grid columns ─────────────────────────────────────────

    @staticmethod
    def column_label_key(column_id: str) -> str:
        return f"dd_grid.column.{column_id.strip().lower()}.label"

    @staticmethod
    def column_fallback_key(column_id: str) -> str:
        return f"dd_grid.column.{column_id.strip().lower()}.fallback"

    # ── Enum values ─────────────────────────────────────────────

    @staticmethod
    def enum_label_key(field_name: str, enum_value: str) -> str:
        clean_field = field_name.strip().lower()
        clean_val = enum_value.strip().lower()
        return f"dd_grid.field.{clean_field}.enum.{clean_val}"

    # ── System labels ───────────────────────────────────────────

    @staticmethod
    def system_key(name: str) -> str:
        """
        Key for built-in system labels.
        Examples: 'ungrouped', 'display_error', 'location_fallback'.
        """
        return f"dd_grid.system.{name.strip().lower()}"

    # ── Validation ──────────────────────────────────────────────

    @classmethod
    def is_valid_key(cls, key: str) -> bool:
        return bool(_KEY_PATTERN.match(key))

        
