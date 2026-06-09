# tests/services/structure/test_hierarchy_range_local_indexing.py

from __future__ import annotations

from services.structure._hierarchy_builder._core import (
    BuildCounters,
    _assign_own_ranges_and_elements,
)
from services.structure._hierarchy_builder._range_logic import (
    _compute_own_range,
    _find_next_same_or_higher_level_elem_i,
)
from services.structure._hierarchy_builder._types import HeadingCandidate
from services.structure.models import MutableHierarchyNode


def _make_heading(
    *,
    elem_i: int,
    raw_uid: str,
    effective_uid: str,
    title: str,
    scope: str = "main_contract",
    page: int = 4,
) -> HeadingCandidate:
    return HeadingCandidate(
        elem_i=elem_i,
        uid=raw_uid,
        raw_uid=raw_uid,
        effective_uid=effective_uid,
        title=title,
        page=page,
        scope=scope,
        metadata={},
    )


def _make_element(
    *,
    element_id: str,
    text: str,
    page: int = 4,
    raw_type: str = "text",
    scope: str = "main_contract",
) -> dict:
    return {
        "element_id": element_id,
        "text": text,
        "page": page,
        "type": raw_type,
        "scope": scope,
    }


def test_find_next_same_or_higher_level_uses_local_anchor_not_global_index() -> None:
    headings_local = [
        _make_heading(
            elem_i=115,
            raw_uid="2.1",
            effective_uid="main_contract:2.1",
            title="2.1 First",
        ),
        _make_heading(
            elem_i=118,
            raw_uid="2.2",
            effective_uid="main_contract:2.2",
            title="2.2 Second",
        ),
        _make_heading(
            elem_i=123,
            raw_uid="2.3",
            effective_uid="main_contract:2.3",
            title="2.3 Third",
        ),
    ]

    # Имитируем старую поломанную ситуацию:
    # global index не совпадает с local scope list index.
    broken_global_idx = {
        ("main_contract", "2.1"): 99,
    }

    result = _find_next_same_or_higher_level_elem_i(
        raw_uid="2.1",
        node_level=2,
        scope="main_contract",
        headings=headings_local,
        key_to_heading_index=broken_global_idx,
        heading_elem_i=115,
    )

    assert result == 118


def test_compute_own_range_prefers_source_elem_i_over_wrong_key_to_elem_i() -> None:
    elements = [_make_element(element_id=f"e{i}", text=f"el {i}") for i in range(130)]

    headings_local = [
        _make_heading(
            elem_i=115,
            raw_uid="2.1",
            effective_uid="main_contract:2.1",
            title="2.1 First",
        ),
        _make_heading(
            elem_i=118,
            raw_uid="2.2",
            effective_uid="main_contract:2.2",
            title="2.2 Second",
        ),
        _make_heading(
            elem_i=123,
            raw_uid="2.3",
            effective_uid="main_contract:2.3",
            title="2.3 Third",
        ),
    ]

    node = MutableHierarchyNode(
        effective_uid="main_contract:2.1",
        raw_uid="2.1",
        scope="main_contract",
        title="2.1 First",
        level=2,
        start_page=4,
        end_page=4,
        diagnostics={"source_elem_i": 115},
    )

    # key_to_elem_i намеренно сломан: указывает не на тот anchor.
    broken_key_to_elem_i = {
        ("main_contract", "2.1"): 10,
    }
    broken_key_to_idx = {
        ("main_contract", "2.1"): 99,
    }

    result = _compute_own_range(
        raw_uid="2.1",
        node=node,
        headings=headings_local,
        elements=elements,
        key_to_elem_i=broken_key_to_elem_i,
        key_to_heading_index=broken_key_to_idx,
        scope="main_contract",
        scope_boundaries={"main_contract": (0, len(elements))},
    )

    assert result.start_elem_i == 115
    assert result.end_elem_i == 118
    assert result.range_end_reason == "next_same_or_higher"


