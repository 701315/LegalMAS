"""Contract tests for ExtractionFieldConfig.risk_weight (B5.3).

Проверяет fail-fast валидацию:
- risk_weight допустим только для presentation=signal;
- risk_weight требует непустой allowed_values;
- enum RiskWeight принимает ровно 4 значения.
"""
from __future__ import annotations

import pytest

from src.engine.playbook.models import (
    ExtractionFieldConfig,
    RiskWeight,
)


class TestRiskWeightContract:
    def test_risk_weight_accepts_all_enum_values(self) -> None:
        for weight in ("high", "medium", "low", "info"):
            f = ExtractionFieldConfig(
                name="x",
                presentation="signal",
                allowed_values=["a", "b"],
                risk_weight=weight,
            )
            assert f.risk_weight == RiskWeight(weight)

    def test_risk_weight_none_by_default(self) -> None:
        f = ExtractionFieldConfig(
            name="x",
            presentation="signal",
            allowed_values=["a"],
        )
        assert f.risk_weight is None

    def test_risk_weight_rejected_on_fact_field(self) -> None:
        with pytest.raises(ValueError, match="risk_weight can only be set on"):
            ExtractionFieldConfig(
                name="x",
                presentation="fact",
                allowed_values=["a"],
                risk_weight="high",
            )

    def test_risk_weight_rejected_on_diagnostic_field(self) -> None:
        with pytest.raises(ValueError, match="risk_weight can only be set on"):
            ExtractionFieldConfig(
                name="x",
                presentation="diagnostic",
                risk_weight="high",
            )

    def test_risk_weight_requires_allowed_values(self) -> None:
        with pytest.raises(ValueError, match="risk_weight requires allowed_values"):
            ExtractionFieldConfig(
                name="x",
                presentation="signal",
                risk_weight="high",
            )

    def test_risk_weight_rejects_unknown_value(self) -> None:
        with pytest.raises(Exception):  # pydantic ValidationError
            ExtractionFieldConfig(
                name="x",
                presentation="signal",
                allowed_values=["a"],
                risk_weight="critical",  # not in enum
            )
