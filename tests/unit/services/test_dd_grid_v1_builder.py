"""
Тесты для DD Grid V1 Builder.

Тестируют новую модель:
- segment_id в индексации (3 уровня: doc_id → seg_id → col_id)
- plan_items как источник истины о запланированных проверках
- 4 состояния ячейки: not_executed, error, not_defined, defined
- not_applicable удалён (фильтруется на уровне планировщика)
- checks_mode для гейтинга групп
"""

import pytest
from datetime import datetime, timezone, timedelta

from engine.playbook.models import (
    AllowedValueSpec,
    CheckDefinition,
    ExtractionConfig,
    ExtractionFieldConfig,
    ExtractionFieldType,
)
from services.dd_grid_v1_builder import build_dd_grid_v1, DDGridV1Data


# ─────────────────────────────────────────────────────────────────────────────
# Fakes
# ─────────────────────────────────────────────────────────────────────────────


class FakePlanItem:
    """Fake RunCheckPlanItem для тестов."""

    def __init__(
        self,
        *,
        document_id: str,
        check_id: str,
        segment_id: str | None = None,
        status: str = "planned",
        id: str | None = None,
        error_details: dict | None = None,
    ) -> None:
        self.id = id or f"plan-{document_id}-{check_id}"
        self.document_id = document_id
        self.check_id = check_id
        self.segment_id = segment_id
        self.status = status
        self.error_details = error_details


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


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _field(
    name: str,
    *,
    field_type: ExtractionFieldType = ExtractionFieldType.STRING,
    label: str | None = None,
    allowed_values=None,
    role: str | None = None,
    presentation: str = "fact",
    required: bool = False,
) -> ExtractionFieldConfig:
    kwargs = {
        "name": name,
        "type": field_type,
        "label": label,
        "presentation": presentation,
        "required": required,
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
    segment_id: str | None = None,
    execution_status: str = "SUCCESS",
    result: str = "pass",
    severity: str = "pass",
    confidence: float = 0.9,
    structured_data=None,
    review_message: str | None = None,
    display_text: str | None = None,
    review_status: str | None = None,
    detector_used: str | None = None,
    quality_flags: dict | None = None,
    qc_status: str = "pending",
    qc_by: str | None = None,
    qc_at: datetime | None = None,
    qc_comment: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> dict:
    return {
        "document_id": document_id,
        "check_id": check_id,
        "segment_id": segment_id,
        "check_name": check_id,
        "execution_status": execution_status,
        "result": result,
        "severity": severity,
        "confidence": confidence,
        "structured_data": structured_data or {},
        "review_message": review_message,
        "display_text": display_text,
        "review_status": review_status,
        "detector_used": detector_used,
        "quality_flags": quality_flags,
        "qc_status": qc_status,
        "qc_by": qc_by,
        "qc_at": qc_at,
        "qc_comment": qc_comment,
        "started_at": started_at,
        "finished_at": finished_at,
    }


def _plan_items(
    checks: list[CheckDefinition],
    documents: dict[str, dict],
    *,
    status: str = "planned",
) -> list[FakePlanItem]:
    """Создать plan_items для всех применимых комбинаций check × document."""
    items = []
    for check in checks:
        for doc_id, doc_meta in documents.items():
            # Эмулируем логику планировщика — не создаём plan_item для неприменимых чеков
            if check.doc_types:
                doc_type = doc_meta.get("doc_type", "")
                if doc_type not in check.doc_types:
                    continue

            items.append(
                FakePlanItem(
                    document_id=doc_id,
                    check_id=check.id,
                    segment_id=doc_meta.get("segment_id"),
                    status=status,
                )
            )
    return items


def _get_cell(data: DDGridV1Data, doc_id: str, check_id: str, field_suffix: str) -> tuple:
    """Helper для получения cell из 3-уровневой структуры."""
    seg_id = "_default"  # canonical fallback для single-segment
    col_id = f"{check_id}__{field_suffix}"
    
    # Если точный col_id не найден, пробуем найти по префиксу (для paired полей)
    if col_id not in data.cell_values[doc_id][seg_id]:
        # Ищем колонку которая начинается с check_id__ и содержит field_suffix
        for cid in data.cell_values[doc_id][seg_id].keys():
            if cid.startswith(f"{check_id}__") and field_suffix in cid:
                col_id = cid
                break
    
    cell = data.cell_values[doc_id][seg_id][col_id]
    drawer = data.drawer_contents[doc_id][seg_id][check_id]
    return cell, drawer


# ─────────────────────────────────────────────────────────────────────────────
# Тесты: Структура и группировка
# ─────────────────────────────────────────────────────────────────────────────


def test_builds_global_groups_sorted_by_display_order_then_label() -> None:
    checks = [
        _check("beta_check", group="beta_group", display_order=20, fields=[_field("flag", allowed_values=["yes", "no"])]),
        _check("alpha_check_b", group="alpha_group", display_order=15, fields=[_field("flag", allowed_values=["yes", "no"])]),
        _check("alpha_check_a", group="alpha_group", display_order=10, fields=[_field("flag", allowed_values=["yes", "no"])]),
    ]

    documents = {"doc-1": {"name": "doc.pdf", "doc_type": "nda", "status": "completed"}}
    plan_items = _plan_items(checks, documents)

    data = build_dd_grid_v1(
        checks=checks,
        check_results=[],
        documents=documents,
        registry=FakeRegistry(),
        plan_items=plan_items,
        checks_mode="all",
    )

    assert [group.group_id for group in data.global_groups] == ["alpha_group", "beta_group"]
    assert [check.check_id for check in data.global_groups[0].checks] == ["alpha_check_a", "alpha_check_b"]


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
        _check("nda_check", origin="DOCUMENT_TYPE", doc_types=["nda"], fields=[_field("flag", allowed_values=["yes", "no"])]),
        _check("loan_check", origin="DOCUMENT_TYPE", doc_types=["loan"], fields=[_field("flag", allowed_values=["yes", "no"])]),
    ]

    documents = {
        "doc-1": {"name": "nda.pdf", "doc_type": "nda", "status": "completed"},
        "doc-2": {"name": "loan.pdf", "doc_type": "loan", "status": "completed"},
    }
    plan_items = _plan_items(checks, documents)

    data = build_dd_grid_v1(
        checks=checks,
        check_results=[],
        documents=documents,
        registry=registry,
        plan_items=plan_items,
        checks_mode="all",
    )

    assert [item.label for item in data.doc_type_classes] == ["Правовые", "Финансовые"]
    assert data.doc_type_classes[0].types[0].type_code == "nda"
    assert data.doc_type_classes[1].types[0].type_code == "loan"


