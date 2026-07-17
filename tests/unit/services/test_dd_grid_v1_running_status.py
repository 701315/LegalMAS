"""
Tests: RUNNING и PENDING execution_status корректно маппятся в DD Grid V1.

Регрессионные тесты для бага: RUNNING → FAILED (неверно).
После патча: RUNNING → IN_PROGRESS, PENDING → SKIPPED.
"""

from __future__ import annotations

import pytest

from services.dd_grid_v1_builder import (
    _normalize_execution_status_for_api,
)
from engine.checks.dd_grid_column_builder import DDGridColumnRuntime
from services.dd_grid_v1_builder import CellValueDTO


# =============================================================================
# Helpers
# =============================================================================

def _make_column() -> DDGridColumnRuntime:
    return DDGridColumnRuntime(
        column_id="test_check__field",
        label="Test Field",
        format="text",
        value_field="field",
        status_field=None,
        status_present_value=None,
        fallback_display="—",
        display_order=0,
        enum_labels={},
        unit=None,
    )


def _make_cell(state: str = "not_executed") -> CellValueDTO:
    return CellValueDTO(
        cell_state=state,
        display_value="—",
    )


def _make_check_result(execution_status: str) -> dict:
    return {
        "check_id": "test_check",
        "document_id": "doc-1",
        "execution_status": execution_status,
    }


# =============================================================================
# Регрессионные тесты: RUNNING и PENDING
# =============================================================================

class TestNonTerminalStatusMapping:
    """
    RUNNING и PENDING — нетерминальные статусы.
    Они НЕ должны маппиться в FAILED.
    """

    def test_running_maps_to_in_progress(self) -> None:
        """
        RUNNING → IN_PROGRESS.

        До патча: RUNNING → FAILED (ложная информация для пользователя).
        После патча: RUNNING → IN_PROGRESS (корректное отображение прогресса).
        """
        column = _make_column()
        cell = _make_cell("not_executed")
        column_cells = [(column, cell)]

        result = _normalize_execution_status_for_api(
            check_result=_make_check_result("RUNNING"),
            column_cells=column_cells,
        )

        assert result == "IN_PROGRESS", (
            f"RUNNING должен маппиться в IN_PROGRESS, получено: {result!r}. "
            f"Вероятно, откат к старому поведению RUNNING → FAILED."
        )

    def test_pending_maps_to_skipped(self) -> None:
        """
        PENDING → SKIPPED.

        Check ещё не начался — семантически эквивалентно отсутствию результата.
        """
        column = _make_column()
        cell = _make_cell("not_executed")
        column_cells = [(column, cell)]

        result = _normalize_execution_status_for_api(
            check_result=_make_check_result("PENDING"),
            column_cells=column_cells,
        )

        assert result == "SKIPPED", (
            f"PENDING должен маппиться в SKIPPED, получено: {result!r}."
        )

    def test_running_is_not_failed(self) -> None:
        """Явная проверка что RUNNING ≠ FAILED."""
        column = _make_column()
        cell = _make_cell("not_executed")

        result = _normalize_execution_status_for_api(
            check_result=_make_check_result("RUNNING"),
            column_cells=[(column, cell)],
        )

        assert result != "FAILED", (
            f"RUNNING не должен маппиться в FAILED. "
            f"Это регрессионный баг: пользователь видит ошибку там где её нет."
        )

    def test_pending_is_not_failed(self) -> None:
        """Явная проверка что PENDING ≠ FAILED."""
        column = _make_column()
        cell = _make_cell("not_executed")

        result = _normalize_execution_status_for_api(
            check_result=_make_check_result("PENDING"),
            column_cells=[(column, cell)],
        )

        assert result != "FAILED", (
            f"PENDING не должен маппиться в FAILED."
        )


# =============================================================================
# Остальные статусы не сломались
# =============================================================================

class TestTerminalStatusMappingUnchanged:
    """
    Патч не должен сломать существующий маппинг терминальных статусов.
    """

    @pytest.mark.parametrize("raw_status,expected", [
        ("SUCCESS", "SUCCESS"),
        ("COMPUTE_FAILED", "FAILED"),
        ("PERSIST_FAILED", "FAILED"),
        ("FAILED", "FAILED"),
        ("TIMEOUT", "TIMEOUT"),
        ("SKIPPED", "SKIPPED"),
    ])
    def test_terminal_statuses_unchanged(
        self,
        raw_status: str,
        expected: str,
    ) -> None:
        """Терминальные статусы маппятся как прежде."""
        column = _make_column()

        # Для SUCCESS нужна ячейка в состоянии defined чтобы не попасть в PARTIAL
        cell_state = "defined" if raw_status == "SUCCESS" else "error"
        cell = _make_cell(cell_state)

        result = _normalize_execution_status_for_api(
            check_result=_make_check_result(raw_status),
            column_cells=[(column, cell)],
        )

        assert result == expected, (
            f"Статус {raw_status!r} должен давать {expected!r}, получено {result!r}."
        )

    def test_lowercase_running_also_handled(self) -> None:
        """
        Проверяем что lowercase 'running' тоже обрабатывается.
        _normalize_execution_status_for_api делает .upper() перед проверкой.
        """
        column = _make_column()
        cell = _make_cell("not_executed")

        result = _normalize_execution_status_for_api(
            check_result=_make_check_result("running"),
            column_cells=[(column, cell)],
        )

        assert result == "IN_PROGRESS"

    def test_lowercase_pending_also_handled(self) -> None:
        """Lowercase 'pending' тоже обрабатывается."""
        column = _make_column()
        cell = _make_cell("not_executed")

        result = _normalize_execution_status_for_api(
            check_result=_make_check_result("pending"),
            column_cells=[(column, cell)],
        )

        assert result == "SKIPPED"



        