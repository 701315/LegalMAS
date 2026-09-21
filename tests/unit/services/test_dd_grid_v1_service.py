# tests/unit/services/test_dd_grid_v1_service.py

"""
Unit tests для _map_dd_grid_v1_to_response() в deal_review_service.

build_dd_grid_v1_response() тестируется интеграционно (требует БД),
поэтому здесь тестируем только маппинг runtime → Pydantic DTO.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from api.schemas.deal_review import DDGridV1ResponseDTO
from engine.checks.dd_grid_column_builder import DDGridColumnRuntime
from engine.playbook.models import (
    AllowedValueSpec,
    CheckDefinition,
    ExtractionConfig,
    ExtractionFieldConfig,
    ExtractionFieldType,
)
from services.dd_grid_v1_builder import (
    CellValueDTO,
    CheckSubgroupDTO,
    DDGridV1Data,
    DocTypeClassDTO,
    DocTypeNodeDTO,
    DocumentMetaDTO,
    DrawerContentDTO,
    DrawerFieldDTO,
    GlobalGroupDTO,
)
from services.deal_review_service import (
    _collect_dd_grid_v1_checks,
    _map_dd_grid_v1_to_response,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_column(
    column_id: str,
    *,
    label: str = "Label",
    fmt: str = "text",
    fallback: str = "—",
    display_order: int = 0,
    enum_labels: dict | None = None,
    unit: str | None = None,
) -> DDGridColumnRuntime:
    return DDGridColumnRuntime(
        column_id=column_id,
        label=label,
        value_field=column_id.split("__")[-1] if "__" in column_id else None,
        status_field=None,
        status_present_value=None,
        format=fmt,
        fallback_display=fallback,
        display_order=display_order,
        enum_labels=enum_labels or {},
        unit=unit,
    )


def _make_subgroup(check_id: str, columns: list[DDGridColumnRuntime]) -> CheckSubgroupDTO:
    return CheckSubgroupDTO(
        check_id=check_id,
        check_name=f"Check {check_id}",
        display_order=0,
        columns=columns,
        display_summary_field=None,
        metadata_fields=["reason", "evidence"],
    )


def _make_cell(
    cell_state: str = "defined",
    display_value: str = "Да",
    raw_value=None,
    *,
    location_clause_ref: str | None = None,
    location_page: int | None = None,
    location_confidence: str | None = None,
    location_source: str = "none",
) -> CellValueDTO:
    return CellValueDTO(
        cell_state=cell_state,
        display_value=display_value,
        raw_value=raw_value,
        location_source=location_source,
        location_clause_ref=location_clause_ref,
        location_page=location_page,
        location_confidence=location_confidence,
    )


def _make_drawer(
    check_id: str,
    doc_id: str,
    *,
    cell_state: str = "defined",
    reason: str | None = None,
    fields: list | None = None,
    evidence_items: list | None = None,
) -> DrawerContentDTO:
    return DrawerContentDTO(
        check_id=check_id,
        check_name=f"Check {check_id}",
        document_id=doc_id,
        cell_state=cell_state,
        reason=reason,
        review_status=None,
        review_message=None,
        display_text=None,
        execution_status="SUCCESS",
        fields=fields or [],
        evidence_items=evidence_items or [],
    )


def _make_minimal_data(
    *,
    deal_id: str = "deal-1",
    run_id: str = "run-1",
) -> tuple[DDGridV1Data, str, str]:
    col = _make_column("consent_check__flag", label="Согласие", fmt="yes_no")
    subgroup = _make_subgroup("consent_check", [col])

    global_group = GlobalGroupDTO(
        group_id="core",
        label="Основные проверки",
        display_order=0,
        checks=[subgroup],
    )

    doc_id = "doc-abc"
    cell = _make_cell("defined", "Да", "yes")
    drawer = _make_drawer("consent_check", doc_id, reason="Согласие найдено")

    data = DDGridV1Data(
        global_groups=[global_group],
        doc_type_classes=[],
        column_registry={"consent_check__flag": col},
        cell_values={doc_id: {"_default": {"consent_check__flag": cell}}},
        drawer_contents={doc_id: {"_default": {"consent_check": drawer}}},
        documents_meta=[
            DocumentMetaDTO(
                document_id=doc_id,
                filename="contract.pdf",
                doc_type="nda",
                status="completed",
                folder_path="01. Legal",
            )
        ],
    )
    return data, deal_id, run_id


# ---------------------------------------------------------------------------
# Tests: response structure
# ---------------------------------------------------------------------------


def test_response_has_correct_deal_and_run_ids() -> None:
    data, deal_id, run_id = _make_minimal_data(deal_id="deal-42", run_id="run-99")
    response = _map_dd_grid_v1_to_response(data, deal_id, run_id)

    assert response.deal_id == "deal-42"
    assert response.run_id == "run-99"
    assert isinstance(response, DDGridV1ResponseDTO)


def test_response_column_registry_contains_all_columns() -> None:
    data, deal_id, run_id = _make_minimal_data()
    response = _map_dd_grid_v1_to_response(data, deal_id, run_id)

    assert "consent_check__flag" in response.column_registry
    col_dto = response.column_registry["consent_check__flag"]
    assert col_dto.label == "Согласие"
    assert col_dto.format == "yes_no"
    assert col_dto.check_id == "consent_check"


def test_response_global_groups_structure() -> None:
    data, deal_id, run_id = _make_minimal_data()
    response = _map_dd_grid_v1_to_response(data, deal_id, run_id)

    assert len(response.global_groups) == 1
    group = response.global_groups[0]
    assert group.group_id == "core"
    assert group.label == "Основные проверки"
    assert len(group.checks) == 1
    assert group.checks[0].check_id == "consent_check"
    assert len(group.checks[0].columns) == 1
    assert group.checks[0].columns[0].column_id == "consent_check__flag"


def test_response_doc_type_classes_empty_when_none() -> None:
    data, deal_id, run_id = _make_minimal_data()
    response = _map_dd_grid_v1_to_response(data, deal_id, run_id)

    assert response.doc_type_classes == []


def test_response_doc_type_classes_with_data() -> None:
    col = _make_column("nda_check__flag", label="NDA Flag", fmt="yes_no")
    subgroup = _make_subgroup("nda_check", [col])

    data = DDGridV1Data(
        global_groups=[],
        doc_type_classes=[
            DocTypeClassDTO(
                group_id="group_legal",
                label="Правовые",
                display_order=10,
                types=[
                    DocTypeNodeDTO(
                        type_code="nda",
                        name="NDA",
                        checks=[subgroup],
                    )
                ],
            )
        ],
        column_registry={"nda_check__flag": col},
        cell_values={},
        drawer_contents={},
        documents_meta=[],
    )

    response = _map_dd_grid_v1_to_response(data, "deal-1", "run-1")

    assert len(response.doc_type_classes) == 1
    cls_dto = response.doc_type_classes[0]
    assert cls_dto.group_id == "group_legal"
    assert cls_dto.label == "Правовые"
    assert len(cls_dto.types) == 1
    assert cls_dto.types[0].type_code == "nda"
    assert cls_dto.types[0].checks[0].check_id == "nda_check"


def test_response_cell_values_mapped_correctly() -> None:
    data, deal_id, run_id = _make_minimal_data()
    response = _map_dd_grid_v1_to_response(data, deal_id, run_id)

    doc_id = "doc-abc"
    assert doc_id in response.cell_values
    cell_dto = response.cell_values[doc_id]["_default"]["consent_check__flag"]
    assert cell_dto.cell_state == "defined"
    assert cell_dto.display_value == "Да"
    assert cell_dto.raw_value == "yes"


def test_response_cell_values_location_propagated() -> None:
    col = _make_column("chk__val")
    subgroup = _make_subgroup("chk", [col])
    doc_id = "doc-1"
    cell = _make_cell(
        "defined",
        "Значение",
        "raw",
        location_clause_ref="п. 1.2",
        location_page=5,
        location_confidence="high",
        location_source="per_field",
    )
    drawer = _make_drawer("chk", doc_id)

    data = DDGridV1Data(
        global_groups=[GlobalGroupDTO("g", "G", 0, [subgroup])],
        doc_type_classes=[],
        column_registry={"chk__val": col},
        cell_values={doc_id: {"_default": {"chk__val": cell}}},
        drawer_contents={doc_id: {"_default": {"chk": drawer}}},
        documents_meta=[DocumentMetaDTO(doc_id, "f.pdf", "nda", "completed")],
    )

    response = _map_dd_grid_v1_to_response(data, "d", "r")

    cell_dto = response.cell_values[doc_id]["_default"]["chk__val"]
    assert cell_dto.location_clause_ref == "п. 1.2"
    assert cell_dto.location_page == 5
    assert cell_dto.location_confidence == "high"
    assert cell_dto.location_source == "per_field"


def test_response_cell_values_location_fallback_propagated() -> None:
    col = _make_column("chk__val")
    subgroup = _make_subgroup("chk", [col])
    doc_id = "doc-1"
    cell = _make_cell(
        "defined",
        "Значение",
        "raw",
        location_clause_ref="main:12.1",
        location_page=9,
        location_confidence="low",
        location_source="display_text",
    )
    drawer = _make_drawer("chk", doc_id)

    data = DDGridV1Data(
        global_groups=[GlobalGroupDTO("g", "G", 0, [subgroup])],
        doc_type_classes=[],
        column_registry={"chk__val": col},
        cell_values={doc_id: {"_default": {"chk__val": cell}}},
        drawer_contents={doc_id: {"_default": {"chk": drawer}}},
        documents_meta=[DocumentMetaDTO(doc_id, "f.pdf", "nda", "completed")],
    )

    response = _map_dd_grid_v1_to_response(data, "d", "r")

    cell_dto = response.cell_values[doc_id]["_default"]["chk__val"]
    assert cell_dto.location_source == "display_text"
    assert cell_dto.location_page == 9


def test_response_drawer_contents_mapped_correctly() -> None:
    data, deal_id, run_id = _make_minimal_data()
    response = _map_dd_grid_v1_to_response(data, deal_id, run_id)

    doc_id = "doc-abc"
    assert doc_id in response.drawer_contents
    drawer_dto = response.drawer_contents[doc_id]["_default"]["consent_check"]
    assert drawer_dto.check_id == "consent_check"
    assert drawer_dto.document_id == doc_id
    assert drawer_dto.reason == "Согласие найдено"
    assert drawer_dto.cell_state == "defined"
    assert drawer_dto.execution_status == "SUCCESS"


def test_response_drawer_fields_propagated() -> None:
    col = _make_column("chk__val", label="Значение")
    subgroup = _make_subgroup("chk", [col])
    doc_id = "doc-1"
    cell = _make_cell()

    drawer_field = DrawerFieldDTO(
        column_id="chk__val",
        field_name="val",
        label="Значение",
        cell_state="defined",
        display_value="Текст",
        raw_value="Текст",
        location_source="per_field",
        location_clause_ref="п. 3.1",
        location_page=3,
        location_confidence="high",
    )
    drawer = _make_drawer("chk", doc_id, fields=[drawer_field])

    data = DDGridV1Data(
        global_groups=[GlobalGroupDTO("g", "G", 0, [subgroup])],
        doc_type_classes=[],
        column_registry={"chk__val": col},
        cell_values={doc_id: {"_default": {"chk__val": cell}}},
        drawer_contents={doc_id: {"_default": {"chk": drawer}}},
        documents_meta=[DocumentMetaDTO(doc_id, "f.pdf", "nda", "completed")],
    )

    response = _map_dd_grid_v1_to_response(data, "d", "r")

    field_dto = response.drawer_contents[doc_id]["_default"]["chk"].fields[0]
    assert field_dto.column_id == "chk__val"
    assert field_dto.label == "Значение"
    assert field_dto.location_clause_ref == "п. 3.1"
    assert field_dto.location_page == 3
    assert field_dto.location_confidence == "high"


def test_response_drawer_evidence_items_propagated() -> None:
    col = _make_column("chk__val")
    subgroup = _make_subgroup("chk", [col])
    doc_id = "doc-1"
    cell = _make_cell()
    drawer = _make_drawer("chk", doc_id, evidence_items=["п. 1.1", "п. 2.3"])

    data = DDGridV1Data(
        global_groups=[GlobalGroupDTO("g", "G", 0, [subgroup])],
        doc_type_classes=[],
        column_registry={"chk__val": col},
        cell_values={doc_id: {"_default": {"chk__val": cell}}},
        drawer_contents={doc_id: {"_default": {"chk": drawer}}},
        documents_meta=[DocumentMetaDTO(doc_id, "f.pdf", "nda", "completed")],
    )

    response = _map_dd_grid_v1_to_response(data, "d", "r")

    assert response.drawer_contents[doc_id]["_default"]["chk"].evidence_items == ["п. 1.1", "п. 2.3"]


def test_response_documents_meta_mapped_correctly() -> None:
    data, deal_id, run_id = _make_minimal_data()
    response = _map_dd_grid_v1_to_response(data, deal_id, run_id)

    assert len(response.documents_meta) == 1
    meta_dto = response.documents_meta[0]
    assert meta_dto.document_id == "doc-abc"
    assert meta_dto.filename == "contract.pdf"
    assert meta_dto.doc_type == "nda"
    assert meta_dto.status == "completed"
    assert meta_dto.folder_path == "01. Legal"


def test_response_column_check_id_extracted_from_column_id() -> None:
    """column_id формат '{check_id}__{field}' — check_id извлекается split'ом."""
    col = _make_column("my_check__some_field", label="Field")
    subgroup = _make_subgroup("my_check", [col])

    data = DDGridV1Data(
        global_groups=[GlobalGroupDTO("g", "G", 0, [subgroup])],
        doc_type_classes=[],
        column_registry={"my_check__some_field": col},
        cell_values={},
        drawer_contents={},
        documents_meta=[],
    )

    response = _map_dd_grid_v1_to_response(data, "d", "r")

    col_dto = response.column_registry["my_check__some_field"]
    assert col_dto.check_id == "my_check"