def test_checks_mode_gates_global_groups() -> None:
    checks = [_check("global_check", origin="GLOBAL_PLAYBOOK", fields=[_field("flag", allowed_values=["yes", "no"])])]
    documents = {"doc-1": {"name": "doc.pdf", "doc_type": "nda", "status": "completed"}}
    plan_items = _plan_items(checks, documents)

    # checks_mode="doc_type_only" → global_groups пустые
    data = build_dd_grid_v1(
        checks=checks,
        check_results=[],
        documents=documents,
        registry=FakeRegistry(),
        plan_items=plan_items,
        checks_mode="doc_type_only",
    )

    assert len(data.global_groups) == 0


def test_checks_mode_gates_doc_type_classes() -> None:
    checks = [_check("doc_check", origin="DOCUMENT_TYPE", doc_types=["nda"], fields=[_field("flag", allowed_values=["yes", "no"])])]
    documents = {"doc-1": {"name": "doc.pdf", "doc_type": "nda", "status": "completed"}}
    plan_items = _plan_items(checks, documents)

    # checks_mode="global_only" → doc_type_classes пустые
    data = build_dd_grid_v1(
        checks=checks,
        check_results=[],
        documents=documents,
        registry=FakeRegistry(types={"nda": FakeTypeConfig("nda", "NDA", "group")}),
        plan_items=plan_items,
        checks_mode="global_only",
    )

    assert len(data.doc_type_classes) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Тесты: Cell states
