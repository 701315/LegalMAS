"""Unit tests for _compute_cell_risk (B5.3)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.services.dd_grid_v1_builder import _compute_cell_risk


@dataclass
class _FieldStub:
    name: str
    presentation: str = "signal"
    risk_weight: str | None = None
    allowed_values: list[Any] = field(default_factory=list)


@dataclass
class _ExtractionStub:
    fields: list[_FieldStub]


@dataclass
class _CheckStub:
    extraction: _ExtractionStub | None


def _payload(value: Any, found: bool = True) -> dict[str, Any]:
    return {"value": value, "found": found}


class TestComputeCellRisk:
    def test_empty_returns_none(self) -> None:
        assert _compute_cell_risk(_CheckStub(extraction=None), {}) == (
            None, None, None, None,
        )
        assert _compute_cell_risk(
            _CheckStub(extraction=_ExtractionStub(fields=[])), {}
        ) == (None, None, None, None)

    def test_no_risk_weight_fields(self) -> None:
        check = _CheckStub(
            extraction=_ExtractionStub(fields=[_FieldStub(name="a")])
        )
        assert _compute_cell_risk(check, {"a": _payload("x")}) == (
            None, None, None, None,
        )

    def test_single_high(self) -> None:
        check = _CheckStub(
            extraction=_ExtractionStub(
                fields=[_FieldStub(name="regime", risk_weight="high")]
            )
        )
        result = _compute_cell_risk(
            check, {"regime": _payload("consent_required")}
        )
        assert result[0] == "high"
        assert result[1] == "regime"
        assert result[2] == "consent_required"

    def test_absence_values_skipped(self) -> None:
        check = _CheckStub(
            extraction=_ExtractionStub(
                fields=[_FieldStub(name="regime", risk_weight="high")]
            )
        )
        for absence in (
            "no", "none", "missing", "not_specified", "unclear", "n/a",
        ):
            assert _compute_cell_risk(
                check, {"regime": _payload(absence)}
            ) == (None, None, None, None), absence

    def test_found_false_skipped(self) -> None:
        check = _CheckStub(
            extraction=_ExtractionStub(
                fields=[_FieldStub(name="regime", risk_weight="high")]
            )
        )
        assert _compute_cell_risk(
            check, {"regime": _payload("consent_required", found=False)}
        ) == (None, None, None, None)

    def test_non_signal_field_skipped(self) -> None:
        check = _CheckStub(
            extraction=_ExtractionStub(
                fields=[
                    _FieldStub(
                        name="display",
                        presentation="fact",
                        risk_weight="high",
                    )
                ]
            )
        )
        assert _compute_cell_risk(
            check, {"display": _payload("x")}
        ) == (None, None, None, None)

    def test_tie_break_alphabetical(self) -> None:
        check = _CheckStub(
            extraction=_ExtractionStub(
                fields=[
                    _FieldStub(name="zeta", risk_weight="high"),
                    _FieldStub(name="alpha", risk_weight="high"),
                ]
            )
        )
        result = _compute_cell_risk(
            check,
            {"alpha": _payload("x"), "zeta": _payload("y")},
        )
        assert result[1] == "alpha"

    def test_max_wins(self) -> None:
        check = _CheckStub(
            extraction=_ExtractionStub(
                fields=[
                    _FieldStub(name="a", risk_weight="low"),
                    _FieldStub(name="b", risk_weight="medium"),
                    _FieldStub(name="c", risk_weight="high"),
                ]
            )
        )
        result = _compute_cell_risk(
            check,
            {"a": _payload("x"), "b": _payload("y"), "c": _payload("z")},
        )
        assert result[0] == "high"
        assert result[1] == "c"