def test_response_enum_labels_preserved() -> None:
    col = _make_column(
        "license__mode",
        fmt="enum",
        enum_labels={"exclusive": "Эксклюзивная", "non_exclusive": "Неисключительная"},
    )
    subgroup = _make_subgroup("license", [col])

    data = DDGridV1Data(
        global_groups=[GlobalGroupDTO("g", "G", 0, [subgroup])],
        doc_type_classes=[],
        column_registry={"license__mode": col},
        cell_values={},
        drawer_contents={},
        documents_meta=[],
    )

    response = _map_dd_grid_v1_to_response(data, "d", "r")

    col_dto = response.column_registry["license__mode"]
    assert col_dto.enum_labels == {"exclusive": "Эксклюзивная", "non_exclusive": "Неисключительная"}


def test_response_unit_preserved_in_column() -> None:
    col = _make_column("penalty__amount", label="Штраф", unit="RUB")
    subgroup = _make_subgroup("penalty", [col])

    data = DDGridV1Data(
        global_groups=[GlobalGroupDTO("g", "G", 0, [subgroup])],
        doc_type_classes=[],
        column_registry={"penalty__amount": col},
        cell_values={},
        drawer_contents={},
        documents_meta=[],
    )

    response = _map_dd_grid_v1_to_response(data, "d", "r")

    col_dto = response.column_registry["penalty__amount"]
    assert col_dto.unit == "RUB"


