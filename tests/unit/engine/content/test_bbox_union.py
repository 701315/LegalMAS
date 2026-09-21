"""Unit tests for B0.4 bbox_union helpers in segment_chunk_builder_v2."""
from __future__ import annotations

import pytest

from engine.content.segment_chunk_builder_v2 import (
    _build_element_bbox_map,
    _compute_bbox_union,
)


# --- _build_element_bbox_map ---

def test_build_map_happy_path():
    layout = {"elements": [
        {"element_id": "e1", "page": 1, "bbox": [1.0, 2.0, 3.0, 4.0]},
        {"element_id": "e2", "page": 2, "bbox": [5, 6, 7, 8]},
    ]}
    m = _build_element_bbox_map(layout)
    assert m == {"e1": (1, [1.0, 2.0, 3.0, 4.0]), "e2": (2, [5.0, 6.0, 7.0, 8.0])}


def test_build_map_empty_elements():
    assert _build_element_bbox_map({}) == {}
    assert _build_element_bbox_map({"elements": []}) == {}


def test_build_map_skips_missing_bbox():
    layout = {"elements": [
        {"element_id": "e1", "page": 1},
        {"element_id": "e2", "page": 1, "bbox": [1, 2, 3, 4]},
    ]}
    m = _build_element_bbox_map(layout)
    assert "e1" not in m
    assert "e2" in m


def test_build_map_skips_malformed_bbox():
    layout = {"elements": [
        {"element_id": "e1", "page": 1, "bbox": [1, 2, 3]},
        {"element_id": "e2", "page": 1, "bbox": "not a list"},
        {"element_id": "e3", "page": 1, "bbox": [1, 2, 3, 4]},
    ]}
    m = _build_element_bbox_map(layout)
    assert set(m.keys()) == {"e3"}


def test_build_map_skips_missing_page():
    layout = {"elements": [
        {"element_id": "e1", "bbox": [1, 2, 3, 4]},
        {"element_id": "e2", "page": "1", "bbox": [1, 2, 3, 4]},
        {"element_id": "e3", "page": True, "bbox": [1, 2, 3, 4]},
    ]}
    assert _build_element_bbox_map(layout) == {}


def test_build_map_skips_non_dict_element():
    layout = {"elements": ["not a dict", None, {"element_id": "e1", "page": 1, "bbox": [1, 2, 3, 4]}]}
    m = _build_element_bbox_map(layout)
    assert set(m.keys()) == {"e1"}


# --- _compute_bbox_union ---

def _map():
    return {
        "e1": (1, [10.0, 20.0, 30.0, 40.0]),
        "e2": (1, [15.0, 25.0, 50.0, 60.0]),
        "e3": (2, [100.0, 200.0, 300.0, 400.0]),
    }


def test_union_single_element():
    assert _compute_bbox_union(["e1"], 1, _map()) == [10.0, 20.0, 30.0, 40.0]


def test_union_same_page():
    u = _compute_bbox_union(["e1", "e2"], 1, _map())
    assert u == [10.0, 20.0, 50.0, 60.0]


def test_union_target_page_filters():
    # target_page=2 -> only e3
    u = _compute_bbox_union(["e1", "e2", "e3"], 2, _map())
    assert u == [100.0, 200.0, 300.0, 400.0]


def test_union_target_page_missing_falls_back_to_all():
    # target_page=99 matches nothing -> union of all
    u = _compute_bbox_union(["e1", "e3"], 99, _map())
    assert u == [10.0, 20.0, 300.0, 400.0]


def test_union_target_page_none_uses_all():
    u = _compute_bbox_union(["e1", "e3"], None, _map())
    assert u == [10.0, 20.0, 300.0, 400.0]


def test_union_empty_element_ids():
    assert _compute_bbox_union([], 1, _map()) is None


def test_union_unknown_elements():
    assert _compute_bbox_union(["unknown1", "unknown2"], 1, _map()) is None


def test_union_empty_map():
    assert _compute_bbox_union(["e1"], 1, {}) is None
