from types import SimpleNamespace

from services.structure._pipeline._core_builder import (
    _filter_toc_zone_headings_when_body_headings_exist,
)


def test_pre_toc_heading_does_not_suppress_only_toc_fallback():
    elements = [
        {"_preamble_zone": "pre_toc"},
        {"_preamble_zone": "in_toc"},
    ]
    headings = [
        SimpleNamespace(elem_i=0, raw_uid="P"),
        SimpleNamespace(elem_i=1, raw_uid="1"),
    ]

    filtered, diagnostics = _filter_toc_zone_headings_when_body_headings_exist(
        headings, elements
    )

    assert filtered == headings
    assert diagnostics["filtered_count"] == 0


def test_unknown_heading_position_does_not_suppress_toc_fallback():
    elements = [{"_preamble_zone": "in_toc"}]
    headings = [
        SimpleNamespace(elem_i=0, raw_uid="1"),
        SimpleNamespace(elem_i=99, raw_uid="unknown"),
    ]

    filtered, diagnostics = _filter_toc_zone_headings_when_body_headings_exist(
        headings, elements
    )

    assert filtered == headings
    assert diagnostics["filtered_count"] == 0


def test_post_toc_heading_suppresses_toc_entries():
    elements = [
        {"_preamble_zone": "in_toc"},
        {"_preamble_zone": "post_toc"},
    ]
    headings = [
        SimpleNamespace(elem_i=0, raw_uid="1"),
        SimpleNamespace(elem_i=1, raw_uid="1"),
    ]

    filtered, diagnostics = _filter_toc_zone_headings_when_body_headings_exist(
        headings, elements
    )

    assert filtered == [headings[1]]
    assert diagnostics["filtered_count"] == 1


def test_toc_only_headings_remain_as_fallback():
    elements = [{"_preamble_zone": "in_toc"}]
    headings = [SimpleNamespace(elem_i=0, raw_uid="1")]

    filtered, diagnostics = _filter_toc_zone_headings_when_body_headings_exist(
        headings, elements
    )

    assert filtered == headings
    assert diagnostics["filtered_count"] == 0