def test_response_subgroup_metadata_fields_preserved() -> None:
    col = _make_column("chk__val")
    subgroup = CheckSubgroupDTO(
        check_id="chk",
        check_name="Check chk",
        display_order=5,
        columns=[col],
        display_summary_field="chk__display",
        metadata_fields=["reason", "evidence", "notes"],
    )

    data = DDGridV1Data(
        global_groups=[GlobalGroupDTO("g", "G", 0, [subgroup])],
        doc_type_classes=[],
        column_registry={"chk__val": col},
        cell_values={},
        drawer_contents={},
        documents_meta=[],
    )

    response = _map_dd_grid_v1_to_response(data, "d", "r")

    subgroup_dto = response.global_groups[0].checks[0]
    assert subgroup_dto.display_summary_field == "chk__display"
    assert subgroup_dto.metadata_fields == ["reason", "evidence", "notes"]
    assert subgroup_dto.display_order == 5

# ---------------------------------------------------------------------------
# Tests: _collect_dd_grid_v1_checks (B1 — doc-type checks in DD Grid V1)
# ---------------------------------------------------------------------------


def _make_check(
    check_id: str,
    *,
    name: str | None = None,
    origin: str = "GLOBAL_PLAYBOOK",
    doc_types: list[str] | None = None,
) -> CheckDefinition:
    return CheckDefinition(
        id=check_id,
        name=name or check_id,
        origin=origin,
        doc_types=doc_types or [],
    )


