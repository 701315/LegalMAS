import pytest
from datetime import datetime


from engine.playbook.models import (
    AllowedValueSpec,
    CheckDefinition,
    ExtractionConfig,
    ExtractionFieldConfig,
    ExtractionFieldType,
)
from services.dd_grid_v1_builder import build_dd_grid_v1


class FakeGroupConfig:
    def __init__(self, group_id: str, label: str, display_order: int) -> None:
        self.group_id = group_id
        self.label = label
        self.display_order = display_order


class FakeTypeConfig:
    def __init__(self, type_code: str, name: str, group: str) -> None:
        self.type_code = type_code
        self.name = name
        self.group = group


class FakeRegistry:
    def __init__(
        self,
        *,
        groups: dict[str, FakeGroupConfig] | None = None,
        types: dict[str, FakeTypeConfig] | None = None,
    ) -> None:
        self._groups = groups or {}
        self._types = types or {}

    def get_document_type_groups(self) -> dict[str, FakeGroupConfig]:
        return dict(self._groups)

    def get_config(self, type_code: str) -> FakeTypeConfig | None:
        return self._types.get(type_code)


def _field(
    name: str,
    *,
    field_type: ExtractionFieldType = ExtractionFieldType.STRING,
    label: str | None = None,
    allowed_values=None,
    role: str | None = None,
    presentation: str = "fact",
) -> ExtractionFieldConfig:
    kwargs = {
        "name": name,
        "type": field_type,
        "label": label,
        "presentation": presentation,
    }
    if allowed_values is not None:
        kwargs["allowed_values"] = allowed_values
    if role is not None:
        kwargs["role"] = role
    return ExtractionFieldConfig(**kwargs)


def _check(
    check_id: str,
    *,
    name: str | None = None,
    origin: str = "GLOBAL_PLAYBOOK",
    group: str | None = None,
    display_order: int = 0,
    doc_types: list[str] | None = None,
    fields: list[ExtractionFieldConfig] | None = None,
) -> CheckDefinition:
    extraction = (
        ExtractionConfig(enabled=True, fields=fields or [])
        if fields
        else ExtractionConfig(enabled=False)
    )
    return CheckDefinition(
        id=check_id,
        name=name or check_id,
        origin=origin,
        group=group,
        display_order=display_order,
        doc_types=doc_types or [],
        ui_mode="risk_detection",
        extraction=extraction,
    )


def _result(
    *,
    document_id: str,
    check_id: str,
    execution_status: str = "SUCCESS",
    result: str = "pass",
    severity: str = "pass",
    confidence: float = 0.9,
    structured_data=None,
    review_message: str | None = None,
    display_text: str | None = None,
    review_status: str | None = None,
) -> dict:
    return {
        "document_id": document_id,
        "check_id": check_id,
        "check_name": check_id,
        "execution_status": execution_status,
        "result": result,
        "severity": severity,
        "confidence": confidence,
        "structured_data": structured_data,
        "review_message": review_message,
        "display_text": display_text,
        "review_status": review_status,
    }


def _single_column_id(data, check_id: str) -> str:
    prefix = f"{check_id}__"
    matches = [col_id for col_id in data.column_registry if col_id.startswith(prefix)]
    assert len(matches) == 1, f"expected one column for {check_id}, got {matches}"
    return matches[0]


def _column_id_with_suffix(data, check_id: str, suffix: str) -> str:
    prefix = f"{check_id}__"
    for col_id in data.column_registry:
        if col_id.startswith(prefix) and col_id.endswith(suffix):
            return col_id
    raise AssertionError(f"column not found for check_id={check_id}, suffix={suffix}")


def test_builds_global_groups_sorted_by_display_order_then_label() -> None:
    checks = [
        _check(
            "beta_check",
            group="beta_group",
            display_order=20,
            fields=[_field("flag", label="Flag", allowed_values=["yes", "no"])],
        ),
        _check(
            "alpha_check_b",
            group="alpha_group",
            display_order=15,
            fields=[_field("flag", label="Flag", allowed_values=["yes", "no"])],
        ),
        _check(
            "alpha_check_a",
            group="alpha_group",
            display_order=10,
            fields=[_field("flag", label="Flag", allowed_values=["yes", "no"])],
        ),
    ]

    data = build_dd_grid_v1(
        checks=checks,
        check_results=[],
        documents={},
        registry=FakeRegistry(),
    )

    assert [group.group_id for group in data.global_groups] == ["alpha_group", "beta_group"]
    assert [check.check_id for check in data.global_groups[0].checks] == [
        "alpha_check_a",
        "alpha_check_b",
    ]


def test_builds_doc_type_classes_from_registry_groups() -> None:
    registry = FakeRegistry(
        groups={
            "group_legal": FakeGroupConfig("group_legal", "Правовые", 10),
            "group_finance": FakeGroupConfig("group_finance", "Финансовые", 20),
        },
        types={
            "nda": FakeTypeConfig("nda", "NDA", "group_legal"),
            "loan": FakeTypeConfig("loan", "Loan Agreement", "group_finance"),
        },
    )

    checks = [
        _check(
            "nda_check",
            origin="DOCUMENT_TYPE",
            doc_types=["nda"],
            fields=[_field("flag", label="Flag", allowed_values=["yes", "no"])],
        ),
        _check(
            "loan_check",
            origin="DOCUMENT_TYPE",
            doc_types=["loan"],
            fields=[_field("flag", label="Flag", allowed_values=["yes", "no"])],
        ),
    ]

    documents = {
        "doc-1": {"name": "nda.pdf", "doc_type": "nda", "status": "completed"},
        "doc-2": {"name": "loan.pdf", "doc_type": "loan", "status": "completed"},
    }

    data = build_dd_grid_v1(
        checks=checks,
        check_results=[],
        documents=documents,
        registry=registry,
    )

    assert [item.label for item in data.doc_type_classes] == ["Правовые", "Финансовые"]
    assert data.doc_type_classes[0].types[0].type_code == "nda"
    assert data.doc_type_classes[0].types[0].checks[0].check_id == "nda_check"
    assert data.doc_type_classes[1].types[0].type_code == "loan"
    assert data.doc_type_classes[1].types[0].checks[0].check_id == "loan_check"


def test_hides_empty_doc_type_classes_and_types_not_present_in_documents() -> None:
    registry = FakeRegistry(
        groups={
            "group_legal": FakeGroupConfig("group_legal", "Правовые", 10),
            "group_finance": FakeGroupConfig("group_finance", "Финансовые", 20),
        },
        types={
            "nda": FakeTypeConfig("nda", "NDA", "group_legal"),
            "loan": FakeTypeConfig("loan", "Loan Agreement", "group_finance"),
        },
    )

    checks = [
        _check(
            "nda_check",
            origin="DOCUMENT_TYPE",
            doc_types=["nda"],
            fields=[_field("flag", label="Flag", allowed_values=["yes", "no"])],
        ),
        _check(
            "loan_check",
            origin="DOCUMENT_TYPE",
            doc_types=["loan"],
            fields=[_field("flag", label="Flag", allowed_values=["yes", "no"])],
        ),
    ]

    documents = {
        "doc-1": {"name": "nda.pdf", "doc_type": "nda", "status": "completed"},
    }

    data = build_dd_grid_v1(
        checks=checks,
        check_results=[],
        documents=documents,
        registry=registry,
    )

    assert len(data.doc_type_classes) == 1
    assert data.doc_type_classes[0].types[0].type_code == "nda"


