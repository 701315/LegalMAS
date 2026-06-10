"""
Regression tests for A3: appendix family predicate separation.

Ensures that schedule/exhibit scopes do NOT inflate appendix-root signals
or suppress valid main sections in structural quality assessment.
"""

import pytest
from unittest.mock import MagicMock


def _make_node(*, raw_uid="", scope="", effective_uid="", title=""):
    node = MagicMock()
    node.raw_uid = raw_uid
    node.scope = scope
    node.effective_uid = effective_uid
    node.title = title
    return node


class TestTrueAppendixFamilyText:
    """_is_true_appendix_family_text should match only true appendix family."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from services.structure._pipeline._core_builder import (
            _is_true_appendix_family_text,
            _is_catalog_family_text,
        )
        self.is_true = _is_true_appendix_family_text
        self.is_catalog = _is_catalog_family_text

    @pytest.mark.parametrize("text", [
        "appendix", "Appendix 1", "APPENDIX A",
        "приложение", "Приложение 1", "Приложения",
        "annex", "Annex A", "ANNEXURE 1",
        "attachment", "Attachment 1",
    ])
    def test_true_appendix_family_positive(self, text):
        assert self.is_true(text) is True

    @pytest.mark.parametrize("text", [
        "schedule", "Schedule 1", "SCHEDULE A",
        "exhibit", "Exhibit 1", "EXHIBIT A",
        "disclosure schedule",
    ])
    def test_schedule_exhibit_not_true_appendix(self, text):
        assert self.is_true(text) is False

    @pytest.mark.parametrize("text", [
        "schedule", "Schedule 1", "exhibit", "Exhibit A",
    ])
    def test_schedule_exhibit_is_catalog_family(self, text):
        assert self.is_catalog(text) is True

    @pytest.mark.parametrize("text", [
        "", None, "  ", "1.1", "Предмет договора", "PARTIES",
    ])
    def test_non_catalog_text(self, text):
        assert self.is_true(text) is False
        assert self.is_catalog(text) is False


class TestCountRootSections:
    """Schedule/exhibit scopes should NOT exclude nodes from root_sections_count."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from services.structure._pipeline._core_builder import _count_root_sections
        self.count = _count_root_sections

    def test_numeric_root_in_schedule_scope_counted(self):
        nodes = [
            _make_node(raw_uid="1", scope="schedule 1"),
            _make_node(raw_uid="2", scope="schedule 2"),
        ]
        assert self.count(nodes) == 2

    def test_numeric_root_in_exhibit_scope_counted(self):
        nodes = [
            _make_node(raw_uid="1", scope="exhibit A"),
        ]
        assert self.count(nodes) == 1

    def test_numeric_root_in_appendix_scope_excluded(self):
        nodes = [
            _make_node(raw_uid="1", scope="appendix 1"),
            _make_node(raw_uid="2", scope="main_contract"),
        ]
        assert self.count(nodes) == 1

    def test_mixed_scopes(self):
        nodes = [
            _make_node(raw_uid="1", scope="main_contract"),
            _make_node(raw_uid="2", scope="schedule 1"),
            _make_node(raw_uid="3", scope="appendix 1"),
            _make_node(raw_uid="4", scope="exhibit A"),
        ]
        # main_contract + schedule + exhibit = 3, appendix excluded
        assert self.count(nodes) == 3


class TestCountAppendixRoots:
    """Only true appendix family should be counted as appendix roots."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from services.structure._pipeline._core_builder import _count_appendix_roots
        self.count = _count_appendix_roots

    def test_appendix_counted(self):
        nodes = [
            _make_node(scope="appendix 1"),
            _make_node(scope="Приложение 2"),
        ]
        assert self.count(nodes) == 2

    def test_schedule_not_counted(self):
        nodes = [
            _make_node(scope="schedule 1"),
            _make_node(scope="Schedule 2"),
        ]
        assert self.count(nodes) == 0

    def test_exhibit_not_counted(self):
        nodes = [
            _make_node(scope="exhibit A"),
        ]
        assert self.count(nodes) == 0

    def test_mixed(self):
        nodes = [
            _make_node(scope="appendix 1"),
            _make_node(scope="schedule 1"),
            _make_node(scope="exhibit A"),
            _make_node(title="Приложение 3"),
        ]
        # Only appendix + Приложение = 2
        assert self.count(nodes) == 2


        