class _FakeDocTypeLoader:
    """
    Тестовый двойник DocTypeCheckLoader.

    Возвращает заранее заданный набор checks по (doc_type, triggers).
    """

    def __init__(self, mapping: dict[str, list[CheckDefinition]]) -> None:
        self._mapping = mapping
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def load_checks_for_doc(
        self,
        doc_type: str,
        applicable_triggers: list[str],
    ) -> list[CheckDefinition]:
        self.calls.append((doc_type, tuple(applicable_triggers)))
        return list(self._mapping.get(doc_type, []))


def test_collect_checks_returns_only_global_when_no_doc_type_results() -> None:
    """
    Global-only run: check_results содержит только GLOBAL_PLAYBOOK.
    Helper НЕ должен подтягивать doc-type checks — иначе grid заполнится
    not_executed ячейками для checks, которые не запускались.
    """
    global_checks = [_make_check("global_a"), _make_check("global_b")]
    check_results = [
        {"check_id": "global_a", "origin": "GLOBAL_PLAYBOOK"},
        {"check_id": "global_b", "origin": "GLOBAL_PLAYBOOK"},
    ]
    documents = {
        "doc-1": {"doc_type": "contract_1.6_real_estate", "applicable_triggers": ["t1"]},
    }
    loader = _FakeDocTypeLoader({"contract_1.6_real_estate": [_make_check("dt_x", origin="DOCUMENT_TYPE", doc_types=["contract_1.6_real_estate"])]})

    result = _collect_dd_grid_v1_checks(
        playbook_checks=global_checks,
        check_results=check_results,
        documents=documents,
        doc_type_loader=loader,
    )

    assert [c.id for c in result] == ["global_a", "global_b"]
    assert loader.calls == []  # loader не должен вызываться вообще