# ─────────────────────────────────────────────────────────────────────────────


def test_cell_state_not_executed_when_result_missing() -> None:
    check = _check("nda_check", doc_types=["nda"], fields=[_field("flag", allowed_values=["yes", "no"])])
    documents = {"doc-1": {"name": "nda.pdf", "doc_type": "nda", "status": "completed"}}
    plan_items = [FakePlanItem(document_id="doc-1", check_id="nda_check", status="planned")]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=[],
        documents=documents,
        registry=FakeRegistry(types={"nda": FakeTypeConfig("nda", "NDA", "group")}),
        plan_items=plan_items,
        checks_mode="all",
    )

    cell, drawer = _get_cell(data, "doc-1", "nda_check", "flag")

    assert cell.cell_state == "not_executed"
    assert cell.display_value == "—"
    assert drawer.cell_state == "not_executed"
    assert drawer.execution_status == "SKIPPED"


def test_cell_state_error_when_execution_status_failed() -> None:
    check = _check("nda_check", doc_types=["nda"], fields=[_field("flag", allowed_values=["yes", "no"])])
    documents = {"doc-1": {"name": "nda.pdf", "doc_type": "nda", "status": "completed"}}
    plan_items = [FakePlanItem(document_id="doc-1", check_id="nda_check", status="dispatched")]
    results = [_result(document_id="doc-1", check_id="nda_check", execution_status="TIMEOUT", structured_data={"flag": {"value": "yes"}})]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(types={"nda": FakeTypeConfig("nda", "NDA", "group")}),
        plan_items=plan_items,
        checks_mode="all",
    )

    cell, drawer = _get_cell(data, "doc-1", "nda_check", "flag")

    assert cell.cell_state == "error"
    assert cell.display_value == "⚠ Error"
    assert drawer.cell_state == "error"
    assert drawer.execution_status == "TIMEOUT"


def test_cell_state_not_defined_when_value_missing() -> None:
    check = _check("nda_check", doc_types=["nda"], fields=[_field("flag", allowed_values=["yes", "no"])])
    documents = {"doc-1": {"name": "nda.pdf", "doc_type": "nda", "status": "completed"}}
    plan_items = [FakePlanItem(document_id="doc-1", check_id="nda_check", status="planned")]
    results = [_result(document_id="doc-1", check_id="nda_check", structured_data={"flag": {"value": None}})]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(types={"nda": FakeTypeConfig("nda", "NDA", "group")}),
        plan_items=plan_items,
        checks_mode="all",
    )

    cell, drawer = _get_cell(data, "doc-1", "nda_check", "flag")

    assert cell.cell_state == "not_defined"
    assert cell.display_value == "—"


def test_cell_state_defined_when_value_present() -> None:
    check = _check("nda_check", doc_types=["nda"], fields=[_field("flag", allowed_values=["yes", "no"])])
    documents = {"doc-1": {"name": "nda.pdf", "doc_type": "nda", "status": "completed"}}
    plan_items = [FakePlanItem(document_id="doc-1", check_id="nda_check", status="planned")]
    results = [_result(document_id="doc-1", check_id="nda_check", structured_data={"flag": {"value": "yes"}})]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(types={"nda": FakeTypeConfig("nda", "NDA", "group")}),
        plan_items=plan_items,
        checks_mode="all",
    )

    cell, drawer = _get_cell(data, "doc-1", "nda_check", "flag")

    assert cell.cell_state == "defined"
    assert cell.raw_value == "yes"
    assert drawer.cell_state == "defined"


# ─────────────────────────────────────────────────────────────────────────────
# Тесты: Форматирование значений
# ─────────────────────────────────────────────────────────────────────────────


