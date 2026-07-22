"""
Unit tests for playbook line item validation service.

Проверяет доменный слой, который валидирует instruction_code
в составе PlaybookLineItem против canonical global checks catalog.
"""

from types import SimpleNamespace

import pytest

from services.playbooks.line_items import (
    PlaybookLineItemValidationError,
    extract_unique_instruction_codes_from_items,
    validate_instruction_codes,
    validate_line_item_payloads,
)


def test_extract_unique_instruction_codes_preserves_order_and_deduplicates():
    items = [
        SimpleNamespace(instruction_code="encumbrances_warranty"),
        SimpleNamespace(instruction_code="change_of_control"),
        SimpleNamespace(instruction_code="encumbrances_warranty"),
        SimpleNamespace(instruction_code="  "),
        SimpleNamespace(instruction_code=None),
    ]

    result = extract_unique_instruction_codes_from_items(items)

    assert result == ["encumbrances_warranty", "change_of_control"]


def test_validate_instruction_codes_accepts_known_codes(mocker):
    mocker.patch(
        "services.playbooks.line_items.get_unknown_global_check_codes",
        return_value=[],
    )

    result = validate_instruction_codes(
        ["encumbrances_warranty", "change_of_control", "encumbrances_warranty"]
    )

    assert result == ["encumbrances_warranty", "change_of_control"]


def test_validate_instruction_codes_rejects_unknown_codes(mocker):
    mocker.patch(
        "services.playbooks.line_items.get_unknown_global_check_codes",
        return_value=["unknown_check"],
    )

    with pytest.raises(PlaybookLineItemValidationError) as exc:
        validate_instruction_codes(["unknown_check"])

    assert exc.value.unknown_codes == ["unknown_check"]


def test_validate_line_item_payloads_reads_instruction_code_attribute(mocker):
    mocker.patch(
        "services.playbooks.line_items.get_unknown_global_check_codes",
        return_value=[],
    )

    payloads = [
        SimpleNamespace(instruction_code="encumbrances_warranty"),
        SimpleNamespace(instruction_code="change_of_control"),
    ]

    result = validate_line_item_payloads(payloads)

    assert result == ["encumbrances_warranty", "change_of_control"]


    