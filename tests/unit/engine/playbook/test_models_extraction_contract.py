"""
Tests for ExtractionFieldConfig label/presentation contract
and CheckDefinition field_extraction validation.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from engine.playbook.models import (
    CheckDefinition,
    DetectorType,
    ExtractionConfig,
    ExtractionFieldConfig,
    ExtractionFieldType,
)


def _field(name, *, label=None, presentation="fact", description="") -> ExtractionFieldConfig:
    return ExtractionFieldConfig(
        name=name,
        type=ExtractionFieldType.STRING,
        label=label,
        presentation=presentation,
        description=description,
    )


def test_field_stores_label_and_presentation():
    f = _field("seller_details", label="Продавец", presentation="fact")
    assert f.label == "Продавец"
    assert f.presentation == "fact"


def test_signal_field_needs_no_label():
    f = _field("seller_details_status", presentation="signal")
    assert f.label is None
    assert f.presentation == "signal"


def test_diagnostic_field_needs_no_label():
    f = _field("reason", presentation="diagnostic")
    assert f.presentation == "diagnostic"


def test_summary_field_needs_no_label():
    f = _field("covenants_display", presentation="summary")
    assert f.presentation == "summary"


def test_check_with_summary_passes_validation():
    check = CheckDefinition(
        id="c1", name="C1", ui_mode="field_extraction",
        detector_type=DetectorType.RULES,
        extraction=ExtractionConfig(enabled=True, fields=[
            _field("covenants_display", presentation="summary"),
            _field("has_cross_default", presentation="signal"),
            _field("reason", presentation="diagnostic"),
        ]),
    )
    assert check.id == "c1"


def test_check_with_labeled_facts_passes_validation():
    check = CheckDefinition(
        id="c2", name="C2", ui_mode="field_extraction",
        detector_type=DetectorType.RULES,
        extraction=ExtractionConfig(enabled=True, fields=[
            _field("seller_details", label="Продавец", presentation="fact"),
            _field("seller_details_status", presentation="signal"),
            _field("reason", presentation="diagnostic"),
        ]),
    )
    assert check.id == "c2"


def test_check_without_summary_and_without_labels_fails():
    with pytest.raises(ValidationError) as exc_info:
        CheckDefinition(
            id="c3", name="C3", ui_mode="field_extraction",
            detector_type=DetectorType.RULES,
            extraction=ExtractionConfig(enabled=True, fields=[
                _field("seller_details", description="Prompt instruction here"),
                _field("seller_details_status", presentation="signal"),
            ]),
        )
    assert "missing explicit `label`" in str(exc_info.value)
    assert "seller_details" in str(exc_info.value)


def test_risk_detection_check_skips_validation():
    check = CheckDefinition(
        id="c4", name="C4", ui_mode="risk_detection",
        detector_type=DetectorType.RULES,
        extraction=ExtractionConfig(enabled=True, fields=[
            _field("risk_clause", description="No label needed"),
        ]),
    )
    assert check.id == "c4"


def test_clause_presence_check_skips_validation():
    check = CheckDefinition(
        id="c5", name="C5", ui_mode="clause_presence",
        detector_type=DetectorType.RULES,
        extraction=ExtractionConfig(enabled=True, fields=[
            _field("clause_text", description="No label needed"),
        ]),
    )
    assert check.id == "c5"


    