def test_formats_yes_no_values() -> None:
    check = _check("consent_check", fields=[_field("consent", label="Consent", allowed_values=["yes", "no"])])
    documents = {"doc-1": {"name": "doc.pdf", "doc_type": "nda", "status": "completed"}}
    plan_items = _plan_items([check], documents)
    results = [_result(document_id="doc-1", check_id="consent_check", structured_data={"consent": {"value": "no"}})]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(),
        plan_items=plan_items,
        checks_mode="all",
    )

    cell, _ = _get_cell(data, "doc-1", "consent_check", "consent")

    assert cell.cell_state == "defined"
    assert cell.display_value == "No"


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
    documents = {"doc-1": {"name": "doc.pdf", "doc_type": "ip", "status": "completed"}}
    plan_items = _plan_items([check], documents)
    results = [_result(document_id="doc-1", check_id="license_check", structured_data={"license_mode": {"value": "exclusive"}})]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(),
        plan_items=plan_items,
        checks_mode="all",
    )

    cell, _ = _get_cell(data, "doc-1", "license_check", "license_mode")

    assert cell.display_value == "Эксклюзивная"


def test_formats_presence_only_values() -> None:
    check = _check("notice_presence_check", fields=[_field("notice_status", allowed_values=["present", "missing"])])
    documents = {"doc-1": {"name": "doc.pdf", "doc_type": "nda", "status": "completed"}}
    plan_items = _plan_items([check], documents)
    results = [_result(document_id="doc-1", check_id="notice_presence_check", structured_data={"notice_status": {"value": "present"}})]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(),
        plan_items=plan_items,
        checks_mode="all",
    )

    cell, drawer = _get_cell(data, "doc-1", "notice_presence_check", "notice_status")

    # Проверяем format через column_registry по правильному column_id
    col_id = f"{check.id}__notice_status"
    assert col_id in data.column_registry
    assert data.column_registry[col_id].format == "presence_only"
    assert cell.cell_state == "defined"
    assert cell.display_value == "Present"


# ─────────────────────────────────────────────────────────────────────────────
# Тесты: Location propagation
# ─────────────────────────────────────────────────────────────────────────────


def test_propagates_exact_location_to_cell_and_drawer() -> None:
    check = _check("consent_check", fields=[_field("consent", allowed_values=["yes", "no"])])
    documents = {"doc-1": {"name": "doc.pdf", "doc_type": "nda", "status": "completed"}}
    plan_items = _plan_items([check], documents)
    results = [
        _result(
            document_id="doc-1",
            check_id="consent_check",
            structured_data={
                "consent": {
                    "value": "yes",
                    "location": {"clause_ref": "п. 1.2", "page": 7, "location_confidence": "high"},
                }
            },
        )
    ]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(),
        plan_items=plan_items,
        checks_mode="all",
    )

    cell, drawer = _get_cell(data, "doc-1", "consent_check", "consent")

    assert cell.location_clause_ref == "п. 1.2"
    assert cell.location_page == 7
    assert cell.location_confidence == "high"
    assert cell.location_source == "per_field"

    assert drawer.fields[0].location_clause_ref == "п. 1.2"
    assert drawer.fields[0].location_page == 7


def test_propagates_location_fallback_to_cell_and_drawer() -> None:
    check = _check("consent_check", fields=[_field("consent", allowed_values=["yes", "no"])])
    documents = {"doc-1": {"name": "doc.pdf", "doc_type": "nda", "status": "completed"}}
    plan_items = _plan_items([check], documents)
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
        plan_items=plan_items,
        checks_mode="all",
    )

    cell, drawer = _get_cell(data, "doc-1", "consent_check", "consent")

    assert cell.location_source == "display_text"
    assert cell.location_confidence == "low"

    assert drawer.fields[0].location_source == "display_text"


# ─────────────────────────────────────────────────────────────────────────────
# Тесты: QC и Observability
# ─────────────────────────────────────────────────────────────────────────────


