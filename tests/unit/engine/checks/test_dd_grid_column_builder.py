# tests/unit/engine/checks/test_dd_grid_column_builder.py

"""
Tests for DDGridColumnBuilder (V1.6).

Covers universal auto-mapping rules and explicit spec path.
No document-specific or check_id-specific logic.
"""

from __future__ import annotations

import pytest

from engine.checks.dd_grid_column_builder import (
    DDGridColumnBuilder,
    DDGridColumnRuntime,
)
from engine.playbook.models import (
    AllowedValueSpec,
    CheckDefinition,
    DDGridColumnSpec,
    DetectorType,
    ExtractionConfig,
    ExtractionFieldConfig,
    ExtractionFieldType,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_field(
    name: str,
    *,
    field_type: ExtractionFieldType = ExtractionFieldType.STRING,
    label: str | None = None,
    presentation: str = "fact",
    allowed_values: list | None = None,
    role: str | None = None,
    unit: str | None = None,
) -> ExtractionFieldConfig:
    kwargs: dict = {
        "name": name,
        "type": field_type,
        "label": label,
        "presentation": presentation,
    }
    if allowed_values is not None:
        kwargs["allowed_values"] = allowed_values
    if role is not None:
        kwargs["role"] = role
    if unit is not None:
        kwargs["unit"] = unit
    return ExtractionFieldConfig(**kwargs)


def _make_check(
    check_id: str = "test_check",
    fields: list[ExtractionFieldConfig] | None = None,
    dd_grid_columns: list[DDGridColumnSpec] | None = None,
    extraction_enabled: bool = True,
    ui_mode: str = "field_extraction",
) -> CheckDefinition:
    if fields is None:
        fields = []

    if extraction_enabled and fields:
        extraction = ExtractionConfig(
            enabled=True,
            fields=fields,
            dd_grid_columns=dd_grid_columns,
        )
    elif extraction_enabled:
        extraction = ExtractionConfig(enabled=False)
    else:
        extraction = None

    return CheckDefinition(
        id=check_id,
        name=f"Test check {check_id}",
        ui_mode=ui_mode,
        detector_type=DetectorType.LLM,
        extraction=extraction,
    )


def _build(check: CheckDefinition):
    return DDGridColumnBuilder().build_columns(check)


# ─── A. Explicit dd_grid_columns config ──────────────────────────────────────


class TestExplicitDDGridColumnsConfig:
    def test_explicit_columns_used_when_defined(self):
        fields = [
            _make_field("gl_value", label="Право"),
            _make_field("forum_value", label="Форум"),
        ]
        specs = [
            DDGridColumnSpec(
                column_id="governing_law",
                label="Применимое право",
                value_field="gl_value",
                display_order=10,
            ),
            DDGridColumnSpec(
                column_id="forum",
                label="Форум разрешения споров",
                value_field="forum_value",
                display_order=20,
            ),
        ]
        check = _make_check(
            check_id="c1", fields=fields, dd_grid_columns=specs
        )

        columns, metadata, display = _build(check)

        assert len(columns) == 2
        assert columns[0].column_id == "c1__governing_law"
        assert columns[0].label == "Применимое право"
        assert columns[1].column_id == "c1__forum"

    def test_explicit_columns_ignore_auto_mapping(self):
        """Если explicit dd_grid_columns задан, автомаппинг не запускается."""
        fields = [
            _make_field(
                "x_status",
                presentation="signal",
                allowed_values=["present", "missing"],
            ),
            _make_field("x_details", label="Детали"),
        ]
        specs = [
            DDGridColumnSpec(
                column_id="single_col",
                label="Только эта колонка",
                value_field="x_details",
                display_order=10,
            ),
        ]
        check = _make_check(fields=fields, dd_grid_columns=specs)

        columns, _, _ = _build(check)

        assert len(columns) == 1
        assert columns[0].label == "Только эта колонка"

    def test_column_id_gets_check_id_prefix(self):
        specs = [
            DDGridColumnSpec(column_id="col_a", label="A"),
        ]
        check = _make_check(
            check_id="my_check_xyz",
            fields=[_make_field("x", label="X")],
            dd_grid_columns=specs,
        )
        columns, _, _ = _build(check)
        assert columns[0].column_id == "my_check_xyz__col_a"

    def test_explicit_enum_labels_populated_from_field(self):
        fields = [
            _make_field(
                "status",
                presentation="signal",
                allowed_values=[
                    AllowedValueSpec(value="yes", label="Да"),
                    AllowedValueSpec(value="no", label="Нет"),
                ],
            ),
        ]
        specs = [
            DDGridColumnSpec(
                column_id="col_status",
                label="Статус",
                value_field="status",
                format="yes_no",
            ),
        ]
        check = _make_check(fields=fields, dd_grid_columns=specs)
        columns, _, _ = _build(check)

        assert columns[0].enum_labels == {"yes": "Да", "no": "Нет"}


# ─── B. Auto-mapping: paired status + details ────────────────────────────────


class TestAutoMappingPairedStatusDetails:
    def test_paired_status_and_details_creates_single_column(self):
        fields = [
            _make_field(
                "confidentiality_status",
                presentation="signal",
                allowed_values=["present", "missing"],
            ),
            _make_field(
                "confidentiality_details",
                label="Конфиденциальность",
            ),
        ]
        check = _make_check(check_id="c_conf", fields=fields)
        columns, _, _ = _build(check)

        assert len(columns) == 1
        col = columns[0]
        assert col.column_id == "c_conf__confidentiality"
        assert col.value_field == "confidentiality_details"
        assert col.status_field == "confidentiality_status"
        assert col.format == "text"
        assert col.label == "Конфиденциальность"

    def test_status_details_pair_has_status_present_value(self):
        fields = [
            _make_field(
                "x_status",
                presentation="signal",
                allowed_values=["present", "missing"],
            ),
            _make_field("x_details", label="Детали"),
        ]
        columns, _, _ = _build(_make_check(fields=fields))
        assert columns[0].status_present_value == "present"

    def test_status_details_pair_fallback_to_first_allowed(self):
        """Если 'present' нет в allowed_values, берём первое."""
        fields = [
            _make_field(
                "x_status",
                presentation="signal",
                allowed_values=["defined", "not_defined"],
            ),
            _make_field("x_details", label="Детали"),
        ]
        columns, _, _ = _build(_make_check(fields=fields))
        assert columns[0].status_present_value == "defined"


# ─── C. Auto-mapping: paired status + value ──────────────────────────────────


class TestAutoMappingPairedStatusValue:
    def test_paired_status_and_value_creates_single_column(self):
        fields = [
            _make_field(
                "governing_law_status",
                presentation="signal",
                allowed_values=["present", "missing"],
            ),
            _make_field("governing_law_value", label="Применимое право"),
        ]
        columns, _, _ = _build(_make_check(check_id="gl", fields=fields))

        assert len(columns) == 1
        col = columns[0]
        assert col.column_id == "gl__governing_law"
        assert col.value_field == "governing_law_value"
        assert col.status_field == "governing_law_status"
        assert col.label == "Применимое право"

    def test_details_takes_precedence_over_value_when_both_present(self):
        """Правило A имеет приоритет над Правилом B."""
        fields = [
            _make_field(
                "x_status",
                presentation="signal",
                allowed_values=["present", "missing"],
            ),
            _make_field("x_details", label="Детали"),
            _make_field("x_value", label="Значение"),
        ]
        columns, _, _ = _build(_make_check(fields=fields))

        # Ожидаем: одну колонку по паре (status, details);
        # x_value становится одиночной колонкой отдельно.
        assert len(columns) == 2
        pair_col = next(c for c in columns if c.status_field == "x_status")
        assert pair_col.value_field == "x_details"


# ─── D. Auto-mapping: standalone status ──────────────────────────────────────


class TestAutoMappingStandaloneStatus:
    def test_standalone_status_creates_presence_only_column(self):
        fields = [
            _make_field(
                "auto_renewal_status",
                allowed_values=["present", "missing"],
                label="Автопродление",
            ),
        ]
        columns, _, _ = _build(_make_check(fields=fields))

        assert len(columns) == 1
        col = columns[0]
        assert col.format == "presence_only"
        assert col.value_field is None
        assert col.status_field == "auto_renewal_status"


# ─── E. Auto-mapping: yes/no ─────────────────────────────────────────────────


class TestAutoMappingYesNo:
    def test_field_with_yes_no_allowed_values(self):
        fields = [
            _make_field(
                "has_advance_lc_escrow",
                allowed_values=["yes", "no", "unclear"],
                label="Аванс/аккредитив",
            ),
        ]
        columns, _, _ = _build(_make_check(fields=fields))

        assert len(columns) == 1
        col = columns[0]
        assert col.format == "yes_no"
        assert col.value_field == "has_advance_lc_escrow"
        assert col.enum_labels["yes"] == "Да"
        assert col.enum_labels["no"] == "Нет"
        assert col.enum_labels["unclear"] == "Не удалось определить"

    def test_yes_no_without_unclear(self):
        fields = [
            _make_field("has_x", allowed_values=["yes", "no"], label="Есть X"),
        ]
        columns, _, _ = _build(_make_check(fields=fields))
        assert columns[0].format == "yes_no"
        assert set(columns[0].enum_labels.keys()) == {"yes", "no"}


# ─── F. Auto-mapping: enum ───────────────────────────────────────────────────


class TestAutoMappingEnum:
    def test_arbitrary_enum_creates_enum_column(self):
        fields = [
            _make_field(
                "payment_schedule_type",
                allowed_values=[
                    "advance_only",
                    "postpayment",
                    "milestone",
                ],
                label="Структура платежей",
            ),
        ]
        columns, _, _ = _build(_make_check(fields=fields))

        assert len(columns) == 1
        col = columns[0]
        assert col.format == "enum"
        assert col.enum_labels["advance_only"] == "Advance only"
        assert col.enum_labels["postpayment"] == "Postpayment"

    def test_enum_labels_use_allowed_value_spec_labels(self):
        fields = [
            _make_field(
                "mode",
                allowed_values=[
                    AllowedValueSpec(value="fast", label="Быстрый"),
                    AllowedValueSpec(value="slow", label="Медленный"),
                ],
                label="Режим",
            ),
        ]
        columns, _, _ = _build(_make_check(fields=fields))
        assert columns[0].enum_labels == {"fast": "Быстрый", "slow": "Медленный"}

    def test_enum_labels_use_generic_ru_labels_for_typical_values(self):
        fields = [
            _make_field(
                "clause_status",
                allowed_values=["present", "missing", "unclear"],
                label="Статус",
            ),
        ]
        columns, _, _ = _build(_make_check(fields=fields))
        col = columns[0]
        assert col.enum_labels["present"] == "Указано"
        assert col.enum_labels["missing"] == "Не указано"
        assert col.enum_labels["unclear"] == "Не удалось определить"

    def test_enum_labels_fallback_to_humanize(self):
        fields = [
            _make_field(
                "kind",
                allowed_values=["custom_value_a", "custom_value_b"],
                label="Тип",
            ),
        ]
        columns, _, _ = _build(_make_check(fields=fields))
        col = columns[0]
        assert col.enum_labels["custom_value_a"] == "Custom value a"


# ─── G. Auto-mapping: text field ─────────────────────────────────────────────


class TestAutoMappingTextField:
    def test_plain_string_field_creates_text_column(self):
        fields = [
            _make_field("seller_name", label="Продавец"),
        ]
        columns, _, _ = _build(_make_check(fields=fields))

        assert len(columns) == 1
        col = columns[0]
        assert col.format == "text"
        assert col.value_field == "seller_name"
        assert col.status_field is None
        assert col.label == "Продавец"

    def test_number_field_creates_text_column_with_unit(self):
        fields = [
            _make_field(
                "contract_amount",
                field_type=ExtractionFieldType.NUMBER,
                label="Сумма договора",
                unit="RUB",
            ),
        ]
        columns, _, _ = _build(_make_check(fields=fields))
        assert columns[0].format == "text"
        assert columns[0].unit == "RUB"


# ─── H. Metadata fields exclusion ────────────────────────────────────────────


class TestMetadataFieldsExclusion:
    def test_field_with_subgroup_metadata_role(self):
        fields = [
            _make_field("value_field", label="V"),
            _make_field(
                "evidence",
                field_type=ExtractionFieldType.EVIDENCE_LIST,
                role="subgroup_metadata",
                presentation="diagnostic",
            ),
        ]
        columns, metadata, _ = _build(_make_check(fields=fields))
        assert len(columns) == 1
        assert "evidence" in metadata

    def test_reserved_field_names_go_to_metadata(self):
        for name in ("reason", "evidence", "explanation", "notes"):
            fields = [
                _make_field("v", label="V"),
                _make_field(name, presentation="diagnostic"),
            ]
            columns, metadata, _ = _build(_make_check(fields=fields))
            assert name in metadata
            assert all(c.value_field != name for c in columns)

    def test_evidence_list_type_goes_to_metadata(self):
        fields = [
            _make_field("v", label="V"),
            _make_field(
                "some_evidence_field",
                field_type=ExtractionFieldType.EVIDENCE_LIST,
                presentation="diagnostic",
            ),
        ]
        columns, metadata, _ = _build(_make_check(fields=fields))
        assert "some_evidence_field" in metadata

    def test_diagnostic_presentation_goes_to_metadata(self):
        fields = [
            _make_field("v", label="V"),
            _make_field("some_diag_field", presentation="diagnostic"),
        ]
        columns, metadata, _ = _build(_make_check(fields=fields))
        assert "some_diag_field" in metadata


# ─── I. Display summary fields ───────────────────────────────────────────────


class TestDisplaySummaryFields:
    def test_field_ending_with_display_is_summary(self):
        # summary_display имеет presentation="fact" — но также имеет label,
        # значит проходит V1.1 validator даже как fact field.
        # Builder всё равно определит его как display summary по имени _display.
        fields = [
            _make_field(
                "summary_display",
                presentation="fact",
                label="Итог",
            ),
            _make_field("v", label="V"),
        ]
        columns, metadata, display = _build(_make_check(fields=fields))
        assert display == "summary_display"
        assert "summary_display" not in [c.value_field for c in columns]
        assert "summary_display" not in metadata

    def test_field_with_summary_presentation_is_summary(self):
        fields = [
            _make_field("my_summary", presentation="summary"),
            _make_field("v", label="V"),
        ]
        columns, metadata, display = _build(_make_check(fields=fields))
        assert display == "my_summary"

    def test_first_display_field_wins_when_multiple(self):
        # Оба поля fact с explicit labels — validator V1.1 проходит.
        # Builder определит их как display по имени.
        fields = [
            _make_field(
                "first_display",
                presentation="fact",
                label="Первый",
            ),
            _make_field(
                "second_display",
                presentation="fact",
                label="Второй",
            ),
        ]
        _, _, display = _build(_make_check(fields=fields))
        assert display == "first_display"


# ─── J. Column ordering ──────────────────────────────────────────────────────


class TestColumnOrdering:
    def test_columns_ordered_by_extraction_fields_order(self):
        fields = [
            _make_field("zeta", label="Z"),
            _make_field("alpha", label="A"),
            _make_field("beta", label="B"),
        ]
        columns, _, _ = _build(_make_check(fields=fields))
        labels = [c.label for c in columns]
        assert labels == ["Z", "A", "B"]

    def test_display_order_uses_step_of_ten(self):
        fields = [
            _make_field("a", label="A"),
            _make_field("b", label="B"),
            _make_field("c", label="C"),
        ]
        columns, _, _ = _build(_make_check(fields=fields))
        orders = [c.display_order for c in columns]
        assert orders == [0, 10, 20]


# ─── K. Common attributes ────────────────────────────────────────────────────


class TestCommonAttributes:
    def test_uses_field_label_when_present(self):
        fields = [_make_field("some_field", label="Красивое имя")]
        columns, _, _ = _build(_make_check(fields=fields))
        assert columns[0].label == "Красивое имя"

    def test_uses_humanized_name_when_no_label(self):
        """
        Fields, не подпадающие под required label validator (signal/diagnostic
        или enum status), могут не иметь explicit label — builder использует
        humanized name как fallback.
        """
        fields = [
            _make_field(
                "some_status_field",
                presentation="signal",
                allowed_values=["yes", "no"],
            ),
        ]
        columns, _, _ = _build(_make_check(fields=fields))
        assert columns[0].label == "Some status field"

    def test_fallback_display_is_em_dash(self):
        fields = [_make_field("v", label="V")]
        columns, _, _ = _build(_make_check(fields=fields))
        assert columns[0].fallback_display == "—"


# ─── L. Edge cases ───────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_no_extraction_returns_empty(self):
        check = CheckDefinition(
            id="c",
            name="C",
            detector_type=DetectorType.RULES,
            extraction=None,
        )
        columns, metadata, display = _build(check)
        assert columns == []
        assert metadata == []
        assert display is None

    def test_extraction_disabled_returns_empty(self):
        check = _make_check(extraction_enabled=True, fields=[])
        # Fields empty → extraction.enabled=False by fixture logic
        columns, metadata, display = _build(check)
        assert columns == []
        assert metadata == []
        assert display is None

    def test_only_metadata_fields_returns_empty_columns(self):
        fields = [
            _make_field("reason", presentation="diagnostic"),
            _make_field(
                "evidence",
                field_type=ExtractionFieldType.EVIDENCE_LIST,
                role="subgroup_metadata",
                presentation="diagnostic",
            ),
        ]
        columns, metadata, _ = _build(_make_check(fields=fields))
        assert columns == []
        assert set(metadata) == {"reason", "evidence"}

    def test_only_display_field_returns_empty_columns(self):
        fields = [
            _make_field(
                "summary_display",
                presentation="summary",  # summary — не требует label по V1.1
            ),
        ]
        columns, metadata, display = _build(_make_check(fields=fields))
        assert columns == []
        assert metadata == []
        assert display == "summary_display"


# ─── M. Real-world patterns ──────────────────────────────────────────────────


class TestRealWorldPatterns:
    def test_governing_law_and_forum_pattern(self):
        """
        Реалистичный паттерн pilot check с 7 fields:
        - governing_law_and_forum_display (summary)
        - governing_law_status + governing_law_value (paired)
        - dispute_forum_status + dispute_forum_value (paired)
        - pre_claim_procedure_present (standalone yes_no)
        - reason (metadata)
        - evidence (metadata)
        """
        fields = [
            _make_field(
                "governing_law_and_forum_display",
                presentation="fact",
                label="Применимое право и форум",
            ),
            _make_field(
                "governing_law_status",
                presentation="signal",
                allowed_values=["present", "missing", "unclear"],
            ),
            _make_field(
                "governing_law_value",
                presentation="fact",
                label="Применимое право",
            ),
            _make_field(
                "dispute_forum_status",
                presentation="signal",
                allowed_values=["present", "missing", "unclear"],
            ),
            _make_field(
                "dispute_forum_value",
                presentation="fact",
                label="Форум",
            ),
            _make_field(
                "pre_claim_procedure_present",
                presentation="signal",
                allowed_values=["yes", "no", "unclear"],
            ),
            _make_field(
                "reason",
                presentation="diagnostic",
            ),
            _make_field(
                "evidence",
                field_type=ExtractionFieldType.EVIDENCE_LIST,
                presentation="diagnostic",
                role="subgroup_metadata",
            ),
        ]
        check = _make_check(check_id="gl_forum", fields=fields)
        columns, metadata, display = _build(check)

        # Ожидаемые колонки:
        # 1. paired governing_law_status + governing_law_value → governing_law
        # 2. paired dispute_forum_status + dispute_forum_value → dispute_forum
        # 3. standalone pre_claim_procedure_present → yes_no
        assert len(columns) == 3

        col_ids = [c.column_id for c in columns]
        assert "gl_forum__governing_law" in col_ids
        assert "gl_forum__dispute_forum" in col_ids
        assert "gl_forum__pre_claim_procedure_present" in col_ids

        # Metadata: reason + evidence
        assert set(metadata) == {"reason", "evidence"}

        # Display summary
        assert display == "governing_law_and_forum_display"

        # Проверяем что pre_claim это yes_no с русскими labels
        pre_claim_col = next(
            c for c in columns
            if c.column_id == "gl_forum__pre_claim_procedure_present"
        )
        assert pre_claim_col.format == "yes_no"
        assert pre_claim_col.enum_labels["yes"] == "Да"
        assert pre_claim_col.enum_labels["no"] == "Нет"

    def test_payment_terms_pattern(self):
        """
        Реалистичный паттерн financial check:
        - payment_display (summary)
        - payment_currency (text)
        - payment_schedule_type (enum)
        - has_late_payment_penalties (enum non-yes-no)
        - has_advance_lc_escrow (yes_no)
        - set_off_rights (enum)
        - has_price_indexation (yes_no)
        - reason (metadata)
        """
        fields = [
            _make_field(
                "payment_display",
                presentation="fact",
                label="Платежные условия",
            ),
            _make_field("payment_currency", label="Валюта"),
            _make_field(
                "payment_schedule_type",
                label="Структура платежей",
                allowed_values=[
                    "advance_only",
                    "postpayment",
                    "milestone",
                ],
            ),
            _make_field(
                "has_late_payment_penalties",
                label="Штрафы за просрочку",
                allowed_values=[
                    "yes_market_rate",
                    "yes_excessive",
                    "no",
                    "unclear",
                ],
            ),
            _make_field(
                "has_advance_lc_escrow",
                label="Авансы/L/C/escrow",
                allowed_values=["yes", "no", "unclear"],
            ),
            _make_field(
                "set_off_rights",
                label="Set-off rights",
                allowed_values=[
                    "counterparty_unilateral",
                    "mutual",
                    "prohibited",
                    "not_addressed",
                ],
            ),
            _make_field(
                "has_price_indexation",
                label="Индексация цен",
                allowed_values=["yes", "no", "unclear"],
            ),
            _make_field("reason", presentation="diagnostic"),
        ]
        check = _make_check(check_id="pay", fields=fields)
        columns, metadata, display = _build(check)

        # Ожидаем 6 колонок:
        # payment_currency (text), payment_schedule_type (enum),
        # has_late_payment_penalties (enum, не yes_no т.к. есть yes_market_rate),
        # has_advance_lc_escrow (yes_no), set_off_rights (enum),
        # has_price_indexation (yes_no)
        assert len(columns) == 6
        assert display == "payment_display"
        assert metadata == ["reason"]

        # has_late_payment_penalties — enum (не yes_no, т.к. нет чистых yes+no)
        penalties = next(
            c for c in columns
            if c.column_id == "pay__has_late_payment_penalties"
        )
        assert penalties.format == "enum"

        # has_advance_lc_escrow — yes_no
        escrow = next(
            c for c in columns
            if c.column_id == "pay__has_advance_lc_escrow"
        )
        assert escrow.format == "yes_no"

        # payment_schedule_type — enum
        schedule = next(
            c for c in columns
            if c.column_id == "pay__payment_schedule_type"
        )
        assert schedule.format == "enum"

        # payment_currency — text
        currency = next(
            c for c in columns
            if c.column_id == "pay__payment_currency"
        )
        assert currency.format == "text"



