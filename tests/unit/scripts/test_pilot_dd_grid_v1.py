# tests/unit/scripts/test_pilot_dd_grid_v1.py

"""
Unit tests для pure helpers в scripts/pilot_dd_grid_v1.py.

Тестируем только функции без I/O и без БД:
- count_cell_states
- collect_sample_cells
- collect_sample_drawers
- build_summary
- check_health
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from scripts.pilot_dd_grid_v1 import (
    build_summary,
    check_health,
    collect_sample_cells,
    collect_sample_drawers,
    count_cell_states,
)


# ---------------------------------------------------------------------------
# Stub DTOs (имитируют runtime dataclasses из dd_grid_v1_builder)
# ---------------------------------------------------------------------------


@dataclass
class StubCell:
    cell_state: str
    display_value: str = "—"
    raw_value: Any = None
    location_clause_ref: str | None = None
    location_page: int | None = None
    location_confidence: str | None = None
    location_source: str = "none"


@dataclass
class StubDrawerField:
    column_id: str = "col__val"
    field_name: str = "val"
    label: str = "Value"
    cell_state: str = "defined"
    display_value: str = "Текст"
    raw_value: Any = None
    location_clause_ref: str | None = None
    location_page: int | None = None
    location_confidence: str | None = None
    location_source: str = "none"


@dataclass
class StubDrawer:
    check_id: str
    check_name: str
    document_id: str
    cell_state: str = "defined"
    reason: str | None = None
    review_status: str | None = None
    review_message: str | None = None
    display_text: str | None = None
    execution_status: str | None = "SUCCESS"
    fields: list = field(default_factory=list)
    evidence_items: list = field(default_factory=list)


@dataclass
class StubColumn:
    column_id: str
    label: str = "Label"
    format: str = "text"
    fallback_display: str = "—"
    display_order: int = 0
    enum_labels: dict = field(default_factory=dict)
    unit: str | None = None


@dataclass
class StubCheckSubgroup:
    check_id: str
    check_name: str
    display_order: int = 0
    columns: list = field(default_factory=list)
    display_summary_field: str | None = None
    metadata_fields: list = field(default_factory=list)


@dataclass
class StubGlobalGroup:
    group_id: str
    label: str
    display_order: int = 0
    checks: list = field(default_factory=list)


@dataclass
class StubDocTypeNode:
    type_code: str
    name: str
    checks: list = field(default_factory=list)


@dataclass
class StubDocTypeClass:
    group_id: str
    label: str
    display_order: int = 0
    types: list = field(default_factory=list)


@dataclass
class StubDocumentMeta:
    document_id: str
    filename: str
    doc_type: str | None = None
    status: str = "completed"
    folder_path: str | None = None


@dataclass
class StubResponse:
    deal_id: str = "deal-1"
    run_id: str = "run-1"
    global_groups: list = field(default_factory=list)
    doc_type_classes: list = field(default_factory=list)
    column_registry: dict = field(default_factory=dict)
    cell_values: dict = field(default_factory=dict)
    drawer_contents: dict = field(default_factory=dict)
    documents_meta: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_minimal_response() -> StubResponse:
    col = StubColumn("chk__flag", label="Согласие", format="yes_no")
    subgroup = StubCheckSubgroup("chk", "Check", columns=[col])
    group = StubGlobalGroup("core", "Основные", 0, [subgroup])

    cell_defined = StubCell("defined", "Да", "yes")
    cell_na = StubCell("not_applicable", "н/о")
    cell_err = StubCell("error", "⚠ Ошибка")

    drawer = StubDrawer(
        check_id="chk",
        check_name="Check",
        document_id="doc-1",
        reason="Clause found",
        evidence_items=["п. 1.1"],
        fields=[StubDrawerField(location_clause_ref="п. 1.1", location_page=3)],
    )

    return StubResponse(
        deal_id="deal-42",
        run_id="run-99",
        global_groups=[group],
        doc_type_classes=[],
        column_registry={"chk__flag": col},
        cell_values={"doc-1": {"chk__flag": cell_defined, "chk__na": cell_na, "chk__err": cell_err}},
        drawer_contents={"doc-1": {"chk": drawer}},
        documents_meta=[StubDocumentMeta("doc-1", "contract.pdf", "nda")],
    )


# ---------------------------------------------------------------------------
# Tests: count_cell_states
# ---------------------------------------------------------------------------


def test_count_cell_states_returns_zeroes_for_empty_response() -> None:
    result = count_cell_states({})
    assert result["defined"] == 0
    assert result["not_defined"] == 0
    assert result["not_applicable"] == 0
    assert result["not_executed"] == 0
    assert result["error"] == 0


def test_count_cell_states_counts_all_states() -> None:
    cell_values = {
        "doc-1": {
            "col-a": StubCell("defined"),
            "col-b": StubCell("not_defined"),
            "col-c": StubCell("not_applicable"),
            "col-d": StubCell("not_executed"),
            "col-e": StubCell("error"),
        },
        "doc-2": {
            "col-a": StubCell("defined"),
            "col-b": StubCell("defined"),
        },
    }

    result = count_cell_states(cell_values)

    assert result["defined"] == 3
    assert result["not_defined"] == 1
    assert result["not_applicable"] == 1
    assert result["not_executed"] == 1
    assert result["error"] == 1


def test_count_cell_states_works_with_dict_cells() -> None:
    cell_values = {
        "doc-1": {
            "col-a": {"cell_state": "defined", "display_value": "Да"},
            "col-b": {"cell_state": "not_defined", "display_value": "—"},
        }
    }

    result = count_cell_states(cell_values)

    assert result["defined"] == 1
    assert result["not_defined"] == 1


# ---------------------------------------------------------------------------
# Tests: collect_sample_cells
# ---------------------------------------------------------------------------


def test_collect_sample_cells_prefers_error_over_defined() -> None:
    cell_values = {
        "doc-1": {
            "col-a": StubCell("defined", "Да"),
            "col-b": StubCell("error", "⚠ Ошибка"),
        }
    }

    samples = collect_sample_cells(cell_values, limit=2)

    assert len(samples) == 2
    assert samples[0]["cell_state"] == "error"
    assert samples[1]["cell_state"] == "defined"


def test_collect_sample_cells_respects_limit() -> None:
    cell_values = {
        "doc-1": {f"col-{i}": StubCell("defined") for i in range(10)},
    }

    samples = collect_sample_cells(cell_values, limit=3)

    assert len(samples) == 3


def test_collect_sample_cells_includes_location_info() -> None:
    cell_values = {
        "doc-1": {
            "col-a": StubCell(
                "defined",
                "Значение",
                "raw",
                location_clause_ref="п. 3.1",
                location_page=5,
                location_confidence="high",
                location_source="per_field",
            ),
        }
    }

    samples = collect_sample_cells(cell_values, limit=1)

    assert samples[0]["location_clause_ref"] == "п. 3.1"
    assert samples[0]["location_page"] == 5
    assert samples[0]["location_confidence"] == "high"
    assert samples[0]["location_source"] == "per_field"


def test_collect_sample_cells_includes_location_source() -> None:
    cell_values = {
        "doc-1": {
            "col-a": StubCell(
                "defined",
                "Значение",
                "raw",
                location_clause_ref="main:12.1",
                location_page=9,
                location_confidence="low",
                location_source="display_text",
            ),
        }
    }

    samples = collect_sample_cells(cell_values, limit=1)

    assert samples[0]["location_source"] == "display_text"
    assert samples[0]["location_clause_ref"] == "main:12.1"
    assert samples[0]["location_page"] == 9


def test_collect_sample_cells_returns_empty_for_empty_input() -> None:
    samples = collect_sample_cells({}, limit=5)
    assert samples == []


# ---------------------------------------------------------------------------
# Tests: collect_sample_drawers
# ---------------------------------------------------------------------------


def test_collect_sample_drawers_prefers_drawers_with_reason_and_evidence() -> None:
    drawer_rich = StubDrawer(
        "chk-a", "A", "doc-1",
        reason="Найдено", evidence_items=["п. 1.1"],
        fields=[StubDrawerField(location_clause_ref="п. 1.1")],
    )
    drawer_empty = StubDrawer("chk-b", "B", "doc-1")

    drawer_contents = {
        "doc-1": {
            "chk-b": drawer_empty,
            "chk-a": drawer_rich,
        }
    }

    samples = collect_sample_drawers(drawer_contents, limit=2)

    assert samples[0]["check_id"] == "chk-a"
    assert samples[0]["evidence_items"] == ["п. 1.1"]


def test_collect_sample_drawers_includes_location_stats() -> None:
    field_exact = StubDrawerField(
        location_clause_ref="п. 3.1",
        location_page=5,
        location_source="per_field",
    )
    field_non_per_field = StubDrawerField(
        location_clause_ref="main:12.1",
        location_source="canonical_check",
    )

    drawer = StubDrawer(
        "chk", "Check", "doc-1",
        fields=[field_exact, field_non_per_field],
    )

    samples = collect_sample_drawers({"doc-1": {"chk": drawer}}, limit=1)

    assert samples[0]["fields_with_location"] == 2
    assert samples[0]["fields_with_non_per_field_location"] == 1


def test_collect_sample_drawers_returns_empty_for_empty_input() -> None:
    samples = collect_sample_drawers({}, limit=5)
    assert samples == []


def test_collect_sample_drawers_respects_limit() -> None:
    drawers = {
        "doc-1": {f"chk-{i}": StubDrawer(f"chk-{i}", f"C{i}", "doc-1") for i in range(10)}
    }

    samples = collect_sample_drawers(drawers, limit=3)

    assert len(samples) == 3


# ---------------------------------------------------------------------------
# Tests: build_summary
# ---------------------------------------------------------------------------


def test_build_summary_counts_groups_columns_documents() -> None:
    response = _make_minimal_response()
    summary = build_summary(response, sample_limit=5)

    assert summary["deal_id"] == "deal-42"
    assert summary["run_id"] == "run-99"
    assert summary["counts"]["global_groups"] == 1
    assert summary["counts"]["doc_type_classes"] == 0
    assert summary["counts"]["columns"] == 1
    assert summary["counts"]["documents"] == 1
    assert summary["counts"]["cells"] == 3
    assert summary["counts"]["drawers"] == 1


def test_build_summary_cell_states_distribution() -> None:
    response = _make_minimal_response()
    summary = build_summary(response, sample_limit=5)

    states = summary["cell_states"]
    assert states["defined"] == 1
    assert states["not_applicable"] == 1
    assert states["error"] == 1


def test_build_summary_handles_empty_response_gracefully() -> None:
    response = StubResponse()
    summary = build_summary(response, sample_limit=5)

    assert summary["counts"]["global_groups"] == 0
    assert summary["counts"]["columns"] == 0
    assert summary["counts"]["documents"] == 0
    assert summary["counts"]["cells"] == 0
    assert summary["cell_states"]["defined"] == 0


def test_build_summary_includes_location_flags() -> None:
    col = StubColumn("chk__val")
    cell_exact = StubCell(
        "defined", "Да", "yes",
        location_clause_ref="п. 1.1", location_page=3,
        location_source="per_field",
    )
    cell_approx = StubCell(
        "defined", "Нет", "no",
        location_clause_ref="main:12.1", location_page=9,
        location_source="canonical_check",
    )

    response = StubResponse(
        column_registry={"chk__val": col},
        cell_values={
            "doc-1": {"chk__val": cell_exact},
            "doc-2": {"chk__val": cell_approx},
        },
        documents_meta=[
            StubDocumentMeta("doc-1", "a.pdf"),
            StubDocumentMeta("doc-2", "b.pdf"),
        ],
    )

    summary = build_summary(response, sample_limit=5)

    assert summary["location"]["cells_with_exact_location"] == 1
    assert summary["location"]["cells_with_approximate_location"] == 1


def test_build_summary_includes_drawer_stats() -> None:
    response = _make_minimal_response()
    summary = build_summary(response, sample_limit=5)

    assert summary["drawers"]["with_reason"] == 1
    assert summary["drawers"]["with_evidence"] == 1


def test_build_summary_samples_are_bounded_by_limit() -> None:
    groups = [StubGlobalGroup(f"g{i}", f"Group {i}", i) for i in range(20)]
    response = StubResponse(global_groups=groups)

    summary = build_summary(response, sample_limit=3)

    assert len(summary["samples"]["groups"]) == 3


def test_build_summary_works_with_dict_response() -> None:
    """build_summary должен работать с dict, а не только с dataclass."""
    response = {
        "deal_id": "d1",
        "run_id": "r1",
        "global_groups": [],
        "doc_type_classes": [],
        "column_registry": {},
        "cell_values": {},
        "drawer_contents": {},
        "documents_meta": [],
    }

    summary = build_summary(response, sample_limit=5)

    assert summary["deal_id"] == "d1"
    assert summary["counts"]["columns"] == 0


# ---------------------------------------------------------------------------
# Tests: check_health
# ---------------------------------------------------------------------------


def test_check_health_ok_when_columns_and_documents_present() -> None:
    summary = build_summary(_make_minimal_response(), sample_limit=5)
    is_healthy, warnings = check_health(summary)

    assert is_healthy is True
    assert warnings == []


def test_check_health_warns_when_no_columns() -> None:
    response = StubResponse(
        documents_meta=[StubDocumentMeta("doc-1", "a.pdf")],
    )
    summary = build_summary(response, sample_limit=5)
    is_healthy, warnings = check_health(summary)

    assert is_healthy is False
    assert any("column_registry" in w for w in warnings)


def test_check_health_warns_when_no_documents() -> None:
    col = StubColumn("chk__val")
    response = StubResponse(column_registry={"chk__val": col})
    summary = build_summary(response, sample_limit=5)
    is_healthy, warnings = check_health(summary)

    assert is_healthy is False
    assert any("documents_meta" in w for w in warnings)


def test_check_health_warns_when_majority_error_cells() -> None:
    col = StubColumn("chk__val")
    # 9 ошибок из 10 ячеек
    error_cells = {f"col-{i}": StubCell("error") for i in range(9)}
    error_cells["col-ok"] = StubCell("defined")

    response = StubResponse(
        column_registry={"chk__val": col},
        cell_values={"doc-1": error_cells},
        documents_meta=[StubDocumentMeta("doc-1", "a.pdf")],
    )
    summary = build_summary(response, sample_limit=5)
    _, warnings = check_health(summary)

    assert any("error" in w for w in warnings)


# ---------------------------------------------------------------------------
# Tests: V1.10 — fallback location без pinpoint ref/page
# ---------------------------------------------------------------------------


def test_build_summary_counts_approximate_location_without_ref_page() -> None:
    """
    Реальный кейс: location_source='canonical_check', но clause_ref=None, page=None.
    Summary должен считать такие ячейки как approximate, а не игнорировать.
    """
    col = StubColumn("chk__val")
    cell_approx_no_ref = StubCell(
        "defined", "Присутствует", "present",
        location_clause_ref=None,
        location_page=None,
        location_confidence="low",
        location_source="canonical_check",
    )

    response = StubResponse(
        column_registry={"chk__val": col},
        cell_values={"doc-1": {"chk__val": cell_approx_no_ref}},
        documents_meta=[StubDocumentMeta("doc-1", "a.pdf")],
    )

    summary = build_summary(response, sample_limit=5)

    assert summary["location"]["cells_with_approximate_location"] == 1
    assert summary["location"]["cells_with_exact_location"] == 0


def test_build_summary_does_not_count_approximate_as_exact_location() -> None:
    """
    Ячейка с location_source='canonical_check' и clause_ref/page заполненными
    (canonical ref) НЕ должна попадать в exact.
    """
    col = StubColumn("chk__val")
    cell_approx_with_ref = StubCell(
        "defined", "РФ", "РФ",
        location_clause_ref="main:12.1",
        location_page=9,
        location_confidence="low",
        location_source="canonical_check",
    )
    cell_exact = StubCell(
        "defined", "Да", "yes",
        location_clause_ref="п. 1.2",
        location_page=3,
        location_confidence="high",
        location_source="per_field",
    )

    response = StubResponse(
        column_registry={"chk__val": col},
        cell_values={
            "doc-1": {"chk__val": cell_approx_with_ref},
            "doc-2": {"chk__val": cell_exact},
        },
        documents_meta=[
            StubDocumentMeta("doc-1", "a.pdf"),
            StubDocumentMeta("doc-2", "b.pdf"),
        ],
    )

    summary = build_summary(response, sample_limit=5)

    assert summary["location"]["cells_with_exact_location"] == 1
    assert summary["location"]["cells_with_approximate_location"] == 1


def test_collect_sample_cells_preserves_location_source_without_ref_page() -> None:
    """
    Sample cells должны содержать location_source, даже если ref/page = None.
    """
    cell_values = {
        "doc-1": {
            "col-a": StubCell(
                "defined", "Присутствует", "present",
                location_clause_ref=None,
                location_page=None,
                location_confidence="low",
                location_source="canonical_check",
            ),
        }
    }

    samples = collect_sample_cells(cell_values, limit=1)

    assert len(samples) == 1
    assert samples[0]["location_source"] == "canonical_check"
    assert samples[0]["location_clause_ref"] is None
    assert samples[0]["location_page"] is None


    