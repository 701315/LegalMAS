"""
Unit tests for Stable Localization Key Generation System (Sprint 4.2).
"""

from __future__ import annotations

import pytest
from src.services.instruction_localization_keys import LocalizationKeyBuilder


class TestLocalizationKeyBuilder:
    """Verify key generation formats, casing, and validator accuracy."""

    def test_check_name_key_format(self) -> None:
        key = LocalizationKeyBuilder.check_name_key("LIABILITY_LIMIT")
        assert key == "playbook.check.liability_limit.name"
        assert LocalizationKeyBuilder.is_valid_key(key) is True

    def test_check_description_key_format(self) -> None:
        key = LocalizationKeyBuilder.check_description_key(" Governing_Law ")
        assert key == "playbook.check.governing_law.description"
        assert LocalizationKeyBuilder.is_valid_key(key) is True

    def test_column_label_key_format(self) -> None:
        key = LocalizationKeyBuilder.column_label_key("termination_notice_period")
        assert key == "dd_grid.column.termination_notice_period.label"
        assert LocalizationKeyBuilder.is_valid_key(key) is True

    def test_column_fallback_display_key_format(self) -> None:
        key = LocalizationKeyBuilder.column_fallback_key("payment_terms")
        assert key == "dd_grid.column.payment_terms.fallback"
        assert LocalizationKeyBuilder.is_valid_key(key) is True

    def test_enum_label_key_format(self) -> None:
        key = LocalizationKeyBuilder.enum_label_key("Contract_Status", " NOT_DEFINED ")
        assert key == "dd_grid.field.contract_status.enum.not_defined"
        assert LocalizationKeyBuilder.is_valid_key(key) is True

    @pytest.mark.parametrize(
        "invalid_key",
        [
            "playbook.check.name",  # missing check_id
            "dd_grid.column.label.header",  # wrong structure
            "dd_grid.field.status.enum",  # missing enum value
            "some.random.key",  # completely invalid
            "playbook.check.test.name.extra",  # extra tail
            "dd_grid.column.col.label_en",  # locale leak violation
        ],
    )
    def test_invalid_keys_fail_validation(self, invalid_key: str) -> None:
        assert LocalizationKeyBuilder.is_valid_key(invalid_key) is False


        