def test_compute_own_range_soft_layout_root_fallback_uses_canonical_reason() -> None:
    elements = [
        _make_element(
            element_id="e0",
            text="3 GENERAL TERMS",
            raw_type="heading",
            page=1,
        ),
        _make_element(
            element_id="e1",
            text="3.1 Existing child",
            raw_type="heading",
            page=1,
        ),
        _make_element(
            element_id="e2",
            text="3.1 body text",
            raw_type="text",
            page=1,
        ),
        _make_element(
            element_id="e3",
            text="4 PAYMENT TERMS",
            raw_type="heading",
            page=2,
        ),
        _make_element(
            element_id="e4",
            text="4.1 Payment shall be made within 10 days.",
            raw_type="text",
            page=2,
        ),
    ]

    # Accepted headings intentionally do NOT include the next root section "4".
    # This forces _compute_own_range() to use the soft layout fallback.
    headings_local = [
        _make_heading(
            elem_i=0,
            raw_uid="3",
            effective_uid="main_contract:3",
            title="3 GENERAL TERMS",
            page=1,
        ),
        _make_heading(
            elem_i=1,
            raw_uid="3.1",
            effective_uid="main_contract:3.1",
            title="3.1 Existing child",
            page=1,
        ),
    ]

    node = MutableHierarchyNode(
        effective_uid="main_contract:3",
        raw_uid="3",
        scope="main_contract",
        title="3 GENERAL TERMS",
        level=1,
        start_page=1,
        end_page=2,
        diagnostics={"source_elem_i": 0},
    )

    result = _compute_own_range(
        raw_uid="3",
        node=node,
        headings=headings_local,
        elements=elements,
        key_to_elem_i={
            ("main_contract", "3"): 0,
            ("main_contract", "3.1"): 1,
        },
        key_to_heading_index={
            ("main_contract", "3"): 0,
            ("main_contract", "3.1"): 1,
        },
        scope="main_contract",
        scope_boundaries={"main_contract": (0, len(elements))},
    )

    # The next root boundary was found only via soft layout fallback at elem_i=3,
    # but the published reason must remain canonical.
    assert result.start_elem_i == 0
    assert result.end_elem_i == 3
    assert result.range_end_reason == "next_same_or_higher"





def test_assign_own_ranges_produces_disjoint_adjacent_siblings_even_with_wrong_global_idx() -> None:
    elements = [
        _make_element(element_id="e115", text="2.1 First line", raw_type="heading"),
        _make_element(element_id="e116", text="2.1 body", raw_type="text"),
        _make_element(element_id="e118", text="2.2 Second line", raw_type="heading"),
        _make_element(element_id="e119", text="2.2 body", raw_type="text"),
        _make_element(element_id="e123", text="2.3 Third line", raw_type="heading"),
        _make_element(element_id="e124", text="2.3 body", raw_type="text"),
    ]

    headings = [
        _make_heading(
            elem_i=0,
            raw_uid="2.1",
            effective_uid="main_contract:2.1",
            title="2.1 First",
        ),
        _make_heading(
            elem_i=2,
            raw_uid="2.2",
            effective_uid="main_contract:2.2",
            title="2.2 Second",
        ),
        _make_heading(
            elem_i=4,
            raw_uid="2.3",
            effective_uid="main_contract:2.3",
            title="2.3 Third",
        ),
    ]

    node_21 = MutableHierarchyNode(
        effective_uid="main_contract:2.1",
        raw_uid="2.1",
        scope="main_contract",
        title="2.1 First",
        level=2,
        start_page=4,
        end_page=4,
        diagnostics={"source_elem_i": 0},
    )
    node_22 = MutableHierarchyNode(
        effective_uid="main_contract:2.2",
        raw_uid="2.2",
        scope="main_contract",
        title="2.2 Second",
        level=2,
        start_page=4,
        end_page=4,
        diagnostics={"source_elem_i": 2},
    )
    node_23 = MutableHierarchyNode(
        effective_uid="main_contract:2.3",
        raw_uid="2.3",
        scope="main_contract",
        title="2.3 Third",
        level=2,
        start_page=4,
        end_page=4,
        diagnostics={"source_elem_i": 4},
    )

    mutable_nodes = {
        "main_contract:2.1": node_21,
        "main_contract:2.2": node_22,
        "main_contract:2.3": node_23,
    }

    # Intentionally broken old global indices.
    broken_key_to_idx = {
        ("main_contract", "2.1"): 99,
        ("main_contract", "2.2"): 100,
        ("main_contract", "2.3"): 101,
    }

    _assign_own_ranges_and_elements(
        headings=headings,
        headings_by_scope={"main_contract": headings},
        elements=elements,
        mutable_nodes=mutable_nodes,
        element_to_effective_uid={},
        stable_element_id_resolver=lambda element, _: element["element_id"],
        key_to_elem_i={
            ("main_contract", "2.1"): 0,
            ("main_contract", "2.2"): 2,
            ("main_contract", "2.3"): 4,
        },
        key_to_idx=broken_key_to_idx,
        scope_boundaries={"main_contract": (0, len(elements))},
        counters=BuildCounters(),
    )

    set_21 = set(node_21.own_element_ids)
    set_22 = set(node_22.own_element_ids)
    set_23 = set(node_23.own_element_ids)

    assert set_21 == {"e115", "e116"}
    assert set_22 == {"e118", "e119"}
    assert set_23 == {"e123", "e124"}

    assert set_21.isdisjoint(set_22)
    assert set_22.isdisjoint(set_23)
    assert set_21.isdisjoint(set_23)

    assert "2.2" not in (node_21.own_text or "")
    assert "2.3" not in (node_22.own_text or "")


    