def test_skips_checks_without_runtime_columns() -> None:
    checks = [
        _check("empty_check"),
        _check(
            "visible_check",
            fields=[_field("flag", label="Flag", allowed_values=["yes", "no"])],
        ),
    ]

    data = build_dd_grid_v1(
        checks=checks,
        check_results=[],
        documents={},
        registry=FakeRegistry(),
    )

    assert "visible_check__flag" in data.column_registry
    assert not any(col_id.startswith("empty_check__") for col_id in data.column_registry)
    assert [check.check_id for group in data.global_groups for check in group.checks] == ["visible_check"]


def test_cell_state_not_applicable_when_doc_type_not_in_check_doc_types() -> None:
    check = _check(
        "loan_only_check",
        origin="DOCUMENT_TYPE",
        doc_types=["loan"],
        fields=[_field("flag", label="Flag", allowed_values=["yes", "no"])],
    )

    documents = {
        "doc-1": {"name": "nda.pdf", "doc_type": "nda", "status": "completed"},
    }

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[],
        documents=documents,
        registry=FakeRegistry(types={"loan": FakeTypeConfig("loan", "Loan", "group_fin")}),
    )

    col_id = _single_column_id(data, "loan_only_check")
    cell = data.cell_values["doc-1"][col_id]

    assert cell.cell_state == "not_applicable"
    assert cell.display_value == "н/о"
    assert data.drawer_contents["doc-1"]["loan_only_check"].cell_state == "not_applicable"


def test_cell_state_not_executed_when_result_missing() -> None:
    check = _check(
        "nda_check",
        origin="DOCUMENT_TYPE",
        doc_types=["nda"],
        fields=[_field("flag", label="Flag", allowed_values=["yes", "no"])],
    )
    documents = {
        "doc-1": {"name": "nda.pdf", "doc_type": "nda", "status": "completed"},
    }

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[],
        documents=documents,
        registry=FakeRegistry(types={"nda": FakeTypeConfig("nda", "NDA", "group_legal")}),
    )

    col_id = _single_column_id(data, "nda_check")
    cell = data.cell_values["doc-1"][col_id]

    assert cell.cell_state == "not_executed"
    assert cell.display_value == "—"
    assert data.drawer_contents["doc-1"]["nda_check"].cell_state == "not_executed"


def test_cell_state_error_when_execution_status_failed() -> None:
    check = _check(
        "nda_check",
        origin="DOCUMENT_TYPE",
        doc_types=["nda"],
        fields=[_field("flag", label="Flag", allowed_values=["yes", "no"])],
    )
    documents = {
        "doc-1": {"name": "nda.pdf", "doc_type": "nda", "status": "completed"},
    }
    results = [
        _result(
            document_id="doc-1",
            check_id="nda_check",
            execution_status="TIMEOUT",
            structured_data={"flag": {"value": "yes"}},
        )
    ]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(types={"nda": FakeTypeConfig("nda", "NDA", "group_legal")}),
    )

    col_id = _single_column_id(data, "nda_check")
    cell = data.cell_values["doc-1"][col_id]

    assert cell.cell_state == "error"
    assert cell.display_value == "⚠ Ошибка"
    assert data.drawer_contents["doc-1"]["nda_check"].cell_state == "error"


def test_cell_state_not_defined_when_value_missing() -> None:
    check = _check(
        "nda_check",
        origin="DOCUMENT_TYPE",
        doc_types=["nda"],
        fields=[_field("flag", label="Flag", allowed_values=["yes", "no"])],
    )
    documents = {
        "doc-1": {"name": "nda.pdf", "doc_type": "nda", "status": "completed"},
    }
    results = [
        _result(
            document_id="doc-1",
            check_id="nda_check",
            structured_data={"flag": {"value": None}},
        )
    ]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(types={"nda": FakeTypeConfig("nda", "NDA", "group_legal")}),
    )

    col_id = _single_column_id(data, "nda_check")
    cell = data.cell_values["doc-1"][col_id]

    assert cell.cell_state == "not_defined"
    assert cell.display_value == "—"


def test_cell_state_not_defined_when_status_not_present_value() -> None:
    check = _check(
        "notice_check",
        fields=[
            _field("notice_status", label="Notice status", allowed_values=["present", "missing"]),
            _field("notice_value", label="Notice"),
        ],
    )
    documents = {
        "doc-1": {"name": "doc.pdf", "doc_type": "nda", "status": "completed"},
    }
    results = [
        _result(
            document_id="doc-1",
            check_id="notice_check",
            structured_data={
                "notice_status": {"value": "missing"},
                "notice_value": {"value": "30 days"},
            },
        )
    ]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(),
    )

    col_id = _column_id_with_suffix(data, "notice_check", "notice")
    cell = data.cell_values["doc-1"][col_id]

    assert cell.cell_state == "not_defined"
    assert cell.display_value == "—"


def test_cell_state_defined_when_value_present() -> None:
    check = _check(
        "nda_check",
        fields=[_field("flag", label="Flag", allowed_values=["yes", "no"])],
    )
    documents = {
        "doc-1": {"name": "doc.pdf", "doc_type": "nda", "status": "completed"},
    }
    results = [
        _result(
            document_id="doc-1",
            check_id="nda_check",
            structured_data={"flag": {"value": "yes"}},
        )
    ]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(),
    )

    col_id = _single_column_id(data, "nda_check")
    cell = data.cell_values["doc-1"][col_id]

    assert cell.cell_state == "defined"
    assert cell.raw_value == "yes"


def test_formats_yes_no_values() -> None:
    check = _check(
        "consent_check",
        fields=[_field("consent", label="Consent", allowed_values=["yes", "no"])],
    )
    documents = {
        "doc-1": {"name": "doc.pdf", "doc_type": "nda", "status": "completed"},
    }
    results = [
        _result(
            document_id="doc-1",
            check_id="consent_check",
            structured_data={"consent": {"value": "no"}},
        )
    ]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(),
    )

    col_id = _single_column_id(data, "consent_check")
    cell = data.cell_values["doc-1"][col_id]

    assert cell.cell_state == "defined"
    assert cell.display_value == "Нет"


def test_formats_enum_values_using_runtime_labels() -> None:
    check = _check(
        "license_check",
        fields=[
            _field(
                "license_mode",
                label="License mode",
                allowed_values=[
                    AllowedValueSpec(value="exclusive", label="Эксклюзивная", display_order=10),
                    AllowedValueSpec(value="non_exclusive", label="Неисключительная", display_order=20),
                ],
            )
        ],
    )
    documents = {
        "doc-1": {"name": "doc.pdf", "doc_type": "ip", "status": "completed"},
    }
    results = [
        _result(
            document_id="doc-1",
            check_id="license_check",
            structured_data={"license_mode": {"value": "exclusive"}},
        )
    ]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(),
    )

    col_id = _single_column_id(data, "license_check")
    cell = data.cell_values["doc-1"][col_id]

    assert cell.display_value == "Эксклюзивная"