def test_qc_confirmed_maps_to_approved_with_full_audit() -> None:
    check = _check("qc_check", fields=[_field("value", label="Значение")])
    documents = {"doc-1": {"name": "doc.pdf", "doc_type": "contract", "status": "classified"}}
    plan_items = _plan_items([check], documents)
    qc_at_dt = datetime(2024, 11, 15, 14, 23, 11, tzinfo=timezone.utc)

    results = [
        _result(
            document_id="doc-1",
            check_id="qc_check",
            structured_data={"value": {"value": "x"}},
            qc_status="confirmed",
            qc_by="lawyer@firm.ru",
            qc_at=qc_at_dt,
            qc_comment="Проверено, всё корректно",
        )
    ]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(),
        plan_items=plan_items,
        checks_mode="all",
    )

    _, drawer = _get_cell(data, "doc-1", "qc_check", "value")

    assert drawer.qc_status == "approved"
    assert drawer.qc_by == "lawyer@firm.ru"
    assert drawer.qc_at == "2024-11-15T14:23:11+00:00"
    assert drawer.qc_comment == "Проверено, всё корректно"


def test_qc_pending_hides_audit_fields() -> None:
    check = _check("pending_check", fields=[_field("value", label="Значение")])
    documents = {"doc-1": {"name": "doc.pdf", "doc_type": "contract", "status": "classified"}}
    plan_items = _plan_items([check], documents)

    results = [
        _result(
            document_id="doc-1",
            check_id="pending_check",
            structured_data={"value": {"value": "x"}},
            qc_status="pending",
            qc_by="should_be_hidden@firm.ru",
            qc_at="2024-11-15T14:23:11+00:00",
            qc_comment="should be hidden",
        )
    ]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(),
        plan_items=plan_items,
        checks_mode="all",
    )

    _, drawer = _get_cell(data, "doc-1", "pending_check", "value")

    assert drawer.qc_status == "pending"
    assert drawer.qc_by is None
    assert drawer.qc_at is None
    assert drawer.qc_comment is None


def test_detection_level_maps_from_detector_used() -> None:
    check = _check("detector_check", fields=[_field("value", label="Значение")])
    documents = {"doc-1": {"name": "doc.pdf", "doc_type": "contract", "status": "classified"}}
    plan_items = _plan_items([check], documents)

    cases = [
        ("rules", "L1", "RulesDetector"),
        ("llm", "L2", "LLMDetector"),
        ("hybrid", "L3", "HybridDetector"),
        ("extraction_only", "L1", "ExtractionExecutor"),
        (None, None, None),
    ]

    for detector_used, expected_level, expected_agent in cases:
        results = [
            _result(
                document_id="doc-1",
                check_id="detector_check",
                structured_data={"value": {"value": "x"}},
                detector_used=detector_used,
                confidence=0.9 if detector_used else None,
            )
        ]

        data = build_dd_grid_v1(
            checks=[check],
            check_results=results,
            documents=documents,
            registry=FakeRegistry(),
            plan_items=plan_items,
            checks_mode="all",
        )

        _, drawer = _get_cell(data, "doc-1", "detector_check", "value")

        assert drawer.detection_level == expected_level, f"detector_used={detector_used!r}"
        assert drawer.agent_name == expected_agent, f"detector_used={detector_used!r}"


def test_quality_flags_normalized_to_true_only() -> None:
    check = _check("quality_check", fields=[_field("value", label="Значение")])
    documents = {"doc-1": {"name": "doc.pdf", "doc_type": "contract", "status": "classified"}}
    plan_items = _plan_items([check], documents)

    results = [
        _result(
            document_id="doc-1",
            check_id="quality_check",
            structured_data={"value": {"value": "x"}},
            detector_used="llm",
            confidence=0.6,
            quality_flags={
                "retry_used": True,
                "llm_fallback_used": False,
                "structure_degraded": True,
            },
        )
    ]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(),
        plan_items=plan_items,
        checks_mode="all",
    )

    _, drawer = _get_cell(data, "doc-1", "quality_check", "value")

    assert drawer.quality_flags == {"retry_used": True, "structure_degraded": True}
    assert "llm_fallback_used" not in (drawer.quality_flags or {})


