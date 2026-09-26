"""Тесты: fallback-значения → cell_state=not_defined."""
from services.dd_grid_v1_builder import (
    _is_field_fallback_value,
    _resolve_cell_state,
)
from engine.checks.dd_grid_column_builder import DDGridColumnRuntime
from engine.playbook.models import (
    CheckDefinition,
    ExtractionConfig,
    ExtractionFieldConfig,
)


def _make_check() -> CheckDefinition:
    return CheckDefinition(
        id="test_check",
        name="test",
        extraction=ExtractionConfig(
            enabled=True,
            fields=[
                ExtractionFieldConfig(
                    name="delivery_mode_display",
                    type="string",
                    presentation="fact",
                    label="Способ передачи",
                    fallback_texts=["Не установлен", "Не удалось определить"],
                ),
            ],
        ),
    )


def _make_column() -> DDGridColumnRuntime:
    return DDGridColumnRuntime(
        column_id="test_check__delivery_mode_display",
        label="Способ передачи",
        value_field="delivery_mode_display",
        status_field=None,
        status_present_value=None,
        format="text",
        fallback_display="—",
        display_order=1,
    )


class TestFallbackCellState:
    def test_fallback_value_not_defined(self):
        check = _make_check()
        column = _make_column()
        result = _resolve_cell_state(
            check=check,
            check_result={"execution_status": "SUCCESS"},
            column=column,
            raw_value="Не установлен",
            status_field_value=None,
        )
        assert result == "not_defined"

    def test_meaningful_value_defined(self):
        check = _make_check()
        column = _make_column()
        result = _resolve_cell_state(
            check=check,
            check_result={"execution_status": "SUCCESS"},
            column=column,
            raw_value="Самовывоз",
            status_field_value=None,
        )
        assert result == "defined"

    def test_helper_empty_fallback(self):
        check = CheckDefinition(
            id="c", name="test",
            extraction=ExtractionConfig(
                enabled=True,
                fields=[ExtractionFieldConfig(
                    name="x", type="string", presentation="fact", label="X",
                )],
            ),
        )
        assert _is_field_fallback_value(check, "x", "Не установлен") is False