def test_formats_presence_only_values() -> None:
    check = _check(
        "notice_presence_check",
        fields=[
            _field(
                "notice_status",
                label="Notice",
                allowed_values=["present", "missing"],
            )
        ],
    )
    documents = {
        "doc-1": {"name": "doc.pdf", "doc_type": "nda", "status": "completed"},
    }
    results = [
        _result(
            document_id="doc-1",
            check_id="notice_presence_check",
            structured_data={"notice_status": {"value": "present"}},
        )
    ]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(),
    )

    col_id = _single_column_id(data, "notice_presence_check")
    cell = data.cell_values["doc-1"][col_id]

    assert data.column_registry[col_id].format == "presence_only"
    assert cell.cell_state == "defined"
    assert cell.display_value == "Присутствует"


def test_uses_fallback_display_for_not_defined_and_not_executed() -> None:
    check = _check(
        "flag_check",
        origin="DOCUMENT_TYPE",
        doc_types=["nda"],
        fields=[_field("flag", label="Flag", allowed_values=["yes", "no"])],
    )
    documents = {
        "doc-1": {"name": "doc1.pdf", "doc_type": "nda", "status": "completed"},
        "doc-2": {"name": "doc2.pdf", "doc_type": "nda", "status": "completed"},
    }
    results = [
        _result(
            document_id="doc-1",
            check_id="flag_check",
            structured_data={"flag": {"value": None}},
        )
    ]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(types={"nda": FakeTypeConfig("nda", "NDA", "group_legal")}),
    )

    col_id = _single_column_id(data, "flag_check")
    assert data.cell_values["doc-1"][col_id].display_value == "—"
    assert data.cell_values["doc-2"][col_id].display_value == "—"


def test_propagates_exact_location_to_cell_and_drawer() -> None:
    check = _check(
        "consent_check",
        fields=[_field("consent", label="Consent", allowed_values=["yes", "no"])],
    )
    documents = {
        "doc-1": {"name": "doc.pdf", "doc_type": "nda", "status": "completed"},
    }
    results = [
        _result(
            document_id="doc-1",
            check_id="consent_check",
            structured_data={
                "consent": {
                    "value": "yes",
                    "location": {
                        "clause_ref": "п. 1.2",
                        "page": 7,
                        "location_confidence": "high",
                    },
                }
            },
        )
    ]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(),
    )

    col_id = _single_column_id(data, "consent_check")
    cell = data.cell_values["doc-1"][col_id]
    drawer = data.drawer_contents["doc-1"]["consent_check"]

    assert cell.location_clause_ref == "п. 1.2"
    assert cell.location_page == 7
    assert cell.location_confidence == "high"

    assert drawer.fields[0].location_clause_ref == "п. 1.2"
    assert drawer.fields[0].location_page == 7
    assert drawer.fields[0].location_confidence == "high"


def test_propagates_location_fallback_to_cell_and_drawer() -> None:
    check = _check(
        "consent_check",
        fields=[_field("consent", label="Consent", allowed_values=["yes", "no"])],
    )
    documents = {
        "doc-1": {"name": "doc.pdf", "doc_type": "nda", "status": "completed"},
    }
    results = [
        _result(
            document_id="doc-1",
            check_id="consent_check",
            structured_data={
                "consent": {
                    "value": "yes",
                    "location": None,
                    "location_fallback": {
                        "reason": "LLM не указал точную ссылку",
                        "check_clause_uid": "main_contract:12.1",
                        "check_page": 9,
                    },
                }
            },
        )
    ]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(),
    )

    col_id = _single_column_id(data, "consent_check")
    cell = data.cell_values["doc-1"][col_id]
    drawer = data.drawer_contents["doc-1"]["consent_check"]

    assert cell.has_location_fallback is True
    assert cell.location_clause_ref == "main_contract:12.1"
    assert cell.location_page == 9
    assert cell.location_fallback_reason == "LLM не указал точную ссылку"

    assert drawer.fields[0].has_location_fallback is True
    assert drawer.fields[0].location_clause_ref == "main_contract:12.1"
    assert drawer.fields[0].location_page == 9
    assert drawer.fields[0].location_fallback_reason == "LLM не указал точную ссылку"


def test_builds_drawer_reason_and_evidence_items_from_metadata_fields() -> None:
    check = _check(
        "notice_check",
        fields=[
            _field("notice_status", label="Notice status", allowed_values=["present", "missing"]),
            _field("notice_value", label="Notice"),
            _field("reason", label="Reason"),
            _field("evidence", field_type=ExtractionFieldType.EVIDENCE_LIST, label="Evidence"),
        ],
    )
    documents = {
        "doc-1": {"name": "doc.pdf", "doc_type": "nda", "status": "completed"},
    }
    results = [
        _result(
            document_id="doc-1",
            check_id="notice_check",
            structured_data={
                "notice_status": {"value": "missing"},
                "notice_value": {"value": None},
                "reason": {"value": "Не найдено обязательное условие"},
                "evidence": {"value": ["п. 1.1", "п. 2.4"]},
            },
            review_message="review message fallback",
            display_text="display text fallback",
        )
    ]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["notice_check"]

    assert drawer.reason == "Не найдено обязательное условие"
    assert drawer.evidence_items == ["п. 1.1", "п. 2.4"]


def test_handles_malformed_structured_data_gracefully() -> None:
    check = _check(
        "flag_check",
        fields=[_field("flag", label="Flag", allowed_values=["yes", "no"])],
    )
    documents = {
        "doc-1": {"name": "doc.pdf", "doc_type": "nda", "status": "completed"},
    }
    results = [
        _result(
            document_id="doc-1",
            check_id="flag_check",
            structured_data="not-a-dict",
        )
    ]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(),
    )

    col_id = _single_column_id(data, "flag_check")
    cell = data.cell_values["doc-1"][col_id]

    assert cell.cell_state == "not_defined"
    assert data.drawer_contents["doc-1"]["flag_check"].fields[0].display_value == "—"


def test_selects_best_result_when_multiple_results_exist_for_same_doc_and_check() -> None:
    check = _check(
        "notice_check",
        fields=[
            _field("notice_status", label="Notice status", allowed_values=["present", "missing"]),
            _field("notice_value", label="Notice"),
        ],
    )
    documents = {
        "doc-1": {"name": "doc.pdf", "doc_type": "nda", "status": "completed"},
    }
    results = [
        _result(
            document_id="doc-1",
            check_id="notice_check",
            result="pass",
            severity="pass",
            confidence=0.1,
            structured_data={
                "notice_status": {"value": "present"},
                "notice_value": {"value": "weak pass value"},
            },
        ),
        _result(
            document_id="doc-1",
            check_id="notice_check",
            result="fail",
            severity="high",
            confidence=0.9,
            structured_data={
                "notice_status": {"value": "present"},
                "notice_value": {"value": "strong fail value"},
            },
        ),
    ]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(),
    )

    col_id = _column_id_with_suffix(data, "notice_check", "notice")
    cell = data.cell_values["doc-1"][col_id]

    assert cell.display_value == "strong fail value"