# ─────────────────────────────────────────────────────────────────────────────
# Тесты: Segment-aware индексация
# ─────────────────────────────────────────────────────────────────────────────


def test_segment_id_included_in_index_keys() -> None:
    """Проверяет что cell_values имеет 3 уровня: doc_id → seg_id → col_id."""
    check = _check("flag_check", fields=[_field("flag", allowed_values=["yes", "no"])])
    documents = {"doc-1": {"name": "doc.pdf", "doc_type": "nda", "status": "completed"}}
    plan_items = _plan_items([check], documents)
    results = [_result(document_id="doc-1", check_id="flag_check", segment_id="_default", structured_data={"flag": {"value": "yes"}})]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(),
        plan_items=plan_items,
        checks_mode="all",
    )

    # Проверяем 3-уровневую структуру
    assert "doc-1" in data.cell_values
    assert "_default" in data.cell_values["doc-1"]
    assert "flag_check__flag" in data.cell_values["doc-1"]["_default"]

    assert "doc-1" in data.drawer_contents
    assert "_default" in data.drawer_contents["doc-1"]
    assert "flag_check" in data.drawer_contents["doc-1"]["_default"]


def test_best_row_selected_within_same_segment() -> None:
    """Best row выбирается только внутри одного (doc, segment, check)."""
    check = _check("notice_check", fields=[_field("notice_status", allowed_values=["present", "missing"]), _field("notice_value", label="Notice")])
    documents = {"doc-1": {"name": "doc.pdf", "doc_type": "nda", "status": "completed"}}
    plan_items = [FakePlanItem(document_id="doc-1", check_id="notice_check", segment_id="_default", status="planned")]

    # Два результата для одного сегмента — должен выбрать fail с высоким confidence
    results = [
        _result(document_id="doc-1", check_id="notice_check", segment_id="_default", result="pass", confidence=0.1, structured_data={"notice_value": {"value": "weak pass"}}),
        _result(document_id="doc-1", check_id="notice_check", segment_id="_default", result="fail", severity="high", confidence=0.9, structured_data={"notice_value": {"value": "strong fail"}}),
    ]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(),
        plan_items=plan_items,
        checks_mode="all",
    )

    # Для paired полей (status + value) билдер создаёт одну колонку с именем check_id__prefix
    # где prefix = часть до _status/_value
    cell, _ = _get_cell(data, "doc-1", "notice_check", "notice")

    assert cell.display_value == "strong fail"


# ─────────────────────────────────────────────────────────────────────────────
# Тесты: Execution status mapping
# ─────────────────────────────────────────────────────────────────────────────


def test_execution_status_partial_when_some_fields_missing() -> None:
    check = _check(
        "lease_term_check",
        fields=[
            _field("term_months", label="Срок аренды"),
            _field("auto_renewal", label="Автопролонгация"),
        ],
    )
    documents = {"doc-1": {"name": "lease.pdf", "doc_type": "lease_contract", "status": "classified"}}
    plan_items = _plan_items([check], documents)
    results = [
        _result(
            document_id="doc-1",
            check_id="lease_term_check",
            execution_status="SUCCESS",
            structured_data={"term_months": {"value": "12"}},
        )
    ]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(),
        plan_items=plan_items,
        checks_mode="all",
    )

    _, drawer = _get_cell(data, "doc-1", "lease_term_check", "term_months")

    assert drawer.execution_status == "PARTIAL"


def test_execution_status_in_progress_when_running() -> None:
    check = _check("lease_term_check", fields=[_field("term_months", label="Срок аренды")])
    documents = {"doc-1": {"name": "lease.pdf", "doc_type": "lease_contract", "status": "classified"}}
    plan_items = [FakePlanItem(document_id="doc-1", check_id="lease_term_check", status="started")]
    results = [
        _result(
            document_id="doc-1",
            check_id="lease_term_check",
            execution_status="RUNNING",
            structured_data={},
        )
    ]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(),
        plan_items=plan_items,
        checks_mode="all",
    )

    _, drawer = _get_cell(data, "doc-1", "lease_term_check", "term_months")

    assert drawer.execution_status == "IN_PROGRESS"


