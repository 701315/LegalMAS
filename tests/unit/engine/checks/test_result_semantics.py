# tests/unit/engine/checks/test_result_semantics.py

"""
Unit tests for canonical result semantics builder.

Tests cover every branch of the display_text / review_status /
needs_manual_review decision table from Spec v2.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from engine.checks.result_semantics import (
    ResultSemantics,
    build_canonical_result_semantics,
    _is_machine_code,
    _is_not_found_value,
    _has_any_extraction,
    _has_factual_extraction,
    _extract_scalar_value,
    _humanize_field_name,
    _extract_meaningful_evidence,
    _format_display_value,
    _MAX_EVIDENCE_DISPLAY_LENGTH,
)
from engine.playbook.models import (
    CheckDefinition,
    DetectorType,
    ExtractionConfig,
    ExtractionFieldConfig,
    ExtractionFieldType,
)
from core.constants import CheckExecutionStatus


# ─── Fixtures ─────────────────────────────────────────────────────────────────


def _make_check(
    *,
    check_id: str = "test_check_001",
    name: str = "Test Check",
    ui_mode: str | None = None,
    severity: str = "medium",
    extraction_fields: list[dict] | None = None,
    auto_label_facts: bool = True,
) -> CheckDefinition:
    """Build a minimal CheckDefinition for testing."""
    extraction = None
    if extraction_fields is not None:
        fields: list[ExtractionFieldConfig] = []

        for f in extraction_fields:
            field_name = f["name"]
            presentation = f.get("presentation", "fact")
            label = f.get("label")

            # Test helper convenience:
            # valid field_extraction checks now require explicit labels
            # for fact/summary fields. Unless a test explicitly wants to
            # verify validator failure, synthesize a deterministic label.
            if auto_label_facts and not label and presentation in ("fact", "summary"):
                label = _humanize_field_name(field_name)

            fields.append(
                ExtractionFieldConfig(
                    name=field_name,
                    type=ExtractionFieldType(f.get("type", "string")),
                    label=label,
                    presentation=presentation,
                    description=f.get("description", ""),
                    unit=f.get("unit"),
                )
            )

        extraction = ExtractionConfig(enabled=True, fields=fields)

    return CheckDefinition(
        id=check_id,
        name=name,
        ui_mode=ui_mode,
        severity=severity,
        detector_type=DetectorType.RULES,
        extraction=extraction,
    )


def _make_exec_result(
    *,
    result: str = "pass",
    severity: str = "medium",
    reason: str | None = None,
    evidence: str | None = None,
    check_name: str | None = "Test Check",
    llm_error_type: str | None = None,
    raw: dict | None = None,
) -> dict:
    """Build a minimal exec_result dict for testing."""
    r: dict = {
        "result": result,
        "severity": severity,
        "check_name": check_name,
        "reason": reason,
        "evidence": evidence or "",
        "raw": raw or {},
    }
    if llm_error_type is not None:
        r["llm_error_type"] = llm_error_type
    return r


# ─── Tests: _is_machine_code ─────────────────────────────────────────────────


class TestIsMachineCode:
    def test_snake_case_is_machine(self):
        assert _is_machine_code("rules_confident_positive") is True

    def test_human_text_is_not_machine(self):
        assert _is_machine_code("manual review required") is False

    def test_mixed_case_is_not_machine(self):
        assert _is_machine_code("НЕ_НАЙДЕНО") is False

    def test_none_is_machine(self):
        assert _is_machine_code(None) is True

    def test_empty_is_machine(self):
        assert _is_machine_code("") is True

    def test_single_word_no_underscore(self):
        # "timeout" has no underscore → not detected as machine code
        # This is correct: single words without _ are ambiguous,
        # and _extract_meaningful_evidence handles them separately
        assert _is_machine_code("timeout") is False

    def test_hyphenated_is_not_machine(self):
        assert _is_machine_code("rules-confident") is False


# ─── Tests: _is_not_found_value ───────────────────────────────────────────────


class TestIsNotFoundValue:
    def test_not_found_string(self):
        assert _is_not_found_value("not_found") is True

    def test_russian_not_found(self):
        assert _is_not_found_value("Не найдено") is True

    def test_absent(self):
        assert _is_not_found_value("absent") is True

    def test_none_is_not_found(self):
        assert _is_not_found_value(None) is True

    def test_empty_string_is_not_found(self):
        assert _is_not_found_value("") is True

    def test_actual_value_is_not_not_found(self):
        assert _is_not_found_value("Российская Федерация") is False

    def test_number_is_not_not_found(self):
        assert _is_not_found_value(42) is False

    def test_boolean_is_not_not_found(self):
        assert _is_not_found_value(True) is False
    def test_null_string(self):
        assert _is_not_found_value("null") is True

    def test_none_string(self):
        assert _is_not_found_value("none") is True

    def test_na_string(self):
        assert _is_not_found_value("n/a") is True

    def test_em_dash_string(self):
        assert _is_not_found_value("—") is True

    def test_russian_not_defined(self):
        assert _is_not_found_value("Не определено") is True

    def test_russian_data_not_defined(self):
        assert _is_not_found_value("Данные не определены") is True


# ─── Tests: _has_factual_extraction ───────────────────────────────────────────


class TestHasFactualExtraction:
    def test_with_value(self):
        sd = {"governing_law": {"value": "РФ"}}
        assert _has_factual_extraction(sd) is True

    def test_with_not_found(self):
        sd = {"governing_law": {"value": "not_found"}}
        assert _has_factual_extraction(sd) is False

    def test_with_none_value(self):
        sd = {"governing_law": {"value": None}}
        assert _has_factual_extraction(sd) is False

    def test_empty_dict(self):
        assert _has_factual_extraction({}) is False

    def test_none_input(self):
        assert _has_factual_extraction(None) is False

    def test_mixed_found_and_not_found(self):
        sd = {
            "governing_law": {"value": "РФ"},
            "forum": {"value": "not_found"},
        }

    def test_metadata_only_is_not_factual(self):
        sd = {
            "reason": {"value": "not enough context"},
            "evidence": {"value": "some snippet"},
        }
        assert _has_factual_extraction(sd) is False

    def test_metadata_and_fact_is_factual(self):
        sd = {
            "reason": {"value": "partial"},
            "governing_law": {"value": "РФ"},
        }
        assert _has_factual_extraction(sd) is True


class TestHasAnyExtraction:
    def test_enabled_extraction(self):
        check = _make_check(
            extraction_fields=[
                {"name": "governing_law", "label": "Применимое право", "description": "Применимое право"},
            ],
        )
        assert _has_any_extraction(check) is True

    def test_disabled_extraction(self):
        check = _make_check()
        assert _has_any_extraction(check) is False

    def test_none_check(self):
        assert _has_any_extraction(None) is False




# ─── Tests: _extract_scalar_value ─────────────────────────────────────────────


class TestExtractScalarValue:
    def test_dict_with_value_key(self):
        assert _extract_scalar_value({"value": "РФ"}) == "РФ"

    def test_plain_value(self):
        assert _extract_scalar_value("plain") == "plain"

    def test_dict_without_value_key(self):
        assert _extract_scalar_value({"other": 1}) == {"other": 1}


# ─── Tests: _humanize_field_name ──────────────────────────────────────────────


class TestHumanizeFieldName:
    def test_snake_case(self):
        assert _humanize_field_name("governing_law") == "Governing law"

    def test_single_word(self):
        assert _humanize_field_name("amount") == "Amount"

    def test_multiple_underscores(self):
        assert _humanize_field_name("termination_notice_days") == "Termination notice days"


# ─── Tests: _format_display_value ─────────────────────────────────────────────


class TestFormatDisplayValue:
    # С Commit 2 (35571dc) сигнатура: _format_display_value(check, field_name, value, unit=None).
    # check=None — валидный кейс: резолв enum-label пропускается, работает
    # базовое форматирование (строки, bool, unit).

    def test_string_value(self):
        assert _format_display_value(None, "test_field", "Российская Федерация") == "Российская Федерация"

    def test_none_value(self):
        assert _format_display_value(None, "test_field", None) == "—"

    def test_bool_true(self):
        assert _format_display_value(None, "test_field", True) == "Да"

    def test_bool_false(self):
        assert _format_display_value(None, "test_field", False) == "Нет"

    def test_with_unit(self):
        assert _format_display_value(None, "test_field", "30", unit="дней") == "30 дней"

    def test_unit_already_present(self):
        assert _format_display_value(None, "test_field", "30 дней", unit="дней") == "30 дней"

    def test_number_value(self):
        assert _format_display_value(None, "test_field", 15000000) == "15000000"


# ─── Tests: _extract_meaningful_evidence ──────────────────────────────────────


class TestExtractMeaningfulEvidence:
    def test_good_evidence(self):
        er = {"evidence": "Договор регулируется законодательством Российской Федерации."}
        result = _extract_meaningful_evidence(er)
        assert result is not None
        assert "Российской Федерации" in result

    def test_short_evidence_rejected(self):
        er = {"evidence": "short"}
        assert _extract_meaningful_evidence(er) is None

    def test_machine_code_evidence_rejected(self):
        er = {"evidence": "rules_confident_positive"}
        assert _extract_meaningful_evidence(er) is None

    def test_error_token_rejected(self):
        er = {"evidence": "timeout"}
        assert _extract_meaningful_evidence(er) is None

    def test_empty_evidence(self):
        er = {"evidence": ""}
        assert _extract_meaningful_evidence(er) is None

    def test_none_evidence(self):
        er = {}
        assert _extract_meaningful_evidence(er) is None


# ─── Tests: field_extraction ui_mode ──────────────────────────────────────────


class TestFieldExtraction:
    def test_governing_law_extracted(self):
        check = _make_check(
            ui_mode="field_extraction",
            extraction_fields=[
                {
                    "name": "governing_law",
                    "label": "Применимое право",
                    "description": "Извлеки применимое право",
                },
            ],
        )
        exec_result = _make_exec_result(result="pass")
        sd = {"governing_law": {"value": "Российская Федерация"}}

        sem = build_canonical_result_semantics(
            check=check,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=sd,
        )

        assert sem.display_text == "Применимое право: Российская Федерация"
        # Commit 2 (35571dc): field_extraction + pass + все fact-поля meaningful
        # → clause_defined (было no_issue_detected до рефакторинга).
        assert sem.review_status == "clause_defined"
        assert sem.needs_manual_review is False

    def test_amount_with_unit(self):
        check = _make_check(
            ui_mode="field_extraction",
            extraction_fields=[
                {
                    "name": "contract_amount",
                    "label": "Сумма договора",
                    "description": "Извлеки сумму договора",
                    "unit": "RUB",
                },
            ],
        )
        exec_result = _make_exec_result(result="pass")
        sd = {"contract_amount": {"value": "15 000 000"}}

        sem = build_canonical_result_semantics(
            check=check,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=sd,
        )

        assert sem.display_text == "Сумма договора: 15 000 000 RUB"

    def test_extraction_not_found(self):
        check = _make_check(
            ui_mode="field_extraction",
            extraction_fields=[
                {"name": "governing_law", "description": "Применимое право"},
            ],
        )
        exec_result = _make_exec_result(result="pass")
        sd = {"governing_law": {"value": "not_found"}}

        sem = build_canonical_result_semantics(
            check=check,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=sd,
        )

        # No factual extraction → falls to domain outcome for pass
        assert sem.display_text == "Признаков риска не обнаружено"

    def test_multiple_fields_uses_first_in_config(self):
        check = _make_check(
            ui_mode="field_extraction",
            extraction_fields=[
                {"name": "governing_law", "label": "Применимое право"},
                {"name": "forum", "label": "Форум"},
            ],
        )
        exec_result = _make_exec_result(result="pass")
        sd = {
            "forum": {"value": "МКАС"},
            "governing_law": {"value": "РФ"},
        }

        sem = build_canonical_result_semantics(
            check=check,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=sd,
        )

        # governing_law is first in extraction config → primary
        assert sem.display_text == "Применимое право: РФ"

    def test_no_description_uses_humanized_name(self):
        check = _make_check(
            ui_mode="field_extraction",
            extraction_fields=[
                {"name": "governing_law"},
            ],
        )
        exec_result = _make_exec_result(result="pass")
        sd = {"governing_law": {"value": "РФ"}}

        sem = build_canonical_result_semantics(
            check=check,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=sd,
        )

        assert sem.display_text == "Governing law: РФ"


class TestFieldExtractionDisplayPriority:
    def test_display_field_has_priority(self):
        check = _make_check(
            ui_mode="field_extraction",
            extraction_fields=[
                {"name": "security_status", "presentation": "signal", "description": "Статус обеспечения"},
                {"name": "security_display", "presentation": "summary", "description": "Вывод по обеспечению"},
            ],
        )
        exec_result = _make_exec_result(result="pass")
        sd = {
            "security_status": {"value": "yes"},
            "security_display": {"value": "Есть залог имущества и корпоративная гарантия"},
        }

        sem = build_canonical_result_semantics(
            check=check,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=sd,
        )

        assert sem.display_text == "Есть залог имущества и корпоративная гарантия"

    def test_details_field_beats_status_field(self):
        check = _make_check(
            ui_mode="field_extraction",
            extraction_fields=[
                {
                    "name": "price_status",
                    "presentation": "signal",
                    "description": "Статус цены",
                },
                {
                    "name": "price_details",
                    "label": "Цена",
                    "presentation": "fact",
                    "description": "Извлеки цену",
                },
            ],
        )
        exec_result = _make_exec_result(result="pass")
        sd = {
            "price_status": {"value": "present"},
            "price_details": {"value": "3 500 рублей, включая НДС"},
        }

        sem = build_canonical_result_semantics(
            check=check,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=sd,
        )

        assert sem.display_text == "Цена: 3 500 рублей, включая НДС"

    def test_ui_mode_none_with_extraction_uses_display_convention(self):
        check = _make_check(
            ui_mode=None,
            extraction_fields=[
                {"name": "forum_display", "presentation": "summary", "description": "Форум"},
            ],
        )
        exec_result = _make_exec_result(result="pass")
        sd = {
            "forum_display": {"value": "Применимое право: РФ; Форум: АС г. Москвы"},
        }

        sem = build_canonical_result_semantics(
            check=check,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=sd,
        )

        assert sem.display_text == "Применимое право: РФ; Форум: АС г. Москвы"

    def test_metadata_only_does_not_build_display_text(self):
        check = _make_check(
            ui_mode="field_extraction",
            extraction_fields=[
                {"name": "governing_law", "description": "Применимое право"},
            ],
        )
        exec_result = _make_exec_result(result="unclear")
        sd = {
            "reason": {"value": "not enough context"},
            "evidence": {"value": "short snippet"},
        }

        sem = build_canonical_result_semantics(
            check=check,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=sd,
        )

        assert sem.display_text is None






# ─── Tests: clause_presence ui_mode ───────────────────────────────────────────


class TestClausePresence:
    def test_pass_no_extraction(self):
        check = _make_check(ui_mode="clause_presence")
        exec_result = _make_exec_result(result="pass")

        sem = build_canonical_result_semantics(
            check=check,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=None,
        )

        assert sem.display_text == "Положение обнаружено"
        # Commit 2 (35571dc): clause_presence + pass → clause_defined
        # (было no_issue_detected до рефакторинга).
        assert sem.review_status == "clause_defined"
        assert sem.needs_manual_review is False

    def test_missing_required_clause(self):
        check = _make_check(ui_mode="clause_presence")
        exec_result = _make_exec_result(result="missing_required_clause")

        sem = build_canonical_result_semantics(
            check=check,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=None,
        )

        assert sem.display_text == "Обязательное положение отсутствует"
        assert sem.review_status == "clause_missing"
        assert sem.needs_manual_review is False

    def test_pass_with_factual_extraction(self):
        check = _make_check(
            ui_mode="clause_presence",
            extraction_fields=[
                {"name": "clause_text", "description": "Текст клаузулы"},
            ],
        )
        exec_result = _make_exec_result(result="pass")
        sd = {"clause_text": {"value": "Стороны обязуются..."}}

        sem = build_canonical_result_semantics(
            check=check,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=sd,
        )

        # Factual extraction with clause_presence → "Положение обнаружено"
        assert sem.display_text == "Положение обнаружено"


# ─── Tests: risk_detection ui_mode ────────────────────────────────────────────


class TestRiskDetection:
    def test_fail_with_extraction(self):
        check = _make_check(
            ui_mode="risk_detection",
            extraction_fields=[
                {"name": "risk_clause", "label": "Рискованная оговорка", "description": "Рискованная оговорка"},
            ],
        )
        exec_result = _make_exec_result(result="fail", severity="high")
        sd = {"risk_clause": {"value": "Golden parachute clause detected"}}

        sem = build_canonical_result_semantics(
            check=check,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=sd,
        )

        assert sem.display_text == "Рискованная оговорка: Golden parachute clause detected"
        assert sem.review_status == "issue_detected"

    def test_pass_no_extraction(self):
        check = _make_check(ui_mode="risk_detection")
        exec_result = _make_exec_result(result="pass")

        sem = build_canonical_result_semantics(
            check=check,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=None,
        )

        assert sem.display_text == "Признаков риска не обнаружено"


# ─── Tests: unclear + factual extraction ──────────────────────────────────────


class TestUnclearWithExtraction:
    def test_unclear_with_partial_data_shows_fact(self):
        check = _make_check(
            ui_mode="field_extraction",
            extraction_fields=[
                {"name": "governing_law", "label": "Применимое право", "description": "Применимое право"},
            ],
        )
        exec_result = _make_exec_result(result="unclear")
        sd = {"governing_law": {"value": "РФ"}}

        sem = build_canonical_result_semantics(
            check=check,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=sd,
        )

        # Factual extraction present → show fact even though result=unclear
        assert sem.display_text == "Применимое право: РФ"
        assert sem.needs_manual_review is True
        assert sem.review_status in ("unclear", "manual_review_required")

    def test_unclear_without_extraction(self):
        check = _make_check(ui_mode="field_extraction")
        exec_result = _make_exec_result(result="unclear")

        sem = build_canonical_result_semantics(
            check=check,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=None,
        )

        assert sem.display_text is None
        assert sem.needs_manual_review is True


# ─── Tests: fail without evidence ─────────────────────────────────────────────


class TestFailWithoutEvidence:
    def test_fail_high_severity_needs_review(self):
        check = _make_check(name="Governing Law Check")
        exec_result = _make_exec_result(
            result="fail",
            severity="high",
            check_name="Governing Law Check",
        )

        sem = build_canonical_result_semantics(
            check=check,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=None,
        )

        assert sem.display_text == "Обнаружено несоответствие: Governing Law Check"
        assert sem.needs_manual_review is True
        assert sem.review_status == "issue_detected"

    def test_fail_critical_severity_needs_review(self):
        exec_result = _make_exec_result(
            result="fail",
            severity="critical",
            check_name="Critical Check",
        )

        sem = build_canonical_result_semantics(
            check=None,
            check_name="Critical Check",
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=None,
        )

        assert sem.needs_manual_review is True

    def test_fail_medium_severity_no_review(self):
        check = _make_check(name="Medium Check")
        exec_result = _make_exec_result(
            result="fail",
            severity="medium",
            check_name="Medium Check",
        )

        sem = build_canonical_result_semantics(
            check=check,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=None,
        )

        assert sem.display_text == "Обнаружено несоответствие: Medium Check"
        assert sem.needs_manual_review is False

    def test_fail_with_evidence_no_review(self):
        check = _make_check(name="Evidence Check")
        exec_result = _make_exec_result(
            result="fail",
            severity="high",
            evidence="Пункт 5.2 договора содержит условие об ограничении ответственности сторон.",
        )

        sem = build_canonical_result_semantics(
            check=check,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=None,
        )

        assert sem.needs_manual_review is False
        assert "ограничении ответственности" in (sem.display_text or "")


# ─── Tests: technical failure ─────────────────────────────────────────────────


class TestTechnicalFailure:
    def test_timeout(self):
        exec_result = _make_exec_result(result="unclear")

        sem = build_canonical_result_semantics(
            check=None,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.TIMEOUT.value,
            structured_data=None,
        )

        assert sem.display_text is None
        assert sem.review_status == "technical_failure"
        assert sem.needs_manual_review is True

    def test_compute_failed(self):
        exec_result = _make_exec_result(result="unclear")

        sem = build_canonical_result_semantics(
            check=None,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.COMPUTE_FAILED.value,
            structured_data=None,
        )

        assert sem.review_status == "technical_failure"
        assert sem.needs_manual_review is True

    def test_legacy_failed(self):
        exec_result = _make_exec_result(result="unclear")

        sem = build_canonical_result_semantics(
            check=None,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.FAILED.value,
            structured_data=None,
        )

        assert sem.review_status == "technical_failure"


# ─── Tests: not applicable ────────────────────────────────────────────────────


class TestNotApplicable:
    def test_by_reason(self):
        exec_result = _make_exec_result(
            result="unclear",
            reason="check_not_applicable",
        )

        sem = build_canonical_result_semantics(
            check=None,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=None,
        )

        assert sem.display_text is None
        assert sem.review_status == "not_applicable"
        assert sem.needs_manual_review is False

    def test_by_raw_error(self):
        exec_result = _make_exec_result(
            result="unclear",
            raw={"error": "check_not_applicable_for_document"},
        )

        sem = build_canonical_result_semantics(
            check=None,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=None,
        )

        assert sem.review_status == "not_applicable"
        assert sem.needs_manual_review is False


# ─── Tests: machine reason ────────────────────────────────────────────────────


class TestMachineReason:
    def test_machine_reason_extracted(self):
        exec_result = _make_exec_result(reason="rules_confident_positive")

        sem = build_canonical_result_semantics(
            check=None,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=None,
        )

        assert sem.machine_reason_code == "rules_confident_positive"

    def test_human_reason_not_extracted_as_machine(self):
        exec_result = _make_exec_result(reason="The clause was found in section 5")

        sem = build_canonical_result_semantics(
            check=None,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=None,
        )

        assert sem.machine_reason_code is None


# ─── Tests: review message ────────────────────────────────────────────────────


class TestReviewMessage:
    def test_review_message_present(self):
        check = _make_check(ui_mode="risk_detection")
        exec_result = _make_exec_result(result="fail")

        sem = build_canonical_result_semantics(
            check=check,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=None,
        )

        assert sem.review_message is not None
        assert len(sem.review_message) > 10

    def test_review_message_for_unclear(self):
        exec_result = _make_exec_result(result="unclear")

        sem = build_canonical_result_semantics(
            check=None,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=None,
        )

        assert sem.review_message is not None
        assert "просмотр" in sem.review_message.lower() or "вывод" in sem.review_message.lower()


# ─── Tests: check=None edge cases ────────────────────────────────────────────


class TestCheckNone:
    def test_check_none_with_check_name_param(self):
        exec_result = _make_exec_result(result="fail", severity="medium")

        sem = build_canonical_result_semantics(
            check=None,
            check_name="Explicit Check Name",
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=None,
        )

        assert sem.display_text == "Обнаружено несоответствие: Explicit Check Name"

    def test_check_none_no_name(self):
        exec_result = _make_exec_result(
            result="fail",
            severity="medium",
            check_name=None,
        )

        sem = build_canonical_result_semantics(
            check=None,
            check_name=None,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=None,
        )

        assert sem.display_text == "Обнаружено несоответствие"

    def test_check_none_with_structured_data(self):
        exec_result = _make_exec_result(result="pass")
        sd = {"some_field": {"value": "some_value"}}

        sem = build_canonical_result_semantics(
            check=None,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=sd,
        )

        # No check → no extraction config → humanized field name
        assert sem.display_text == "Some field: some_value"


# ─── Tests: evidence as fallback display ──────────────────────────────────────


class TestEvidenceFallback:
    def test_evidence_used_when_no_extraction(self):
        check = _make_check(ui_mode="risk_detection", name="Risk Check")
        exec_result = _make_exec_result(
            result="fail",
            severity="medium",
            evidence="Пункт 8.3 содержит условие о золотом парашюте для генерального директора.",
        )

        sem = build_canonical_result_semantics(
            check=check,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=None,
        )

        assert "золотом парашюте" in (sem.display_text or "")

    def test_long_evidence_truncated(self):
        long_evidence = "А" * 300
        exec_result = _make_exec_result(
            result="fail",
            severity="medium",
            evidence=long_evidence,
        )

        sem = build_canonical_result_semantics(
            check=None,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=None,
        )

        assert sem.display_text is not None
        assert len(sem.display_text) <= _MAX_EVIDENCE_DISPLAY_LENGTH + 5
        assert sem.display_text.endswith("…")


# ─── Tests: ResultSemantics immutability ──────────────────────────────────────


class TestResultSemanticsImmutable:
    def test_frozen_dataclass(self):
        sem = ResultSemantics(
            display_text="test",
            machine_reason_code=None,
            review_status="no_issue_detected",
            review_message=None,
            needs_manual_review=False,
        )

        with pytest.raises(AttributeError):
            sem.display_text = "changed"  # type: ignore[misc]


class TestPresentationRoles:
    def test_signal_field_not_used_as_display(self):
        """Signal fields must never appear as primary display text."""
        check = _make_check(
            ui_mode="field_extraction",
            extraction_fields=[
                # Naming contract: seller_details (singleton) не может
                # делить префикс с seller_details_status (paired).
                # Переименовано: seller_details → seller_name,
                # seller_details_status → seller_status.
                {
                    "name": "seller_status",
                    "presentation": "signal",
                    "description": "Статус продавца",
                },
                {
                    "name": "seller_name",
                    "label": "Продавец",
                    "presentation": "fact",
                    "description": "Реквизиты продавца",
                },
            ],
        )
        exec_result = _make_exec_result(result="pass")
        sd = {
            "seller_status": {"value": "defined"},
            "seller_name": {"value": "ООО «Альфа», ИНН 7700000000"},
        }

        sem = build_canonical_result_semantics(
            check=check,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=sd,
        )

        assert sem.display_text == "Продавец: ООО «Альфа», ИНН 7700000000"
        assert "defined" not in (sem.display_text or "")

    def test_diagnostic_field_not_used_as_display(self):
        """Diagnostic fields (reason, red_flags) must never appear as display."""
        check = _make_check(
            ui_mode="field_extraction",
            extraction_fields=[
                {
                    "name": "red_flags",
                    "presentation": "diagnostic",
                    "description": "Коды рисков",
                },
                {
                    "name": "applicable_regimes",
                    "label": "Применимые режимы",
                    "presentation": "fact",
                    "description": "Режимы экспортного контроля",
                },
            ],
        )
        exec_result = _make_exec_result(result="pass")
        sd = {
            "red_flags": {"value": "EXP1, EXP2"},
            "applicable_regimes": {"value": "ITAR; EAR"},
        }

        sem = build_canonical_result_semantics(
            check=check,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=sd,
        )

        assert sem.display_text == "Применимые режимы: ITAR; EAR"
        assert "EXP1" not in (sem.display_text or "")

    def test_summary_field_has_highest_priority(self):
        """Summary field wins over all other fields."""
        check = _make_check(
            ui_mode="field_extraction",
            extraction_fields=[
                {
                    "name": "covenants_display",
                    "presentation": "summary",
                    "description": "Краткий вывод",
                },
                {
                    "name": "covenant_thresholds_summary",
                    "label": "Пороговые значения",
                    "presentation": "fact",
                    "description": "Пороги",
                },
            ],
        )
        exec_result = _make_exec_result(result="pass")
        sd = {
            "covenants_display": {
                "value": "Maintenance ковенанты: Net Debt/EBITDA ≤ 3.5x"
            },
            "covenant_thresholds_summary": {
                "value": "Net Debt/EBITDA ≤ 3.5x"
            },
        }

        sem = build_canonical_result_semantics(
            check=check,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=sd,
        )

        assert sem.display_text == "Maintenance ковенанты: Net Debt/EBITDA ≤ 3.5x"

    def test_label_beats_description_for_fact_field(self):
        """Label is used as display label, description is ignored."""
        check = _make_check(
            ui_mode="field_extraction",
            extraction_fields=[
                {
                    "name": "seller_details",
                    "label": "Продавец",
                    "presentation": "fact",
                    "description": "Укажи Продавца и его реквизиты. Если данных нет, верни строго: 'Данные не определены'.",
                },
            ],
        )
        exec_result = _make_exec_result(result="pass")
        sd = {"seller_details": {"value": "ООО «Ромашка»"}}

        sem = build_canonical_result_semantics(
            check=check,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=sd,
        )

        assert sem.display_text == "Продавец: ООО «Ромашка»"
        assert "Укажи" not in (sem.display_text or "")

    def test_no_label_on_fact_falls_back_to_humanized_name(self):
        """Fact field without label uses humanized field_name."""
        check = _make_check(
            ui_mode="field_extraction",
            extraction_fields=[
                {
                    "name": "buyer_details",
                    "presentation": "fact",
                    "description": "Реквизиты покупателя",
                },
            ],
        )
        exec_result = _make_exec_result(result="pass")
        sd = {"buyer_details": {"value": "ООО «Вектор»"}}

        sem = build_canonical_result_semantics(
            check=check,
            exec_result=exec_result,
            execution_status=CheckExecutionStatus.SUCCESS.value,
            structured_data=sd,
        )

        assert sem.display_text == "Buyer details: ООО «Вектор»"


class TestModelValidation:
    def test_field_extraction_without_summary_and_without_labels_fails(self):
        """CheckDefinition must reject field_extraction checks with no display contract."""
        with pytest.raises(ValidationError) as exc_info:
            CheckDefinition(
                id="bad_check",
                name="Bad Check",
                ui_mode="field_extraction",
                detector_type=DetectorType.RULES,
                extraction=ExtractionConfig(
                    enabled=True,
                    fields=[
                        ExtractionFieldConfig(
                            name="seller_details",
                            description="Укажи продавца",
                        ),
                    ],
                ),
            )
        assert "missing explicit `label`" in str(exc_info.value)

    def test_field_extraction_with_summary_is_valid(self):
        check = CheckDefinition(
            id="good_check_1",
            name="Good Check",
            ui_mode="field_extraction",
            detector_type=DetectorType.RULES,
            extraction=ExtractionConfig(
                enabled=True,
                fields=[
                    ExtractionFieldConfig(
                        name="covenants_display",
                        presentation="summary",
                        description="Краткий вывод",
                    ),
                    ExtractionFieldConfig(
                        name="has_cross_default",
                        presentation="signal",
                        description="Cross-default",
                    ),
                ],
            ),
        )
        assert check.extraction is not None

    def test_field_extraction_with_labeled_facts_is_valid(self):
        check = CheckDefinition(
            id="good_check_2",
            name="Good Check 2",
            ui_mode="field_extraction",
            detector_type=DetectorType.RULES,
            extraction=ExtractionConfig(
                enabled=True,
                fields=[
                    # Naming contract: singleton не может делить префикс
                    # с paired <prefix>_status. Переименовано:
                    # seller_details → seller_name, seller_details_status → seller_status.
                    ExtractionFieldConfig(
                        name="seller_name",
                        label="Продавец",
                        presentation="fact",
                        description="Реквизиты продавца",
                    ),
                    ExtractionFieldConfig(
                        name="seller_status",
                        presentation="signal",
                        description="Статус продавца",
                    ),
                ],
            ),
        )
        assert check.extraction is not None

    def test_non_field_extraction_does_not_require_labels(self):
        check = CheckDefinition(
            id="risk_check",
            name="Risk Check",
            ui_mode="risk_detection",
            detector_type=DetectorType.RULES,
            extraction=ExtractionConfig(
                enabled=True,
                fields=[
                    ExtractionFieldConfig(
                        name="risk_clause",
                        description="Рискованная оговорка",
                    ),
                ],
            ),
        )
        assert check.extraction is not None

        