def test_collect_checks_adds_doc_type_checks_when_results_present() -> None:
    """
    global_and_doc_type run: check_results содержит DOCUMENT_TYPE записи.
    Helper должен подтянуть doc-type CheckDefinition через loader.
    """
    global_checks = [_make_check("global_a")]
    check_results = [
        {"check_id": "global_a", "origin": "GLOBAL_PLAYBOOK"},
        {"check_id": "dt_check_1", "origin": "DOCUMENT_TYPE"},
        {"check_id": "dt_check_2", "origin": "DOCUMENT_TYPE"},
    ]
    documents = {
        "doc-1": {"doc_type": "contract_1.6_real_estate", "applicable_triggers": ["t1"]},
    }
    loader = _FakeDocTypeLoader({
        "contract_1.6_real_estate": [
            _make_check("dt_check_1", origin="DOCUMENT_TYPE", doc_types=["contract_1.6_real_estate"]),
            _make_check("dt_check_2", origin="DOCUMENT_TYPE", doc_types=["contract_1.6_real_estate"]),
        ]
    })

    result = _collect_dd_grid_v1_checks(
        playbook_checks=global_checks,
        check_results=check_results,
        documents=documents,
        doc_type_loader=loader,
    )

    ids = [c.id for c in result]
    assert ids == ["global_a", "dt_check_1", "dt_check_2"]
    assert loader.calls == [("contract_1.6_real_estate", ("t1",))]


def test_collect_checks_filters_loaded_doc_type_checks_by_present_result_ids() -> None:
    """
    Loader вернул 3 doc-type checks для YAML, но только 1 из них реально
    выполнялся в этом run (есть в check_results). Helper оставляет только его.
    """
    global_checks = [_make_check("global_a")]
    check_results = [
        {"check_id": "global_a", "origin": "GLOBAL_PLAYBOOK"},
        {"check_id": "dt_executed", "origin": "DOCUMENT_TYPE"},
    ]
    documents = {
        "doc-1": {"doc_type": "contract_2.1_lease", "applicable_triggers": []},
    }
    loader = _FakeDocTypeLoader({
        "contract_2.1_lease": [
            _make_check("dt_executed", origin="DOCUMENT_TYPE", doc_types=["contract_2.1_lease"]),
            _make_check("dt_not_executed_1", origin="DOCUMENT_TYPE", doc_types=["contract_2.1_lease"]),
            _make_check("dt_not_executed_2", origin="DOCUMENT_TYPE", doc_types=["contract_2.1_lease"]),
        ]
    })

    result = _collect_dd_grid_v1_checks(
        playbook_checks=global_checks,
        check_results=check_results,
        documents=documents,
        doc_type_loader=loader,
    )

    ids = [c.id for c in result]
    assert ids == ["global_a", "dt_executed"]