def test_builds_documents_meta_sorted_by_filename() -> None:
    check = _check(
        "flag_check",
        fields=[_field("flag", label="Flag", allowed_values=["yes", "no"])],
    )
    documents = {
        "doc-2": {"name": "beta.pdf", "doc_type": "nda", "status": "completed"},
        "doc-1": {"name": "Alpha.pdf", "doc_type": "nda", "status": "completed"},
    }

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[],
        documents=documents,
        registry=FakeRegistry(),
    )

    assert [item.filename for item in data.documents_meta] == ["Alpha.pdf", "beta.pdf"]


def test_drawer_reason_from_explanation_field_not_duplicated_in_evidence() -> None:
    """
    explanation и notes — reason-like metadata.
    Они должны попадать в drawer.reason, но не дублироваться в evidence_items.
    """
    check = _check(
        "compliance_check",
        fields=[
            _field("status", label="Status", allowed_values=["present", "missing"]),
            _field("explanation", label="Explanation", role="subgroup_metadata"),
            _field("notes", label="Notes", role="subgroup_metadata"),
            _field("evidence", field_type=ExtractionFieldType.EVIDENCE_LIST, label="Evidence"),
        ],
    )
    documents = {
        "doc-1": {"name": "doc.pdf", "doc_type": "nda", "status": "completed"},
    }
    results = [
        _result(
            document_id="doc-1",
            check_id="compliance_check",
            structured_data={
                "status": {"value": "present"},
                "explanation": {"value": "Clause found in section 3"},
                "notes": {"value": "Minor formatting issue"},
                "evidence": {"value": ["п. 3.1", "п. 3.2"]},
            },
        )
    ]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["compliance_check"]

    # explanation is the first reason-like field found → goes to reason
    assert drawer.reason == "Clause found in section 3"

    # evidence_items contains ONLY evidence list items, not explanation/notes
    assert drawer.evidence_items == ["п. 3.1", "п. 3.2"]

    # notes must NOT leak into evidence
    assert "Minor formatting issue" not in drawer.evidence_items


def test_drawer_reason_falls_back_to_review_message_when_no_metadata_reason() -> None:
    """
    Если reason/explanation/notes отсутствуют в structured_data,
    drawer.reason должен fallback к review_message, затем к display_text.
    """
    check = _check(
        "simple_check",
        fields=[_field("flag", label="Flag", allowed_values=["yes", "no"])],
    )
    documents = {
        "doc-1": {"name": "doc.pdf", "doc_type": "nda", "status": "completed"},
    }
    results = [
        _result(
            document_id="doc-1",
            check_id="simple_check",
            structured_data={"flag": {"value": "yes"}},
            review_message="Review: все в порядке",
            display_text="Флаг установлен",
        )
    ]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["simple_check"]

    # No reason/explanation/notes → fallback to review_message
    assert drawer.reason == "Review: все в порядке"
    assert drawer.review_message == "Review: все в порядке"
    assert drawer.display_text == "Флаг установлен"


def test_drawer_reason_falls_back_to_display_text_when_no_review_message() -> None:
    """
    Если reason/explanation/notes И review_message отсутствуют,
    drawer.reason fallback к display_text.
    """
    check = _check(
        "simple_check",
        fields=[_field("flag", label="Flag", allowed_values=["yes", "no"])],
    )
    documents = {
        "doc-1": {"name": "doc.pdf", "doc_type": "nda", "status": "completed"},
    }
    results = [
        _result(
            document_id="doc-1",
            check_id="simple_check",
            structured_data={"flag": {"value": "yes"}},
            display_text="Флаг установлен",
        )
    ]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["simple_check"]

    assert drawer.reason == "Флаг установлен"
    assert drawer.review_message is None
    assert drawer.display_text == "Флаг установлен"

def test_column_registry_keeps_first_column_on_duplicate_id() -> None:
    """
    B2 safety net: если runtime по любой причине сгенерирует duplicate column_id,
    registry должен сохранить первую колонку и залогировать error.

    Это защита от future regressions и коллизий из explicit dd_grid_columns.
    """
    from engine.checks.dd_grid_column_builder import (
        DDGridColumnBuilder,
        DDGridColumnRuntime,
    )
    from unittest.mock import patch

    # Создаём check с одной валидной колонкой
    check_a = _check(
        "chk_a",
        fields=[_field("flag", label="Flag A", allowed_values=["yes", "no"])],
    )
    check_b = _check(
        "chk_b",
        fields=[_field("flag", label="Flag B", allowed_values=["yes", "no"])],
    )

    # Патчим build_columns чтобы вернуть колонки с одинаковым column_id
    original_build = DDGridColumnBuilder.build_columns
    collision_col_a = DDGridColumnRuntime(
        column_id="conflict__col",
        label="First",
        value_field="flag",
        status_field=None,
        status_present_value=None,
        format="yes_no",
        fallback_display="—",
        display_order=0,
        enum_labels={},
        unit=None,
    )
    collision_col_b = DDGridColumnRuntime(
        column_id="conflict__col",  # тот же column_id
        label="Second",
        value_field="flag",
        status_field=None,
        status_present_value=None,
        format="yes_no",
        fallback_display="—",
        display_order=0,
        enum_labels={},
        unit=None,
    )

    def fake_build(self, check):
        if check.id == "chk_a":
            return [collision_col_a], [], None
        return [collision_col_b], [], None

    with patch.object(DDGridColumnBuilder, "build_columns", fake_build):
        data = build_dd_grid_v1(
            checks=[check_a, check_b],
            check_results=[],
            documents={},
            registry=FakeRegistry(),
        )

    # Registry должен содержать первую колонку, вторая отброшена
    assert "conflict__col" in data.column_registry
    assert data.column_registry["conflict__col"].label == "First"
    assert data.column_registry["conflict__col"].value_field == "flag"

    # Дубликатов не должно быть
    assert len(data.column_registry) == 1
    