# ─────────────────────────────────────────────────────────────────────────────
# Тесты: Drawer reason precedence
# ─────────────────────────────────────────────────────────────────────────────


def test_drawer_reason_from_metadata_fields_not_duplicated_in_evidence() -> None:
    """explanation и notes попадают в reason, но не дублируются в evidence_items."""
    check = _check(
        "compliance_check",
        fields=[
            _field("status", allowed_values=["present", "missing"]),
            _field("explanation", label="Explanation", role="subgroup_metadata"),
            _field("notes", label="Notes", role="subgroup_metadata"),
            _field("evidence", field_type=ExtractionFieldType.EVIDENCE_LIST, label="Evidence"),
        ],
    )
    documents = {"doc-1": {"name": "doc.pdf", "doc_type": "nda", "status": "completed"}}
    plan_items = _plan_items([check], documents)
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
        plan_items=plan_items,
        checks_mode="all",
    )

    _, drawer = _get_cell(data, "doc-1", "compliance_check", "status")

    assert drawer.reason == "Clause found in section 3"
    assert drawer.evidence_items == ["п. 3.1", "п. 3.2"]
    assert "Minor formatting issue" not in drawer.evidence_items


def test_drawer_reason_fallback_to_review_message() -> None:
    """Если нет metadata reason → fallback к review_message."""
    check = _check("simple_check", fields=[_field("flag", allowed_values=["yes", "no"])])
    documents = {"doc-1": {"name": "doc.pdf", "doc_type": "nda", "status": "completed"}}
    plan_items = _plan_items([check], documents)
    results = [
        _result(
            document_id="doc-1",
            check_id="simple_check",
            structured_data={"flag": {"value": "yes"}},
            review_message="Review: всё в порядке",
            display_text="Флаг установлен",
        )
    ]

    data = build_dd_grid_v1(
        checks=[check],
        check_results=results,
        documents=documents,
        registry=FakeRegistry(),
        plan_items=plan_items,
        checks_mode="all",
    )

    _, drawer = _get_cell(data, "doc-1", "simple_check", "flag")

    assert drawer.reason == "Review: всё в порядке"
    assert drawer.review_message == "Review: всё в порядке"


# ─────────────────────────────────────────────────────────────────────────────
# Тесты: Column registry collision safety
# ─────────────────────────────────────────────────────────────────────────────


def test_column_registry_keeps_first_column_on_duplicate_id() -> None:
    """Если duplicate column_id — сохраняется первая колонка, вторая отбрасывается."""
    from engine.checks.dd_grid_column_builder import DDGridColumnBuilder, DDGridColumnRuntime
    from unittest.mock import patch

    check_a = _check("chk_a", fields=[_field("flag", allowed_values=["yes", "no"])])
    check_b = _check("chk_b", fields=[_field("flag", allowed_values=["yes", "no"])])

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
        column_id="conflict__col",
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

    def fake_build(self, check, *args, **kwargs):
        if check.id == "chk_a":
            return [collision_col_a], [], None
        return [collision_col_b], [], None

    documents = {"doc-1": {"name": "doc.pdf", "doc_type": "nda", "status": "completed"}}
    plan_items = _plan_items([check_a, check_b], documents)

    with patch.object(DDGridColumnBuilder, "build_columns", fake_build):
        data = build_dd_grid_v1(
            checks=[check_a, check_b],
            check_results=[],
            documents=documents,
            registry=FakeRegistry(),
            plan_items=plan_items,
            checks_mode="all",
        )

    assert "conflict__col" in data.column_registry
    assert data.column_registry["conflict__col"].label == "First"
    assert len(data.column_registry) == 1



