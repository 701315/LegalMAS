"""
Tests for DD Grid V1 data contract extensions in playbook models.

Covers:
- ExtractionFieldType.EVIDENCE_LIST
- AllowedValueSpec / DDGridColumnSpec / LocationInfo / LocationFallback
- ExtractionFieldConfig: role, mixed allowed_values formats
- ExtractionConfig: dd_grid_columns
- CheckDefinition: group, display_order
- Backward compatibility: old YAML without new fields still valid
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from engine.playbook.models import (
    AllowedValueSpec,
    CheckDefinition,
    DDGridColumnSpec,
    DetectorType,
    ExtractionConfig,
    ExtractionFieldConfig,
    ExtractionFieldType,
    LocationFallback,
    LocationInfo,
)


# ────────────────────── A. Enum / base model parsing ──────────────────────


class TestExtractionFieldTypeEvidenceList:
    """EVIDENCE_LIST enum value is accepted and round-trips correctly."""

    def test_evidence_list_value(self):
        assert ExtractionFieldType.EVIDENCE_LIST == "evidence_list"
        assert ExtractionFieldType("evidence_list") is ExtractionFieldType.EVIDENCE_LIST

    def test_all_existing_types_still_valid(self):
        for val in ("string", "number", "date", "boolean", "clause_ref", "evidence_list"):
            assert ExtractionFieldType(val).value == val


class TestAllowedValueSpec:
    """AllowedValueSpec parsing and defaults."""

    def test_minimal(self):
        spec = AllowedValueSpec(value="yes", label="Да")
        assert spec.value == "yes"
        assert spec.label == "Да"
        assert spec.display_order == 0

    def test_with_display_order(self):
        spec = AllowedValueSpec(value="no", label="Нет", display_order=20)
        assert spec.display_order == 20

    def test_missing_required_fields_raises(self):
        with pytest.raises(ValidationError):
            AllowedValueSpec(value="yes")  # type: ignore[call-arg]


class TestDDGridColumnSpec:
    """DDGridColumnSpec parsing, defaults, and optional fields."""

    def test_minimal(self):
        col = DDGridColumnSpec(column_id="gov_law", label="Применимое право")
        assert col.column_id == "gov_law"
        assert col.label == "Применимое право"
        assert col.value_field is None
        assert col.status_field is None
        assert col.format is None
        assert col.display_order == 0

    def test_full(self):
        col = DDGridColumnSpec(
            column_id="gov_law",
            label="Применимое право",
            value_field="governing_law_value",
            status_field="governing_law_status",
            status_present_value="specified",
            format="enum",
            fallback_display="—",
            display_order=10,
        )
        assert col.value_field == "governing_law_value"
        assert col.status_present_value == "specified"
        assert col.format == "enum"
        assert col.fallback_display == "—"

    def test_missing_column_id_raises(self):
        with pytest.raises(ValidationError):
            DDGridColumnSpec(label="Test")  # type: ignore[call-arg]


class TestLocationInfo:
    """LocationInfo parsing and defaults."""

    def test_minimal(self):
        loc = LocationInfo()
        assert loc.clause_ref is None
        assert loc.page is None
        assert loc.clause_uid is None
        assert loc.location_confidence == "low"

    def test_full_high_confidence(self):
        loc = LocationInfo(
            clause_ref="п. 12.1",
            page=12,
            clause_uid="clause_12_1",
            location_confidence="high",
        )
        assert loc.clause_ref == "п. 12.1"
        assert loc.page == 12
        assert loc.location_confidence == "high"

    def test_invalid_confidence_raises(self):
        with pytest.raises(ValidationError):
            LocationInfo(location_confidence="medium")  # type: ignore[arg-type]


class TestLocationFallback:
    """LocationFallback parsing."""

    def test_minimal(self):
        fb = LocationFallback(reason="LLM не указал ссылку")
        assert fb.reason == "LLM не указал ссылку"
        assert fb.check_clause_uid is None
        assert fb.check_page is None

    def test_with_check_location(self):
        fb = LocationFallback(
            reason="Не уверен в привязке",
            check_clause_uid="clause_7_1",
            check_page=7,
        )
        assert fb.check_clause_uid == "clause_7_1"
        assert fb.check_page == 7

    def test_missing_reason_raises(self):
        with pytest.raises(ValidationError):
            LocationFallback()  # type: ignore[call-arg]


# ──────────────── B. ExtractionFieldConfig extensions ─────────────────


def _field(
    name: str,
    *,
    label: str | None = None,
    presentation: str = "fact",
    field_type: ExtractionFieldType = ExtractionFieldType.STRING,
    role: str | None = None,
    allowed_values: list | None = None,
) -> ExtractionFieldConfig:
    """Helper to build ExtractionFieldConfig with minimal boilerplate."""
    kwargs: dict = {
        "name": name,
        "type": field_type,
        "label": label,
        "presentation": presentation,
    }
    if role is not None:
        kwargs["role"] = role
    if allowed_values is not None:
        kwargs["allowed_values"] = allowed_values
    return ExtractionFieldConfig(**kwargs)


class TestExtractionFieldConfigAllowedValues:
    """allowed_values accepts both list[str] and list[AllowedValueSpec]."""

    def test_legacy_list_str(self):
        f = _field("status", allowed_values=["yes", "no", "partial"])
        assert f.allowed_values == ["yes", "no", "partial"]

    def test_allowed_value_specs(self):
        specs = [
            AllowedValueSpec(value="yes", label="Да", display_order=10),
            AllowedValueSpec(value="no", label="Нет", display_order=20),
        ]
        f = _field("status", allowed_values=specs)
        assert len(f.allowed_values) == 2
        assert isinstance(f.allowed_values[0], AllowedValueSpec)
        assert f.allowed_values[0].label == "Да"

    def test_empty_allowed_values_default(self):
        f = _field("name")
        assert f.allowed_values == []


class TestExtractionFieldConfigRole:
    """role field on ExtractionFieldConfig."""

    def test_default_none(self):
        f = _field("name")
        assert f.role is None

    def test_subgroup_metadata(self):
        f = _field("evidence", role="subgroup_metadata")
        assert f.role == "subgroup_metadata"

    def test_arbitrary_role_accepted(self):
        f = _field("x", role="custom_role")
        assert f.role == "custom_role"


class TestExtractionFieldConfigEvidenceListType:
    """EVIDENCE_LIST type is accepted in ExtractionFieldConfig."""

    def test_evidence_list_type(self):
        f = _field(
            "evidence",
            field_type=ExtractionFieldType.EVIDENCE_LIST,
            presentation="diagnostic",
            role="subgroup_metadata",
        )
        assert f.type == ExtractionFieldType.EVIDENCE_LIST
        assert f.role == "subgroup_metadata"
        assert f.presentation == "diagnostic"


# ──────────────── C. ExtractionConfig extensions ─────────────────


class TestExtractionConfigDDGridColumns:
    """ExtractionConfig.dd_grid_columns field."""

    def test_default_none(self):
        cfg = ExtractionConfig(
            enabled=True,
            fields=[_field("x", label="X")],
        )
        assert cfg.dd_grid_columns is None

    def test_explicit_columns(self):
        cols = [
            DDGridColumnSpec(
                column_id="gov_law",
                label="Применимое право",
                value_field="governing_law_value",
                display_order=10,
            ),
            DDGridColumnSpec(
                column_id="forum",
                label="Форум",
                value_field="forum_value",
                display_order=20,
            ),
        ]
        cfg = ExtractionConfig(
            enabled=True,
            fields=[_field("governing_law_value", label="Право")],
            dd_grid_columns=cols,
        )
        assert cfg.dd_grid_columns is not None
        assert len(cfg.dd_grid_columns) == 2
        assert cfg.dd_grid_columns[0].column_id == "gov_law"

    def test_old_yaml_without_dd_grid_columns_still_valid(self):
        """Backward compat: ExtractionConfig from old YAML dict."""
        raw = {
            "enabled": True,
            "fields": [{"name": "seller", "type": "string", "label": "Продавец"}],
        }
        cfg = ExtractionConfig(**raw)
        assert cfg.dd_grid_columns is None
        assert cfg.enabled is True


# ──────────────── D. CheckDefinition extensions ─────────────────


class TestCheckDefinitionGroupAndDisplayOrder:
    """CheckDefinition.group and display_order fields."""

    def test_defaults(self):
        check = CheckDefinition(
            id="c1",
            name="C1",
            detector_type=DetectorType.RULES,
        )
        assert check.group is None
        assert check.display_order == 0

    def test_explicit_values(self):
        check = CheckDefinition(
            id="c2",
            name="C2",
            detector_type=DetectorType.RULES,
            group="dispute_resolution",
            display_order=15,
        )
        assert check.group == "dispute_resolution"
        assert check.display_order == 15


class TestCheckDefinitionValidatorWithNewFields:
    """Existing field_extraction validator works correctly with V1 extensions."""

    def test_validator_passes_with_evidence_list_metadata_field(self):
        """
        Check with ui_mode=field_extraction, evidence_list field with
        role=subgroup_metadata and presentation=diagnostic passes validation.
        """
        check = CheckDefinition(
            id="c_gov_law",
            name="Governing Law",
            ui_mode="field_extraction",
            group="dispute_resolution",
            display_order=10,
            detector_type=DetectorType.LLM,
            extraction=ExtractionConfig(
                enabled=True,
                fields=[
                    _field("governing_law_display", presentation="summary"),
                    _field("governing_law_value", label="Применимое право"),
                    _field(
                        "evidence",
                        field_type=ExtractionFieldType.EVIDENCE_LIST,
                        presentation="diagnostic",
                        role="subgroup_metadata",
                    ),
                    _field("reason", presentation="diagnostic"),
                ],
            ),
        )
        assert check.id == "c_gov_law"
        assert check.group == "dispute_resolution"

    def test_validator_passes_with_allowed_value_specs(self):
        """
        Check with AllowedValueSpec allowed_values passes validation.
        """
        check = CheckDefinition(
            id="c_test",
            name="Test Check",
            ui_mode="field_extraction",
            detector_type=DetectorType.LLM,
            extraction=ExtractionConfig(
                enabled=True,
                fields=[
                    _field(
                        "status",
                        label="Статус",
                        allowed_values=[
                            AllowedValueSpec(value="present", label="Указано"),
                            AllowedValueSpec(value="absent", label="Не указано"),
                        ],
                    ),
                ],
            ),
        )
        assert check.id == "c_test"

    def test_validator_still_rejects_unlabeled_facts(self):
        """
        Existing validation contract: fact fields without label
        still raise ValidationError.
        """
        with pytest.raises(ValidationError) as exc_info:
            CheckDefinition(
                id="c_bad",
                name="Bad Check",
                ui_mode="field_extraction",
                detector_type=DetectorType.RULES,
                extraction=ExtractionConfig(
                    enabled=True,
                    fields=[
                        _field("some_field"),  # no label, no summary
                    ],
                ),
            )
        assert "missing explicit `label`" in str(exc_info.value)

    def test_old_check_without_group_and_display_order_still_valid(self):
        """
        Backward compat: CheckDefinition from old compiled dict
        without group/display_order still works.
        """
        raw = {
            "id": "chk_old",
            "name": "Old Check",
            "detector_type": "rules",
            "ui_mode": "field_extraction",
            "extraction": {
                "enabled": True,
                "fields": [
                    {"name": "value1", "type": "string", "label": "Value 1"},
                ],
            },
        }
        check = CheckDefinition(**raw)
        assert check.group is None
        assert check.display_order == 0


# ---------------------------------------------------------------------------
# Tests: extraction field naming contract validation (Вариант 3 — hardening)
# ---------------------------------------------------------------------------


def _make_extraction_field(
    name: str,
    *,
    field_type: ExtractionFieldType = ExtractionFieldType.STRING,
    allowed_values=None,
) -> ExtractionFieldConfig:
    kwargs = {"name": name, "type": field_type}
    if allowed_values is not None:
        kwargs["allowed_values"] = allowed_values
    return ExtractionFieldConfig(**kwargs)


def test_extraction_config_rejects_duplicate_field_names() -> None:
    """Два поля с одинаковым name должны быть отвергнуты валидатором."""
    with pytest.raises(ValueError, match="дублирующиеся имена"):
        ExtractionConfig(
            enabled=True,
            fields=[
                _make_extraction_field("payment_method"),
                _make_extraction_field("payment_method"),
            ],
        )


def test_extraction_config_rejects_singleton_prefix_conflicting_with_paired_status() -> None:
    """
    YAML содержит и singleton 'payment_method', и paired 'payment_method_status'.
    Оба сгенерируют одинаковый column_id → должно быть отвергнуто.
    """
    with pytest.raises(ValueError, match="naming contract"):
        ExtractionConfig(
            enabled=True,
            fields=[
                _make_extraction_field(
                    "payment_method_status",
                    allowed_values=["specified", "unspecified"],
                ),
                _make_extraction_field(
                    "payment_method",
                    allowed_values=["cash", "transfer"],
                ),
            ],
        )


def test_extraction_config_rejects_singleton_prefix_conflicting_with_paired_details() -> None:
    """Аналогично для paired '_details' суффикса."""
    with pytest.raises(ValueError, match="naming contract"):
        ExtractionConfig(
            enabled=True,
            fields=[
                _make_extraction_field(
                    "notice_status",
                    allowed_values=["present", "missing"],
                ),
                _make_extraction_field("notice_details"),
                _make_extraction_field("notice"),
            ],
        )


def test_extraction_config_rejects_singleton_prefix_conflicting_with_paired_value() -> None:
    """Аналогично для paired '_value' суффикса."""
    with pytest.raises(ValueError, match="naming contract"):
        ExtractionConfig(
            enabled=True,
            fields=[
                _make_extraction_field(
                    "governing_law_status",
                    allowed_values=["specified", "unspecified"],
                ),
                _make_extraction_field("governing_law_value"),
                _make_extraction_field(
                    "governing_law",
                    allowed_values=["RU", "EN"],
                ),
            ],
        )


def test_extraction_config_allows_clean_paired_pattern() -> None:
    """Правильно оформленная paired пара без singleton-конфликта проходит валидацию."""
    cfg = ExtractionConfig(
        enabled=True,
        fields=[
            _make_extraction_field(
                "notice_status",
                allowed_values=["present", "missing"],
            ),
            _make_extraction_field("notice_details"),
        ],
    )
    assert len(cfg.fields) == 2


def test_extraction_config_allows_clean_singleton_fields() -> None:
    """Только singleton поля без парных суффиксов проходят валидацию."""
    cfg = ExtractionConfig(
        enabled=True,
        fields=[
            _make_extraction_field("cadastral_number"),
            _make_extraction_field("area_sqm"),
            _make_extraction_field(
                "object_type",
                allowed_values=["land_plot", "building"],
            ),
        ],
    )
    assert len(cfg.fields) == 3


def test_extraction_config_allows_multiple_paired_pairs_without_conflicts() -> None:
    """Несколько парных pairs без конфликтов проходят валидацию."""
    cfg = ExtractionConfig(
        enabled=True,
        fields=[
            _make_extraction_field(
                "notice_status", allowed_values=["present", "missing"]
            ),
            _make_extraction_field("notice_details"),
            _make_extraction_field(
                "consent_status", allowed_values=["yes", "no"]
            ),
            _make_extraction_field("consent_details"),
        ],
    )
    assert len(cfg.fields) == 4


def test_extraction_config_skips_validation_when_disabled() -> None:
    """При extraction.enabled=False валидатор не срабатывает."""
    cfg = ExtractionConfig(enabled=False, fields=[])
    assert cfg.enabled is False


def test_extraction_config_skips_validation_when_fields_empty() -> None:
    """Пустой fields (при enabled=False) не должен ломать валидатор."""
    cfg = ExtractionConfig(enabled=False)
    assert cfg.fields == []


def test_extraction_config_error_message_lists_conflicting_fields() -> None:
    """Сообщение об ошибке должно содержать имена конфликтующих полей."""
    with pytest.raises(ValueError) as exc_info:
        ExtractionConfig(
            enabled=True,
            fields=[
                _make_extraction_field(
                    "payment_method_status", allowed_values=["specified"]
                ),
                _make_extraction_field("payment_method_details"),
                _make_extraction_field(
                    "payment_method", allowed_values=["cash", "transfer"]
                ),
            ],
        )
    msg = str(exc_info.value)
    assert "payment_method" in msg
    assert "payment_method_status" in msg or "payment_method_details" in msg
    
        