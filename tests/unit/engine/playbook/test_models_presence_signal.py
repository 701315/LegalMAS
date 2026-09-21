"""Contract tests for PresenceSignalConfig and its validator on ExtractionConfig."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from engine.playbook.models import (
    CheckDefinition,
    DetectorType,
    ExtractionConfig,
    ExtractionFieldConfig,
    ExtractionFieldType,
    PresenceSignalConfig,
)


def _status_field():
    return ExtractionFieldConfig(
        name="coc_status",
        type=ExtractionFieldType.STRING,
        presentation="signal",
        allowed_values=["present", "missing", "unclear"],
    )


def _fact_field():
    return ExtractionFieldConfig(
        name="coc_display",
        type=ExtractionFieldType.STRING,
        presentation="summary",
    )


def _valid_signal() -> PresenceSignalConfig:
    return PresenceSignalConfig(
        field="coc_status",
        present_values=["present"],
        missing_values=["missing"],
        unclear_values=["unclear"],
    )


# --- classify() unit ---

def test_classify_present():
    assert _valid_signal().classify("present") == "present"
    assert _valid_signal().classify("PRESENT") == "present"
    assert _valid_signal().classify(" present ") == "present"


def test_classify_missing():
    assert _valid_signal().classify("missing") == "missing"


def test_classify_unclear():
    assert _valid_signal().classify("unclear") == "unclear"


def test_classify_undeclared():
    assert _valid_signal().classify("unknown_value") == "undeclared"


def test_classify_none_returns_unclear():
    assert _valid_signal().classify(None) == "unclear"


# --- ExtractionConfig validator ---

def test_valid_presence_signal_accepted():
    cfg = ExtractionConfig(
        enabled=True,
        fields=[_status_field(), _fact_field()],
        presence_signal=_valid_signal(),
    )
    assert cfg.presence_signal is not None


def test_presence_signal_without_enabled_rejected():
    with pytest.raises(ValidationError, match="extraction.enabled=false"):
        ExtractionConfig(
            enabled=False,
            fields=[_status_field()],
            presence_signal=_valid_signal(),
        )


def test_presence_signal_field_not_declared_rejected():
    with pytest.raises(ValidationError, match="not declared in extraction.fields"):
        ExtractionConfig(
            enabled=True,
            fields=[_fact_field()],
            presence_signal=_valid_signal(),
        )


def test_presence_signal_overlapping_groups_rejected():
    with pytest.raises(ValidationError, match="groups overlap"):
        ExtractionConfig(
            enabled=True,
            fields=[_status_field()],
            presence_signal=PresenceSignalConfig(
                field="coc_status",
                present_values=["present", "missing"],
                missing_values=["missing"],
                unclear_values=["unclear"],
            ),
        )


def test_presence_signal_missing_coverage_rejected():
    with pytest.raises(ValidationError, match="must cover allowed_values exactly"):
        ExtractionConfig(
            enabled=True,
            fields=[_status_field()],
            presence_signal=PresenceSignalConfig(
                field="coc_status",
                present_values=["present"],
                missing_values=["missing"],
                unclear_values=[],
            ),
        )


def test_presence_signal_extra_value_rejected():
    with pytest.raises(ValidationError, match="must cover allowed_values exactly"):
        ExtractionConfig(
            enabled=True,
            fields=[_status_field()],
            presence_signal=PresenceSignalConfig(
                field="coc_status",
                present_values=["present"],
                missing_values=["missing", "absent"],
                unclear_values=["unclear"],
            ),
        )


def test_presence_signal_requires_allowed_values_on_field():
    f = ExtractionFieldConfig(
        name="coc_status",
        type=ExtractionFieldType.STRING,
        presentation="signal",
    )
    with pytest.raises(ValidationError, match="must declare allowed_values"):
        ExtractionConfig(
            enabled=True,
            fields=[f],
            presence_signal=_valid_signal(),
        )


# --- CheckDefinition validator ---

def test_check_definition_rejects_presence_signal_with_wrong_ui_mode():
    with pytest.raises(ValidationError, match="requires"):
        CheckDefinition(
            id="c1",
            name="C1",
            ui_mode="risk_detection",
            detector_type=DetectorType.HYBRID,
            extraction=ExtractionConfig(
                enabled=True,
                fields=[_status_field()],
                presence_signal=_valid_signal(),
            ),
        )


def test_check_definition_accepts_presence_signal_with_field_extraction():
    check = CheckDefinition(
        id="c1",
        name="C1",
        ui_mode="field_extraction",
        detector_type=DetectorType.HYBRID,
        extraction=ExtractionConfig(
            enabled=True,
            fields=[_status_field()],
            presence_signal=_valid_signal(),
        ),
    )
    assert check.extraction.presence_signal is not None


def test_check_definition_accepts_presence_signal_with_ui_mode_none():
    check = CheckDefinition(
        id="c1",
        name="C1",
        ui_mode=None,
        detector_type=DetectorType.HYBRID,
        extraction=ExtractionConfig(
            enabled=True,
            fields=[_status_field()],
            presence_signal=_valid_signal(),
        ),
    )
    assert check.extraction.presence_signal is not None
