"""Тесты: location доступен для clause_defined / clause_partially_defined.

Проверяем _POSITIVE_LOCATION_COMBOS — какие пары (ui_mode, review_status)
разрешают location. Остальные пары — fail-safe: location suppressed.
"""
import pytest

from services.dd_grid_v1_builder import _is_positive_location_finding


class TestPositiveLocationNewStatuses:
    """Новые review_status из PR #2 — должны разрешать location."""

    @pytest.mark.parametrize("ui_mode,status", [
        ("field_extraction", "clause_defined"),
        ("field_extraction", "clause_partially_defined"),
        ("clause_presence",  "clause_defined"),
    ])
    def test_new_statuses_allow_location(self, ui_mode, status):
        assert _is_positive_location_finding(ui_mode, status) is True


class TestPositiveLocationLegacyRegression:
    """Legacy-пары не сломались."""

    @pytest.mark.parametrize("ui_mode,status", [
        ("field_extraction", "no_issue_detected"),
        ("field_extraction", "unclear"),
        ("clause_presence",  "no_issue_detected"),
        ("clause_presence",  "unclear"),
        ("risk_detection",   "issue_detected"),
        ("risk_detection",   "unclear"),
    ])
    def test_legacy_pairs_still_allow_location(self, ui_mode, status):
        assert _is_positive_location_finding(ui_mode, status) is True


class TestPositiveLocationSuppressions:
    """clause_missing не должен разрешать location — темы нет."""

    @pytest.mark.parametrize("ui_mode,status", [
        ("field_extraction", "clause_missing"),
        ("clause_presence",  "clause_missing"),
        ("risk_detection",   "no_issue_detected"),  # не положительный для risk
    ])
    def test_suppressed_combos(self, ui_mode, status):
        assert _is_positive_location_finding(ui_mode, status) is False


class TestPositiveLocationLegacyNone:
    """review_status = None → legacy fallback (не подавляем принудительно)."""

    def test_none_status_returns_none(self):
        # None означает legacy record — caller сам решает по cell_state.
        assert _is_positive_location_finding("field_extraction", None) is None


        