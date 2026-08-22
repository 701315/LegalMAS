"""Unit tests для Compatibility Builder (Phase 5)."""

import pytest
from services.document_layout.compatibility_builder import CompatibilityBuilder
from services.document_layout.monolingual_projector import ProjectionResult
from services.document_layout.schemas import (
    CanonicalTable,
    CanonicalTableCell,
    LayoutPrimaryCompat,
    MarkerTrace,
    ProjectedElement,
)


class TestCompatibilityBuilder:
    def test_build_layout_primary_constructs_valid_payload(self):
        el = ProjectedElement(
            element_id="ru:atom:000001",
            source_element_ids=["atom:000001"],
            text="1. Предмет Договора",
            page=1,
            reading_order=1,
            reading_order_source="docling_texts",
            type="heading",
            label="section_header",
            marker="1.",
            is_marker_only=False,
            bbox=(50.0, 30.0, 250.0, 50.0),
            language="ru",
            projection_method="native_language_atom",
        )

        proj_result = ProjectionResult(
            elements=[el],
            source_atom_count=1,
            projected_atom_count=1,
            marker_trace=MarkerTrace(projected=1),
        )

        table = CanonicalTable(
            table_id="table:0001",
            page=1,
            bbox=(50.0, 100.0, 400.0, 200.0),
            num_rows=2,
            num_cols=2,
            language="shared",
            cells=[
                CanonicalTableCell(row=0, col=0, text="Колонка 1"),
                CanonicalTableCell(row=0, col=1, text="Колонка 2"),
            ],
            markdown="| Колонка 1 | Колонка 2 |",
        )

        builder = CompatibilityBuilder()
        payload = builder.build_layout_primary(
            projection_result=proj_result,
            canonical_tables=[table],
            document_id="00000000-0000-0000-0000-000000000001",
            document_version_id="00000000-0000-0000-0000-000000000002",
            run_id="00000000-0000-0000-0000-000000000003",
            target_language="ru",
            source_canonical_layout_ref="s3://bucket/canonical.json",
        )

        # 1. Проверяем валидность root-структуры
        assert "elements" in payload
        assert len(payload["elements"]) == 2  # 1 текст + 1 таблица

        # 2. Проверяем метаданные для extract_worker bypass
        metadata = payload.get("metadata", {})
        assert metadata.get("language_filter", {}).get("analysis_source_kind") == (
            "canonical_filtered_layout_v2"
        )
        assert metadata.get("language_filter", {}).get("downstream_requires_primary_source") is False

        # 3. Проверяем интеграцию таблицы
        table_el = [e for e in payload["elements"] if e.get("is_table")][0]
        assert table_el["element_id"] == "ru:table:0001"
        assert table_el["type"] == "table"
        assert table_el["table_ref"] == "canonical:table:0001"
        assert table_el["table_rows"]
        assert table_el["table_rows"][0]["row_index"] == 0
        assert table_el["table_rows"][0]["cells"]
        assert table_el["table_topology"] is not None
        assert payload["schema_version"] == "layout_primary_compat_v2"
        assert "| Колонка 1 | Колонка 2 |" in table_el["text"]

        # 4. Проверяем, что payload успешно десериализуется Pydantic-моделью
        assert LayoutPrimaryCompat.model_validate(payload)