def test_collect_checks_merges_duplicate_doc_type_checks_from_multiple_documents() -> None:
    """
    Два документа разных типов вернули одинаковый check_id из loader.
    Helper дедуплицирует и объединяет doc_types в одну CheckDefinition.
    """
    global_checks: list[CheckDefinition] = []
    check_results = [
        {"check_id": "shared_check", "origin": "DOCUMENT_TYPE"},
    ]
    documents = {
        "doc-1": {"doc_type": "contract_1.6_real_estate", "applicable_triggers": []},
        "doc-2": {"doc_type": "contract_2.1_lease", "applicable_triggers": []},
    }
    loader = _FakeDocTypeLoader({
        "contract_1.6_real_estate": [
            _make_check("shared_check", origin="DOCUMENT_TYPE", doc_types=["contract_1.6_real_estate"]),
        ],
        "contract_2.1_lease": [
            _make_check("shared_check", origin="DOCUMENT_TYPE", doc_types=["contract_2.1_lease"]),
        ],
    })

    result = _collect_dd_grid_v1_checks(
        playbook_checks=global_checks,
        check_results=check_results,
        documents=documents,
        doc_type_loader=loader,
    )

    assert len(result) == 1
    assert result[0].id == "shared_check"
    assert set(result[0].doc_types) == {"contract_1.6_real_estate", "contract_2.1_lease"}


def test_collect_checks_deduplicates_same_doc_type_across_documents() -> None:
    """
    Два документа одного типа не должны вызывать loader дважды.
    """
    global_checks: list[CheckDefinition] = []
    check_results = [
        {"check_id": "dt_check", "origin": "DOCUMENT_TYPE"},
    ]
    documents = {
        "doc-1": {"doc_type": "contract_1.6_real_estate", "applicable_triggers": ["t1"]},
        "doc-2": {"doc_type": "contract_1.6_real_estate", "applicable_triggers": ["t1"]},
    }
    loader = _FakeDocTypeLoader({
        "contract_1.6_real_estate": [
            _make_check("dt_check", origin="DOCUMENT_TYPE", doc_types=["contract_1.6_real_estate"]),
        ],
    })

    result = _collect_dd_grid_v1_checks(
        playbook_checks=global_checks,
        check_results=check_results,
        documents=documents,
        doc_type_loader=loader,
    )

    assert len(result) == 1
    assert result[0].id == "dt_check"
    assert loader.calls == [("contract_1.6_real_estate", ("t1",))]


def test_collect_checks_handles_documents_without_doc_type_gracefully() -> None:
    """
    Документ без doc_type не должен ломать loader.
    """
    global_checks = [_make_check("global_a")]
    check_results = [
        {"check_id": "global_a", "origin": "GLOBAL_PLAYBOOK"},
        {"check_id": "dt_check", "origin": "DOCUMENT_TYPE"},
    ]
    documents = {
        "doc-1": {"doc_type": None, "applicable_triggers": []},
        "doc-2": {"doc_type": "contract_2.1_lease", "applicable_triggers": []},
    }
    loader = _FakeDocTypeLoader({
        "contract_2.1_lease": [
            _make_check("dt_check", origin="DOCUMENT_TYPE", doc_types=["contract_2.1_lease"]),
        ],
    })

    result = _collect_dd_grid_v1_checks(
        playbook_checks=global_checks,
        check_results=check_results,
        documents=documents,
        doc_type_loader=loader,
    )

    ids = [c.id for c in result]
    assert ids == ["global_a", "dt_check"]
    # Только contract_2.1_lease должен вызываться
    assert loader.calls == [("contract_2.1_lease", ())]


def test_collect_checks_survives_loader_exception() -> None:
    """
    Если loader падает для одного doc_type, helper продолжает работу.
    """
    class _RaisingLoader:
        def __init__(self) -> None:
            self.calls = 0

        def load_checks_for_doc(self, doc_type: str, applicable_triggers: list[str]):
            self.calls += 1
            raise RuntimeError("YAML load failed")

    global_checks = [_make_check("global_a")]
    check_results = [
        {"check_id": "global_a", "origin": "GLOBAL_PLAYBOOK"},
        {"check_id": "dt_check", "origin": "DOCUMENT_TYPE"},
    ]
    documents = {
        "doc-1": {"doc_type": "contract_1.6_real_estate", "applicable_triggers": []},
    }
    loader = _RaisingLoader()

    result = _collect_dd_grid_v1_checks(
        playbook_checks=global_checks,
        check_results=check_results,
        documents=documents,
        doc_type_loader=loader,
    )

    # Global остался, doc-type checks не загрузились из-за exception
    assert [c.id for c in result] == ["global_a"]
    assert loader.calls == 1

    

    