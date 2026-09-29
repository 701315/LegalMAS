"""
B7.9.2 / viewer-highlight: _extract_layout_element_ids unit tests.

Проверяет fallback-цепочку для viewer highlight:
  check_result.bbox.element_ids  →  [check_result.element_id]  →  []

Пока B3.6 не реализован, layout_element_ids в CellValueDTO заполняются
из этих источников. Тесты фиксируют контракт и защищают от регрессий.
"""

from __future__ import annotations

from services.dd_grid_v1_builder import _extract_layout_element_ids


class TestExtractFromBbox:
    def test_bbox_element_ids_list(self):
        cr = {
            "bbox": {
                "page": 5,
                "union": [10.0, 20.0, 30.0, 40.0],
                "element_ids": ["ru:node:5:0002"],
            }
        }
        assert _extract_layout_element_ids(cr) == ["ru:node:5:0002"]

    def test_bbox_multiple_element_ids(self):
        cr = {
            "bbox": {
                "page": 3,
                "union": [0.0, 0.0, 1.0, 1.0],
                "element_ids": ["a", "b", "c"],
            }
        }
        assert _extract_layout_element_ids(cr) == ["a", "b", "c"]

    def test_bbox_empty_element_ids_falls_back_to_element_id(self):
        cr = {
            "bbox": {"page": 5, "union": [], "element_ids": []},
            "element_id": "ru:node:5:0002",
        }
        assert _extract_layout_element_ids(cr) == ["ru:node:5:0002"]

    def test_bbox_missing_element_ids_key_falls_back(self):
        cr = {
            "bbox": {"page": 5, "union": []},
            "element_id": "ru:node:5:0002",
        }
        assert _extract_layout_element_ids(cr) == ["ru:node:5:0002"]

    def test_bbox_not_a_dict_falls_back(self):
        cr = {
            "bbox": "not-a-dict",
            "element_id": "ru:node:5:0002",
        }
        assert _extract_layout_element_ids(cr) == ["ru:node:5:0002"]


class TestExtractFromSingleElementId:
    def test_single_element_id_only(self):
        cr = {"element_id": "ru:node:5:0002"}
        assert _extract_layout_element_ids(cr) == ["ru:node:5:0002"]

    def test_single_element_id_stripped(self):
        cr = {"element_id": "  ru:node:5:0002  "}
        assert _extract_layout_element_ids(cr) == ["ru:node:5:0002"]

    def test_single_element_id_empty_string(self):
        cr = {"element_id": ""}
        assert _extract_layout_element_ids(cr) == []

    def test_single_element_id_whitespace(self):
        cr = {"element_id": "   "}
        assert _extract_layout_element_ids(cr) == []


class TestEmptyAndInvalid:
    def test_none_check_result(self):
        assert _extract_layout_element_ids(None) == []

    def test_empty_dict(self):
        assert _extract_layout_element_ids({}) == []

    def test_no_relevant_keys(self):
        assert _extract_layout_element_ids({"page": 5, "clause_uid": "x"}) == []

    def test_bbox_element_ids_with_none_entries(self):
        cr = {
            "bbox": {
                "element_ids": ["a", None, "  ", "b"],
            }
        }
        assert _extract_layout_element_ids(cr) == ["a", "b"]

    def test_bbox_element_ids_with_non_string_entries(self):
        cr = {
            "bbox": {
                "element_ids": ["a", 42, "b"],
            }
        }
        assert _extract_layout_element_ids(cr) == ["a", "42", "b"]


class TestIsolation:
    def test_returns_fresh_list(self):
        """Изменение результата не должно менять исходный check_result."""
        element_ids = ["ru:node:5:0002"]
        cr = {"bbox": {"element_ids": element_ids}}
        out = _extract_layout_element_ids(cr)
        out.append("injected")
        assert element_ids == ["ru:node:5:0002"]