def test_build_dd_grid_v1_extracts_location_page_from_clause_ref_when_missing() -> None:
    check = _check(
        "lease_term_check",
        fields=[_field("term_months", label="Срок аренды")],
    )

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[
            {
                "document_id": "doc-1",
                "check_id": "lease_term_check",
                "result": "pass",
                "severity": "pass",
                "execution_status": "SUCCESS",
                "structured_data": {
                    "term_months": {
                        "value": "12",
                        "location": {
                            "clause_ref": "п. 7.3.3, стр. 8",
                            "page": None,
                            "location_confidence": "high",
                        },
                    }
                },
            }
        ],
        documents={
            "doc-1": {
                "filename": "lease.pdf",
                "doc_type": "lease_contract",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    cell = data.cell_values["doc-1"]["lease_term_check__term_months"]
    drawer_field = data.drawer_contents["doc-1"]["lease_term_check"].fields[0]

    assert cell.location_page == 8
    assert drawer_field.location_page == 8


def test_build_dd_grid_v1_sets_default_fallback_reason_when_missing() -> None:
    check = _check(
        "lease_term_check",
        fields=[_field("term_months", label="Срок аренды")],
    )

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[
            {
                "document_id": "doc-1",
                "check_id": "lease_term_check",
                "result": "pass",
                "severity": "pass",
                "execution_status": "SUCCESS",
                "structured_data": {
                    "term_months": {
                        "value": "12",
                        "location_fallback": {
                            "check_clause_uid": "п. 7.3.3, стр. 8",
                            "check_page": None,
                        },
                    }
                },
            }
        ],
        documents={
            "doc-1": {
                "filename": "lease.pdf",
                "doc_type": "lease_contract",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    cell = data.cell_values["doc-1"]["lease_term_check__term_months"]
    drawer_field = data.drawer_contents["doc-1"]["lease_term_check"].fields[0]

    assert cell.has_location_fallback is True
    assert cell.location_fallback_reason == "Точная ссылка на пункт документа не определена"
    assert cell.location_confidence == "low"
    assert cell.location_page == 8

    assert drawer_field.has_location_fallback is True
    assert drawer_field.location_fallback_reason == "Точная ссылка на пункт документа не определена"
    assert drawer_field.location_page == 8


def test_build_dd_grid_v1_maps_compute_failed_to_api_failed() -> None:
    check = _check(
        "lease_term_check",
        fields=[_field("term_months", label="Срок аренды")],
    )

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[
            {
                "document_id": "doc-1",
                "check_id": "lease_term_check",
                "result": "unclear",
                "severity": "unclear",
                "execution_status": "COMPUTE_FAILED",
                "structured_data": {},
            }
        ],
        documents={
            "doc-1": {
                "filename": "lease.pdf",
                "doc_type": "lease_contract",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["lease_term_check"]

    assert drawer.execution_status == "FAILED"
    assert drawer.cell_state == "error"


def test_build_dd_grid_v1_maps_timeout_to_api_timeout() -> None:
    check = _check(
        "lease_term_check",
        fields=[_field("term_months", label="Срок аренды")],
    )

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[
            {
                "document_id": "doc-1",
                "check_id": "lease_term_check",
                "result": "unclear",
                "severity": "unclear",
                "execution_status": "TIMEOUT",
                "structured_data": {},
            }
        ],
        documents={
            "doc-1": {
                "filename": "lease.pdf",
                "doc_type": "lease_contract",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["lease_term_check"]

    assert drawer.execution_status == "TIMEOUT"
    assert drawer.cell_state == "error"


def test_build_dd_grid_v1_maps_missing_result_to_skipped() -> None:
    check = _check(
        "lease_term_check",
        doc_types=["lease_contract"],
        fields=[_field("term_months", label="Срок аренды")],
    )

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[],
        documents={
            "doc-1": {
                "filename": "lease.pdf",
                "doc_type": "lease_contract",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["lease_term_check"]

    assert drawer.execution_status == "SKIPPED"
    assert drawer.cell_state == "not_executed"


def test_build_dd_grid_v1_maps_not_applicable_check_to_skipped_execution_status() -> None:
    check = _check(
        "lease_term_check",
        doc_types=["nda"],
        fields=[_field("term_months", label="Срок аренды")],
    )

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[],
        documents={
            "doc-1": {
                "filename": "lease.pdf",
                "doc_type": "lease_contract",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["lease_term_check"]

    assert drawer.execution_status == "SKIPPED"
    assert drawer.cell_state == "not_applicable"


def test_build_dd_grid_v1_marks_success_with_missing_fields_as_partial() -> None:
    check = _check(
        "lease_term_check",
        fields=[
            _field("term_months", label="Срок аренды"),
            _field("auto_renewal", label="Автопролонгация"),
        ],
    )

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[
            {
                "document_id": "doc-1",
                "check_id": "lease_term_check",
                "result": "pass",
                "severity": "pass",
                "execution_status": "SUCCESS",
                "structured_data": {
                    "term_months": {
                        "value": "12",
                    }
                },
            }
        ],
        documents={
            "doc-1": {
                "filename": "lease.pdf",
                "doc_type": "lease_contract",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["lease_term_check"]
    field_states = {field.field_name: field.cell_state for field in drawer.fields}

    assert drawer.execution_status == "PARTIAL"
    assert field_states["term_months"] == "defined"
    assert field_states["auto_renewal"] == "not_defined"

    
def test_build_dd_grid_v1_maps_rules_detector_to_l1() -> None:
    check = _check(
        "confidentiality_check",
        fields=[_field("presence", label="Наличие")],
    )

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[
            {
                "document_id": "doc-1",
                "check_id": "confidentiality_check",
                "result": "pass",
                "severity": "pass",
                "execution_status": "SUCCESS",
                "detector_used": "rules",
                "confidence": None,
                "quality_flags": None,
                "qc_status": "pending",
                "qc_by": None,
                "qc_at": None,
                "qc_comment": None,
                "structured_data": {
                    "presence": {"value": "present"},
                },
            }
        ],
        documents={
            "doc-1": {
                "filename": "nda.pdf",
                "doc_type": "nda",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["confidentiality_check"]

    assert drawer.detection_level == "L1"
    assert drawer.confidence is None


def test_build_dd_grid_v1_maps_llm_detector_to_l2_with_confidence() -> None:
    check = _check(
        "termination_check",
        fields=[_field("clause_text", label="Текст клаузы")],
    )

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[
            {
                "document_id": "doc-1",
                "check_id": "termination_check",
                "result": "pass",
                "severity": "pass",
                "execution_status": "SUCCESS",
                "detector_used": "llm",
                "confidence": 0.87,
                "quality_flags": None,
                "qc_status": "pending",
                "qc_by": None,
                "qc_at": None,
                "qc_comment": None,
                "structured_data": {
                    "clause_text": {"value": "договор расторгается..."},
                },
            }
        ],
        documents={
            "doc-1": {
                "filename": "nda.pdf",
                "doc_type": "nda",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["termination_check"]

    assert drawer.detection_level == "L2"
    assert drawer.confidence == pytest.approx(0.87)


def test_build_dd_grid_v1_maps_hybrid_detector_to_l3() -> None:
    check = _check(
        "hybrid_check",
        fields=[_field("status", label="Статус")],
    )

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[
            {
                "document_id": "doc-1",
                "check_id": "hybrid_check",
                "result": "pass",
                "severity": "pass",
                "execution_status": "SUCCESS",
                "detector_used": "hybrid",
                "confidence": 0.72,
                "quality_flags": None,
                "qc_status": "pending",
                "structured_data": {
                    "status": {"value": "active"},
                },
            }
        ],
        documents={
            "doc-1": {
                "filename": "agreement.pdf",
                "doc_type": "agreement",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["hybrid_check"]

    assert drawer.detection_level == "L3"
    assert drawer.confidence == pytest.approx(0.72)


def test_build_dd_grid_v1_unknown_detector_returns_none_level() -> None:
    check = _check(
        "unknown_check",
        fields=[_field("value", label="Значение")],
    )

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[
            {
                "document_id": "doc-1",
                "check_id": "unknown_check",
                "result": "pass",
                "severity": "pass",
                "execution_status": "SUCCESS",
                "detector_used": None,
                "confidence": None,
                "quality_flags": None,
                "qc_status": "pending",
                "structured_data": {
                    "value": {"value": "something"},
                },
            }
        ],
        documents={
            "doc-1": {
                "filename": "doc.pdf",
                "doc_type": "contract",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["unknown_check"]

    assert drawer.detection_level is None
    assert drawer.confidence is None


def test_build_dd_grid_v1_normalizes_quality_flags_to_true_only() -> None:
    check = _check(
        "quality_check",
        fields=[_field("value", label="Значение")],
    )

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[
            {
                "document_id": "doc-1",
                "check_id": "quality_check",
                "result": "pass",
                "severity": "pass",
                "execution_status": "SUCCESS",
                "detector_used": "llm",
                "confidence": 0.6,
                "quality_flags": {
                    "retry_used": True,
                    "llm_fallback_used": False,
                    "structure_degraded": True,
                },
                "qc_status": "pending",
                "structured_data": {
                    "value": {"value": "x"},
                },
            }
        ],
        documents={
            "doc-1": {
                "filename": "doc.pdf",
                "doc_type": "contract",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["quality_check"]

    assert drawer.quality_flags == {
        "retry_used": True,
        "structure_degraded": True,
    }
    assert "llm_fallback_used" not in (drawer.quality_flags or {})


def test_build_dd_grid_v1_empty_quality_flags_becomes_none() -> None:
    check = _check(
        "clean_check",
        fields=[_field("value", label="Значение")],
    )

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[
            {
                "document_id": "doc-1",
                "check_id": "clean_check",
                "result": "pass",
                "severity": "pass",
                "execution_status": "SUCCESS",
                "detector_used": "llm",
                "confidence": 0.95,
                "quality_flags": {},
                "qc_status": "pending",
                "structured_data": {
                    "value": {"value": "x"},
                },
            }
        ],
        documents={
            "doc-1": {
                "filename": "doc.pdf",
                "doc_type": "contract",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["clean_check"]
    assert drawer.quality_flags is None


def test_build_dd_grid_v1_qc_confirmed_maps_to_approved_with_full_audit() -> None:
    check = _check(
        "qc_check",
        fields=[_field("value", label="Значение")],
    )
    from datetime import timezone

    qc_at_dt = datetime(2024, 11, 15, 14, 23, 11, tzinfo=timezone.utc)

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[
            {
                "document_id": "doc-1",
                "check_id": "qc_check",
                "result": "pass",
                "severity": "pass",
                "execution_status": "SUCCESS",
                "detector_used": "llm",
                "confidence": 0.9,
                "quality_flags": None,
                "qc_status": "confirmed",
                "qc_by": "lawyer@firm.ru",
                "qc_at": qc_at_dt,
                "qc_comment": "Проверено, всё корректно",
                "structured_data": {
                    "value": {"value": "x"},
                },
            }
        ],
        documents={
            "doc-1": {
                "filename": "doc.pdf",
                "doc_type": "contract",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["qc_check"]

    assert drawer.qc_status == "approved"
    assert drawer.qc_by == "lawyer@firm.ru"
    assert drawer.qc_at == "2024-11-15T14:23:11+00:00"
    assert drawer.qc_comment == "Проверено, всё корректно"


def test_build_dd_grid_v1_qc_pending_hides_audit_fields() -> None:
    check = _check(
        "pending_check",
        fields=[_field("value", label="Значение")],
    )

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[
            {
                "document_id": "doc-1",
                "check_id": "pending_check",
                "result": "pass",
                "severity": "pass",
                "execution_status": "SUCCESS",
                "detector_used": "llm",
                "confidence": 0.9,
                "quality_flags": None,
                "qc_status": "pending",
                "qc_by": "should_be_hidden@firm.ru",
                "qc_at": "2024-11-15T14:23:11+00:00",
                "qc_comment": "should be hidden",
                "structured_data": {
                    "value": {"value": "x"},
                },
            }
        ],
        documents={
            "doc-1": {
                "filename": "doc.pdf",
                "doc_type": "contract",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["pending_check"]

    assert drawer.qc_status == "pending"
    assert drawer.qc_by is None
    assert drawer.qc_at is None
    assert drawer.qc_comment is None


def test_build_dd_grid_v1_qc_overridden_maps_to_needs_review() -> None:
    check = _check(
        "override_check",
        fields=[_field("value", label="Значение")],
    )

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[
            {
                "document_id": "doc-1",
                "check_id": "override_check",
                "result": "pass",
                "severity": "pass",
                "execution_status": "SUCCESS",
                "detector_used": "llm",
                "confidence": 0.5,
                "quality_flags": None,
                "qc_status": "overridden",
                "qc_by": "reviewer@firm.ru",
                "qc_at": "2024-11-15T14:23:11+00:00",
                "qc_comment": "Требует дополнительной проверки",
                "structured_data": {
                    "value": {"value": "x"},
                },
            }
        ],
        documents={
            "doc-1": {
                "filename": "doc.pdf",
                "doc_type": "contract",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["override_check"]

    assert drawer.qc_status == "needs_review"
    assert drawer.qc_by == "reviewer@firm.ru"
    assert drawer.qc_comment == "Требует дополнительной проверки"


def test_build_dd_grid_v1_no_check_result_all_transparency_fields_none() -> None:
    check = _check(
        "missing_check",
        doc_types=["nda"],
        fields=[_field("value", label="Значение")],
    )

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[],
        documents={
            "doc-1": {
                "filename": "nda.pdf",
                "doc_type": "nda",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["missing_check"]

    assert drawer.detection_level is None
    assert drawer.confidence is None
    assert drawer.quality_flags is None
    assert drawer.qc_status is None
    assert drawer.qc_by is None
    assert drawer.qc_at is None
    assert drawer.qc_comment is None

def test_build_dd_grid_v1_ignores_non_boolean_quality_flags_diagnostics_blob() -> None:
    check = _check(
        "diag_check",
        fields=[_field("value", label="Значение")],
    )

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[
            {
                "document_id": "doc-1",
                "check_id": "diag_check",
                "result": "pass",
                "severity": "pass",
                "execution_status": "SUCCESS",
                "detector_used": "extraction_only",
                "confidence": 1.0,
                "quality_flags": {
                    "raw": {"source": "field_extraction_mode"},
                    "source": "field_extraction_mode",
                    "rules_llm_decision": "skip_presence_for_extraction",
                    "citation_anchor_uid": "main_contract:7.3.3",
                    "llm_required": False,
                    "llm_degraded": False,
                },
                "qc_status": "pending",
                "structured_data": {
                    "value": {"value": "x"},
                },
            }
        ],
        documents={
            "doc-1": {
                "filename": "doc.pdf",
                "doc_type": "contract",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["diag_check"]
    assert drawer.quality_flags is None

    
def test_build_dd_grid_v1_extraction_only_maps_to_l1_with_no_confidence() -> None:
    """
    extraction_only — field extraction без LLM presence detection.
    Должен маппиться в L1 и иметь confidence=None (L1 детерминирован).
    """
    check = _check(
        "field_extraction_check",
        fields=[_field("value", label="Значение")],
    )

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[
            {
                "document_id": "doc-1",
                "check_id": "field_extraction_check",
                "result": "pass",
                "severity": "pass",
                "execution_status": "SUCCESS",
                "detector_used": "extraction_only",
                "confidence": 1.0,
                "quality_flags": None,
                "qc_status": "pending",
                "structured_data": {
                    "value": {"value": "some extracted value"},
                },
            }
        ],
        documents={
            "doc-1": {
                "filename": "contract.pdf",
                "doc_type": "contract",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["field_extraction_check"]

    assert drawer.detection_level == "L1"
    assert drawer.confidence is None

def test_build_dd_grid_v1_derives_agent_name_from_detector_used() -> None:
    check = _check(
        "agent_check",
        fields=[_field("value", label="Значение")],
    )

    cases = [
        ("rules", "RulesDetector"),
        ("llm", "LLMDetector"),
        ("hybrid", "HybridDetector"),
        ("extraction_only", "ExtractionExecutor"),
        (None, None),
        ("unknown_detector", None),
    ]

    for detector_used, expected_agent in cases:
        data = build_dd_grid_v1(
            checks=[check],
            check_results=[
                {
                    "document_id": "doc-1",
                    "check_id": "agent_check",
                    "result": "pass",
                    "severity": "pass",
                    "execution_status": "SUCCESS",
                    "detector_used": detector_used,
                    "quality_flags": None,
                    "qc_status": "pending",
                    "structured_data": {"value": {"value": "x"}},
                }
            ],
            documents={
                "doc-1": {
                    "filename": "doc.pdf",
                    "doc_type": "contract",
                    "status": "classified",
                }
            },
            registry=FakeRegistry(),
        )

        drawer = data.drawer_contents["doc-1"]["agent_check"]
        assert drawer.agent_name == expected_agent, (
            f"detector_used={detector_used!r}: expected {expected_agent!r}, got {drawer.agent_name!r}"
        )


def test_build_dd_grid_v1_extracts_input_tokens_from_raw_context_tokens() -> None:
    check = _check(
        "token_check",
        fields=[_field("value", label="Значение")],
    )

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[
            {
                "document_id": "doc-1",
                "check_id": "token_check",
                "result": "pass",
                "severity": "pass",
                "execution_status": "SUCCESS",
                "detector_used": "extraction_only",
                "quality_flags": {
                    "raw": {
                        "context_tokens": 1177,
                        "llm_invoked": False,
                        "llm_attempts": None,
                    }
                },
                "qc_status": "pending",
                "structured_data": {"value": {"value": "x"}},
            }
        ],
        documents={
            "doc-1": {
                "filename": "doc.pdf",
                "doc_type": "contract",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["token_check"]
    assert drawer.input_tokens == 1177
    assert drawer.output_tokens is None
    assert drawer.retry_attempts is None


def test_build_dd_grid_v1_execution_time_ms_none_when_delta_zero() -> None:
    """started_at == finished_at → delta == 0 → execution_time_ms = None."""
    from datetime import datetime, timezone

    check = _check(
        "time_check",
        fields=[_field("value", label="Значение")],
    )

    same_ts = datetime(2026, 7, 7, 1, 25, 17, tzinfo=timezone.utc)

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[
            {
                "document_id": "doc-1",
                "check_id": "time_check",
                "result": "pass",
                "severity": "pass",
                "execution_status": "SUCCESS",
                "detector_used": "extraction_only",
                "quality_flags": None,
                "qc_status": "pending",
                "started_at": same_ts,
                "finished_at": same_ts,
                "structured_data": {"value": {"value": "x"}},
            }
        ],
        documents={
            "doc-1": {
                "filename": "doc.pdf",
                "doc_type": "contract",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["time_check"]
    assert drawer.execution_time_ms is None


def test_build_dd_grid_v1_execution_time_ms_valid_when_delta_positive() -> None:
    from datetime import datetime, timedelta, timezone

    check = _check(
        "time_check",
        fields=[_field("value", label="Значение")],
    )

    started = datetime(2026, 7, 7, 1, 25, 17, tzinfo=timezone.utc)
    finished = started + timedelta(milliseconds=3500)

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[
            {
                "document_id": "doc-1",
                "check_id": "time_check",
                "result": "pass",
                "severity": "pass",
                "execution_status": "SUCCESS",
                "detector_used": "extraction_only",
                "quality_flags": None,
                "qc_status": "pending",
                "started_at": started,
                "finished_at": finished,
                "structured_data": {"value": {"value": "x"}},
            }
        ],
        documents={
            "doc-1": {
                "filename": "doc.pdf",
                "doc_type": "contract",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["time_check"]
    assert drawer.execution_time_ms == 3500


def test_build_dd_grid_v1_no_check_result_all_observability_fields_none() -> None:
    check = _check(
        "obs_check",
        doc_types=["nda"],
        fields=[_field("value", label="Значение")],
    )

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[],
        documents={
            "doc-1": {
                "filename": "nda.pdf",
                "doc_type": "nda",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["obs_check"]
    assert drawer.agent_name is None
    assert drawer.model_version is None
    assert drawer.execution_time_ms is None
    assert drawer.retry_attempts is None
    assert drawer.input_tokens is None
    assert drawer.output_tokens is None

    # ---------------------------------------------------------------------------
# B3.P1.2 — Telemetry propagation refined semantics tests
# ---------------------------------------------------------------------------


def test_extraction_only_without_llm_invoked_maps_to_l1_and_extractor_agent() -> None:
    """
    extraction_only + extraction_llm_invoked=False → L1 + ExtractionExecutor.
    Детерминированный extraction без LLM.
    """
    check = _check(
        "pure_extraction_check",
        fields=[_field("value", label="Значение")],
    )

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[
            {
                "document_id": "doc-1",
                "check_id": "pure_extraction_check",
                "result": "pass",
                "severity": "pass",
                "execution_status": "SUCCESS",
                "detector_used": "extraction_only",
                "confidence": 1.0,
                "quality_flags": {
                    "raw": {
                        "extraction_mode": "rules",
                        "extraction_llm_invoked": False,
                        "context_tokens": 1177,
                        "duration_ms": 320,
                    }
                },
                "qc_status": "pending",
                "structured_data": {"value": {"value": "x"}},
            }
        ],
        documents={
            "doc-1": {
                "filename": "doc.pdf",
                "doc_type": "contract",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["pure_extraction_check"]

    assert drawer.detection_level == "L1"
    assert drawer.agent_name == "ExtractionExecutor"
    assert drawer.confidence is None
    assert drawer.input_tokens == 1177
    assert drawer.execution_time_ms == 320


def test_extraction_only_with_llm_invoked_mode_llm_maps_to_l2() -> None:
    """
    extraction_only + extraction_llm_invoked=True + mode=llm → L2 + ExtractionLLMDetector.
    """
    check = _check(
        "llm_extraction_check",
        fields=[_field("value", label="Значение")],
    )

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[
            {
                "document_id": "doc-1",
                "check_id": "llm_extraction_check",
                "result": "pass",
                "severity": "pass",
                "execution_status": "SUCCESS",
                "detector_used": "extraction_only",
                "confidence": 0.9,
                "quality_flags": {
                    "raw": {
                        "extraction_mode": "llm",
                        "extraction_llm_invoked": True,
                        "llm_invoked": True,
                        "model": "qwen-2.5-7b",
                        "prompt_tokens": 856,
                        "completion_tokens": 124,
                        "duration_ms": 1840,
                        "llm_attempts": 1,
                    }
                },
                "qc_status": "pending",
                "structured_data": {"value": {"value": "extracted text"}},
            }
        ],
        documents={
            "doc-1": {
                "filename": "doc.pdf",
                "doc_type": "contract",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["llm_extraction_check"]

    assert drawer.detection_level == "L2"
    assert drawer.agent_name == "ExtractionLLMDetector"
    assert drawer.confidence == pytest.approx(0.9)
    assert drawer.model_version == "qwen-2.5-7b"
    assert drawer.input_tokens == 856
    assert drawer.output_tokens == 124
    assert drawer.execution_time_ms == 1840
    assert drawer.retry_attempts == 1


def test_extraction_only_with_llm_invoked_mode_hybrid_maps_to_l3() -> None:
    """
    extraction_only + extraction_llm_invoked=True + mode=hybrid → L3.
    """
    check = _check(
        "hybrid_extraction_check",
        fields=[_field("value", label="Значение")],
    )

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[
            {
                "document_id": "doc-1",
                "check_id": "hybrid_extraction_check",
                "result": "pass",
                "severity": "pass",
                "execution_status": "SUCCESS",
                "detector_used": "extraction_only",
                "confidence": 0.85,
                "quality_flags": {
                    "raw": {
                        "extraction_mode": "hybrid",
                        "extraction_llm_invoked": True,
                        "llm_invoked": True,
                        "model": "qwen-2.5-7b",
                        "prompt_tokens": 1200,
                        "completion_tokens": 200,
                        "duration_ms": 2500,
                    }
                },
                "qc_status": "pending",
                "structured_data": {"value": {"value": "rag result"}},
            }
        ],
        documents={
            "doc-1": {
                "filename": "doc.pdf",
                "doc_type": "contract",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["hybrid_extraction_check"]

    assert drawer.detection_level == "L3"
    assert drawer.agent_name == "ExtractionLLMDetector"
    assert drawer.confidence == pytest.approx(0.85)
    assert drawer.input_tokens == 1200
    assert drawer.output_tokens == 200
    assert drawer.execution_time_ms == 2500


def test_raw_duration_ms_takes_priority_over_db_timestamps() -> None:
    """
    raw.duration_ms имеет приоритет над started_at/finished_at.
    """
    from datetime import datetime, timezone

    check = _check(
        "duration_check",
        fields=[_field("value", label="Значение")],
    )

    same_ts = datetime(2026, 7, 7, 1, 25, 17, tzinfo=timezone.utc)

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[
            {
                "document_id": "doc-1",
                "check_id": "duration_check",
                "result": "pass",
                "severity": "pass",
                "execution_status": "SUCCESS",
                "detector_used": "extraction_only",
                "quality_flags": {
                    "raw": {
                        "extraction_llm_invoked": False,
                        "duration_ms": 4200,
                    }
                },
                "qc_status": "pending",
                "started_at": same_ts,
                "finished_at": same_ts,
                "structured_data": {"value": {"value": "x"}},
            }
        ],
        documents={
            "doc-1": {
                "filename": "doc.pdf",
                "doc_type": "contract",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["duration_check"]

    # raw.duration_ms=4200 побеждает даже когда DB delta=0
    assert drawer.execution_time_ms == 4200


def test_prompt_tokens_takes_priority_over_context_tokens() -> None:
    """
    raw.prompt_tokens имеет приоритет над raw.context_tokens.
    """
    check = _check(
        "tokens_check",
        fields=[_field("value", label="Значение")],
    )

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[
            {
                "document_id": "doc-1",
                "check_id": "tokens_check",
                "result": "pass",
                "severity": "pass",
                "execution_status": "SUCCESS",
                "detector_used": "extraction_only",
                "quality_flags": {
                    "raw": {
                        "extraction_llm_invoked": True,
                        "extraction_mode": "llm",
                        "llm_invoked": True,
                        "prompt_tokens": 856,
                        "context_tokens": 1177,
                        "completion_tokens": 124,
                    }
                },
                "qc_status": "pending",
                "structured_data": {"value": {"value": "x"}},
            }
        ],
        documents={
            "doc-1": {
                "filename": "doc.pdf",
                "doc_type": "contract",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["tokens_check"]

    # prompt_tokens=856 побеждает context_tokens=1177
    assert drawer.input_tokens == 856
    assert drawer.output_tokens == 124


def test_presence_llm_telemetry_propagated_to_drawer() -> None:
    """
    detector_used=llm → L2, LLMDetector, model/tokens из raw.
    """
    check = _check(
        "presence_llm_check",
        fields=[_field("value", label="Значение")],
    )

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[
            {
                "document_id": "doc-1",
                "check_id": "presence_llm_check",
                "result": "fail",
                "severity": "high",
                "execution_status": "SUCCESS",
                "detector_used": "llm",
                "confidence": 0.78,
                "quality_flags": {
                    "raw": {
                        "llm_invoked": True,
                        "model": "qwen-2.5-7b",
                        "prompt_tokens": 512,
                        "completion_tokens": 96,
                        "duration_ms": 1200,
                        "llm_attempts": 2,
                    }
                },
                "qc_status": "pending",
                "structured_data": {"value": {"value": "риск найден"}},
            }
        ],
        documents={
            "doc-1": {
                "filename": "doc.pdf",
                "doc_type": "contract",
                "status": "classified",
            }
        },
        registry=FakeRegistry(),
    )

    drawer = data.drawer_contents["doc-1"]["presence_llm_check"]

    assert drawer.detection_level == "L2"
    assert drawer.agent_name == "LLMDetector"
    assert drawer.confidence == pytest.approx(0.78)
    assert drawer.model_version == "qwen-2.5-7b"
    assert drawer.input_tokens == 512
    assert drawer.output_tokens == 96
    assert drawer.execution_time_ms == 1200
    assert drawer.retry_attempts == 2

    