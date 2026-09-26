"""Тесты _derive_review_status: 3 clause-статуса для field_extraction."""
import pytest

from engine.checks.result_semantics import (
    _count_meaningful_fact_fields,
    _derive_review_status,
)
from engine.playbook.models import (
    CheckDefinition, ExtractionConfig, ExtractionFieldConfig,
)


def _field(name: str, **kwargs) -> ExtractionFieldConfig:
    base = {"name": name, "type": "string", "presentation": "fact", "label": name}
    base.update(kwargs)
    return ExtractionFieldConfig(**base)


def _check(check_id: str, fields, ui_mode: str = "field_extraction"):
    return CheckDefinition(
        id=check_id, name="test", ui_mode=ui_mode,
        extraction=ExtractionConfig(enabled=True, fields=fields),
    )


class TestCountMeaningfulFactFields:
    def test_all_meaningful(self):
        check = _check("c", [
            _field("a", fallback_texts=["Не установлено"]),
            _field("b", fallback_texts=["Не установлено"]),
        ])
        sd = {"a": {"value": "X"}, "b": {"value": "Y"}}
        assert _count_meaningful_fact_fields(check, sd) == (2, 2)

    def test_partial(self):
        check = _check("c", [
            _field("a", fallback_texts=["Не установлено"]),
            _field("b", fallback_texts=["Не установлено"]),
        ])
        sd = {"a": {"value": "X"}, "b": {"value": "Не установлено"}}
        assert _count_meaningful_fact_fields(check, sd) == (1, 2)

    def test_none_meaningful(self):
        check = _check("c", [
            _field("a", fallback_texts=["Не установлено"]),
        ])
        sd = {"a": {"value": "Не установлено"}}
        assert _count_meaningful_fact_fields(check, sd) == (0, 1)

    def test_no_extraction(self):
        """Check без extraction config → (0, 0)."""
        check = CheckDefinition(id="c", name="test")
        assert _count_meaningful_fact_fields(check, {}) == (0, 0)

    def test_none_check(self):
        """check=None → (0, 0)."""
        assert _count_meaningful_fact_fields(None, {}) == (0, 0)


class TestDeriveReviewStatus:
    def _call(self, check, sd, result="pass", ui_mode="field_extraction"):
        return _derive_review_status(
            result=result,
            exec_result={},
            execution_status="SUCCESS",
            ui_mode=ui_mode,
            check=check,
            structured_data=sd,
        )

    def test_clause_defined_all_meaningful(self):
        check = _check("c", [
            _field("a", fallback_texts=["Не установлено"]),
            _field("b", fallback_texts=["Не установлено"]),
        ])
        sd = {"a": {"value": "X"}, "b": {"value": "Y"}}
        assert self._call(check, sd) == "clause_defined"

    def test_clause_partially_defined(self):
        check = _check("c", [
            _field("a", fallback_texts=["Не установлено"]),
            _field("b", fallback_texts=["Не установлено"]),
        ])
        sd = {"a": {"value": "X"}, "b": {"value": "Не установлено"}}
        assert self._call(check, sd) == "clause_partially_defined"

    def test_clause_missing_on_result(self):
        check = _check("c", [
            _field("a", fallback_texts=["Не установлено"]),
        ])
        sd = {"a": {"value": "Не установлено"}}
        assert self._call(check, sd, result="missing_required_clause") == "clause_missing"

    def test_risk_detection_unchanged(self):
        check = _check("c", [_field("a")], ui_mode="risk_detection")
        sd = {"a": {"value": "X"}}
        assert self._call(check, sd, ui_mode="risk_detection") == "no_issue_detected"

    def test_legacy_field_extraction_no_fact_fields(self):
        """Check без fact-полей → старое поведение no_issue_detected."""
        check = _check("c", [_field("x", presentation="signal")])
        sd = {"x": {"value": "present"}}
        assert self._call(check, sd) == "no_issue_detected"
        