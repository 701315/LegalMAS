from engine.checks.result_semantics import build_canonical_result_semantics
from engine.playbook.models import (
    CheckDefinition,
    DetectorType,
    EvidenceConfig,
    ExtractionConfig,
    ExtractionFieldConfig,
    ExtractionFieldType,
    LLMConfig,
    RetrievalConfig,
    RulesConfig,
)


def _make_check_with_grid_fields() -> CheckDefinition:
    return CheckDefinition(
        id="subject_title_cluster",
        name="Предмет договора и титул продавца",
        detector_type=DetectorType.HYBRID,
        rules=RulesConfig(),
        llm=LLMConfig(),
        evidence=EvidenceConfig(),
        retrieval=RetrievalConfig(),
        extraction=ExtractionConfig(
            enabled=True,
            mode="hybrid",
            fields=[
                ExtractionFieldConfig(
                    name="cadastral_number",
                    type=ExtractionFieldType.STRING,
                    presentation="fact",
                    label="Кадастровый номер",
                    display_in_grid=True,
                    display_priority=2,
                ),
                ExtractionFieldConfig(
                    name="address_details",
                    type=ExtractionFieldType.STRING,
                    presentation="fact",
                    label="Адрес",
                    display_in_grid=True,
                    display_priority=3,
                ),
                ExtractionFieldConfig(
                    name="object_type_details",
                    type=ExtractionFieldType.STRING,
                    presentation="fact",
                    label="Вид объекта",
                    display_in_grid=True,
                    display_priority=1,
                ),
                ExtractionFieldConfig(
                    name="egrn_extract_details",
                    type=ExtractionFieldType.STRING,
                    presentation="fact",
                    label="Выписка ЕГРН",
                    display_in_grid=False,
                ),
            ],
        ),
    )


def test_grid_display_uses_explicit_display_in_grid_fields() -> None:
    check = _make_check_with_grid_fields()

    structured_data = {
        "cadastral_number": {
            "value": "78:36:0005503:4",
            "confidence": 1.0,
            "found": True,
        },
        "address_details": {
            "value": "Санкт-Петербург, ADDRESS1",
            "confidence": 0.9,
            "found": True,
        },
        "object_type_details": {
            "value": "земельный участок",
            "confidence": 1.0,
            "found": True,
        },
        "egrn_extract_details": {
            "value": "Выписка ЕГРН от 01.03.2026",
            "confidence": 0.8,
            "found": True,
        },
    }

    semantics = build_canonical_result_semantics(
        check=check,
        exec_result={"result": "pass", "severity": "pass"},
        execution_status="completed",
        structured_data=structured_data,
    )

    assert semantics.display_text == (
        "Вид объекта: земельный участок; "
        "Кадастровый номер: 78:36:0005503:4; "
        "Адрес: Санкт-Петербург, ADDRESS1"
    )


def test_grid_display_falls_back_to_single_primary_fact_when_no_display_fields() -> None:
    check = CheckDefinition(
        id="simple_check",
        name="Simple check",
        detector_type=DetectorType.HYBRID,
        rules=RulesConfig(),
        llm=LLMConfig(),
        evidence=EvidenceConfig(),
        retrieval=RetrievalConfig(),
        extraction=ExtractionConfig(
            enabled=True,
            mode="hybrid",
            fields=[
                ExtractionFieldConfig(
                    name="field_a",
                    type=ExtractionFieldType.STRING,
                    presentation="fact",
                    label="Поле A",
                ),
                ExtractionFieldConfig(
                    name="field_b",
                    type=ExtractionFieldType.STRING,
                    presentation="fact",
                    label="Поле B",
                ),
            ],
        ),
    )

    structured_data = {
        "field_a": {"value": "значение A", "confidence": 1.0, "found": True},
        "field_b": {"value": "значение B", "confidence": 1.0, "found": True},
    }

    semantics = build_canonical_result_semantics(
        check=check,
        exec_result={"result": "pass", "severity": "pass"},
        execution_status="completed",
        structured_data=structured_data,
    )

    assert semantics.display_text == "Поле A: значение A"


def test_grid_display_ignores_signal_fields_even_if_display_flag_absent() -> None:
    check = CheckDefinition(
        id="signal_check",
        name="Signal check",
        detector_type=DetectorType.HYBRID,
        rules=RulesConfig(),
        llm=LLMConfig(),
        evidence=EvidenceConfig(),
        retrieval=RetrievalConfig(),
        extraction=ExtractionConfig(
            enabled=True,
            mode="hybrid",
            fields=[
                ExtractionFieldConfig(
                    name="status_field",
                    type=ExtractionFieldType.STRING,
                    presentation="signal",
                    label="Статус",
                    display_in_grid=True,
                    display_priority=1,
                    allowed_values=["defined", "not_defined"],
                ),
                ExtractionFieldConfig(
                    name="details_field",
                    type=ExtractionFieldType.STRING,
                    presentation="fact",
                    label="Детали",
                    display_in_grid=True,
                    display_priority=2,
                ),
            ],
        ),
    )

    structured_data = {
        "status_field": {"value": "defined", "confidence": 1.0, "found": True},
        "details_field": {"value": "содержимое", "confidence": 1.0, "found": True},
    }

    semantics = build_canonical_result_semantics(
        check=check,
        exec_result={"result": "pass", "severity": "pass"},
        execution_status="completed",
        structured_data=structured_data,
    )

    assert semantics.display_text == "Детали: содержимое"


    